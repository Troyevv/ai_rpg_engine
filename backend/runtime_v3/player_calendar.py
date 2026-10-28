"""POV calendar projection. Filter before ranges, markers and counts are built."""
from copy import deepcopy
from backend.runtime_v3.calendar import calendar_range
from backend.runtime_v3.kinship import knowledge_status


def known_claim(state, observer, subject, predicates):
    return any(f.get('claim') and f['claim']['subject_id'] == subject
               and f['claim']['predicate'] in predicates
               and knowledge_status(state, observer, fid) == 'known'
               for fid, f in state['facts'].items())


def visible_calendar_state(state, history=None):
    view = deepcopy(state)
    observer = state['camera']['controlled_actor_id']
    # Personal observances require the observer's participation. Public calendar
    # observances remain visible, but cannot disclose private participant lists.
    profile = (view['meta'].get('calendar') or {}).get('profile') or {}
    profile['observances'] = [e for e in profile.get('observances', [])
        if not e.get('character_ids') or observer in e['character_ids']]
    from backend.runtime_v3.remote import visible_commitments
    view['scheduled_events'] = {eid:e for eid,e in visible_commitments(state,observer,history).items()
        if observer is not None and (
            known_claim(state, observer, eid, {'scheduled_event', 'commitment'})
            or (e.get('commitment') and observer in e['character_ids']))}
    # Pregnancy plans need their own knowledge even when the observer is involved.
    for pid, pregnancy in state.get('pregnancies', {}).items():
        if knowledge_status(state, observer, pregnancy['fact_id']) != 'known':
            view['scheduled_events'].pop(pid, None)
    return view


def player_calendar(state, start_date, end_date, names=None, history=None):
    result = calendar_range(visible_calendar_state(state,history), start_date, end_date)
    from backend.runtime_v3.calendar import ordinal, profile_of
    from backend.runtime_v3.weather import weather_at
    cal = state['meta'].get('calendar') or {}
    if cal.get('start_date'):
        origin = ordinal(cal['start_date'], profile_of(state))
        for day in result['days']:
            minute = cal['start_minute']//1440*1440 + (ordinal(day['date'],profile_of(state))-origin)*1440
            if minute//1440 == state['meta']['world_time']//1440: minute=state['meta']['world_time']
            day['weather'] = weather_at(state, minute=minute)
    for event in result['events']:
        if event['kind']=='birthday':
            cid=event['character_ids'][0]
            event['name']=state['characters'][cid].get('display_name') or (names or {}).get(cid) or cid
    return result
