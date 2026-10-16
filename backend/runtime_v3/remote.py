"""Deterministic remote actions. History audits the same canonical records.

No phone database, inferred contact graph, prose trigger, or background agent.
"""
from copy import deepcopy
from backend.runtime_v3.models import (
    Character, Fact, Knowledge, WorldHistoryV3, identity,
    assert_world_state_v3_invariants,
)
from backend.runtime_v3.remote_models import Contact, Conversation, RemoteEvent, RemoteCommand
from backend.runtime_v3.life import capabilities


OPEN_CALL = {'ringing', 'answered'}


def members(conversation):
    return {m['actor_id'] for m in conversation['members'] if m['left_at'] is None}


def participants(event):
    return {event['sender_id'], *event['recipient_ids']}


def active_call(state, actor):
    return next((e for e in state.get('remote_events', {}).values()
                 if e['channel'] == 'VOICE_CALL' and e['status'] in OPEN_CALL
                 and actor in participants(e)), None)


def validate_state(state):
    actors = state['characters']; now = state['meta']['world_time']
    for key, c in state['contacts'].items():
        if key != c['id'] or c['owner_id'] not in actors or c['character_id'] is not None and c['character_id'] not in actors:
            raise ValueError('Некорректная ссылка контакта.')
        if c['kind'] != 'person' and c['character_id'] is not None:
            raise ValueError('Сервисный адрес не является персонажем.')
    for key, c in state['conversations'].items():
        if key != c['id'] or members(c) - actors.keys(): raise ValueError('Некорректные участники переписки.')
        current = [m['actor_id'] for m in c['members'] if m['left_at'] is None]
        if len(current) != len(set(current)): raise ValueError('Повторный участник группы.')
        for m in c['members']:
            if m['actor_id'] not in actors or m['joined_at'] > now or m['left_at'] is not None and not m['joined_at'] <= m['left_at'] <= now:
                raise ValueError('Некорректный период участия.')
    calls = set()
    for key, e in state['remote_events'].items():
        if key != e['id'] or participants(e) - actors.keys() or not e['world_time'] <= e['updated_at'] <= now:
            raise ValueError('Некорректное событие связи.')
        if not set(e['read_by']) <= set(e['delivered_to']) <= set(e['recipient_ids']):
            raise ValueError('Чтение требует доставки конкретному получателю.')
        if e['channel'] == 'TEXT_MESSAGE' and e['status'] not in {'sent', 'delivered'}:
            raise ValueError('Некорректное состояние сообщения.')
        if e['channel'] == 'VOICE_CALL' and e['status'] in OPEN_CALL:
            if calls & participants(e): raise ValueError('Одновременные звонки не поддерживаются.')
            calls |= participants(e)


def _event_history(batch, state, event, previous=None):
    """A lifecycle transition references its stable interaction identity."""
    eid = identity('remote_transition', event['id'], event['status'], event['read_by'])
    batch.events.append(dict(id=eid, remote_interaction_id=event['id'],
        remote=deepcopy(event), text='', medium='message' if event['channel']=='TEXT_MESSAGE' else 'conversation',
        participants=sorted(participants(event)), witnesses=[], fact_ids=[], evidence=event['provenance'],
        turn_id=state['meta']['turn_id'], minute=state['meta']['world_time'],
        player_observed=False))
    batch.state_changes.append(dict(kind='remote_transition', entity=event['id'], before=deepcopy(previous),
        after=deepcopy(event), source_event_id=eid, minute=state['meta']['world_time'], turn_id=state['meta']['turn_id']))


def _read(state, event, actor, batch):
    if actor not in event['delivered_to']: raise ValueError('Сообщение недоступно этому персонажу.')
    if actor in event['read_by']: return
    previous = deepcopy(event); event['read_by'].append(actor)
    event['updated_at'] = state['meta']['world_time']
    _event_history(batch, state, event, previous)
    # This is testimony about authored text, not proof that its assertions are true.
    fid = identity('communicated_text', event['id'])
    state['facts'][fid] = Fact(id=fid, text='Сообщение: «'+event['content']+'»', visibility='secret',
        character_ids=sorted(participants(event))).model_dump()
    from backend.runtime_v3.knowledge import acquire_communication
    acquire_communication(state, actor, fid, event, batch)


