"""Apply independent Extraction proposals with one final StatePatch against the original snapshot."""
from collections import defaultdict
from copy import deepcopy

from backend.runtime_v3.scene_steps import compile_scene, decode, input_schema
from backend.runtime_v3.structured_payload import consequence_payload
from backend.runtime_v3.raw import SECTIONS
from backend.services.world_delta_errors import StructuralDeltaError


def identifiers(value, key=''):
    if isinstance(value, dict):
        for name, item in value.items():
            yield from identifiers(item, name)
    elif isinstance(value, list):
        for item in value:
            yield from identifiers(item, key)
    elif isinstance(value, str) and (key in ('id','endpoint','perceived_by','supersedes')
                                      or key.endswith(('_id','_ids'))):
        yield key, value


def components(proposal, before):
    """Union declarations with their local consumers, regardless of submission order."""
    units = []
    for section, value in proposal.items():
        if section == 'scene' and isinstance(value, dict):
            units.extend((section, key, item) for key, item in value.items())
        elif isinstance(value, list):
            units.extend((section, i, item) for i, item in enumerate(value))
        else:
            units.append((section, None, value))
    # Menu annotations consume committed facts. A bad annotation cannot
    # invalidate its source. Evaluate them after all world changes.
    choices = [unit for unit in units if unit[0] == 'choices']
    units = [unit for unit in units if unit[0] != 'choices']
    parents = list(range(len(units)))

    def root(i):
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    # Updating an existing actor/fact does not redeclare its identity. Other
    # records can already refer to it even if the proposed update is invalid.
    existing_ids = {identifier for section in before.values() if isinstance(section, dict)
                    for identifier, entry in section.items() if isinstance(entry, dict)}
    declarations = defaultdict(list)
    for i, (_, _, item) in enumerate(units):
        for key, value in identifiers(item):
            if key == 'id' and value not in existing_ids:
                declarations[value].append(i)
    for i, (section, field, item) in enumerate(units):
        for _, value in identifiers(item, field if section == 'scene' else ''):
            for owner in declarations.get(value, ()):
                parents[root(i)] = root(owner)
    groups = defaultdict(list)
    for i, unit in enumerate(units):
        groups[root(i)].append(unit)
    yield from groups.values()
    for choice in choices:
        yield [choice]


def scene_with_authored_ending(proposal, authored, before):
    extracted = proposal.get('scene', {})
    scene = {**extracted, **authored} if isinstance(extracted, dict) else dict(authored)
    ending = scene.get('ending')
    second = extracted.get('ending') if isinstance(extracted, dict) else None
    if not isinstance(ending, dict) or not isinstance(second, dict):
        return scene
    location = ending.get('location_id')
    cast, extracted_cast = ending.get('present_ids'), second.get('present_ids')
    if (not isinstance(location, str) or second.get('location_id') != location
            or not isinstance(cast, list) or not isinstance(extracted_cast, list) or len(extracted_cast)>64):
        return scene
    # Extraction can name a host omitted from the author's cast. Enrich the cast
    # only at the same endpoint, without relocating anyone on a disagreement.
    steps = proposal.get('scene_steps', [])
    moving = set()
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get('kind') == 'movement' and isinstance(step.get('actor_ids'), list):
                moving.update(cid for cid in step['actor_ids'] if isinstance(cid, str))
    present = list(cast)
    for cid in extracted_cast:
        if len(present) >= 64:
            break
        if isinstance(cid, str) and cid not in present and cid not in moving and before['characters'].get(cid, {}).get('location_id') == location:
            present.append(cid)
    scene['ending'] = {**ending, 'present_ids': present}
    return scene


def resolve_consequences(payload, before, narrative, turn_id, suggestions, resolve, *, namespace=None, authored_scene=None):
    def evaluate(candidate):
        raw = compile_scene(candidate, before, narrative, turn_id, namespace=namespace, version=10, suggestions=suggestions)
        return raw, resolve(raw)

    try:
        proposal, normalization, decoding_warnings = consequence_payload(payload, (*SECTIONS,'scene_steps','choices'))
    except (TypeError, ValueError):
        proposal, normalization = {}, None
        decoding_warnings = [dict(section='extraction', code='raw_root_invalid', action='preserve_scene')]
    extracted_scene = proposal.get('scene', {})
    if authored_scene:
        proposal['scene'] = scene_with_authored_ending(proposal, authored_scene, before)
    if not suggestions and 'choices' in proposal:
        # No author-provided menu exists to annotate. Ignore unsolicited
        # indexes, including malformed ones, before grouping consequences.
        proposal = {k:v for k,v in proposal.items() if k != 'choices'}
    # Stabilize server-owned step IDs before isolating any rejected records.
    valid_shape = isinstance(proposal.get('scene_steps', []), list) and isinstance(proposal.get('scene', {}), dict)
    if valid_shape:
        proposal = decode(proposal, version=10)
    try:
        raw, result = evaluate(proposal)
    except StructuralDeltaError:
        accepted = {}
        raw, result = evaluate(accepted)
        warnings = []
        limits = input_schema(10, before['camera']['mode'])['properties']
        # A broken envelope must not turn an over-budget array into thousands
        # of independent resolver runs or circumvent the section limit.
        bounded = {}
        for section, value in proposal.items():
            if isinstance(value,list) and len(value) > limits.get(section,{}).get('maxItems',128):
                warnings.append(dict(section=section,code='section_budget_exceeded',action='skip_section'))
            else:
                bounded[section] = value

        def include(group):
            candidate = deepcopy(accepted)
            for section, key, item in group:
                if key is None:
                    candidate[section] = item
                else:
                    candidate.setdefault(section, {})[key] = item
            ordered = {section: [rows[k] for k in sorted(rows)]
                       if isinstance(proposal[section], list) else rows for section, rows in candidate.items()}
            return candidate, *evaluate(ordered)

        for group in components(bounded, before):
            try:
                accepted, raw, result = include(group)
            except StructuralDeltaError as exc:
                # The optional Narrative ending can refer to an ID that neither
                # source declared. Retain a valid endpoint supplied by Extraction.
                fallback = [(s,k,extracted_scene[k]) if s=='scene' and k in (authored_scene or {})
                            and isinstance(extracted_scene,dict) and k in extracted_scene else (s,k,v)
                            for s,k,v in group]
                if fallback != group:
                    try:
                        accepted, raw, result = include(fallback)
                    except StructuralDeltaError:
                        pass
                    else:
                        warnings.append(dict(section='scene',code=exc.code,action='used_extracted_scene'))
                        continue
                # Perceptions in a single utterance may have different recipients.
                # Keep independently resolvable claims together in the same event.
                section, key, step = group[0]
                if (len(group)==1 and section=='scene_steps' and isinstance(step,dict)
                        and step.get('kind')=='information' and isinstance(step.get('claims'),list)
                        and 1 < len(step['claims']) <= 16):
                    claims = []
                    for i, claim in enumerate(step['claims']):
                        try:
                            accepted, raw, result = include([(section,key,dict(step,claims=[*claims,claim]))])
                        except StructuralDeltaError as invalid:
                            warnings.append(dict(section=section,index=key,claim_index=i,code=invalid.code,action='skip_claim'))
                        else:
                            claims.append(claim)
                else:
                    warnings.append(dict(section=section, code=exc.code, action='skip_group',
                        records=[dict(section=s, key=k) for s,k,_ in group]))
        result.warnings.extend(warnings)
    result.warnings.extend(decoding_warnings)
    if normalization:
        result.warnings.append(dict(section='extraction',code='structured_payload_normalized',action=normalization))
    return raw, result
