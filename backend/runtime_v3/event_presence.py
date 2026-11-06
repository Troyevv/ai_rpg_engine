"""Current-turn participation and perception, prior to Knowledge and commit."""
from backend.runtime_v3.models import fatal
from backend.runtime_v3.remote import active_call, participants


def _places(resolver, actor, *, observed_subject=False):
    """Possible places during the turn, including departures before final_scene."""
    places = set()
    for snapshot in (resolver.before, resolver.state):
        camera = snapshot['camera']
        location = snapshot['characters'].get(actor, {}).get('location_id')
        if location is not None:
            places.add(location)
        if actor in camera['present_character_ids']:
            # An unlocated camera can still have established physical members.
            places.add(camera['location_id'])
        if observed_subject and actor in camera['observed_character_ids']:
            # A visible figure in a doorway can be addressed or observed.
            # This does not put them in the room or make them a witness.
            places.add(camera['location_id'])
    places.update(m['to_location_id'] for m in resolver.history.movements if m['actor_id'] == actor)
    return places


def validate_event_presence(resolver, event, index, written):
    state, before = resolver.state, resolver.before
    eid, channel = event['local_id'], event.get('interaction_channel')
    medium, location = event['medium'], event.get('location_id')

    def reject(field, reason, actor=None):
        fatal(reason, 'event_presence_invalid', repairable=True, section='events',
              index=index, field=field, entity=eid, source_ids=[eid, actor] if actor else [eid])

    if location is not None and (not isinstance(location, str) or location not in state['locations']):
        reject('location_id', f'Неизвестная локация Event {eid}: {location}.')
    if channel not in (None, 'physical', 'call'):
        reject('interaction_channel', f'Неизвестный канал Event {eid}: {channel}.')

    transport = None
    if channel == 'call':
        profile = before['meta']['communication']
        transport = active_call(before, before['camera']['controlled_actor_id'])
        if not ((profile['voice_call'] or profile['landline']) and transport and
                transport['status'] == 'answered' and medium == 'conversation'):
            reject('interaction_channel', f'Для {eid} нужен действующий отвеченный звонок и medium=conversation.')
    elif written and channel != 'physical':
        transport = written
        author = event.get('author_id')
        if author and author != written['sender_id']:
            reject('author_id', f'{author} не отправлял сообщение {written["id"]}.', author)

    if transport:
        endpoints = participants(transport)
        readers = endpoints if channel == 'call' else {transport['sender_id'], *transport['read_by']}
        for role, allowed in [('participants', endpoints), ('witnesses', readers)]:
            for n, actor in enumerate(event[role]):
                if actor not in allowed:
                    reject(f'{role}[{n}]', f'{actor}: канал {transport["id"]} не подтверждает {role}.', actor)
        if location is not None and not any(location in _places(resolver, actor) for actor in endpoints):
            reject('location_id', f'Место {location} не связано ни с одной стороной контакта {eid}.')
        return

    common = {location} if location is not None else None
    if medium == 'message' and location is None:
        # A local reading of an artifact has no live remote audience.
        common = {before['camera']['location_id'], state['camera']['location_id']}
    for role in ('participants', 'witnesses'):
        for n, actor in enumerate(event[role]):
            if medium == 'message' and channel != 'physical' and role == 'participants' and actor == event.get('author_id'):
                # Attribution of an artifact does not establish contact or perception.
                continue
            places = _places(resolver, actor, observed_subject=role == 'participants' and medium in ('observation', 'conversation'))
            common = places if common is None else common & places
            if not common:
                reject(f'{role}[{n}]', f'{actor}: присутствие в месте Event {eid} не подтверждено. '
                       'Сверьте состав сцены, принятый маршрут и источник связи.', actor)


def situation_supported(resolver, change, events, written_sources):
    """Bind a situation to the end position or to a current accepted interaction."""
    actor = change['id']
    state = resolver.state
    location = state['characters'][actor]['location_id']
    if 'source_event_id' in change:
        ref = change['source_event_id']
        if not isinstance(ref, str) or ref not in events:
            return False
        candidates = [events[ref]]
    else:
        camera = state['camera']
        if actor in camera['present_character_ids'] or actor in camera['observed_character_ids']:
            return True
        if any(m['actor_id'] == actor and m['to_location_id'] == location for m in resolver.history.movements):
            return True
        candidates = events.values()

    for event in candidates:
        if actor not in event['witnesses'] and actor not in event['participants']:
            continue
        if event.get('interaction_channel') == 'call':
            return True
        written = written_sources.get(event['local_id'])
        if written:
            if actor == written['sender_id'] or actor in written['read_by']:
                return True
            continue
        if event['medium'] == 'message' and actor not in event['witnesses']:
            continue  # The author of a previously written artifact need not be involved now.
        if location is not None and event.get('location_id', location) == location:
            return True
    return False
