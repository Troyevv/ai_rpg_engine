"""Persist source-backed events and immutable event-specific contexts."""
from backend.services.world import identity
from backend.services.timeline import current_time
from .references import require


def apply_events(state, before, events, sequence, since):
    world=state['world'];now=current_time(state);new_events={}
    camera=world['scenes'][state['camera']['scene_id']]
    for e in sorted(events,key=lambda e:(e.get('minute',now),e.get('order',0),e['id'])):
        minute=e.get('minute')
        if minute is not None:require((since if since is not None else now)<=minute<=now,'событие вне интервала хода','invalid_time',section='events',entity=e['id'])
        sid=identity('event_scene',sequence,e['id'])
        location=e.get('location')
        world['scenes'][sid]=dict(id=sid,location=location,participants=list(e['participants']),witnesses=list(e['witnesses']),
            start_minute=minute,end_minute=minute,order=e.get('order'),text=e['text'],status='ended',historical=True,event_ids=[e['id']])
        record=dict(e,minute=minute,location=location,scene_id=sid,source_sequence=sequence,recorded_minute=now,player_observed=True)
        world['events'][e['id']]=record;new_events[e['id']]=record
        # Director tracks observed activity even if event location is unknown;
        # this index does not imply historical membership or location.
        live=camera if location is None or camera['location']==location else world['scenes'].get(before['camera']['scene_id'])
        if live and not live.get('historical') and (location is None or live['location']==location):live['event_ids'].append(e['id'])
        for cid in e['participants']:world['characters'][cid]['last_event_id']=e['id']
    return new_events
