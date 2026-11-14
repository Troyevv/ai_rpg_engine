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


class Step(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence: str = ''
    input_source: InputSource | None = None
    advance_candidate_ids: list[str] = Field(default_factory=list, max_length=3)
    minute: int | None = Field(default=None, ge=0)
    timing: Literal['after_previous','simultaneous','uncertain'] = 'after_previous'


class MovementStep(Step):
    kind: Literal['movement']
    actor_id: str
    assertion: Literal['intent', 'preparation', 'attempt', 'departure', 'completed_arrival']
    endpoint: str | None = None
    involuntary_source_id: str | None = None


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


def project_schema(schema):
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
    steps = STEP.json_schema()
    schema.setdefault('$defs', {}).update(steps.pop('$defs', {}))
    props.update(scene=scene, scene_steps={'type':'array', 'maxItems':64, 'items':steps},
        agency_findings={'type':'array','items':{'type':'object','additionalProperties':False,
            'properties':{'narrative_evidence':{'type':'string'},
                'classification':{'enum':['unauthorized_choice','uncertain','incidental_detail']}},
            'required':['narrative_evidence','classification']}})
    schema['required'] = ['scene', 'scene_steps']
    return schema


@lru_cache(maxsize=1)
def input_schema():
    from backend.runtime_v3.raw import prompt_schema
    return prompt_schema(semantic_slice=True, scene_sequence=True, consequence_first=True,
                         explicit_departures=True, grounded_choices=True, player_agency_required=True)


def decode(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            fatal('Некорректный JSON Extraction/6.', 'raw_root_invalid', repairable=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('scene_steps'), list) or not isinstance(payload.get('scene'), dict):
        fatal('Ожидается Extraction/6: scene_steps и scene.', 'raw_root_invalid', repairable=True)
    return deepcopy(payload)


def validate(payload):
    from jsonschema import Draft202012Validator
    from backend.services.world_delta_errors import StructuralDeltaError
    p = decode(payload)
    errors = []
    for error in Draft202012Validator(input_schema()).iter_errors(p):
        path = list(error.absolute_path)
        if path and path[0] in OPTIONAL_SECTIONS | {'choices'}:
            continue  # Existing optional-domain owners still isolate annotation errors.
        errors.append(StructuralDeltaError(error.message, 'scene_schema_invalid',
            section=path[0] if path else 'scene_steps', path='.'.join(map(str,path)) or '$',
            **({'index':path[1]} if len(path)>1 and isinstance(path[1],int) else {})))
    if errors:
        raise StructuralDeltaError.combine(errors)
    ids = [s['id'] for s in p['scene_steps']]
    if len(set(ids)) != len(ids):
        fatal('Повторный ID смыслового шага.', 'semantic_duplicate', section='scene_steps')
    return p


def compile_scene(payload, state, narrative, turn_id, *, namespace=None):
    p = validate(payload)
    original=deepcopy(p)
    records = {name:deepcopy(p.get(name, [])) for name in SECTIONS}
    warnings=[]
    for name in OPTIONAL_SECTIONS:
        if not isinstance(records[name],list):
            records[name]=[]
            warnings.append(dict(section=name,code='optional_section_invalid',action='drop_section'))
    normalize_facts(records, p, state)
    scene, camera = deepcopy(p['scene']), state['camera']
    positions = {cid:c['location_id'] for cid,c in state['characters'].items()}
    positions.update({c['id']:None for c in records['promotions']})
    aliases = {s['id']:identity('scene-step', turn_id, namespace, s['id']) for s in p['scene_steps']}
    actions, movement_sources = [], {}
    order=-1
    for index, value in enumerate(p['scene_steps']):
        try:
            step = STEP.validate_python(value)
        except ValidationError as exc:
            fatal(str(exc), 'scene_step_invalid', section='scene_steps', index=index)
        if step.timing=='uncertain' or index==0 and step.timing=='simultaneous':
            fatal('Не установлен относительный порядок значимых шагов.', 'scene_order_ambiguous', section='scene_steps', index=index)
        if step.timing!='simultaneous': order += 1
        eid = aliases[step.id]
        actor = getattr(step, 'actor_id', getattr(step, 'source_actor_id', None))
        targets = getattr(step, 'target_ids', [])
        role_ids=set(([actor] if actor else []) + targets)
        if isinstance(step, InformationStep):
            role_ids.update(cid for claim in step.claims for cid in claim.perceived_by)
        if isinstance(step, OccurrenceStep):role_ids.update(step.actor_ids+step.witnesses)
        if role_ids - positions.keys():
            fatal('Неизвестная личность в смысловом шаге.', 'scene_actor_unknown',
                  section='scene_steps', index=index, source_ids=sorted(role_ids-positions.keys()))
        if isinstance(step, OccurrenceStep) and step.input_source:
            actor = camera['controlled_actor_id'] if camera['controlled_actor_id'] in step.actor_ids else None
        action_id = None
        if step.input_source:
            if actor != camera['controlled_actor_id'] or actor is None:
                fatal('Источник ввода принадлежит только управляемому автору.', 'player_action_source_invalid', section='scene_steps', index=index)
            action_id = identity('scene-action', turn_id, namespace, step.id)
            outcome = getattr(step, 'outcome', 'completed')
            if isinstance(step, MovementStep) and step.assertion in ('intent','preparation','attempt'):
                outcome = 'attempted'
            actions.append(dict(id=action_id, player_evidence=step.input_source.quote,
                meaning=step.input_source.meaning, target_ids=step.input_source.intended_target_ids
                if step.input_source.intended_target_ids is not None else targets,
                narrative_target_ids=targets, outcome=outcome,
                target_mode='interaction' if targets else 'reference'))
        common = dict(id=eid, text=step.text, evidence=step.evidence, order=order,
                      advance_candidate_ids=step.advance_candidate_ids)
        if step.minute is not None: common['minute'] = step.minute
        if isinstance(step, MovementStep):
            if step.assertion in ('intent','preparation','attempt'):
                continue  # No completed geography, contact, or Knowledge.
            if step.actor_id not in positions:
                fatal('Неизвестный участник маршрута.', 'character_unknown', section='scene_steps', index=index)
            if step.assertion == 'departure' and step.endpoint is not None:
                fatal('Уход с неизвестным назначением не задаёт endpoint.', 'movement_endpoint_invalid', section='scene_steps', index=index)
            movement = dict(actor_id=actor, assertion=step.assertion,
                from_location_id=positions[actor], to_location_id=step.endpoint,
                order=order, evidence=step.evidence, source_event_id=eid)
            if action_id: movement['player_action_id'] = action_id
            if step.involuntary_source_id:
                movement.update(player_assertion='involuntary', source_event_id=step.involuntary_source_id)
            movement_sources[len(records['movements'])] = index
            records['movements'].append(movement)
            positions[actor] = step.endpoint
            event = dict(common, participants=[actor], witnesses=[], medium='action',
                location_id=step.endpoint if step.endpoint is not None else movement['from_location_id'])
            if action_id: event.update(actor_id=actor, target_ids=[], player_action_id=action_id)
        elif isinstance(step, InformationStep):
            item = dict(common, source_actor_id=step.source_actor_id, target_ids=targets,
                medium=step.medium, claims=[c.model_dump(exclude_none=True) for c in step.claims])
            if step.channel: item['interaction_channel'] = step.channel
            if action_id: item['player_action_id'] = action_id
            if step.channel != 'call' and actor in positions and positions[actor] is not None:
                item['location_id'] = positions[actor]
            records['information_events'].append(item)
            continue
        elif isinstance(step, InteractionStep):
            if step.outcome in ('deferred','not_performed') and targets:
                fatal('Несостоявшееся взаимодействие не имеет достигнутых адресатов.', 'scene_step_invalid', section='scene_steps', index=index)
            event = dict(common, participants=list(dict.fromkeys([actor]+targets)), witnesses=[],
                actor_id=actor, target_ids=targets, medium='conversation', interaction_channel=step.channel)
            if step.channel == 'physical' and positions.get(actor) is not None:
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
        if camera['mode'] != 'observer':
            fatal('Extraction не меняет режим камеры.', 'camera_invalid', section='scene', field='observer_location_id')
        location = scene.pop('observer_location_id')
    visible = scene.pop('visible_character_ids', None)
    if visible is None:
        visible = [cid for cid in camera['present_character_ids'] if positions.get(cid)==location]
        if subject in positions and subject not in visible:
            visible.append(subject)
    elif camera['mode']=='actor' and subject not in visible:
        fatal('Явная композиция исключает управляемого персонажа.', 'camera_actor_missing', section='scene', field='visible_character_ids')
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
    # Map compiler failures too: they happen before a Resolver can own the raw.
    from backend.services.world_delta_errors import StructuralDeltaError
    try:
        raw = compile_semantic(raw,state,narrative,turn_id,namespace=namespace)
    except StructuralDeltaError as exc:
        errors=[]
        for row in exc.diagnostics('compilation'):
            section,index=row.get('section'),row.get('index')
            if section=='information_events' and isinstance(index,int):
                candidates=[i for i,s in enumerate(original['scene_steps']) if s['kind']=='information']
                row.update(compiled_path=row.get('path'),section='scene_steps',domain='scene_steps',index=candidates[index],
                    path=f'scene_steps[{candidates[index]}]',source_ids=[original['scene_steps'][candidates[index]]['id']])
            path={k:v for k,v in row.items() if k not in ('code','repair_error_code','repair_error_type','repair_reason','stage')}
            errors.append(StructuralDeltaError(row['repair_reason'],row['code'],repairable=exc.repairable,**path))
        raise StructuralDeltaError.combine(errors) from exc
    raw.records['events'].sort(key=lambda event:event['order'])
    raw.event_sources = {}
    for i, event in enumerate(raw.records['events']):
        local = next((s['id'] for s in p['scene_steps'] if aliases[s['id']]==event['id']),None)
        if local is not None:
            raw.event_sources[i] = dict(section='scene_steps',index=next(n for n,s in enumerate(p['scene_steps']) if s['id']==local),local_id=local)
    raw.semantic_candidate = original
    raw.movement_sources = movement_sources
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
    if row.get('code')=='narrative_agency_conflict' and source is None:
        findings=raw.semantic_candidate.get('agency_findings',[])
        indexes=[i for i,f in enumerate(findings) if f['classification']=='unauthorized_choice']
        if indexes:
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
