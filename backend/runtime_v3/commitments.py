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


def commitment_ready(state, event):
    """Read-only readiness shared by temporal consumers (QA-01/QA-03).

    Pending is not fulfilled. Legacy resolved prerequisites with no outcome
    remain compatible; failed/blocked outcomes never unlock a dependent plan.
    This does not move dates, resolve events or infer transitive outcomes.
    """
    return event['status'] == 'pending' and all(
        state['scheduled_events'].get(key, {}).get('status') == 'resolved'
        and state['scheduled_events'][key].get('outcome')
        not in ('cancelled', 'dependency_cancelled', 'missed', 'blocked')
        for key in event.get('depends_on', [])
    )


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
        def reject(reason, code='commitment_invalid', **details):
            from backend.runtime_v3.models import fatal
            fatal(reason, code, repairable=True, section='scheduled_event_changes', index=index, entity=eid, **details)
        if not isinstance(eid, str) or not eid.strip() or assertion not in ASSERTIONS:
            reject('Нужны canonical ID и подтверждённая семантика изменения.'); continue
        old = events.get(eid)
        from backend.runtime_v3.remote import commitment_sources
        sources=commitment_sources(resolver.before,item, delivered=bool(getattr(resolver, 'remote_semantic_sources', None))) if item.get('remote_source_ids') else []
        voice=[]
        if resolver.before['meta'].get('interaction_focus')=='call' and not sources:
            from backend.runtime_v3.call_continuity import commitment_sources as voice_sources
            voice=voice_sources(resolver,item)
            if assertion in ('agreed','rescheduled','cancelled') and not voice:
                reject('Голосовая договорённость требует подтверждённых proposal/assent источников.', 'commitment_call_evidence'); continue
        admitted=getattr(resolver, 'remote_semantic_sources', {})
        if admitted and sources and any(e['id'] not in admitted for e in sources):
            reject('Источник не входит в принятый semantic context.', 'commitment_remote_source'); continue
        if item.get('remote_source_ids') and not sources:
            reject('Сообщения не прочитаны участниками договорённости.', 'commitment_remote_unperceived'); continue
        if sources and getattr(resolver,'remote_semantic_sources',None) and assertion=='agreed' and not set(item.get('character_ids',[])) <= {e['sender_id'] for e in sources}:
            reject('Каждому участнику нужна собственная подтверждающая реплика.', 'commitment_missing_assent'); continue
        if sources and old and assertion=='rescheduled' and admitted:
            fresh={e['sender_id'] for e in sources if e['id'] not in old.get('remote_source_ids',[])}
            if not set(item.get('character_ids',old['character_ids'])) <= fresh:
                reject('Переносу нужно новое согласие участников.', 'commitment_missing_assent'); continue
        if sources and old and assertion!='agreed' and set(item['remote_source_ids'])<=set(old.get('remote_source_ids',[])):
            reject('Старое сообщение не является новым решением.', 'commitment_remote_replay'); continue
        if voice and old and assertion!='agreed' and item.get('call_evidence')==old.get('call_evidence'):
            reject('Нужны новые доказательства изменения плана.', 'commitment_remote_replay'); continue
        if old and old['status'] != 'pending':
            reject('Завершённый план нельзя повторно активировать.', 'commitment_terminal'); continue
        if old is None and assertion not in ('agreed', 'started'):
            reject('Изменение ссылается на неизвестный план.'); continue
        if old and assertion == 'agreed':
            # A repeat is not a reschedule and must never move a relative anchor.
            repeated = resolver.typed(ScheduledEvent, {**old, **{k:item[k] for k in EDITABLE if k in item}}, 'scheduled_event_changes', index)
            if repeated is None: reject('Повреждены поля повторного плана.')
            if any(repeated[k] != old.get(k) for k in EDITABLE if k != 'id'):
                reject('Для изменения существующего плана нужен rescheduled.'); continue
            continue
        if (old is None or assertion == 'rescheduled') and not item.get('temporal'):
            reject('Новому плану/переносу нужна структурная temporal привязка, не LLM minute.'); continue
        fields = deepcopy(old or {})
        fields.update({k:item[k] for k in EDITABLE if k in item})
        fields.update(commitment=True, evidence=item['evidence'], source_turn=resolver.turn_id)
        if sources: fields['remote_source_ids']=item['remote_source_ids']
        elif resolver.before['meta'].get('interaction_focus')=='call':
            from backend.runtime_v3.remote import active_call
            call=active_call(resolver.before,resolver.before['camera']['controlled_actor_id'])
            if call and call['status']=='answered':
                from backend.runtime_v3.remote import participants
                if assertion=='agreed' and not set(fields.get('character_ids',[])) <= participants(call):
                    reject('Участник не присутствовал в разговоре.', 'commitment_missing_assent'); continue
                fields['remote_call_id']=call['id']
                fields['call_evidence']=item.get('call_evidence',[])
                fields['call_time_source_id']=item.get('call_time_source_id',fields.get('call_time_source_id'))
        if old is None or assertion == 'rescheduled':
            fields['time_reference_minute'] = resolver.before['meta']['world_time']
            if sources:
                anchor=next((e for e in sources if e['id']==item.get('remote_time_source_id')),None)
                if anchor is None:
                    reject('Относительное время сообщения требует его canonical ID.', 'commitment_remote_time'); continue
                fields['time_reference_minute']=anchor['world_time']
            if voice:
                anchor=next((e for e in voice if e['id']==item.get('call_time_source_id') and e['assertion']=='proposal'),None)
                if anchor is None:
                    reject('Голосовое время требует исходное предложение.', 'commitment_call_time'); continue
                fields['time_reference_minute']=anchor['world_time']
            fields['last_attempt_minute'] = None
            if 'temporal' in item: fields['due_minute'] = None
        status = {'occurred':'resolved', 'ended':'resolved', 'cancelled':'cancelled', 'missed':'cancelled'}.get(assertion, 'pending')
        if 'status' in item and item['status'] != status:
            reject('Статус противоречит подтверждённому исходу.'); continue
        fields['status'] = status
        fields['outcome'] = {'occurred':'fulfilled', 'ended':'fulfilled', 'cancelled':'cancelled',
                             'missed':'missed', 'blocked':'blocked'}.get(assertion, '')
        entry = resolver.typed(ScheduledEvent, fields, 'scheduled_event_changes', index)
        if entry is None: reject('Повреждены поля договорённости.')
        if not entry['character_ids'] or len(set(entry['character_ids'])) != len(entry['character_ids']):
            reject('Нужны уникальные участники.'); continue
        if resolver.mode == 'background' and resolver.protected_actor_id in entry['character_ids'] + (old or {}).get('character_ids', []):
            reject('Фоновая симуляция не меняет план protected actor.', 'background_commitment_protected'); continue
        for cid in entry['character_ids']: resolver.actor(cid, 'scheduled_event_changes', index)
        if any(state['characters'][cid].get('life_status') == 'dead' for cid in entry['character_ids']):
            reject('Участник умер; план не может стать выполненным или активным.'); continue
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
            # Remote decisions must be grounded in THIS record's admitted sources,
            # never an unrelated older message in the concatenated thread.
            authored=[e for e in (voice or sources) if e['sender_id']==controlled]
            source_id=item.get('player_source_id')
            if source_id is None and admitted and sources:
                exact=[e for e in authored if e['content']==proof]
                if len(exact)==1:
                    source_id=exact[0]['id']
                    item['player_source_id']=source_id
            player_sources=[e['content'] for e in authored] if sources or voice else [resolver.player_input]
            failure = ('player_assertion' if item.get('player_assertion') != 'explicit_choice' else
                       'player_source_id' if (voice and source_id is None) or (source_id is not None and not any(e['id']==source_id for e in authored)) else
                       'player_evidence' if (admitted and sources and source_id is None) or not isinstance(proof,str) or not normalized(proof) or not any(normalized(proof) in normalized(text) for text in player_sources) else None)
            if source_id is not None and failure is None:
                source=next(e for e in authored if e['id']==source_id)
                if proof != source['content']: failure='player_evidence'
            if failure:
                reject('Решение controlled actor требует явного источника: '+failure, 'controlled_actor_unsupported', evidence_field=failure)
                continue
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
            if not duplicate and sources:
                duplicate=next((e for e in events.values() if set(e.get('remote_source_ids',[]))==set(item['remote_source_ids']) and set(e['character_ids'])==set(entry['character_ids']) and scheduled_window(state,e)['start_minute']==window['start_minute']),None)
            if duplicate:
                reject('Повтор существующего плана: используй его canonical ID.', 'commitment_duplicate'); continue
        events[eid] = entry
        accepted[eid] = (index, old)

    # Resolve references after the batch so departure/return can be created together.
    invalid = invalid_dependencies(events, accepted)
    if invalid:
        from backend.runtime_v3.models import fatal
        fatal('Неизвестная или циклическая зависимость договорённости.',
              'commitment_dependency_invalid', repairable=True,
              section='scheduled_event_changes', source_ids=sorted(invalid))
    from backend.runtime_v3.life import _transition
    for eid, (index, old) in accepted.items():
        item = raw.records['scheduled_event_changes'][index]
        _transition(resolver,'scheduled_events',eid,old,events[eid],item)
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


def invalidate_dead_commitments(resolver, dead_ids):
    """Commitment owner marks impossible participation, never successful completion."""
    for event in resolver.state['scheduled_events'].values():
        if event['status'] == 'pending' and dead_ids.intersection(event['character_ids']):
            event.update(status='cancelled',outcome='cancelled',evidence='canonical:participant_dead',source_turn=resolver.turn_id)
