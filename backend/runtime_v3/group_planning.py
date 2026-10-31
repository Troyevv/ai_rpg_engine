"""Pure bounded group selection and source-bound response lifecycle for Remote.

No scheduler or message store. Canonical conversations own attempt pacing;
RemoteEvents own request annotations. All writes are staged in the existing job.
"""
from copy import deepcopy
import hashlib
import json
from pydantic import Field
from backend.runtime_v3.remote_models import RemoteModel, GroupResponseChange, GroupRequestChange, ResponseRequest
from backend.runtime_v3.life import capabilities

COOLDOWN_MINUTES = 30
MAX_MESSAGES = 3
MAX_GROUPS = 2


class GroupMessage(RemoteModel):
    actor_id: str
    content: str = Field(min_length=1)
    basis_ids: list[str] = Field(min_length=1, max_length=8)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=8)
    read_previous: bool = False


class GroupReaction(RemoteModel):
    # Output/context token budgets bound processing, not a literary reply count.
    messages: list[GroupMessage] = Field(default_factory=list)


class GroupSeries(RemoteModel):
    conversation_id: str
    messages: list[GroupMessage] = Field(min_length=1, max_length=MAX_MESSAGES)


class RequestAnnotation(RemoteModel):
    message_index: int = Field(ge=0, lt=MAX_MESSAGES)
    target_id: str
    evidence: str = Field(min_length=1)
    expires_at: int = Field(ge=0)


class GroupSemantics(RemoteModel):
    requests: list[RequestAnnotation] = Field(max_length=MAX_MESSAGES)


def pending(state, conversation_id):
    """Derived, not an independently mutable pause flag. No prose heuristics."""
    from backend.runtime_v3.remote import members
    group = state['conversations'].get(conversation_id)
    if not group or not group['group']:
        return []
    current = members(group)
    now = state['meta']['world_time']
    result = []
    for e in state['remote_events'].values():
        request = e.get('response_request')
        if (e['conversation_id'] != conversation_id or not request or request['resolved_by']
                or request.get('closed_reason') or request['expires_at'] <= now):
            continue
        target = request['target_id']
        if ({e['sender_id'], target} <= current
                and target == state['camera']['controlled_actor_id']
                and all(state['characters'][a]['life_status'] != 'dead' for a in (target, e['sender_id']))):
            result.append(e)
    return sorted(result, key=lambda e: (e['ordinal'], e['id']))


def available(state, actor):
    caps = capabilities(state, actor)
    return actor != state['camera']['controlled_actor_id'] and caps['can_act'] and caps['can_perceive']


def stimulus(state, group):
    """Identity of canonical inputs, not a classifier of literary importance.

    Exclude clock/turn and delivery bookkeeping. The author decides whether a
    change warrants speech. Record after acceptance so our own series cannot
    recursively trigger itself. No world facts are granted to any speaker.
    """
    from backend.runtime_v3.remote import members
    actors = members(group) - {state['camera']['controlled_actor_id']}
    inputs = dict(
        characters={a: {k: state['characters'][a][k] for k in
                    ('goals', 'intentions', 'life_status')} for a in sorted(actors)},
        relationships={k:v for k,v in state['relationships'].items()
                       if v['source_id'] in actors or v['target_id'] in actors},
        threads={k:v for k,v in state['threads'].items() if actors.intersection(v['character_ids'])},
        knowledge={k:v for k,v in state['knowledge'].items() if v['actor_id'] in actors},
        plans={k:v for k,v in state['scheduled_events'].items() if actors.intersection(v['character_ids'])},
        messages={k: {f:v[f] for f in ('sender_id', 'content', 'response_request')}
                  for k,v in state['remote_events'].items() if v['conversation_id'] == group['id']})
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ready(state, group, events=()):
    if not group['group'] or pending(state, group['id']):
        return False
    now, turn = state['meta']['world_time'], state['meta']['turn_id']
    recent = [c['initiative_pacing'] for c in state['conversations'].values() if c.get('initiative_pacing')]
    if any(p['turn_id'] == turn for p in recent):
        return False
    pacing = group.get('initiative_pacing')
    event_ids = {e['id'] for e in events}
    return (not pacing or bool(event_ids - set(pacing.get('event_ids', [])))
            or now - pacing['world_time'] >= COOLDOWN_MINUTES
            or pacing.get('stimulus') is not None and pacing['stimulus'] != stimulus(state, group))


