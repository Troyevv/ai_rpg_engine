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
    from backend.runtime_v3.group_planning import pending
    required = {source_id, *[e['id'] for e in thread[-24:]], *[e['id'] for e in pending(state, source['conversation_id'])]}
    rows = [e for e in thread if e['id'] in required or e['id'] in linked]
    if len(rows) > 48 or sum(len(e['content']) for e in rows) > 64000:
        raise ValueError('Контекст договорённости слишком велик; исходные сообщения сохранены.')
    return rows


RESPONSE_JSON_INSTRUCTION = 'Return one valid JSON object matching the supplied schema and example. '


def same_extraction_context(recorded, current, *, response_only=False):
    """Keep completed pre-fix response gates reusable; no evidence/schema changes.

    Only the exact old prompt lacking JSON guidance is compatible. The existing
    Resolver still validates the cached response against the staged source.
    """
    if recorded == current:
        return True
    if not response_only or not current:
        return False
    data = json.loads(current[1]['content'])
    data.pop('example_json_output', None)
    legacy = [dict(current[0], content=current[0]['content'].replace(RESPONSE_JSON_INSTRUCTION, '', 1)),
              dict(current[1], content=json.dumps(data, ensure_ascii=False))]
    return recorded == legacy


def messages(snapshot, source_id, *, response_only=False):
    state = snapshot['world_state']
    rows = evidence_slice(state, source_id)
    if not rows:
        return None
    if response_only:
        # Same source-bound Extraction contract, restricted to releasing the
        # existing wait before authoring. Consequences follow once, afterwards.
        schema = extraction_schema()
        schema['properties'] = {k:v for k,v in schema['properties'].items()
                                if k in ('final_scene','group_response_changes')}
        scene=dict(location_id=state['camera']['location_id'],
            present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0)
        return [dict(role='system', content=(
            'Remote semantic extraction/1. Interpret ONLY explicit answers or refusals to pending_group_requests. '
            + RESPONSE_JSON_INSTRUCTION +
            'Return final_scene unchanged and group_response_changes with canonical request_event_id, '
            'response_event_id, assertion answered/refused and exact evidence. Reading, silence, mentions '
            'and unrelated messages are not answers. Do not extract other consequences in this phase.')),
            dict(role='user',content=json.dumps(dict(schema=schema,final_scene=scene,
                example_json_output=dict(final_scene=scene,group_response_changes=[]),
                controlled_actor_id=state['camera']['controlled_actor_id'],
                pending_group_requests=[dict(event_id=e['id'], **e['response_request'])
                    for e in rows if e.get('response_request') and not e['response_request']['resolved_by']],
                accepted_messages=[{k:e[k] for k in ('id','sender_id','content','ordinal','world_time')}
                    for e in rows if e['sender_id']==state['camera']['controlled_actor_id'] or e.get('response_request')]),ensure_ascii=False))]
    ids = set().union(*(participants(e) for e in rows))
    schema = extraction_schema()
    allowed = ('final_scene', 'locations', 'scheduled_event_changes', 'character_changes', 'group_response_changes','group_request_changes','thread_changes','relationship_changes')
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
             'Use known_locations canonical IDs when a place already exists, matching names and aliases. '
             'For a new place established in accepted messages, emit locations with id, name and evidence '
             'using the common contract; reference that ID in the plan in this same response. '
             'Never invent a place to fill a plan: use location_id=null when no specific meeting place was agreed. '
             'A speaker being at an office does not establish it as the meeting place. '
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
             'For an explicit request addressed to controlled_actor_id in an accepted group message, '
             'emit group_request_changes with source_event_id, target_id, exact evidence, expires_at '
             '(canonical minute when the request becomes stale). Mentions alone do not request answers. '
             'For pending_group_requests, emit group_response_changes ONLY for an explicit answer or refusal '
             'authored by the target in this same group. Cite request_event_id, response_event_id, assertion '
             'answered/refused and exact evidence from the answer. Reading, silence, unrelated messages and '
             'ordinary Narrative are not answers. No invented consent. '
             'Threads may develop from accepted speech; cite source_event_id and evidence, never fabricate completed actions. '
             'Directed relationships use the common grounded_feelings contract with source_event_ids from '
             'relationship_sources, rationale and bounded dimension changes. Sources require actual reading, '
             'not mere delivery. Explicit player-directed feelings must be quoted from the current source_event_id, '
             'not a historical player message. A proposed meeting is never evidence of consent or an occurrence. '
             'Empty changes are valid when no consequences are established.')
    return [dict(role='system', content=rules), dict(role='user', content=json.dumps(dict(
        pending_group_requests=[dict(event_id=e['id'], **e['response_request']) for e in rows if e.get('response_request')],
        relationship_sources=[e for e in relationship_sources(snapshot) if e['id'] in {r['id'] for r in rows}],
        relationships=state['relationships'], threads=state['threads'],
        source_event_id=source_id, controlled_actor_id=state['camera']['controlled_actor_id'],
        current_time=current_time(state), calendar=state['meta']['calendar'],
        final_scene=dict(location_id=state['camera']['location_id'],
                         present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0),
        example_json_output=dict(final_scene=dict(location_id=state['camera']['location_id'],
            present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0),
            locations=[], scheduled_event_changes=[], character_changes=[]),
        known_locations=[{k:place[k] for k in ('id','name','aliases','parent_id')}
                         for place in state['locations'].values()],
        accepted_messages=[{k:e[k] for k in ('id','ordinal','sender_id','recipient_ids','conversation_id','world_time','content','read_by','delivered_to')} for e in rows],
        characters={cid:dict(id=cid, intentions=state['characters'][cid]['intentions']) for cid in sorted(ids)},
        existing_plans=[commitment_view(state,e) for e in state['scheduled_events'].values() if ids.intersection(e['character_ids'])],
        schema=schema), ensure_ascii=False))]


