"""Extraction -> existing Remote commands inside the Resolver's atomic patch.

Only the LLM interprets prose. This adapter checks IDs, routing, time and agency;
it has no provider, persistence, clock advancement or independent phone state.
"""
from pydantic import ValidationError

from backend.runtime_v3.models import WorldHistoryV3, fatal, identity
from backend.services.world_delta_errors import StructuralDeltaError
from backend.runtime_v3.remote import apply, advance, members, resolve_identity
from backend.runtime_v3.remote_models import ExtractedRemoteEvent, HISTORICAL_CHANNELS


def apply_extracted_remote(resolver, raw, events):
    records = raw.records.get('remote_events', [])
    batch_history = WorldHistoryV3()
    if not records and resolver.letter_sources:
        fatal("Authored letter has no accepted send.", "letter_source_unbound", repairable=True)
    if not records:
        return batch_history
    state = resolver.state
    start = resolver.before['meta']['world_time']
    finish = state['meta']['world_time']
    previous_minute = start
    seen = set()
    used_artifacts = set()
    endings = []

    def reject(index, message, field='', code='remote_extraction_invalid'):
        fatal(message, code, repairable=True, section='remote_events', index=index,
              path=f'remote_events[{index}]' + ('.' + field if field else ''),
              severity='recoverable', action='extraction_repair')

    def command(cmd, actor, claim=None, ordinal=None):
        snapshot, batch = apply({'world_state': state}, cmd, actor_id=actor, autonomous=True)
        state.clear()
        state.update(snapshot['world_state'])
        for section, values in batch.items():
            for value in values:
                value.update(extraction_section='remote_events', source_ordinal=index if ordinal is None else ordinal,
                             narrative_evidence=(row if claim is None else claim).evidence)
            getattr(batch_history, section).extend(values)

    def settle_endings(deadline):
        for ending in sorted(list(endings), key=lambda e: (e[0], e[1])):
            minute, ordinal, claim, eid, operation = ending
            if minute > deadline: continue
            state['meta']['world_time'] = minute
            try:
                if claim.status == 'ended':
                    command(dict(action='end', event_id=eid, operation_id=identity('narrative_end', operation)),
                            claim.sender_id, claim, ordinal)
                else:
                    advance(state, batch_history)
                    if state['remote_events'][eid]['status'] != 'missed':
                        reject(ordinal, 'Для missed ещё не истёк канонический таймаут.', 'status')
            except StructuralDeltaError:
                raise
            except ValueError as exc:
                reject(ordinal, str(exc))
            finally:
                state['meta']['world_time'] = finish
            endings.remove(ending)

    for index, item in enumerate(records):
        try:
            row = ExtractedRemoteEvent.model_validate(item)
        except ValidationError as exc:
            reject(index, 'Повреждено событие связи.', '.'.join(map(str, exc.errors()[0]['loc'])))
        actor, recipients = row.sender_id, set(row.recipient_ids)
        if row.channel in HISTORICAL_CHANNELS and not row.existing_event_id:
            artifact = resolver.letter_sources.get(row.artifact_id)
            if (not artifact or row.artifact_id in used_artifacts or row.content
                    or 'sender_id' in artifact and artifact['sender_id'] != actor
                    or 'recipient_id' in artifact and [artifact['recipient_id']] != row.recipient_ids
                    or 'channel' in artifact and artifact['channel'] != row.channel or row.status is not None or row.ended_at is not None):
                reject(index, 'Нет соответствующего авторского артефакта письма.', 'artifact_id', 'letter_source_missing')
            used_artifacts.add(row.artifact_id)
            row.content = artifact['content']
        elif row.artifact_id:
            reject(index, 'Артефакт допустим только для нового письма.', 'artifact_id')
        if row.reader_id and (not row.existing_event_id or row.channel not in HISTORICAL_CHANNELS):
            reject(index, 'Чтение требует существующего письма.', 'reader_id')
        if actor not in state['characters'] or recipients - state['characters'].keys():
            reject(index, 'Неизвестный участник связи.', 'sender_id')
        if actor in recipients or len(recipients) != len(row.recipient_ids):
            reject(index, 'Повторный получатель или отправитель среди получателей.', 'recipient_ids')
        if row.source_event_id and row.source_event_id not in events:
            resolver.warn('remote_events', index, 'Необязательная ссылка Event недоступна; provenance сохранён по ходу.',
                          field='source_event_id', code='remote_optional_source_invalid')
            row.source_event_id = None
        # A continuing/staged interaction references its canonical identity. Never
        # turn its depiction into another send, read, answer or lifecycle action.
        if row.existing_event_id:
            if row.reader_id:
                advance(state, batch_history)
            event = state['remote_events'].get(row.existing_event_id)
            if (not event or event['sender_id'] != actor or set(event['recipient_ids']) != recipients
                    or event['channel'] != row.channel or row.content and event['content'] != row.content
                    or row.status and event['status'] != row.status
                    or row.minute is not None and event['world_time'] != row.minute):
                reject(index, 'Ссылка противоречит принятому событию связи.', 'existing_event_id')
            if row.reader_id:
                if row.reader_id == resolver.protected_actor_id or row.reader_id not in recipients:
                    reject(index, 'Недопустимое автономное чтение.', 'reader_id', 'remote_extraction_agency')
                try:
                    command(dict(action='read', event_id=event['id'], operation_id=identity('letter_read', event['id'], row.reader_id)), row.reader_id)
                except ValueError:
                    reject(index, 'Письмо ещё недоступно для чтения.', 'reader_id')
                event = state['remote_events'][row.existing_event_id]
        else:
            if actor == resolver.protected_actor_id:
                reject(index, 'Extraction не отправляет сообщения и не звонит за игрока.', 'sender_id', 'remote_extraction_agency')
            minute = finish if row.minute is None else row.minute
            if not previous_minute <= minute <= finish:
                reject(index, 'Время связи вне хода или нарушает порядок событий.', 'minute')
            previous_minute = minute
            if row.minute is None:
                resolver.warn('remote_events', index, 'Точное время не установлено; использована граница хода.', code='remote_time_unspecified')
            if row.channel == 'TEXT_MESSAGE' and (not row.content.strip() or row.status not in (None, 'delivered') or row.ended_at is not None):
                reject(index, 'Нужны извлечённый текст и допустимый статус сообщения.', 'content')
            if row.channel == 'VOICE_CALL' and (row.content or row.status not in (None, 'ringing', 'missed', 'ended')):
                reject(index, 'Некорректный payload звонка.', 'status')
            if row.ended_at is not None and (row.channel != 'VOICE_CALL' or row.status not in ('ended', 'missed') or not minute <= row.ended_at <= finish):
                reject(index, 'Некорректное время завершения звонка.', 'ended_at')
            operation = identity('narrative_remote', resolver.turn_id, resolver.mode, resolver.event_namespace, index)
            eid = identity('remote', actor, operation)
            if eid in state['remote_events'] or eid in seen:
                reject(index, 'Повторное событие должно ссылаться на existing_event_id.', 'existing_event_id')
            seen.add(eid)
            settle_endings(minute)
            state['meta']['world_time'] = minute
            try:
                advance(state, batch_history)
                contact_id, conversation_id = row.contact_id, row.conversation_id
                if row.established_contact:
                    if contact_id or conversation_id or len(recipients) != 1:
                        reject(index, 'Новый адрес требует одного получателя и не заменяет существующий канал.', 'established_contact')
                    existing = next((c for c in state['contacts'].values()
                        if c['owner_id'] == actor and c['address'] == row.established_contact.address), None)
                    if existing and existing['character_id'] != row.recipient_ids[0]:
                        reject(index, 'Адрес уже связан с другой или неизвестной личностью.', 'established_contact')
                    if existing:
                        contact_id = existing['id']
                    else:
                        contact_op = identity('narrative_contact', operation)
                        command(dict(action='add_contact', operation_id=contact_op,
                                     **row.established_contact.model_dump()), actor)
                        contact_id = identity('contact', actor, contact_op)
                        linked = resolve_identity({'world_state': state}, contact_id,
                            address=row.established_contact.address, character_id=row.recipient_ids[0],
                            evidence='narrative_extraction:' + operation)
                        state.clear()
                        state.update(linked['world_state'])
                        # The contact creation and identity use the same accepted
                        # source, so History stores the completed canonical row.
                        batch_history.state_changes[-1]['after'] = dict(state['contacts'][contact_id])
                if contact_id and conversation_id:
                    reject(index, 'Укажи один адресный маршрут.', 'contact_id')
                if row.channel in HISTORICAL_CHANNELS and (contact_id or conversation_id or row.established_contact):
                    reject(index, 'Письмо адресуется каноническому персонажу.', 'recipient_ids')
                if row.channel not in HISTORICAL_CHANNELS and not contact_id and not conversation_id:
                    # Canonical IDs only; no name matching, invented reverse
                    # address or mass contact creation. Prefer a direct thread.
                    conversation_id = next((c['id'] for c in state['conversations'].values()
                        if not c['group'] and members(c) == {actor, *recipients}), None)
                    if not conversation_id and len(recipients) == 1:
                        contact_id = next((c['id'] for c in state['contacts'].values()
                            if c['owner_id'] == actor and c['character_id'] in recipients
                            and c['available'] and not c['blocked']), None)
                command(dict(action='call' if row.channel == 'VOICE_CALL' else 'send',
                    channel=row.channel if row.channel != 'VOICE_CALL' else 'TEXT_MESSAGE',
                    operation_id=operation, contact_id=contact_id,
                    conversation_id=conversation_id, content=row.content,
                    character_id=row.recipient_ids[0] if not contact_id and not conversation_id and len(recipients) == 1 else None), actor)
                event = state['remote_events'][eid]
                if set(event['recipient_ids']) != recipients:
                    reject(index, 'Получатели не совпадают с каноническим адресатом/составом беседы.', 'recipient_ids')
                if row.channel == 'VOICE_CALL' and row.status in ('ended', 'missed'):
                    endings.append((row.ended_at if row.ended_at is not None else finish, index, row, eid, operation))
                event = state['remote_events'][eid]
            except StructuralDeltaError:
                raise
            except ValueError as exc:
                reject(index, str(exc))
            finally:
                state['meta']['world_time'] = finish
        # A literary delivery is not perception. Source-bound message facts
        # cannot grant the recipient Knowledge before Remote's explicit read.
        sources = [events[row.source_event_id]] if row.source_event_id else [e for e in events.values()
            if e['medium'] == 'message' and actor in e['participants'] and recipients & set(e['participants'])]
        for source in sources:
            if event['channel'] != 'VOICE_CALL' and source['medium'] == 'message':
                unread = set(event['recipient_ids']) - set(event['read_by'])
                if any(k.get('source_event_id') == source['local_id'] and k.get('actor_id') in unread
                       for k in raw.records['knowledge_gained'] if isinstance(k, dict)):
                    reject(index, 'Доставка не даёт Knowledge до чтения.', 'source_event_id', 'remote_unread_knowledge')
                source['witnesses'] = [a for a in source['witnesses'] if a not in unread]
                for fid in source['fact_ids']:
                    if state['facts'][fid]['visibility'] != 'secret':
                        reject(index, 'Содержание сообщения не является общедоступным фактом.', 'source_event_id', 'remote_private_fact')

    if used_artifacts != resolver.letter_sources.keys():
        fatal('Authored letter has no accepted send.', 'letter_source_unbound', repairable=True)
    settle_endings(finish)
    return batch_history
