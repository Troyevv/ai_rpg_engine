"""Source-bound adapter into the existing Extraction/Resolver contract.

No phone state store: messages live in WorldState, attempts in the job journal,
and consequences in the normal History/StatePatch transaction.
"""
import json
from copy import deepcopy
from backend.runtime_v3.raw import RawTurnResult, extraction_schema
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.calendar import current_time, commitment_view
from backend.runtime_v3.remote import participants


class SemanticValidationError(ValueError):
    """A proposed commitment was rejected; never report it as saved."""
    def __init__(self, warnings, candidate_ids=()):
        self.warnings=warnings
        self.candidate_ids=list(candidate_ids)
        super().__init__('Семантическая проверка связи: '+json.dumps(warnings,ensure_ascii=False))


def evidence_slice(state, source_id):
    source = state['remote_events'][source_id]
    if source['channel'] != 'TEXT_MESSAGE':
        return []
    thread = [e for e in state['remote_events'].values()
              if e['channel'] == 'TEXT_MESSAGE' and e['conversation_id'] == source['conversation_id']]
    # Keep complete messages, plus the original evidence for existing plans.
    # Never cut an authored message at the old 400-character preview boundary.
    linked = {eid for plan in state['scheduled_events'].values()
              if plan['status'] == 'pending' for eid in plan.get('remote_source_ids', [])}
    required = {source_id, *[e['id'] for e in thread[-24:]]}
    rows = [e for e in thread if e['id'] in required or e['id'] in linked]
    if len(rows) > 48 or sum(len(e['content']) for e in rows) > 64000:
        raise ValueError('Контекст договорённости слишком велик; исходные сообщения сохранены.')
    return rows


def messages(snapshot, source_id):
    state = snapshot['world_state']
    rows = evidence_slice(state, source_id)
    if not rows:
        return None
    ids = set().union(*(participants(e) for e in rows))
    schema = extraction_schema()
    allowed = ('final_scene', 'scheduled_event_changes', 'character_changes')
    schema['properties'] = {k:v for k,v in schema['properties'].items() if k in allowed}
    character=schema['properties']['character_changes']['items']
    character['properties']={k:v for k,v in character['properties'].items() if k in ('id','evidence','intentions_updates')}
    props = schema['properties']['scheduled_event_changes']['items']['properties']
    props.update(remote_source_ids=dict(type='array', items=dict(type='string'), minItems=1, maxItems=8),
                 remote_time_source_id=dict(type='string'), player_source_id=dict(type='string',
                 description='Canonical ID of the controlled actor message explicitly proposing/accepting/changing this plan; must belong to remote_source_ids.'))
    schema['properties']['scheduled_event_changes']['items']['allOf']=[{
        'if':{'required':['character_ids','assertion'],'properties':{
            'character_ids':{'contains':{'const':state['camera']['controlled_actor_id']}},
            'assertion':{'enum':['agreed','rescheduled']}}},
        'then':{'required':['player_assertion','player_source_id','player_evidence'],
                'properties':{'player_assertion':{'const':'explicit_choice'}}}}]
    rules = ('Remote semantic extraction/1. Return one valid JSON object matching the supplied schema. '
             'Extract ONLY accepted phone content into the existing RawTurnResult schema. '
             'This is GM truth, not a broadcast of Knowledge. No physical actions, emotion, goals or values. '
             'A proposal alone or hypothetical/past discussion is NOT an agreement. Require explicit assent from each '
             'participant; never include every group member automatically. Use scheduled_event_changes with assertion '
             'agreed/rescheduled/cancelled/occurred, exact evidence, remote_source_ids and remote_time_source_id. '
             'Anchor relative dates to the original proposal timestamp using temporal.minute_offset for hours/minutes, day_offset for tomorrow, weekday/day_period for imprecise windows; never invented due_minute. '
             'Reuse existing plan IDs on reschedule/cancellation/completion; due does not mean occurred. '
             'For EXTERNAL participant require player_assertion=explicit_choice AND player_source_id identifying their '
             'own explicit proposal/assent/change in remote_source_ids. Copy its entire content as player_evidence; '
             'never quote the NPC confirmation as player evidence. The adapter verifies sender_id and binds the '
             'canonical text, so no extra Narrative player_input is needed. A question proposing a concrete meeting '
             'can establish the proposer choice only after the other participants explicitly assent. Greeting, '
             'refusal, hypothetical discussion and mere receipt are not assent. Never invent explicit_choice. '
             'Agreement does not require creating motivations. Only explicitly authored intentions '
             'may use character_changes.intentions_updates; preserve their exact wording, source_event_id and evidence. '
             'Do not create an intention for a recipient. Existing intention lifecycle uses fresh evidence, not time. '
             'Return final_scene exactly as supplied, including zero elapsed_minutes. No choices. '
             'Empty changes are valid when no consequences are established.')
    return [dict(role='system', content=rules), dict(role='user', content=json.dumps(dict(
        source_event_id=source_id, controlled_actor_id=state['camera']['controlled_actor_id'],
        current_time=current_time(state), calendar=state['meta']['calendar'],
        final_scene=dict(location_id=state['camera']['location_id'],
                         present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0),
        example_json_output=dict(final_scene=dict(location_id=state['camera']['location_id'],
            present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0),
            scheduled_event_changes=[], character_changes=[]),
        accepted_messages=[{k:e[k] for k in ('id','ordinal','sender_id','recipient_ids','conversation_id','world_time','content','read_by','delivered_to')} for e in rows],
        characters={cid:dict(id=cid, intentions=state['characters'][cid]['intentions']) for cid in sorted(ids)},
        existing_plans=[commitment_view(state,e) for e in state['scheduled_events'].values() if ids.intersection(e['character_ids'])],
        schema=schema), ensure_ascii=False))]