def apply(snapshot, command, *, actor_id=None, autonomous=False):
    """Pure action; the repository commits state + History in one transaction."""
    cmd = RemoteCommand.model_validate(command) if isinstance(command, dict) else command
    result = deepcopy(snapshot); state = assert_world_state_v3_invariants(result['world_state'])
    result['world_state'] = state; batch = WorldHistoryV3()
    actor = actor_id or state['camera']['controlled_actor_id']
    if actor not in state['characters'] or (autonomous and actor == state['camera']['controlled_actor_id']):
        raise ValueError('Недоступное управление персонажем.')
    caps = capabilities(state, actor)
    if not caps['can_act']: raise ValueError('Персонаж сейчас не может пользоваться связью.')
    cfg = state['meta']['communication']; now = state['meta']['world_time']
    if not (cfg['text_message'] or cfg['voice_call']): raise ValueError('Связь недоступна в этом сеттинге.')
    provenance = ('npc_initiative:' if autonomous else 'player_action:') + cmd.operation_id
    cid = cmd.contact_id; contact = state['contacts'].get(cid)
    if cid and (not contact or contact['owner_id'] != actor): raise ValueError('Это не контакт управляемого персонажа.')
    conversation = state['conversations'].get(cmd.conversation_id)
    if cmd.conversation_id and (not conversation or actor not in members(conversation)):
        raise ValueError('Нет доступа к переписке.')
    if cmd.action == 'resolve_contact':
        if autonomous or not contact: raise ValueError('Личность должна быть явно подтверждена.')
        previous=deepcopy(contact)
        result=resolve_identity(result,cid,address=cmd.address,evidence=cmd.evidence,
            character_id=cmd.character_id,name=cmd.label)
        state=result['world_state']
        batch.state_changes.append(dict(kind='contact_identity',entity=cid,before=previous,after=deepcopy(state['contacts'][cid])))
    elif cmd.action in {'add_contact', 'edit_contact'}:
        if cmd.action == 'edit_contact' and not contact: raise ValueError('Контакт не найден.')
        cid = cid or identity('contact', actor, cmd.operation_id)
        before = deepcopy(contact)
        state['contacts'][cid] = Contact(**(dict(contact, label=cmd.label or contact['label'],
            blocked=cmd.blocked) if contact else dict(id=cid, owner_id=actor, label=cmd.label,
                address=cmd.address, kind=cmd.kind, provenance=provenance, created_at=now))).model_dump()
        batch.state_changes.append(dict(kind='contact', entity=cid, before=before, after=deepcopy(state['contacts'][cid])))
    elif cmd.action == 'create_group':
        known = {c['character_id'] for c in state['contacts'].values()
                 if c['owner_id']==actor and not c['blocked'] and c['available'] and c['identity_visible']}
        ids = set(cmd.member_ids) | {actor}
        if not ids - {actor} <= known or not 2 <= len(ids) <= 16:
            raise ValueError('Группа требует явно доступных участников из контактов.')
        gid = identity('conversation', actor, cmd.operation_id)
        state['conversations'][gid] = Conversation(id=gid, title=cmd.label, group=True, provenance=provenance,
            members=[dict(actor_id=a, joined_at=now, provenance=provenance) for a in sorted(ids)]).model_dump()
        batch.state_changes.append(dict(kind='group_created', entity=gid, after=deepcopy(state['conversations'][gid])))
    elif cmd.action in {'join', 'leave', 'remove'}:
        if not conversation or not conversation['group']: raise ValueError('Группа не найдена.')
        targets = set(cmd.member_ids) if cmd.action != 'leave' else {actor}
        known = {c['character_id'] for c in state['contacts'].values() if c['owner_id']==actor and c['identity_visible'] and not c['blocked']}
        previous = deepcopy(conversation)
        for target in targets:
            if cmd.action == 'join':
                if target not in known or target in members(conversation) or len(members(conversation))>=16:
                    raise ValueError('Нельзя добавить участника.')
                conversation['members'].append(dict(actor_id=target, joined_at=now, left_at=None, provenance=provenance))
            else:
                if target not in members(conversation): raise ValueError('Участник уже вышел.')
                for m in conversation['members']:
                    if m['actor_id']==target and m['left_at'] is None: m['left_at']=now
        batch.state_changes.append(dict(kind='membership', entity=conversation['id'], before=previous, after=deepcopy(conversation)))
    elif cmd.action in {'send', 'call'}:
        channel = 'TEXT_MESSAGE' if cmd.action=='send' else 'VOICE_CALL'
        if not cfg['text_message' if cmd.action=='send' else 'voice_call']:
            raise ValueError('Этот канал связи недоступен.')
        if cmd.action=='call' and not caps['can_speak']: raise ValueError('Персонаж не может говорить.')
        if cmd.action=='send' and not cmd.content.strip(): raise ValueError('Сообщение пустое.')
        if contact and (contact['blocked'] or not contact['available']): raise ValueError('Контакт недоступен или заблокирован.')
        if cmd.service:
            if cmd.action!='call' or cfg['presentation']!='phone' or not cfg['region']:
                raise ValueError('Экстренный номер не настроен для сеттинга.')
            destination = cfg['emergency_numbers'].get(cmd.service)
            if not destination: raise ValueError('Экстренный номер не настроен для региона.')
            recipients = []
        elif conversation:
            if cmd.action=='call' and conversation['group']: raise ValueError('Групповые звонки не поддерживаются.')
            recipients = sorted(members(conversation)-{actor})
            destination = conversation['id']
        elif contact:
            destination = contact['address']; recipients = [contact['character_id']] if contact['character_id'] else []
        else: raise ValueError('Выбери контакт, переписку или настроенную службу.')
        for target in recipients:
            if any(c['owner_id']==target and c['character_id']==actor and c['blocked'] for c in state['contacts'].values()):
                raise ValueError('Канал заблокирован получателем.')
        if cmd.action=='call' and any(active_call(state, a) for a in [actor, *recipients]):
            raise ValueError('Участник уже занят звонком.')
        if cmd.action=='send' and not conversation:
            # Shared stable direct container for linked identities; unresolved address stays owned.
            gid = identity('direct', *sorted([actor, *recipients])) if recipients else identity('direct', actor, cid)
            if gid not in state['conversations']:
                state['conversations'][gid] = Conversation(id=gid, contact_id=cid, provenance=provenance,
                    members=[dict(actor_id=a, joined_at=now, provenance=provenance) for a in sorted({actor,*recipients})]).model_dump()
            conversation = state['conversations'][gid]
        eid = identity('remote', actor, cmd.operation_id)
        if eid in state['remote_events']: raise ValueError('Повторная операция должна быть проверена по History.')
        event = RemoteEvent(id=eid, ordinal=max((e['ordinal'] for e in state['remote_events'].values()),default=0)+1,
            channel=channel, sender_id=actor, recipient_ids=recipients,
            destination=destination, contact_id=cid, conversation_id=conversation['id'] if conversation else None,
            content=cmd.content if cmd.action=='send' else '', world_time=now, updated_at=now,
            turn_id=state['meta']['turn_id'], status='ringing' if cmd.action=='call' else 'delivered' if recipients else 'sent',
            delivered_to=recipients if cmd.action=='send' else [], provenance=provenance, operation_id=cmd.operation_id).model_dump()
        state['remote_events'][eid] = event; _event_history(batch, state, event)
    elif cmd.action == 'read':
        if not caps['can_perceive']: raise ValueError('Персонаж не может прочитать сообщение.')
        events = [state['remote_events'].get(cmd.event_id)] if cmd.event_id else list(state['remote_events'].values())
        for event in events:
            if event and event['channel']=='TEXT_MESSAGE' and actor in event['delivered_to'] and (cmd.event_id or conversation and event['conversation_id']==conversation['id']):
                _read(state, event, actor, batch)
    elif cmd.action == 'focus':
        call = active_call(state, actor)
        if cmd.focus=='call' and (not call or call['status']!='answered'): raise ValueError('Нет активного разговора.')
        state['meta']['interaction_focus'] = cmd.focus
    else:
        event = state['remote_events'].get(cmd.event_id)
        if not event or event['channel']!='VOICE_CALL' or actor not in participants(event): raise ValueError('Звонок недоступен.')
        previous = deepcopy(event)
        if cmd.action in {'answer','decline','ignore'}:
            if event['status']!='ringing' or actor not in event['recipient_ids']: raise ValueError('Нет входящего звонка.')
            if cmd.action=='answer' and not caps['can_speak']: raise ValueError('Персонаж не может говорить.')
            event['status'] = {'answer':'answered','decline':'declined','ignore':'missed'}[cmd.action]
        elif cmd.action=='end':
            if event['status'] not in OPEN_CALL: raise ValueError('Звонок уже закончен.')
            event['status']='ended'
        else: raise ValueError('Неизвестное действие связи.')
        event['updated_at']=now
        if state['camera']['controlled_actor_id'] in participants(event):
            state['meta']['interaction_focus']='call' if event['status']=='answered' else 'physical'
        _event_history(batch, state, event, previous)
    result['world_state'] = assert_world_state_v3_invariants(state)
    return result, batch.to_dict()


