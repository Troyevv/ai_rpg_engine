"""Evidence-bound transitions of existing scheduled_events, not another runtime.

Extraction classifies semantics; Python verifies sources, identity, references,
agency and transitions. No prose parsing, clock-triggered completion or penalties.
"""
from copy import deepcopy
from backend.runtime_v3.models import ScheduledEvent
from backend.runtime_v3.calendar import scheduled_window

ASSERTIONS = ('agreed', 'rescheduled', 'cancelled', 'occurred', 'missed', 'blocked', 'started', 'ended')
EDITABLE = ('id', 'description', 'character_ids', 'temporal', 'end_temporal',
            'due_minute', 'condition', 'type', 'location_id', 'interrupts', 'depends_on')


def invalid_dependencies(events, candidates=None):
    """Small explicit prerequisite graph; no scheduling/workflow inference."""
    invalid = set()
    for eid in events if candidates is None else candidates:
        seen, stack = set(), list(events[eid].get('depends_on', []))
        while stack:
            parent = stack.pop()
            if parent == eid or parent not in events:
                invalid.add(eid); break
            if parent not in seen:
                seen.add(parent); stack.extend(events[parent].get('depends_on', []))
    return invalid


def apply_commitments(resolver, raw):
    state = resolver.state
    events = state['scheduled_events']
    accepted = {}
    for index, item in resolver.records(raw, 'scheduled_event_changes'):
        eid, assertion = item.get('id'), item.get('assertion')
        def reject(reason, code='commitment_invalid'):
            resolver.warn('scheduled_event_changes', index, reason, entity=eid, code=code)
        if not isinstance(eid, str) or not eid.strip() or assertion not in ASSERTIONS:
            reject('Нужны canonical ID и подтверждённая семантика изменения.'); continue
        old = events.get(eid)
        if old and old['status'] != 'pending':
            reject('Завершённый план нельзя повторно активировать.', 'commitment_terminal'); continue
        if old is None and assertion not in ('agreed', 'started'):
            reject('Изменение ссылается на неизвестный план.'); continue
        if old and assertion == 'agreed':
            # A repeat is not a reschedule and must never move a relative anchor.
            repeated = resolver.typed(ScheduledEvent, {**old, **{k:item[k] for k in EDITABLE if k in item}}, 'scheduled_event_changes', index)
            if repeated is None: continue
            if any(repeated[k] != old.get(k) for k in EDITABLE if k != 'id'):
                reject('Для изменения существующего плана нужен rescheduled.'); continue
            continue
        if (old is None or assertion == 'rescheduled') and not item.get('temporal'):
            reject('Новому плану/переносу нужна структурная temporal привязка, не LLM minute.'); continue
        fields = deepcopy(old or {})
        fields.update({k:item[k] for k in EDITABLE if k in item})
        fields.update(commitment=True, evidence=item['evidence'], source_turn=resolver.turn_id)
        if old is None or assertion == 'rescheduled':
            fields['time_reference_minute'] = resolver.before['meta']['world_time']
            fields['last_attempt_minute'] = None
            if 'temporal' in item: fields['due_minute'] = None
        status = {'occurred':'resolved', 'ended':'resolved', 'cancelled':'cancelled', 'missed':'cancelled'}.get(assertion, 'pending')
        if 'status' in item and item['status'] != status:
            reject('Статус противоречит подтверждённому исходу.'); continue
        fields['status'] = status
        fields['outcome'] = {'occurred':'fulfilled', 'ended':'fulfilled', 'cancelled':'cancelled',
                             'missed':'missed', 'blocked':'blocked'}.get(assertion, '')
        entry = resolver.typed(ScheduledEvent, fields, 'scheduled_event_changes', index)
        if entry is None: continue
        if not entry['character_ids'] or len(set(entry['character_ids'])) != len(entry['character_ids']):
            reject('Нужны уникальные участники.'); continue
        if resolver.mode == 'background' and resolver.protected_actor_id in entry['character_ids'] + (old or {}).get('character_ids', []):
            reject('Фоновая симуляция не меняет план protected actor.', 'background_commitment_protected'); continue
        for cid in entry['character_ids']: resolver.actor(cid, 'scheduled_event_changes', index)
        if entry['location_id'] is not None and entry['location_id'] not in state['locations']:
            reject('Неизвестное место плана.'); continue
        if old and assertion not in ('rescheduled', 'agreed'):
            if any(entry[k] != old.get(k) for k in EDITABLE if k != 'id'):
                reject('Изменение исхода не переписывает идентичность и сроки плана.'); continue
        controlled = resolver.before['camera']['controlled_actor_id']
        npc_cancellation = assertion == 'cancelled' and item.get('decision_actor_id') in entry['character_ids'] and item.get('decision_actor_id') != controlled
        if controlled in set(entry['character_ids'] + (old or {}).get('character_ids', [])) and assertion in ('agreed', 'rescheduled', 'cancelled') and not npc_cancellation:
            proof = item.get('player_evidence')
            from backend.runtime_v3.resolver import normalized
            if (item.get('player_assertion') != 'explicit_choice' or not isinstance(proof, str)
                or not normalized(proof) or normalized(proof) not in normalized(resolver.player_input)):
                reject('Решение controlled actor требует явного player_input.', 'controlled_actor_unsupported'); continue
        window = scheduled_window(state, entry)
        if (old is None or assertion == 'rescheduled') and (window['start_minute'] is None or window['start_minute'] < 0):
            reject('Нужна разрешимая календарная привязка.'); continue
        if entry['end_temporal'] and (window['end_minute'] is None or window['start_minute'] is None or window['end_minute'] < window['start_minute']):
            reject('Конец интервала должен быть не раньше начала.'); continue
        if old is None and assertion == 'agreed' and window['end_minute'] < resolver.before['meta']['world_time']:
            reject('Прошедшее обсуждение не создаёт будущий план.'); continue
        if assertion in ('started', 'ended'):
            if not entry['end_temporal'] or (assertion == 'ended' and (not old or old['started_minute'] is None)):
                reject('Начало/конец требуют личного интервала и допустимого перехода.'); continue
            if assertion == 'started':
                if window['start_minute'] > state['meta']['world_time']:
                    reject('Будущий интервал ещё не начался.'); continue
                if old and old['started_minute'] is not None:
                    reject('Интервал уже начат.'); continue
                entry['started_minute'] = state['meta']['world_time']
        if entry['end_temporal'] and assertion == 'occurred':
            reject('Для интервала используй started/ended.'); continue
        if old is None:
            # Exact identity guard, not fuzzy language interpretation. A distinct
            # repeated appointment needs its own temporal anchor and fresh proof.
            duplicate = next((e for e in events.values() if
                e['description'].strip().casefold() == entry['description'].strip().casefold()
                and set(e['character_ids']) == set(entry['character_ids'])
                and scheduled_window(state, e)['start_minute'] == window['start_minute']), None)
            if duplicate:
                reject('Повтор существующего плана: используй его canonical ID.', 'commitment_duplicate'); continue
        events[eid] = entry
        accepted[eid] = (index, old)

    # Resolve references after the batch so departure/return can be created together.
    # Reject invalid optional records locally, including references to rejected ones.
    while True:
        invalid = invalid_dependencies(events, accepted)
        if not invalid: break
        for eid in sorted(invalid):
            index, old = accepted.pop(eid)
            if old is None: events.pop(eid)
            else: events[eid] = old
            resolver.warn('scheduled_event_changes', index, 'Неизвестная или циклическая зависимость.',
                          entity=eid, code='commitment_dependency_invalid')
    # Cancellation invalidates only explicit dependencies, never merely related plans.
    changed = True
    while changed:
        changed = False
        for event in events.values():
            if event['status'] != 'pending': continue
            parent = next((events[p] for p in event.get('depends_on', []) if p in events and events[p]['status'] == 'cancelled'), None)
            if parent:
                event.update(status='cancelled', outcome='dependency_cancelled',
                             evidence=parent['evidence'], source_turn=resolver.turn_id)
                changed = True