def history_cues(state, group, events):
    from backend.runtime_v3.remote import members
    actors = members(group) - {state['camera']['controlled_actor_id']}
    return [e for e in events if e.get('id') and not e.get('remote_interaction_id')
            and actors.intersection(e.get('participants', []))][-64:]


def opportunities(state, history_events=()):
    from backend.runtime_v3.remote import members
    if not state['meta']['communication']['text_message']:
        return []
    result = []
    for group in sorted(state['conversations'].values(), key=lambda c: (
            (c.get('initiative_pacing') or {}).get('world_time', -1), c['id'])):
        # Structural participation selects context, never importance or meaning.
        events = history_cues(state, group, history_events)
        if not ready(state, group, events):
            continue
        actors = sorted(a for a in members(group) if available(state, a))
        if len(actors) < 2:
            continue
        basis = {}
        for actor in actors:
            c = state['characters'][actor]
            ids = [r['id'] for r in c['intentions'] if r['status'] == 'active'
                   and (r['due_minute'] is None or r['due_minute'] <= state['meta']['world_time'])]
            # Existing story threads motivate spontaneous initiative without an intention.
            ids += [t['id'] for t in state['threads'].values() if t['status'] in ('active', 'developing')
                    and actor in t['character_ids'] and len(set(t['character_ids']) & set(actors)) >= 2]
            ids += [e['id'] for e in state['remote_events'].values()
                    if e['conversation_id'] == group['id'] and actor in e['read_by']
                    and 0 <= state['meta']['world_time'] - e['world_time'] <= 120]
            ids += [key for key, k in state['knowledge'].items()
                    if k['actor_id'] == actor and k['status'] == 'known'
                    and k.get('source_turn') is not None and k['source_turn'] >= state['meta']['turn_id'] - 2
                    and len(set(state['facts'][k['fact_id']]['character_ids']) & set(actors)) >= 2]
            if ids:
                basis[actor] = list(dict.fromkeys(ids))[-8:]
        motivated = set(basis)
        # Conversation identity permits a spontaneous attempt; it is not
        # evidence of a fact or a substitute for the speaker's Knowledge.
        for actor in actors:
            basis.setdefault(actor, [group['id']])
        actors = sorted(actors, key=lambda a: (a not in motivated, a))[:4]
        basis = {a: ids for a, ids in basis.items() if a in actors}
        result.append(dict(conversation_id=group['id'], actor_ids=actors, basis=basis, event_cues=events,
            initiative='changed_context' if (group.get('initiative_pacing') or {}).get('stimulus') not in
                (None, stimulus(state, group)) else 'spontaneous'))
        if len(result) == MAX_GROUPS:
            break
    return result


GROUP_TEXT_CONTEXT = (
    'For group_series and group reactions, the channel is TEXT_MESSAGE: each content is a written message '
    'in a remote group conversation, not dialogue staged in a shared physical room. '
    'Group membership and message delivery provide no visual or auditory perception, gestures, facial expressions, '
    'physical actions or whereabouts of other members. Participants may be in different locations. '
    'Each actor may use their own Knowledge, read messages and supplied personal context only; '
    'another actor\'s personal context is not shared knowledge. Own location and canonical co-presence are '
    'personal context, not new movement or permission to infer offscreen presence. They may discuss genuine '
    'co-presence when supported by that context or known evidence; do not ban physical topics or figurative speech. '
    'Preserve each speaker\'s personality and communication style, with natural humour, gossip, conflict, emotion, '
    'profanity and short or long messages as appropriate. No mandatory messenger slang, format or reply. '
    'Use the supplied CommunicationProfile delivery policy and technology, not assumptions about a modern app. '
    'These group-text instructions do not apply to letters, couriers or other channels. '
)