def resolve_identity(snapshot, contact_id, *, address, evidence, character_id=None, name=None):
    """Explicit evidence boundary for import/accepted identity establishment.

    Names never match identity. Shared destinations never acquire a person link.
    """
    result=deepcopy(snapshot); state=result['world_state']; c=state['contacts'][contact_id]
    if address != c['address'] or not evidence.strip() or c['kind']!='person':
        raise ValueError('Нет подтверждения личности для этого адреса.')
    if c['character_id']:
        if character_id and character_id!=c['character_id']: raise ValueError('Конфликт личности контакта.')
        return result
    if character_id is None:
        if not name or not name.strip(): raise ValueError('Нужно подтверждённое имя нового человека.')
        character_id=identity('remote_person', c['owner_id'], address, evidence)
        state['characters'].setdefault(character_id, Character(id=character_id, display_name=name).model_dump())
        if not any(card['id']==character_id for card in result['character_cards']):
            result['character_cards'].append(dict(id=character_id,name=name,aliases=[],fields={},is_player=False))
    elif character_id not in state['characters']: raise ValueError('Персонаж не найден.')
    c.update(character_id=character_id, identity_visible=True, provenance=c['provenance']+'; '+evidence)
    result['world_state']=assert_world_state_v3_invariants(state)
    return result