def resolve(snapshot, source_id, response, diagnostics=None, *, relationship_query=None, relationship_receipts=None):
    state = snapshot['world_state']
    rows = evidence_slice(state, source_id)
    raw = RawTurnResult.parse(response)
    expected = dict(location_id=state['camera']['location_id'],
                    present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=0)
    if raw.final_scene != expected or raw.choices or any(v for k,v in raw.records.items()
            if k not in ('locations','scheduled_event_changes','character_changes','group_response_changes','group_request_changes','thread_changes','relationship_changes')):
        raise ValueError('Телефонное извлечение пытается изменить физическую сцену или неподдерживаемый раздел.')
    by_id = {e['id']:e for e in rows}
    actor = state['camera']['controlled_actor_id']
    for index, item in enumerate(raw.records['scheduled_event_changes']):
        if not isinstance(item, dict) or not isinstance(item.get('remote_source_ids'), list) or not item['remote_source_ids'] or any(not isinstance(eid,str) or eid not in by_id for eid in item['remote_source_ids']):
            raise SemanticValidationError([dict(section='scheduled_events',index=index,code='commitment_remote_source',entity=item.get('id') if isinstance(item,dict) else None)],
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
    scoped_relationships=[]
    for index,item in enumerate(raw.records['relationship_changes']):
        ids=item.get('source_event_ids', []) if isinstance(item,dict) else None
        owned=isinstance(item,dict) and item.get('player_assertion')=='explicit_directed_feelings'
        quote=item.get('player_evidence') if isinstance(item,dict) else None
        current=by_id[source_id]
        if (not isinstance(ids,list) or any(not isinstance(eid,str) for eid in ids)
                or not set(ids) <= by_id.keys() or owned and (current['sender_id']!=actor
                    or not isinstance(quote,str) or not quote.strip() or quote not in current['content'])):
            optional_warnings.append(dict(section='relationships',index=index,code='remote_relationship_source',action='drop_record'))
        else:
            scoped_relationships.append(item)
    raw.records['relationship_changes']=scoped_relationships
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
    threads=[]
    for index,item in enumerate(raw.records['thread_changes']):
        source=item.get('source_event_id') if isinstance(item,dict) else None
        event=by_id.get(source) if isinstance(source,str) else None
        if not event or not isinstance(item.get('evidence'),str) or not item['evidence'] or item['evidence'] not in event['content']:
            optional_warnings.append(dict(section='threads',index=index,code='remote_thread_source',action='drop_record'))
        else:
            threads.append(item)
    raw.records['thread_changes']=threads
    narrative = '\n'.join(e['content'] for e in rows)
    authored = '\n'.join(e['content'] for e in rows if e['sender_id'] == actor)
    resolver = StateResolver(state, narrative, authored, turn_id=state['meta']['turn_id'], observed=False)
    resolver.remote_semantic_sources = by_id
    resolver.relationship_query = relationship_query
    resolver.relationship_receipts = relationship_receipts or []
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


def resolve_optional(snapshot, source_id, response, diagnostics, **resolver_options):
    """Quarantine only identified optional plans after one unsuccessful repair.

    Every attempt starts from the same snapshot and runs the common Resolver.
    Canonical/envelope errors still propagate. Rejected proposals remain in the
    durable job journal; existing canonical plans are never deleted or edited.
    """
    raw = RawTurnResult.parse(response)
    payload = dict(final_scene=raw.final_scene, choices=raw.choices, **raw.records)
    original_indices = list(range(len(payload['scheduled_event_changes'])))
    # Each rejection must remove at least one candidate: bounded, no LLM retries.
    while True:
        try:
            return resolve(snapshot, source_id, payload, diagnostics, **resolver_options)
        except SemanticValidationError as exc:
            records = payload['scheduled_event_changes']
            indices = {w['index'] for w in exc.warnings
                       if isinstance(w.get('index'), int) and 0 <= w['index'] < len(records)}
            if not indices:
                raise  # No proven safe isolation boundary.
            rejected = [r for i, r in enumerate(records) if i in indices]
            payload['scheduled_event_changes'] = [r for i, r in enumerate(records) if i not in indices]
            diagnostics.extend(dict(w, index=original_indices[w['index']], action='defer_record',
                remote_source_ids=[e['id'] for e in evidence_slice(snapshot['world_state'], source_id)])
                for w in exc.warnings if w.get('index') in indices)
            original_indices = [i for position, i in enumerate(original_indices) if position not in indices]
            # Do not commit a newly proposed place solely attached to a rejected
            # plan. Shared places needed by valid plans remain in that transaction.
            unused = {r.get('location_id') for r in rejected if isinstance(r, dict) and isinstance(r.get('location_id'), str)}
            used = {r.get('location_id') for r in payload['scheduled_event_changes'] if isinstance(r, dict) and isinstance(r.get('location_id'), str)}
            used.update(r['parent_id'] for r in payload['locations']
                        if isinstance(r, dict) and isinstance(r.get('parent_id'), str))
            retained = []
            for location in payload['locations']:
                lid = location.get('id') if isinstance(location, dict) else None
                if isinstance(lid, str) and lid in unused - used:
                    diagnostics.append(dict(section='locations', entity=lid, code='remote_deferred_plan_location',
                        action='defer_record', source_event_id=source_id))
                else:
                    retained.append(location)
            payload['locations'] = retained


def relationship_sources(snapshot, source_ids=None):
    """Canonical utterances perceived by participants, using common #107 evidence.

    Stable RemoteEvent IDs prevent consuming successive delivery/read transitions
    as independent evidence. This is a projection, not another event journal.
    """
    return [dict(id=e['id'], turn_id=e['turn_id'], participants=sorted({e['sender_id'], *e['read_by']}),
        scene_action=dict(actor_id=e['sender_id'], modality='speech', phase='completed'),
        evidence=e['content'], remote_interaction_id=e['id'])
        for e in snapshot['world_state']['remote_events'].values()
        if e['channel']=='TEXT_MESSAGE' and e['read_by'] and (source_ids is None or e['id'] in source_ids)]