def context(snapshot, options):
    """Per-speaker knowledge; no unrelated conversations or omniscient history."""
    state = snapshot['world_state']
    from backend.runtime_v3.personality import context_profile
    cards = {c['id']: c for c in snapshot.get('character_cards', [])}
    result = []
    for option in options:
        gid = option['conversation_id']
        actors = []
        for actor in option['actor_ids']:
            c = state['characters'][actor]
            actors.append(dict(id=actor, name=c['display_name'],
                personality=context_profile(c),
                legacy_voice=({k:v for k,v in cards.get(actor, {}).get('fields', {}).items()
                              if k in ('Характер', 'Стиль общения')} if c.get('personality') is None else {}),
                personal_context=dict(own_location_id=c['location_id'],
                    present_character_ids=(state['camera']['present_character_ids']
                        if actor in state['camera']['present_character_ids'] else [])),
                intentions=c['intentions'][:3], goals=c['goals'][:3],
                relationships=[r for r in state['relationships'].values() if r['source_id'] == actor
                               and r['target_id'] in option['actor_ids']][:8],
                knowledge=[dict(id=key, text=state['facts'][k['fact_id']]['text'], status=k['status'])
                           for key, k in state['knowledge'].items() if k['actor_id'] == actor and k['status'] == 'known'][-8:],
                history=[{k:e[k] for k in ('id','sender_id','content','world_time')}
                         for e in state['remote_events'].values() if e['conversation_id'] == gid
                         and (e['sender_id'] == actor or actor in e['read_by'])][-6:]))
        result.append(dict(**option, title=state['conversations'][gid]['title'], actors=actors,
            channel='TEXT_MESSAGE', communication_profile=deepcopy(state['meta']['communication']),
            gm_story_context=[dict(id=t['id'], description=t['description'], state=t['state'], character_ids=t['character_ids']) for t in state['threads'].values()
                     if t['id'] in {b for ids in option['basis'].values() for b in ids}]))
    return result


def resolve_responses(resolver, raw):
    """Extraction interprets answers; Runtime validates source identity/order/access."""
    state = resolver.state
    admitted = getattr(resolver, 'remote_semantic_sources', {})
    for index, row in enumerate(raw.records['group_request_changes']):
        try:
            claim = GroupRequestChange.model_validate(row)
            event = state['remote_events'][claim.source_event_id]
            group = state['conversations'].get(event['conversation_id'])
            if (admitted and claim.source_event_id not in admitted
                    or not group or not group['group'] or event['channel'] != 'TEXT_MESSAGE'
                    or event['sender_id'] == state['camera']['controlled_actor_id']
                    or claim.target_id != state['camera']['controlled_actor_id']
                    or claim.target_id not in event['recipient_ids']
                    or claim.evidence not in event['content'] or claim.expires_at <= event['world_time']):
                raise ValueError('group_request_source')
            if not event.get('response_request'):
                # Concurrent accepted questions retain separate source identities;
                # a later annotation never overwrites an outstanding request.
                previous = deepcopy(event)
                event['response_request'] = ResponseRequest(target_id=claim.target_id, expires_at=claim.expires_at,
                    evidence=claim.evidence, provenance='remote_extraction:' + event['id']).model_dump()
                resolver.history.state_changes.append(dict(kind='group_request', entity=event['id'],
                    before=previous, after=deepcopy(event), source_event_id=event['id']))
        except (ValueError, KeyError, TypeError):
            resolver.warn('group_request_changes', index, 'Запрос не подтверждён источником.', code='group_request_source')
    for index, row in enumerate(raw.records['group_response_changes']):
        try:
            claim = GroupResponseChange.model_validate(row)
            request = state['remote_events'][claim.request_event_id]
            response = state['remote_events'][claim.response_event_id]
            annotation = request.get('response_request')
            if (admitted and not {claim.request_event_id, claim.response_event_id} <= admitted.keys()
                    or not annotation or annotation.get('closed_reason') or annotation['resolved_by'] not in (None, response['id'])
                    or response['sender_id'] != annotation['target_id']
                    or not response['provenance'].startswith('player_action:')
                    or response['conversation_id'] != request['conversation_id']
                    or response['ordinal'] <= request['ordinal']
                    or annotation['target_id'] not in request['read_by']
                    or claim.evidence not in response['content']):
                raise ValueError('group_response_source')
            if annotation['resolved_by'] is None:
                previous = deepcopy(request)
                annotation['resolved_by'] = response['id']
                resolver.history.state_changes.append(dict(kind='group_response', entity=request['id'],
                    before=previous, after=deepcopy(request), source_event_id=response['id'],
                    assertion=claim.assertion, evidence=claim.evidence))
        except (ValueError, KeyError, TypeError):
            resolver.warn('group_response_changes', index, 'Ответ не подтверждён источником.', code='group_response_source')