def projection(snapshot):
    """Only the controlled actor's own records; no preview content before read."""
    state=snapshot['world_state']; actor=state['camera']['controlled_actor_id']; cfg=state['meta']['communication']
    if not actor or cfg['presentation']!='phone' or not (cfg['text_message'] or cfg['voice_call']): return None
    from backend.runtime_v3.portraits import projection as portrait
    names={c['id']:c['name'] for c in snapshot['character_cards']}
    own=[c for c in state['contacts'].values() if c['owner_id']==actor]
    known={c['character_id']:c for c in own if c['identity_visible'] and c['character_id']}
    def subject(cid):
        c=known.get(cid)
        if cid==actor: return dict(id=cid,name=names.get(cid,cid),**portrait(state,cid))
        if c: return dict(id=cid,name=c['label'],**portrait(state,cid))
        return dict(id='',name='Неизвестный участник',portrait=None,silhouette='neutral')
    contacts=[]
    for c in own:
        item=deepcopy(c); cid=item.pop('character_id')
        item['subject']=subject(cid) if cid and c['identity_visible'] else dict(id='',name=c['label'],portrait=None,silhouette='neutral')
        contacts.append(item)
    events=[]
    for e in sorted(state['remote_events'].values(),key=lambda e:(e['world_time'],e['ordinal'])):
        if actor not in participants(e): continue
        row={k:deepcopy(e[k]) for k in ('id','channel','conversation_id','world_time','status','destination')}
        row['outgoing']=e['sender_id']==actor
        row['unread']=e['channel']=='TEXT_MESSAGE' and actor in e['delivered_to'] and actor not in e['read_by']
        row['content']=e['content'] if e['sender_id']==actor or actor in e['read_by'] else None
        row['subject']=subject(e['sender_id'] if e['sender_id']!=actor else next(iter(e['recipient_ids']),''))
        if e['contact_id'] and e['contact_id'] in state['contacts'] and state['contacts'][e['contact_id']]['owner_id']==actor:
            row['subject']['name']=state['contacts'][e['contact_id']]['label']
        row['label']=row['subject']['name']; events.append(row)
        from backend.runtime_v3.calendar import calendar_label
        row['time_label']=calendar_label(state,e['world_time'])
        if not e['contact_id'] and e['destination'] in cfg['emergency_numbers'].values():
            service=next(k for k,v in cfg['emergency_numbers'].items() if v==e['destination'])
            row['label']={'medical':'Скорая помощь','police':'Полиция','fire':'Пожарная служба'}[service]
            row['subject']['name']=row['label']
    conversations=[]
    for c in state['conversations'].values():
        if not any(m['actor_id']==actor for m in c['members']): continue
        conversations.append(dict(id=c['id'],title=c['title'] or next((known[a]['label'] for a in members(c)-{actor} if a in known),'Переписка'),
            group=c['group'],contact_id=c['contact_id'] if c['contact_id'] in {r['id'] for r in own} else None,active=actor in members(c),participants=[subject(a) for a in sorted(members(c))]))
    return dict(actor_id=actor,capabilities=cfg,contacts=contacts,conversations=conversations,
        events=events,focus=state['meta']['interaction_focus'],
        emergency=[dict(service=k,number=cfg['emergency_numbers'].get(k) if cfg['region'] else None) for k in ('medical','police','fire')] if cfg['voice_call'] else [])