def resolve(snapshot, source_id, response, diagnostics=None):
    state = snapshot['world_state']
    rows = evidence_slice(state, source_id)
    raw = RawTurnResult.parse(response)
    expected = dict(location_id=state['camera']['location_id'],
                    present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0)
    if raw.final_scene != expected or raw.choices or any(v for k,v in raw.records.items()
            if k not in ('scheduled_event_changes','character_changes')):
        raise ValueError('Телефонное извлечение пытается изменить физическую сцену или неподдерживаемый раздел.')
    by_id = {e['id']:e for e in rows}
    actor = state['camera']['controlled_actor_id']
    for item in raw.records['scheduled_event_changes']:
        if not isinstance(item, dict) or not isinstance(item.get('remote_source_ids'), list) or not item['remote_source_ids'] or any(not isinstance(eid,str) or eid not in by_id for eid in item['remote_source_ids']):
            raise SemanticValidationError([dict(section='scheduled_events',code='commitment_remote_source',entity=item.get('id') if isinstance(item,dict) else None)],
                [r['id'] for r in raw.records['scheduled_event_changes'] if isinstance(r,dict) and isinstance(r.get('id'),str)])
        # Resolve declared identity, not meaning: explicit_choice still belongs
        # to Extraction and is mandatory. Never infer consent from message presence.
        if item.get('player_assertion')=='explicit_choice':
            authored=[e for e in rows if e['id'] in item['remote_source_ids'] and e['sender_id']==actor]
            declared=item.get('player_source_id')
            matches=[e for e in authored if e['id']==declared] if declared is not None else [
                e for e in authored if item.get('player_evidence')==e['content']]
            if len(matches)==1:
                item['player_source_id']=matches[0]['id']
                item['player_evidence']=matches[0]['content']
    optional_warnings=[]
    valid_characters=[]
    for index,item in enumerate(raw.records['character_changes']):
        if not isinstance(item, dict) or set(item) - {'id','evidence','intentions_updates'}:
            optional_warnings.append(dict(section='characters',index=index,code='remote_optional_record_invalid',action='drop_record'))
            continue
        valid=[]
        for change in item.get('intentions_updates', []) if isinstance(item.get('intentions_updates',[]),list) else [None]:
            if not isinstance(change,dict):
                optional_warnings.append(dict(section='characters',index=index,code='remote_intention_source',action='drop_record'));continue
            source=change.get('source_event_id')
            event = by_id.get(source) if isinstance(source,str) else None
            if not event or event['sender_id'] != item.get('id') or not isinstance(change.get('evidence'),str) or not change['evidence'].strip() or change['evidence'] not in event['content']:
                optional_warnings.append(dict(section='characters',index=index,code='remote_intention_source',action='drop_record'));continue
            if not change.get('id') and change.get('text') != change.get('evidence'):
                optional_warnings.append(dict(section='characters',index=index,code='remote_intention_wording',action='drop_record'));continue
            valid.append(change)
        if valid: valid_characters.append(dict(item,intentions_updates=valid))
    raw.records['character_changes']=valid_characters
    narrative = '\n'.join(e['content'] for e in rows)
    authored = '\n'.join(e['content'] for e in rows if e['sender_id'] == actor)
    resolver = StateResolver(state, narrative, authored, turn_id=state['meta']['turn_id'], observed=False)
    resolver.remote_semantic_sources = by_id
    from backend.services.world_delta_errors import StructuralDeltaError
    try:
        result = resolver.resolve(raw)
    except StructuralDeltaError as exc:
        if exc.path.get('section') != 'scheduled_event_changes': raise
        raise SemanticValidationError([dict(exc.path,section='scheduled_events',code=exc.code,reason=str(exc))],
            [r['id'] for r in raw.records['scheduled_event_changes'] if isinstance(r,dict) and isinstance(r.get('id'),str)]) from exc
    critical=[w for w in result.warnings if w.get('section') in ('scheduled_events','scheduled_event_changes') and w.get('code')!='commitment_duplicate']
    if critical:
        raise SemanticValidationError(critical,[r['id'] for r in raw.records['scheduled_event_changes'] if isinstance(r,dict) and isinstance(r.get('id'),str)])
    if diagnostics is not None: diagnostics.extend(optional_warnings+result.warnings)
    after = deepcopy(snapshot)
    after['world_state'] = result.state
    # Extraction is not a second physical scene or elapsed turn.
    after['world_state']['camera'] = deepcopy(state['camera'])
    for row in result.history.get('turns', []):
        row['interaction_channel']='phone'
        row['remote_source_ids']=[e['id'] for e in rows]
    return after, result.history


def staged_sources(snapshot):
    """Reuse ordinary Extraction for autonomous messages accepted by Director."""
    state=snapshot['world_state'];result={}
    for row in snapshot.get('_remote_batch',{}).get('events',[]):
        eid=row.get('remote_interaction_id')
        if eid in state['remote_events'] and state['remote_events'][eid]['channel']=='TEXT_MESSAGE':
            result.update({e['id']:e for e in evidence_slice(state,eid)})
    return result
