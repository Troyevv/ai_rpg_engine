"""Apply independent Extraction proposals with one final StatePatch against the original snapshot."""
from collections import defaultdict
from copy import deepcopy

from backend.runtime_v3.scene_steps import compile_scene, decode, input_schema
from backend.runtime_v3.structured_payload import object_payload
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


def resolve_consequences(payload, before, narrative, turn_id, suggestions, resolve, *, namespace=None):
    def evaluate(candidate):
        raw = compile_scene(candidate, before, narrative, turn_id, namespace=namespace, version=10, suggestions=suggestions)
        return raw, resolve(raw)

    try:
        proposal, normalization = object_payload(payload)
    except (TypeError, ValueError):
        raw, result = evaluate({})
        result.warnings.append(dict(section='extraction', code='raw_root_invalid', action='preserve_scene'))
        return raw, result
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
    if normalization:
        result.warnings.append(dict(section='extraction',code='structured_payload_normalized',action=normalization))
    return raw, result
