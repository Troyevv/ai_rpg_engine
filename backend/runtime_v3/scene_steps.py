"""Extraction/6: ordered semantic sources compiled into existing domain records.

Only this boundary accepts the external envelope. No prose interpretation lives
here. Local IDs are model labels; generated IDs/order/origins are server owned.
"""
from copy import deepcopy
from functools import lru_cache
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from backend.runtime_v3.models import fatal, identity
from backend.runtime_v3.raw import RawTurnResult, SECTIONS, OPTIONAL_SECTIONS, SECTION_BUDGETS, PerceivedClaim, compile_semantic


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class InputSource(StrictModel):
    quote: str = Field(min_length=1)
    meaning: Literal['preserved', 'changed', 'uncertain']
    # Omit when the selected and achieved targets agree; partial outcomes retain
    # the separately intended set instead of fabricating successful recipients.
    intended_target_ids: list[str] | None = None


class MovementInputSource(StrictModel):
    quote: str = Field(min_length=1)
    meaning: Literal['preserved', 'changed', 'uncertain']


class Step(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence: str = ''
    input_source: InputSource | None = None
    advance_candidate_ids: list[str] = Field(default_factory=list, max_length=3)
    minute: int | None = Field(default=None, ge=0)
    timing: Literal['after_previous','simultaneous','uncertain'] = 'after_previous'


class MovementFields(Step):
    kind: Literal['movement']
    assertion: Literal['intent', 'preparation', 'attempt', 'departure', 'completed_arrival']
    endpoint: str | None = None
    involuntary_source_id: str | None = None


class MovementStep(MovementFields):
    actor_id: str


class GroupMovementStep(MovementFields):
    actor_ids: list[str] = Field(min_length=1)
    assertion: Literal['intent', 'preparation', 'attempt', 'departure', 'completed_arrival', 'local_exit']


class InteractionStep(Step):
    kind: Literal['interaction']
    actor_id: str
    target_ids: list[str]
    outcome: Literal['completed', 'partial', 'attempted', 'deferred', 'not_performed']
    channel: Literal['physical', 'call'] = 'physical'


class InformationStep(Step):
    kind: Literal['information']
    source_actor_id: str | None
    target_ids: list[str] = Field(default_factory=list)
    medium: Literal['conversation', 'observation', 'discovery', 'testimony', 'message']
    channel: Literal['physical', 'call'] | None = None
    claims: list[PerceivedClaim] = Field(min_length=1, max_length=16)


class OccurrenceStep(Step):
    """Non-contact domain source (birth, objective event, witnessed action)."""
    kind: Literal['occurrence']
    actor_ids: list[str]
    fact_ids: list[str] = Field(default_factory=list)
    witnesses: list[str] = Field(default_factory=list)
    location_id: str | None = None


STEP = TypeAdapter(Annotated[MovementStep | InteractionStep | InformationStep | OccurrenceStep,
                             Field(discriminator='kind')])


class TravellingInteraction(InteractionStep):
    during_step_id: str | None = None


class TravellingInformation(InformationStep):
    during_step_id: str | None = None


GROUP_STEP = TypeAdapter(Annotated[GroupMovementStep | TravellingInteraction | TravellingInformation | OccurrenceStep,
                                   Field(discriminator='kind')])


class MovementV8(GroupMovementStep):
    input_source: MovementInputSource | None = None


STEP_V8 = TypeAdapter(Annotated[MovementV8 | TravellingInteraction | TravellingInformation | OccurrenceStep,
                                Field(discriminator='kind')])


def step_adapter(version):
    return STEP_V8 if version >= 8 else GROUP_STEP if version >= 7 else STEP


def movers(step):
    return step.actor_ids if isinstance(step, GroupMovementStep) else [step.actor_id]


def project_schema(schema, *, version=6, camera_mode=None):
    """Replace, never supplement, the duplicate model-facing representations."""
    props = schema['properties']
    for section,(limit,_) in SECTION_BUDGETS.items():
        if section in props:props[section]['maxItems']=limit
    # Existing NPC review accepts partial cards and marks them pending_review.
    promotion=props['promotions']['items']
    promotion['properties']['fields'].pop('required', None)
    promotion['required']=[key for key in promotion.get('required',[]) if key!='character']
    for section in ('possession_deltas','appearance_deltas','development_evidence'):
        for field in ('player_evidence','player_assertion'):
            props[section]['items']['properties'].pop(field,None)
            props[section]['items']['required']=[key for key in props[section]['items'].get('required',[]) if key!=field]
    props['scheduled_event_changes']['items']['properties']['location_id'] = {'type':['string','null']}
    scene = props.pop('final_scene')
    for name in ('events', 'movements', 'information_events', 'knowledge_gained', 'player_agency'):
        props.pop(name, None)
    for name in ('location_id', 'present_character_ids', 'observed_character_ids'):
        scene['properties'].pop(name, None)
    scene['required'] = [k for k in scene.get('required', []) if k in scene['properties']]
    # Optional composition override is visibility, never geography. The actor
    # camera's subject cannot be overridden by the provider.
    scene['properties'].update(
        visible_character_ids={'type':'array', 'items':{'type':'string'}},
        observed_character_ids={'type':'array', 'items':{'type':'string'}},
        observer_location_id={'type':['string','null']})
    if version >= 7 and camera_mode == 'actor':
        scene['properties'].pop('observer_location_id')
    if version >= 9:
        for record in (props['value_deltas']['items'],
                       props['personality_deltas']['items']['properties']['operations']['items']):
            for field in ('expected_revision', 'expected_text'):
                record['properties'].pop(field)
                record['required'].remove(field)
        choice = props['choices']['items']
        for field in ('action', 'speech'):
            choice['properties'].pop(field, None)
        choice['properties']['index'] = dict(type='integer', minimum=0, maximum=5)
        choice['required'] = ['index', 'grounding']
    steps = step_adapter(version).json_schema()
    if version >= 9:
        for definition in steps['$defs'].values():
            if 'timing' in definition.get('properties', {}):
                definition['required'].remove('id')
        info = steps['$defs']['TravellingInformation']
        info['required'].remove('text')
        inline_claim = {'required':['fact'], 'properties':{'fact':{'type':'object', 'required':['text']}}}
        info['anyOf'] = [{'required':['text']}, {'properties':{'claims':{
            'minItems':1, 'maxItems':1, 'items':inline_claim}}}]


    schema.setdefault('$defs', {}).update(steps.pop('$defs', {}))
    props.update(scene=scene, scene_steps={'type':'array', 'maxItems':64, 'items':steps},
        agency_findings={'type':'array','items':{'type':'object','additionalProperties':False,
            'properties':{'narrative_evidence':{'type':'string'},
                'classification':{'enum':['unauthorized_choice','uncertain','incidental_detail']}},
            'required':['narrative_evidence','classification']}})
    schema['required'] = ['scene', 'scene_steps']
    from backend.runtime_v3.scene_schema import project_structure
    project_structure(schema, movement_type='MovementV8' if version >= 8 else 'GroupMovementStep' if version >= 7 else 'MovementStep', interaction_type='TravellingInteraction' if version >= 7 else 'InteractionStep')
    return schema


@lru_cache(maxsize=8)
def input_schema(version=6, camera_mode=None):
    from backend.runtime_v3.raw import prompt_schema
    return prompt_schema(semantic_slice=True, scene_sequence=True, spatial_version=version, camera_mode=camera_mode, consequence_first=True,
                         explicit_departures=True, grounded_choices=True, player_agency_required=True)


def decode(payload, *, version=6):
    if isinstance(payload, str):
        try:
            from backend.runtime_v3.structured_payload import object_payload
            payload, _ = object_payload(payload)
        except (ValueError, TypeError):
            fatal('Некорректный JSON Extraction/6.', 'raw_root_invalid', repairable=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('scene_steps'), list) or not isinstance(payload.get('scene'), dict):
        fatal('Ожидается Extraction/6: scene_steps и scene.', 'raw_root_invalid', repairable=True)
    result = deepcopy(payload)
    if version >= 9:
        ids = {s['id'] for s in result['scene_steps'] if isinstance(s, dict) and isinstance(s.get('id'), str)}
        for index, step in enumerate(result['scene_steps']):
            if isinstance(step, dict) and 'id' not in step:
                label = f'step-{index+1}'
                while label in ids:
                    label += '_'
                step['id'] = label
                ids.add(label)
    return result


def validate(payload, state=None, *, version=6, collect=False, warnings=None):
    from jsonschema import Draft202012Validator
    from backend.services.world_delta_errors import StructuralDeltaError
    p = decode(payload, version=version)
    if version >= 9:
        warnings = warnings if warnings is not None else []
        for field in ('diagnostic', 'diagnostics'):
            if field in p:
                del p[field]
                warnings.append(dict(section=field, code='raw_feedback_ignored', action='ignore_field'))
        for index, step in enumerate(p['scene_steps']):
            if not isinstance(step, dict):
                continue
            claims = step.get('claims')
            if step.get('kind') == 'information' and 'text' not in step and isinstance(claims,list) and len(claims)==1:
                fact = claims[0].get('fact') if isinstance(claims[0],dict) else None
                if isinstance(fact,dict) and isinstance(fact.get('text'),str):
                    step['text'] = fact['text']
            for field in ('evidence', 'timing'):
                no_order = (field == 'timing' and len(p['scene_steps']) == 1
                            and step.get('timing') in ('uncertain', 'simultaneous'))
                if field in step and (field == 'evidence' and step[field] is None or no_order):
                    del step[field]
                    warnings.append(dict(section='scene_steps', index=index, field=field,
                                         code='optional_annotation_ignored', action='use_default'))
    errors = []
    for error in Draft202012Validator(input_schema(version, state['camera']['mode'] if state else None)).iter_errors(p):
        path = list(error.absolute_path)
        if path and path[0] in OPTIONAL_SECTIONS | {'choices'}:
            continue  # Existing optional-domain owners still isolate annotation errors.
        errors.extend(schema_diagnostics(error, p))
    ids = [s['id'] for s in p['scene_steps']
           if isinstance(s, dict) and isinstance(s.get('id'), str)]
    if len(set(ids)) != len(ids):
        errors.append(StructuralDeltaError('Повторный ID смыслового шага.',
            'semantic_duplicate', section='scene_steps'))
    errors.extend(independent_scene_errors(p, state, errors, version=version))
    if collect:
        return p, errors
    if errors:
        raise StructuralDeltaError.combine(errors)
    return p


def schema_diagnostics(error, payload):
    """Unwrap our step discriminator/nullable fields, not unrelated union arms.

    jsonschema already does validation. This only translates its errors back to
    model field paths, retaining every independent claim rather than best_match.
    """
    from backend.services.world_delta_errors import StructuralDeltaError
    path = list(error.absolute_path)
    children = error.context
    if (error.validator == 'additionalProperties' and path == ['scene']
            and set(error.instance) - set(error.schema.get('properties', {})) == {'observer_location_id'}):
        return [StructuralDeltaError('Камера актёра не принимает observer_location_id. Repair scene снимает эту недопустимую аннотацию.',
            'camera_invalid', section='scene', field='observer_location_id', path='scene.observer_location_id')]
    if error.validator == 'oneOf' and len(path) == 2 and path[0] == 'scene_steps':
        kind = error.instance.get('kind') if isinstance(error.instance, dict) else None
        names = {'movement': ('MovementStep', 'GroupMovementStep', 'MovementV8'),
                 'interaction': ('InteractionStep', 'TravellingInteraction'),
                 'information': ('InformationStep', 'TravellingInformation'),
                 'occurrence': ('OccurrenceStep',)}.get(kind, ())
        branches = error.schema['oneOf']
        selected = next((i for i, arm in enumerate(branches)
                         if any(arm.get('$ref', '').endswith('/' + name) for name in names)
                         or arm.get('properties', {}).get('kind', {}).get('const') == kind), None)
        if selected is not None:
            children = [e for e in children if list(e.schema_path)[0] == selected]
        else:
            children = []  # Unknown kind: one useful discriminator error.
    elif error.validator == 'anyOf' and error.instance is not None:
        children = [e for e in children if not (e.validator == 'type' and e.validator_value == 'null')]
    else:
        children = []  # Keep XOR/conditional errors at their actual claim path.
    if children:
        return [row for child in children for row in schema_diagnostics(child, payload)]
    paths = [path]
    if error.validator == 'additionalProperties' and isinstance(error.instance, dict):
        paths = [path + [key] for key in error.instance if key not in error.schema.get('properties', {})] or [path]
    if error.validator == 'required' and isinstance(error.instance, dict):
        # jsonschema emits a separate ValidationError for EACH missing key.
        # Its required array contains all keys; expanding that array would mix
        # one key's reason with every other missing field (and duplicate rows).
        paths = [path + [key] for key in error.validator_value
                 if key not in error.instance and error.message == f'{key!r} is a required property'] or [path]
    result = []
    for parts in paths:
        rendered = ''.join(f'[{v}]' if isinstance(v, int) else ('.' if i else '') + v
                           for i, v in enumerate(parts)) or '$'
        detail = dict(section=parts[0] if parts else 'scene_steps', path=rendered)
        if len(parts) > 1 and isinstance(parts[1], int):
            detail['index'] = parts[1]
            if parts[0] == 'scene_steps':
                step = payload['scene_steps'][parts[1]]
                if isinstance(step, dict):
                    detail.update(step_id=step.get('id'), source_ids=[step['id']] if step.get('id') else [])
                if 'claims' in parts:
                    at = parts.index('claims')
                    if len(parts) > at + 1:
                        detail['claim_index'] = parts[at + 1]
                        detail['repair_options'] = [
                            'New fact: supply fact.text and optional structured fact.claim; preserve the perceived meaning.',
                            'Existing whole assertion: use fact_id instead of fact. Never invent a link or repeat it as an unrelated top-level Fact.',
                            'Retain other claims, perceivers and independent steps unless their own diagnostics require correction.']
        code = 'scene_schema_invalid'
        if parts[:1] == ['scene_steps'] and len(parts) > 2:
            step = payload['scene_steps'][parts[1]]
            if step.get('kind') == 'movement' and parts[2] == 'endpoint': code = 'movement_endpoint_invalid'
            if step.get('kind') == 'interaction' and parts[2] == 'target_ids' and error.validator == 'maxItems': code = 'scene_step_invalid'
        result.append(StructuralDeltaError(error.message, code, **detail))
    return result


def independent_scene_errors(payload, state, schema_errors, *, version=6):
    """Check declarations, never tentative routes or partially compiled records.

    A malformed node cannot support dependent checks. Other valid nodes and
    scene fields can still report their own errors in the same bounded repair.
    No WorldState or candidate is changed during this pass.
    """
    from backend.services.world_delta_errors import StructuralDeltaError
    errors = []
    camera = state['camera'] if state is not None else None
    known = set(state['characters']) if state is not None else set()
    promotions = payload.get('promotions', [])
    if isinstance(promotions, list):
        known.update(p['id'] for p in promotions
                     if isinstance(p, dict) and isinstance(p.get('id'), str))

    def reject(message, code, **path):
        errors.append(StructuralDeltaError('Runtime v3: ' + message, code, **path))

    for index, value in enumerate(payload['scene_steps']):
        path = dict(section='scene_steps', index=index)
        try:
            step = step_adapter(version).validate_python(value)
        except ValidationError as exc:
            for error in exc.errors(include_input=False, include_url=False):
                loc = list(error['loc'])
                if loc and loc[0] in ('movement', 'interaction', 'information', 'occurrence'):
                    loc.pop(0)
                claim_index = loc[1] if len(loc) > 1 and loc[0] == 'claims' else None
                # Suppress duplicate schema/model errors for the same claim,
                # never an independent claim's cross-field validator error.
                if any(e.path.get('section') == 'scene_steps' and e.path.get('index') == index
                       and (claim_index is None or e.path.get('claim_index') == claim_index)
                       for e in schema_errors):
                    continue
                field = ''.join(f'[{v}]' if isinstance(v, int) else ('.' if n else '') + v
                                for n, v in enumerate(loc))
                detail = dict(path, field=field, step_id=value.get('id'),
                              source_ids=[value['id']] if value.get('id') else [])
                if claim_index is not None: detail['claim_index'] = claim_index
                reject(error['msg'], 'scene_step_invalid', **detail)
            continue
        if step.timing == 'uncertain' or index == 0 and step.timing == 'simultaneous':
            reject('Не установлен относительный порядок значимых шагов.',
                   'scene_order_ambiguous', **path)
        during = getattr(step, 'during_step_id', None)
        if during:
            source = next((s for s in payload['scene_steps'][:index] if isinstance(s, dict) and s.get('id')==during), None)
            if not source or source.get('kind')!='movement' or source.get('assertion')!='completed_arrival':
                reject('Разговор в пути требует предшествующий фактический совместный маршрут.',
                       'scene_route_invalid', field='during_step_id', **path)
        actor = getattr(step, 'actor_id', getattr(step, 'source_actor_id', None))
        targets = getattr(step, 'target_ids', [])
        if isinstance(step, GroupMovementStep):
            actor = camera['controlled_actor_id'] if camera and camera['controlled_actor_id'] in step.actor_ids else step.actor_ids[0]
        if camera is not None:
            roles = set(([actor] if actor else []) + targets)
            if isinstance(step, GroupMovementStep):
                roles.update(step.actor_ids)
                if len(set(step.actor_ids)) != len(step.actor_ids):
                    reject('Повторный участник пути.', 'scene_step_invalid', **path)
            if isinstance(step, InformationStep):
                roles.update(cid for claim in step.claims for cid in claim.perceived_by)
            if isinstance(step, OccurrenceStep):
                roles.update(step.actor_ids + step.witnesses)
                actor = camera['controlled_actor_id'] if camera['controlled_actor_id'] in step.actor_ids else None
            if roles - known:
                reject('Неизвестная личность в смысловом шаге.', 'scene_actor_unknown',
                       source_ids=sorted(roles - known), **path)
            if step.input_source and (actor is None or actor != camera['controlled_actor_id']):
                reject('Источник ввода принадлежит только управляемому автору.',
                       'player_action_source_invalid', **path)
        if (camera is not None and isinstance(step, MovementFields)
                and actor is not None and actor == camera['controlled_actor_id']
                and step.assertion in ('departure', 'completed_arrival', 'local_exit')
                and step.input_source is None and step.involuntary_source_id is None):
            reject('Перемещение управляемого героя требует input_source с релевантной цитатой '
                   'ввода или involuntary_source_id. Источник соседнего шага не наследуется.',
                   'movement_agency', **path)

    scene = payload['scene']
    if camera is not None:
        if camera['mode'] != 'observer' and isinstance(scene.get('observer_location_id'), str):
            reject('Extraction не меняет режим камеры. Сними observer_location_id через null '
                   'в адресном repair; положение героя определяется маршрутом.',
                   'camera_invalid', section='scene', field='observer_location_id')
        visible = scene.get('visible_character_ids')
        if camera['mode'] == 'actor' and isinstance(visible, list) and all(isinstance(cid, str) for cid in visible) and camera['controlled_actor_id'] not in visible:
            reject('Явная композиция исключает управляемого персонажа.',
                   'camera_actor_missing', section='scene', field='visible_character_ids')
    return errors


def bind_profile_baselines(records, state):
    # Domain owners retain stale/conflicting edit checks. Compare against the
    # immutable pre-turn state bound to this candidate and job revision.
    for domain in ('value_deltas', 'personality_deltas'):
        for row in records[domain]:
            if not isinstance(row, dict) or not isinstance(row.get('actor_id'), str):
                continue
            actor = state['characters'].get(row['actor_id'], {})
            if domain == 'value_deltas':
                items, operations = actor.get('values') or {}, [row]
            else:
                items = (actor.get('personality') or {}).get('items', {})
                operations = row.get('operations')
            for op in operations if isinstance(operations, list) else []:
                if isinstance(op, dict) and isinstance(op.get('item_id'), str):
                    old = items.get(op['item_id'], {})
                    op['expected_text'] = old.get('text')
                    op['expected_revision'] = old.get('revision', 0)


def compile_scene(payload, state, narrative, turn_id, *, namespace=None, version=6, defer_errors=False, suggestions=()):
    from backend.services.world_delta_errors import StructuralDeltaError
    warnings = []
    p, errors = validate(payload, state, version=version, collect=True, warnings=warnings)
    # Typed declarations remain usable as proposals for independent diagnostics.
    # They confer no authority and pending errors make publication impossible.
    deferred = {'camera_invalid', 'camera_actor_missing', 'movement_agency', 'player_action_source_invalid', 'movement_endpoint_invalid'}
    if errors and (not defer_errors or any(e.code not in deferred for e in errors)):
        raise StructuralDeltaError.combine(errors)
    # Conditional endpoint rules do not make an otherwise typed proposal
    # unreadable; malformed field types still cannot support dependent checks.
    if errors:
        try:
            for step in p['scene_steps']: step_adapter(version).validate_python(step)
        except ValidationError:
            raise StructuralDeltaError.combine(errors)
    original=deepcopy(p)
    records = {name:deepcopy(p.get(name, [])) for name in SECTIONS}
    for name in OPTIONAL_SECTIONS:
        if not isinstance(records[name],list):
            records[name]=[]
            warnings.append(dict(section=name,code='optional_section_invalid',action='drop_section'))
    if version >= 9:
        bind_profile_baselines(records, state)
    normalize_facts(records, p, state)
    scene, camera = deepcopy(p['scene']), state['camera']
    positions = {cid:c['location_id'] for cid,c in state['characters'].items()}
    positions.update({c['id']:None for c in records['promotions']})
    aliases = {s['id']:identity('scene-step', turn_id, namespace, s['id']) for s in p['scene_steps']}
    actions, movement_sources = [], {}
    event_routes = {}
    local_exits = set()
    order=-1
    for index, value in enumerate(p['scene_steps']):
        step = step_adapter(version).validate_python(value)
        if step.timing!='simultaneous': order += 1
        eid = aliases[step.id]
        actor = getattr(step, 'actor_id', getattr(step, 'source_actor_id', None))
        targets = getattr(step, 'target_ids', [])
        if isinstance(step, GroupMovementStep):
            actor = camera['controlled_actor_id'] if camera and camera['controlled_actor_id'] in step.actor_ids else step.actor_ids[0]
        if isinstance(step, OccurrenceStep) and step.input_source:
            actor = camera['controlled_actor_id'] if camera['controlled_actor_id'] in step.actor_ids else None
        action_id = None
        if step.input_source:
            action_id = identity('scene-action', turn_id, namespace, step.id)
            outcome = getattr(step, 'outcome', 'completed')
            if isinstance(step, MovementFields) and step.assertion in ('intent','preparation','attempt'):
                outcome = 'attempted'
            actions.append(dict(id=action_id, player_evidence=step.input_source.quote,
                meaning=step.input_source.meaning, target_ids=getattr(step.input_source, 'intended_target_ids', None)
                if getattr(step.input_source, 'intended_target_ids', None) is not None else targets,
                narrative_target_ids=targets, outcome=outcome,
                target_mode='interaction' if targets else 'reference'))
        common = dict(id=eid, text=step.text, evidence=step.evidence, order=order,
                      advance_candidate_ids=step.advance_candidate_ids)
        if step.minute is not None: common['minute'] = step.minute
        during = getattr(step, 'during_step_id', None)
        if during:
            event_routes[eid] = aliases[during]
        if isinstance(step, MovementFields):
            if step.assertion in ('intent','preparation','attempt'):
                continue  # No completed geography, contact, or Knowledge.
            participants = movers(step)
            if step.assertion == 'local_exit':
                # Leaving a local interaction is not crossing a canonical address.
                local_exits.update(participants)
                event = dict(common, participants=participants, witnesses=[], medium='action')
            else:
                for traveller in participants:
                    movement = dict(actor_id=traveller, assertion=step.assertion,
                        from_location_id=positions[traveller], to_location_id=step.endpoint,
                        order=order, evidence=step.evidence, source_event_id=eid)
                    if action_id and traveller == camera['controlled_actor_id']:
                        movement['player_action_id'] = action_id
                    if step.involuntary_source_id and traveller == camera['controlled_actor_id']:
                        movement.update(player_assertion='involuntary', source_event_id=step.involuntary_source_id)
                    movement_sources[len(records['movements'])] = index
                    records['movements'].append(movement)
                    positions[traveller] = step.endpoint
                event = dict(common, participants=participants, witnesses=[], medium='action',
                    location_id=step.endpoint if step.endpoint is not None else movement['from_location_id'])
            if action_id: event.update(actor_id=actor, target_ids=[], player_action_id=action_id)
        elif isinstance(step, InformationStep):
            item = dict(common, source_actor_id=step.source_actor_id, target_ids=targets,
                medium=step.medium, claims=[c.model_dump(exclude_none=True) for c in step.claims])
            if step.channel: item['interaction_channel'] = step.channel
            if action_id: item['player_action_id'] = action_id
            if not during and step.channel != 'call' and actor in positions and positions[actor] is not None:
                item['location_id'] = positions[actor]
            records['information_events'].append(item)
            continue
        elif isinstance(step, InteractionStep):
            event = dict(common, participants=list(dict.fromkeys([actor]+targets)), witnesses=[],
                actor_id=actor, target_ids=targets, medium='conversation', interaction_channel=step.channel)
            if not during and step.channel == 'physical' and positions.get(actor) is not None:
                event['location_id'] = positions[actor]
            if action_id:
                event['player_action_id'] = action_id
                if step.outcome == 'completed': event['player_assertion'] = 'completed_interaction'
        else:
            event = dict(common, participants=step.actor_ids, witnesses=step.witnesses, fact_ids=step.fact_ids, medium='observation')
            if step.location_id: event['location_id'] = step.location_id
            if action_id: event.update(actor_id=actor, target_ids=[], player_action_id=action_id)
        records['events'].append(event)

    subject = camera['controlled_actor_id'] if camera['mode']=='actor' else camera.get('subject_id')
    location = positions.get(subject, camera['location_id'])
    if 'observer_location_id' in scene:
        observer_location = scene.pop('observer_location_id')
        if camera['mode'] == 'observer':
            location = observer_location
    visible = scene.pop('visible_character_ids', None)
    if visible is None:
        visible = ([subject] if camera['mode']=='actor' and subject in local_exits else
                   [cid for cid in camera['present_character_ids'] if positions.get(cid)==location and cid not in local_exits])
        if subject in positions and subject not in visible:
            visible.append(subject)
    scene.update(location_id=location,present_character_ids=visible)
    scene.setdefault('observed_character_ids', [])
    # Exact local references only, including unchanged domain consumers.
    reference_fields = {'source_event_id','source_event_ids','event_id','event_ids','player_action_id'}
    action_aliases = {s['id']:identity('scene-action',turn_id,namespace,s['id']) for s in p['scene_steps'] if s.get('input_source')}
    def refs(value, key=''):
        if isinstance(value, dict): return {k:refs(v,k) for k,v in value.items()}
        if isinstance(value, list): return [refs(v,key) for v in value]
        if isinstance(value,str) and (key in reference_fields or key.endswith(('_event_id','_event_ids'))):
            return (action_aliases if key=='player_action_id' else aliases).get(value,value)
        return value
    choices=p.get('choices',[])
    if version >= 9:
        from backend.runtime_v3.suggestions import bind_suggestions
        choices = bind_suggestions(choices, suggestions, warnings)
    choices=[c for c in choices if isinstance(c,dict) and isinstance(c.get('action'),str) and isinstance(c.get('speech',''),str)][:6] if isinstance(choices,list) else []
    # Narrow legacy metadata adaptation; domain handlers still validate the
    # accepted Event, Fact, actors, outcome, ownership and current input.
    by_id={s['id']:s for s in p['scene_steps']}
    for values in records.values():
        for item in values:
            if isinstance(item,dict):
                source=by_id.get(item.get('source_event_id'))
                if source and not item.get('evidence'):
                    item['evidence']=source.get('evidence') or source['text']
    for section,assertion in (('possession_deltas','explicit_choice'),('appearance_deltas','explicit_choice'),('development_evidence','completed_voluntary_behavior')):
        for item in records[section]:
            source=by_id.get(item.get('source_event_id'))
            provenance=source.get('input_source') if source else None
            if provenance and provenance['meaning']=='preserved' and source.get('outcome','completed') in ('completed','partial'):
                item.update(player_evidence=provenance['quote'],player_assertion=assertion)
    raw = RawTurnResult(scene, refs(records), deepcopy(choices), warnings,
        dict(status='violated' if any(f['classification']=='unauthorized_choice' for f in p.get('agency_findings',[])) else 'preserved',
             actions=actions, narrative_audit=[dict(f,player_action_id=None) for f in p.get('agency_findings',[])]))
    raw.semantic_candidate = original
    raw.movement_sources = movement_sources
    raw.event_routes = event_routes
    # Map compiler failures too: they happen before a Resolver can own the raw.
    from backend.services.world_delta_errors import StructuralDeltaError
    try:
        raw = compile_semantic(raw, state, narrative, turn_id, namespace=namespace,
                               private_inline_facts=version >= 9)
    except StructuralDeltaError as exc:
        compiled_errors=[]
        for row in exc.diagnostics('compilation'):
            section,index=row.get('section'),row.get('index')
            if section=='information_events' and isinstance(index,int):
                candidates=[i for i,s in enumerate(original['scene_steps']) if s['kind']=='information']
                row.update(compiled_path=row.get('path'),section='scene_steps',domain='scene_steps',index=candidates[index],
                    path=f'scene_steps[{candidates[index]}]',source_ids=[original['scene_steps'][candidates[index]]['id']])
            path={k:v for k,v in row.items() if k not in ('code','repair_error_code','repair_error_type','repair_reason','stage')}
            compiled_errors.append(StructuralDeltaError(row['repair_reason'],row['code'],repairable=exc.repairable,**path))
        raise StructuralDeltaError.combine(errors + compiled_errors) from exc
    raw.records['events'].sort(key=lambda event:event['order'])
    raw.event_sources = {}
    for i, event in enumerate(raw.records['events']):
        local = next((s['id'] for s in p['scene_steps'] if aliases[s['id']]==event['id']),None)
        if local is not None:
            raw.event_sources[i] = dict(section='scene_steps',index=next(n for n,s in enumerate(p['scene_steps']) if s['id']==local),local_id=local)
    raw.semantic_candidate = original
    raw.movement_sources = movement_sources
    raw.event_routes = event_routes
    raw.preflight_errors = [row for e in errors for row in e.diagnostics('compilation')]
    return raw


CONTRACT = '''
Extraction/6: return scene_steps in actual chronological order + scene, per schema.
Interpret unchanged WHOLE Narrative/input against canonical before. Preserve every significant outcome.
Each step states meaning ONCE; Runtime builds Events/Movement/PlayerAction/Fact/Knowledge and final position.
No events/movements/information_events/player_agency/final_scene copies. No everyday gesture inventory.
movement: intent/preparation/attempt != departure (unknown endpoint=null) != completed_arrival (reached endpoint).
New places and NPC initiative allowed. Name of destination != contact; greeting after arrival is its own step.
input_source: exact relevant input quote and meaning, once on the controlled actor's step; never an NPC reply.
Targets are actually reached addressees; partial input keeps intended_target_ids separately. Reference != delivery.
Report significant unchosen decisions anywhere in prose as agency_findings unauthorized_choice; do not launder prose.
information: claims reuse PerceivedClaim; perceived_by is per claim, never inferred from targets/presence/delivery.
Reuse fact_id only for the WHOLE assertion; fragment/hypothetical question never reveals a complete secret.
occurrence: objective domain source (e.g. birth/possession), not a pre-existing newborn contact. fact_ids link assertions without granting Knowledge. Domain source_event_id uses step.id.
scene: elapsed_minutes/situation and non-derivable visibility only. visible_character_ids overrides composition,
never moves anybody; omit to retain still-visible prior cast and follow camera subject. No automatic NPC visibility.
observer_location_id is observer-only. POV never transfers control. Unknown relative ordering needs correction,
never sort by ID: timing=uncertain. Explicit simultaneity uses timing=simultaneous with the preceding step; otherwise sequence order. Supply minute only if known. Runtime owns background/Skip clocks.
chronology_claims: narrator/belief/lie/quotation; event_elapsed links an existing event_id and elapsed_days; current_calendar uses date/weekday ID, no fake Event. Calendar outranks old titles; significant contradiction needs narrative recovery. Missing claims prove no check.
possession_deltas/appearance_deltas/development_evidence inherit input provenance from their exact step source_event_id; no repeated player quote/assertion.
Facts immutable, exact ID references, no fuzzy merges. Situation!=Emotion; EXTERNAL desires/commitments require input.
'''


def normalize_facts(records, candidate, state):
    """Idempotence only within an exact ID and complete immutable Fact identity."""
    from backend.runtime_v3.models import Fact
    seen={}
    def canonical(value):
        try:return Fact.model_validate({k:v for k,v in value.items() if k!='evidence'}).model_dump()
        except ValidationError as exc:fatal(str(exc),'fact_invalid',section='facts')
    unique=[]
    for item in records['facts']:
        fid=item['id'];fact=canonical(item)
        if fid in seen and seen[fid]!=fact:
            fatal('Конфликт локального ID факта.', 'canonical_id_conflict',section='facts',entity=fid)
        if fid not in seen:unique.append(item)
        seen[fid]=fact
    records['facts']=unique
    for index,step in enumerate(candidate['scene_steps']):
        if step['kind']!='information':continue
        for claim in step['claims']:
            value=claim.get('fact');fid=value.get('id') if isinstance(value,dict) else None
            if not fid:continue
            fact=canonical(value)
            existing=seen.get(fid,state['facts'].get(fid))
            if existing is not None:
                if fact!=existing:
                    fatal('Новый claim конфликтует с ID/содержанием/секретностью факта.',
                        'canonical_id_conflict',section='scene_steps',index=index,entity=fid)
                claim.pop('fact');claim['fact_id']=fid
            else:seen[fid]=fact


def source_diagnostic(raw, row):
    """Translate a derivative error to its external source, retaining audit path."""
    if not raw.semantic_candidate:return row
    row=deepcopy(row);section,index=row.get('section'),row.get('index')
    source=None
    if section=='events':source=raw.event_sources.get(index)
    elif section=='movements' and index in raw.movement_sources:
        n=raw.movement_sources[index]
        source=dict(section='scene_steps',index=n,local_id=raw.semantic_candidate['scene_steps'][n]['id'])
    elif section=='information_events' and isinstance(index,int) and index<len(raw.records['information_events']):
        eid=raw.records['information_events'][index].get('id')
        source=next((raw.event_sources.get(i) for i,e in enumerate(raw.records['events']) if e.get('id')==eid),None)
    elif section in ('knowledge','knowledge_gained') and isinstance(index,int) and index<len(raw.records['knowledge_gained']):
        eid=raw.records['knowledge_gained'][index].get('source_event_id')
        source=next((raw.event_sources.get(i) for i,e in enumerate(raw.records['events']) if e.get('id')==eid),None)
    elif section=='facts' and isinstance(index,int) and index<len(raw.records['facts']):
        fid=raw.records['facts'][index].get('id')
        source=next((raw.event_sources.get(i) for i,e in enumerate(raw.records['events'])
            if any(c.get('fact_id')==fid for c in e.get('information_source',{}).get('claims',[]))),None)
    elif section=='player_agency':
        # Action indices belong to generated action inventory; resolve by ID.
        path=row.get('path','')
        if path.startswith('player_agency.actions['):
            try:
                n=int(path.split('[',1)[1].split(']',1)[0]);action=raw.player_agency['actions'][n]
                candidates=[(i,s) for i,s in enumerate(raw.semantic_candidate['scene_steps']) if s.get('input_source')]
                i,step=candidates[n]
                source=dict(section='scene_steps',index=i,local_id=step['id'])
            except (ValueError,IndexError):pass
    if row.get('code')=='narrative_agency_conflict' and source and source.get('section')=='scene_steps':
        step = raw.semantic_candidate['scene_steps'][source['index']]
        row['correction_ground'] = dict(kind='agency', evidence=step.get('evidence') or step.get('text'))
    if row.get('code')=='narrative_agency_conflict' and source is None:
        findings=raw.semantic_candidate.get('agency_findings',[])
        indexes=[i for i,f in enumerate(findings) if f['classification']=='unauthorized_choice']
        if indexes:
            row['correction_grounds'] = [dict(kind='agency', evidence=findings[i].get('narrative_evidence')) for i in indexes]
            row.update(compiled_path=row.get('path'),section='agency_findings',domain='agency_findings',
                index=indexes[0],path=f'agency_findings[{indexes[0]}]',source_ids=[])
    if source and source.get('section')=='scene_steps':
        row.update(compiled_path=row.get('path'),domain='scene_steps',**source)
        row['path']=f"scene_steps[{source['index']}]"
        row['source_ids']=[source['local_id']]
        # Internal field names are preserved only as diagnostic metadata.
        if 'field' in row:row['compiled_field']=row.pop('field')
    elif section=='final_scene':
        row.update(compiled_path=row.get('path'),section='scene',domain='scene',path='scene')
    return row


SPATIAL_CONTRACT = CONTRACT.replace('Extraction/6', 'Extraction/7') + """
A movement uses actor_ids for ALL actually travelling together, one reached endpoint and one input_source
only when the controlled actor travels. Runtime creates per-actor routes; NPCs inherit no player choice.
One completed_arrival suffices for a completed shared trip; do not duplicate departure/arrival/quotes.
Retain conversation as separate steps before/after the trip. For conversation DURING a completed shared trip,
reference its earlier movement step with during_step_id; Runtime checks co-travellers, no fake intermediate location.
Examples: two people walk to a square and talk there => one arrival [both], then conversation.
One stays behind => arrival names only traveller. Preparing coats/planning a trip => preparation/intent, no arrival.
departure means crossing the boundary of the canonical location to unknown destination.
Leaving the kitchen for another room INSIDE the same canonical home => local_exit, endpoint=null;
retain address, remove from local visible cast. A closed door grants no perception: perceived_by only actual hearers.
If rooms already are canonical child locations, use arrival to that room; common parent proves no contact.
A new reached shore may be declared in locations; never keep the old address just because destination is new.
Preserve BOTH travel and conversation from compound actions. Visibility never supplies missing travellers.
Create each new assertion once: inline fact OR a top-level fact referenced by fact_id, not both.
"""