def accept_series(snapshot, series, annotations, options, operation_id, *, source_id=None):
    """Sequential Remote commands, with eligibility/pause checks after every event."""
    from backend.runtime_v3.remote import apply, members
    from backend.runtime_v3.models import WorldHistoryV3, identity
    from backend.runtime_v3.remote_initiative import accept
    offered = next((o for o in options if o['conversation_id'] == series.conversation_id), None)
    permitted = (reaction_option(snapshot['world_state'], source_id) if source_id else
        next((o for o in opportunities(snapshot['world_state'], offered.get('event_cues', ()) if offered else ()) if o['conversation_id'] == series.conversation_id), None))
    if not offered or not permitted:
        raise ValueError('group_series_stale')
    requests = {r.message_index:r for r in annotations.requests}
    if len(requests) != len(annotations.requests) or any(i >= len(series.messages) for i in requests):
        raise ValueError('group_request_index')
    result = deepcopy(snapshot)
    batch = WorldHistoryV3().to_dict()
    accepted_ids = []
    for index, item in enumerate(series.messages):
        state = result['world_state']
        group = state['conversations'][series.conversation_id]
        if pending(state, group['id']):
            break
        if item.actor_id not in permitted['actor_ids'] or item.actor_id not in members(group) or not available(state, item.actor_id):
            raise ValueError('group_sender_stale')
        # Continuation is grounded in the accepted earlier message, not a
        # fabricated intention. A speaker must choose to read it first.
        allowed = permitted['basis'].get(item.actor_id, [])
        if source_id and item.actor_id not in state['remote_events'][source_id]['read_by']:
            result, delta = apply(result, dict(action='read', operation_id=f'{operation_id}:source:{index}',
                event_id=source_id), actor_id=item.actor_id, autonomous=True)
            for section, rows in delta.items(): batch[section].extend(rows)
        if index and not item.read_previous:
            raise ValueError('group_continuation_requires_read')
        if index and item.read_previous:
            for eid in accepted_ids:
                e = state['remote_events'][eid]
                if e['sender_id'] == item.actor_id:
                    continue
                result, delta = apply(result, dict(action='read', operation_id=f'{operation_id}:r{index}:{e["ordinal"]}', event_id=eid),
                                      actor_id=item.actor_id, autonomous=True)
                for section, rows in delta.items(): batch[section].extend(rows)
            # Planner references the listed initiating basis; Runtime binds the
            # actual perceived earlier event in the acceptance provenance.
            allowed = list({b for ids in permitted['basis'].values() for b in ids})
        if not set(item.basis_ids) <= set(allowed):
            raise ValueError('group_basis')
        option = dict(actor_id=item.actor_id, actions=['send'], basis_ids=allowed,
                      paths=[dict(conversation_id=group['id'])])
        proposal = dict(actor_id=item.actor_id, action='send', conversation_id=group['id'],
                        content=item.content, basis_ids=item.basis_ids, knowledge_ids=item.knowledge_ids)
        request = requests.get(index)
        annotation = None
        if request:
            actor = state['camera']['controlled_actor_id']
            if (request.target_id != actor or actor not in members(group) or actor == item.actor_id
                    or request.evidence not in item.content or request.expires_at <= state['meta']['world_time']):
                raise ValueError('group_request_source')
            annotation = dict(target_id=actor, evidence=request.evidence, expires_at=request.expires_at,
                              provenance=f'group_semantics:{operation_id}:{index}', resolved_by=None)
        result, delta = accept(result, proposal, [option], f'{operation_id}:g{index}', response_request=annotation)
        for section, rows in delta.items(): batch[section].extend(rows)
        accepted_ids.append(identity('remote', item.actor_id, f'{operation_id}:g{index}'))
    return result, batch


