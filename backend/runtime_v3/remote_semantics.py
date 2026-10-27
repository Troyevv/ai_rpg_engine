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
                 remote_time_source_id=dict(type='string'))
    rules = ('Remote semantic extraction/1. Extract ONLY accepted phone content into the existing RawTurnResult schema. '
             'This is GM truth, not a broadcast of Knowledge. No physical actions, emotion, goals or values. '
             'A proposal alone or hypothetical/past discussion is NOT an agreement. Require explicit assent from each '
             'participant; never include every group member automatically. Use scheduled_event_changes with assertion '
             'agreed/rescheduled/cancelled/occurred, exact evidence, remote_source_ids and remote_time_source_id. '
             'Anchor relative dates to the original proposal timestamp using temporal.minute_offset for hours/minutes, day_offset for tomorrow, weekday/day_period for imprecise windows; never invented due_minute. '
             'Reuse existing plan IDs on reschedule/cancellation/completion; due does not mean occurred. '
             'For EXTERNAL participant require player_assertion=explicit_choice and exact player_evidence from their '
             'authored message. Agreement does not require creating motivations. Only explicitly authored intentions '
             'may use character_changes.intentions_updates; preserve their exact wording, source_event_id and evidence. '
             'Do not create an intention for a recipient. Existing intention lifecycle uses fresh evidence, not time. '
             'Return final_scene exactly as supplied, including zero elapsed_minutes. No choices. '
             'Empty changes are valid when no consequences are established.')
    return [dict(role='system', content=rules), dict(role='user', content=json.dumps(dict(
        source_event_id=source_id, controlled_actor_id=state['camera']['controlled_actor_id'],
        current_time=current_time(state), calendar=state['meta']['calendar'],
        final_scene=dict(location_id=state['camera']['location_id'],
                         present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0),
        accepted_messages=[{k:e[k] for k in ('id','ordinal','sender_id','recipient_ids','conversation_id','world_time','content','read_by','delivered_to')} for e in rows],
        characters={cid:dict(id=cid, intentions=state['characters'][cid]['intentions']) for cid in sorted(ids)},
        existing_plans=[commitment_view(state,e) for e in state['scheduled_events'].values() if ids.intersection(e['character_ids'])],
        schema=schema), ensure_ascii=False))]


def resolve(snapshot, source_id, response):
    state = snapshot['world_state']
    rows = evidence_slice(state, source_id)
    raw = RawTurnResult.parse(response)
    expected = dict(location_id=state['camera']['location_id'],
                    present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0)
    if raw.final_scene != expected or raw.choices or any(v for k,v in raw.records.items()
            if k not in ('scheduled_event_changes','character_changes')):
        raise ValueError('Телефонное извлечение пытается изменить физическую сцену или неподдерживаемый раздел.')
    by_id = {e['id']:e for e in rows}
    for item in raw.records['scheduled_event_changes']:
        if not isinstance(item, dict) or not isinstance(item.get('remote_source_ids'), list) or not item['remote_source_ids'] or any(not isinstance(eid,str) or eid not in by_id for eid in item['remote_source_ids']):
            raise ValueError('Договорённости нужны принятые источники этого разговора.')
    for item in raw.records['character_changes']:
        if not isinstance(item, dict) or set(item) - {'id','evidence','intentions_updates'}:
            raise ValueError('Телефонное извлечение поддерживает только явно выраженные намерения.')
        for change in item.get('intentions_updates', []):
            event = by_id.get(change.get('source_event_id'))
            if not event or event['sender_id'] != item['id'] or not isinstance(change.get('evidence'),str) or not change['evidence'].strip() or change['evidence'] not in event['content']:
                raise ValueError('Намерение не подтверждено автором телефонной реплики.')
            if not change.get('id') and change.get('text') != change.get('evidence'):
                raise ValueError('Новое намерение должно сохранять авторскую формулировку.')
    actor = state['camera']['controlled_actor_id']
    narrative = '\n'.join(e['content'] for e in rows)
    authored = '\n'.join(e['content'] for e in rows if e['sender_id'] == actor)
    resolver = StateResolver(state, narrative, authored, turn_id=state['meta']['turn_id'], observed=False)
    resolver.remote_semantic_sources = by_id
    result = resolver.resolve(raw)
    if result.warnings:
        raise ValueError('Семантическая проверка связи: '+json.dumps(result.warnings, ensure_ascii=False))
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
