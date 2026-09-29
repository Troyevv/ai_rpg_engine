"""Test-only conversion of old scenario fixtures to the v3 extraction wire format.

Production never accepts WorldDelta v2. This lets transport/provider regression
scenarios keep their prose while exercising the new extraction contract.
"""
from copy import deepcopy
from backend.runtime_v3.models import identity
from backend.services.timeline import parse_time


def wire(payload,narrative,before=None):
    if not isinstance(payload,dict) or 'final_scene' in payload:return deepcopy(payload)
    if 'scene' not in payload:return deepcopy(payload)
    from canonical_fixture import canonical
    p=canonical(payload);scene=p['scene'];delta=p['world_delta']
    result=dict(final_scene=dict(location_id=identity('location',scene['location'].strip().casefold()),
        present_character_ids=scene['present_ids'],situation=scene['text'],elapsed_minutes=scene.get('elapsed_minutes',0)),choices=p.get('choices',[]))
    if before and 'elapsed_minutes' not in scene:
        now=before['world_state']['meta']['world_time'];minute=parse_time(scene.get('time',''),now)
        if minute is not None:result['final_scene']['elapsed_minutes']=minute-now
    mapping={'characters':'character_changes','relationships':'relationship_changes','knowledge':'knowledge_gained',
        'transitions':'movements','threads':'thread_changes','scheduled_events':'scheduled_event_changes'}
    for section,records in delta.items():result[mapping.get(section,section)]=deepcopy(records)
    places={scene['location']}
    for event in result.get('events',[]):
        if isinstance(event.get('location'),str):places.add(event['location']);event['location_id']=identity('location',event['location'].strip().casefold())
    for movement in result.get('movements',[]):
        if isinstance(movement.get('to_location'),str):places.add(movement['to_location']);movement['to_location_id']=identity('location',movement['to_location'].strip().casefold())
    existing=before['world_state']['locations'] if before else {}
    result['locations']=[dict(id=identity('location',place.strip().casefold()),name=place,evidence=narrative) for place in sorted(places)
        if identity('location',place.strip().casefold()) not in existing]
    for fact in result.get('facts',[]):fact['visibility']='secret' if fact.get('secret') else 'public'
    for scheduled in result.get('scheduled_event_changes',[]):
        if 'participants' in scheduled:scheduled['character_ids']=scheduled['participants']
    return result


def setup_scenario(repo,sid,present=None,observer=False):
    from backend.runtime_v3.models import Location,assert_world_state_v3_invariants
    snapshot=repo.get_snapshot(sid);state=snapshot['world_state']
    present=present if present is not None else ['character_1','character_2']
    for place in ('кабинет','коридор','ординаторская'):
        lid=identity('location',place)
        state['locations'][lid]=Location(id=lid,name=place).model_dump()
    state['meta'].update(world_time=540,turn_id=0)
    state['camera']=dict(location_id=identity('location','кабинет'),present_character_ids=present,
        controlled_actor_id=None if observer else 'character_1',mode='observer' if observer else 'actor',situation='Начало')
    for cid,actor in state['characters'].items():actor['location_id']=identity('location','кабинет' if cid in present else 'коридор')
    assert_world_state_v3_invariants(state)
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(__import__('json').dumps(snapshot),sid))
    return snapshot


def execute(repo,job,payload,narrative,repaired=None):
    import json
    from unittest.mock import patch
    import engine
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if kw.get('response_format'):yield json.dumps(repaired if len(calls)==3 and repaired is not None else payload,ensure_ascii=False)
        else:yield narrative
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,job,engine.Worker())
    return calls