def reaction_option(state, source_id):
    from backend.runtime_v3.remote import members
    source = state['remote_events'][source_id]
    group = state['conversations'][source['conversation_id']]
    actors = sorted(a for a in members(group) if available(state, a) and a in source['delivered_to'])
    return dict(conversation_id=group['id'], actor_ids=actors, basis={a:[source_id] for a in actors})


def same_reaction_context(recorded, current):
    if recorded[1:] == current[1:]:
        return True
    # Exact pre-channel-context checkpoint only: preserve already accepted work
    # on Retry, while still requiring identical source, history and Knowledge.
    data = json.loads(current[1]['content'])
    data['source_message'].pop('channel')
    for group in data['groups']:
        group.pop('channel')
        group.pop('communication_profile')
        for actor in group['actors']:
            for field in ('personality', 'legacy_voice', 'personal_context'):
                actor.pop(field)
    legacy = [dict(current[0], content=current[0]['content'].replace(GROUP_TEXT_CONTEXT, '', 1)),
              dict(current[1], content=json.dumps(data, ensure_ascii=False))]
    return recorded == legacy


def reaction_context(snapshot, source_id):
    state = snapshot['world_state']
    option = reaction_option(state, source_id)
    source = state['remote_events'][source_id]
    return [dict(role='system', content=(
        'Group communication reaction/1. Author an optional natural conversation in response to the supplied '
        'player message, using the existing communication job. Return one valid JSON object matching the schema. '
        'Return {"messages":[]} for silence. '
        'Several NPCs may answer the player AND each other, including returning speakers. '
        'Do not author the player, invent agreement or move anyone physically. Each selected speaker '
        'chooses to read the delivered source message before speaking; subsequent speakers must set '
        'read_previous=true to read preceding accepted replies. Use the source ID as basis_ids. '
        'Preserve per-speaker Knowledge. Rumours are not canonical facts. End at an explicit request '
        'for a voluntary player decision; do not invent its answer. No mandatory reply. '
        + GROUP_TEXT_CONTEXT + 'Schema: '
        + json.dumps(GroupReaction.model_json_schema(), ensure_ascii=False))),
        dict(role='user', content=json.dumps(dict(groups=context(snapshot, [option]),
            source_message={k:source[k] for k in ('id','sender_id','channel','content','world_time')},
            controlled_actor_id=state['camera']['controlled_actor_id']), ensure_ascii=False))]


def record_attempt(snapshot, group_id, operation_id, batch, *, event_ids=None):
    group = snapshot['world_state']['conversations'][group_id]
    before = deepcopy(group)
    state = snapshot['world_state']
    group['initiative_pacing'] = dict(world_time=state['meta']['world_time'], turn_id=state['meta']['turn_id'], operation_id=operation_id, stimulus=stimulus(state, group),
        event_ids=list(event_ids) if event_ids is not None else (before.get('initiative_pacing') or {}).get('event_ids', []))
    batch.setdefault('state_changes', []).append(dict(kind='group_initiative_attempt', entity=group_id,
        before=before, after=deepcopy(group), operation_id=operation_id))


def close_invalid_requests(state, batch):
    """A departure/death permanently ends the request, without supplying an answer."""
    from backend.runtime_v3.remote import members
    for event in state['remote_events'].values():
        request = event.get('response_request')
        if not request or request['resolved_by'] or request.get('closed_reason'):
            continue
        people = {event['sender_id'], request['target_id']}
        group = state['conversations'][event['conversation_id']]
        reason = 'death' if any(state['characters'][a]['life_status'] == 'dead' for a in people) else (
            'membership' if not people <= members(group) else None)
        if reason:
            previous = deepcopy(event)
            request['closed_reason'] = reason
            batch.state_changes.append(dict(kind='group_request_closed', entity=event['id'],
                before=previous, after=deepcopy(event), reason=reason, minute=state['meta']['world_time']))