def context_projection(state):
    actor=state['camera']['controlled_actor_id']; call=active_call(state,actor)
    if not any(state['meta']['communication'][k] for k in ('voice_call','text_message')): return None
    rows=[]
    for e in reversed(list(state['remote_events'].values())):
        if actor not in participants(e): continue
        row={k:e[k] for k in ('id','channel','sender_id','recipient_ids','status','world_time')}
        if e['channel']=='TEXT_MESSAGE':
            row['read']=actor in e['read_by'] or e['sender_id']==actor
            if row['read']: row['content']=e['content'][:1000]
        rows.append(row)
        if len(rows)>=6: break
    return dict(focus=state['meta']['interaction_focus'],active_call=call['id'] if call and call['status']=='answered' else None,
        participants=sorted(participants(call)) if call and call['status']=='answered' else [],recent=rows,
        constraints='Only committed events exist. Never invent device controls, incoming messages or calls. '
        'Unread content is unknown. Ringing is not consent. Phone controls belong exclusively to the UI. '
        'Remote speech has no visual contact, touch or shared physical location; do not move the camera. '
        'Physical focus addresses the physical scene, call focus addresses only the connected participants. '
        'Never duplicate message contents as physical dialogue. Agreements use ordinary commitments.')


def advance(state, batch):
    """Only canonical time, never prose or physical actions, expires ringing."""
    now=state['meta']['world_time']; timeout=state['meta']['communication']['ring_timeout_minutes']
    for event in state['remote_events'].values():
        if event['channel']=='VOICE_CALL' and event['status']=='ringing' and now-event['world_time']>=timeout:
            previous=deepcopy(event); event.update(status='missed',updated_at=now)
            _event_history(batch,state,event,previous)
    if not active_call(state,state['camera']['controlled_actor_id']): state['meta']['interaction_focus']='physical'
