"""Current-turn participation and perception, prior to Knowledge and commit."""
from backend.runtime_v3.models import fatal
from backend.runtime_v3.remote import active_call, participants


def _scene_places(snapshot, actor, observed_subject=False):
    camera = snapshot['camera']
    location = snapshot['characters'].get(actor, {}).get('location_id')
    places = {location} if location is not None else set()
    if actor in camera['present_character_ids'] or (observed_subject and actor in camera['observed_character_ids']):
        places.add(camera['location_id'])
    return places


def _meeting_slots(resolver, actor, observed_subject, route, orders, event_order):
    """Each (phase, place) is one common snapshot, never a union across time."""
    start = _scene_places(resolver.before, actor, observed_subject)
    end = _scene_places(resolver.state, actor, observed_subject)
    slots = set()
    if event_order is None:
        slots.update(('start', place) for place in start)
        slots.update(('end', place) for place in end)
    if not orders:
        return slots

    # A final_scene placement (or an unordered leg) has no position on the
    # explicit ordinal axis. It cannot anchor the actor between ordered steps.
    changes = [m for m in route if m['from_location_id'] != m['to_location_id']]
    if any(m.get('order') is None for m in changes):
        return slots
    if not changes:
        slots.update((order, place) for order in orders for place in start & end)
        return slots

    # Resolver has already sorted the accepted route for this actor. Equal
    # orders on DIFFERENT routes form one batch; do not iterate actors as time.
    for order in orders:
        places = start & {changes[0]['from_location_id']}
        for move in changes:
            if move['order'] > order:
                break
            if move['order'] == event_order:
                # No relative order within a tie between Event and movement.
                places = set()
                break
            places = {move['to_location_id']}
        slots.update((order, place) for place in places)
    return slots


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
        if location is not None and not any(
                location in _scene_places(snapshot, actor) for snapshot in (before, state) for actor in endpoints
        ) and not any(m['actor_id'] in endpoints and m['to_location_id'] == location for m in resolver.history.movements):
            reject('location_id', f'Место {location} не связано ни с одной стороной контакта {eid}.')
        return readers.intersection(event['participants'] + event['witnesses'])

    allowed_places = {location} if location is not None else None
    if medium == 'message' and location is None:
        # A local reading of an artifact has no live remote audience.
        allowed_places = {before['camera']['location_id'], state['camera']['location_id']}
    routes = {}
    for move in resolver.history.movements:
        routes.setdefault(move['actor_id'], []).append(move)
    actors = set(event['participants'] + event['witnesses'])
    orders = {m['order'] for actor in actors for m in routes.get(actor, ())
              if m.get('order') is not None and m['from_location_id'] != m['to_location_id']}
    # Without a comparable move, Event.order orders Events only. Established
    # common starting/ending scenes still count; crossed endpoints never do.
    event_order = event.get('order') if orders else None
    if event_order is not None:
        orders = {event_order}
    common = None
    local_actors = set()
    for role in ('participants', 'witnesses'):
        for n, actor in enumerate(event[role]):
            if medium == 'message' and channel != 'physical' and role == 'participants' and actor == event.get('author_id'):
                # Attribution of an artifact does not establish contact or perception.
                continue
            local_actors.add(actor)
            visible = role == 'participants' and medium in ('observation', 'conversation')
            slots = _meeting_slots(resolver, actor, visible, routes.get(actor, ()), orders, event_order)
            if allowed_places is not None:
                slots = {slot for slot in slots if slot[1] in allowed_places}
            common = slots if common is None else common & slots
            if not common:
                reject(f'{role}[{n}]', f'{actor}: присутствие в месте Event {eid} не подтверждено. '
                       'Сверьте одновременное присутствие, order перемещений и Event или источник связи.', actor)

    # An encounter before departure is valid History but cannot anchor a new
    # situation at the old location after the actor has left.
    meeting_places = {place for _, place in common or ()}
    return {actor for actor in local_actors
            if state['characters'][actor]['location_id'] in meeting_places
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
