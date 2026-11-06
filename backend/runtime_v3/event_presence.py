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
    """Return involved actors whose end-of-turn situation this Event can support."""
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
        return readers.intersection(event['participants'] + event['witnesses'])

    common = {location} if location is not None else None
    if medium == 'message' and location is None:
        # A local reading of an artifact has no live remote audience.
        common = {before['camera']['location_id'], state['camera']['location_id']}
    local_actors = set()
    for role in ('participants', 'witnesses'):
        for n, actor in enumerate(event[role]):
            if medium == 'message' and channel != 'physical' and role == 'participants' and actor == event.get('author_id'):
                # Attribution of an artifact does not establish contact or perception.
                continue
            local_actors.add(actor)
            places = _places(resolver, actor, observed_subject=role == 'participants' and medium in ('observation', 'conversation'))
            common = places if common is None else common & places
            if not common:
                reject(f'{role}[{n}]', f'{actor}: присутствие в месте Event {eid} не подтверждено. '
                       'Сверьте состав сцены, принятый маршрут и источник связи.', actor)

    # An encounter before departure is valid History but cannot anchor a new
    # situation at the old location after the actor has left.
    return {actor for actor in local_actors
            if state['characters'][actor]['location_id'] in common
            and (state['characters'][actor]['location_id'] is not None or actor in state['camera']['present_character_ids'])}


def situation_supported(resolver, change, event_actors):
    actor = change['id']
    if 'source_event_id' in change:
        ref = change['source_event_id']
        return isinstance(ref, str) and actor in event_actors.get(ref, ())
    camera = resolver.state['camera']
    if actor in camera['present_character_ids'] or actor in camera['observed_character_ids']:
        return True
    if any(move['actor_id'] == actor for move in resolver.history.movements):
        return True
    return any(actor in actors for actors in event_actors.values())
