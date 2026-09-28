"""Saved-pipeline corpus, deterministic mutation stress and consecutive turns."""
from copy import deepcopy
from pathlib import Path
import json
import random
import pytest
from test_engine import db, CONFIG
from test_api import api
from test_player_agency import execute
from test_temporal_delta import setup, payload, A, B, C, QUOTE
from backend.services.turn_delta.final_state import assert_world_invariants
from backend.services.world import CARD_FIELDS
from backend.services.world_delta import WorldDelta

CORPUS=Path(__file__).parent/'fixtures'/'runtime_failures'


def save_turn(repo,sid,p,kind='start',config=None,player='Я подхожу к окну.'):
    before=repo.get_save(sid)['state']
    job=repo.begin_job(sid,player,kind,dict(CONFIG,recent_turns=100,**(config or {})))
    calls=execute(repo,job,p,QUOTE)
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    state=repo.get_save(sid)['state']
    assert_world_invariants(state,before)
    diag=repo.turn_diagnostics(sid)[0]
    assert len(calls)==len(diag['requests'])==2
    assert not diag['repairs'] and diag['timing']['total']>=0
    return state,diag


def initial_turn(repo,sid,present):
    p=payload([A],location='коридор');p['world_delta']={};p['scene']['elapsed_minutes']=0
    return save_turn(repo,sid,p)


@pytest.mark.parametrize('path',sorted(CORPUS.glob('*.json')),ids=lambda p:p.stem)
def test_failure_corpus_commits_with_two_requests(db,path):
    f=json.loads(path.read_text());repo,_,sid=db
    setup(repo,sid,f['initial'])
    if f['kind']=='background':initial_turn(repo,sid,f['initial'])
    state,diag=save_turn(repo,sid,f['payload'],f['kind'],f['config'])
    for cid,location in f['expected_positions'].items():assert state['world']['characters'][cid]['location']==location
    assert set(w['code'] for w in diag['warnings'])==set(f['warning_codes'])
    if not any(code.startswith('evidence_') for code in f['warning_codes']):
        assert state['world']['knowledge'][B+':f']['source_event_id']=='e'
    if path.stem.startswith('09_'):
        assert diag['derivations']==[dict(section='scene',entity=A,code='final_location_derived_from_scene',origin='кабинет',destination='коридор')]


def variation(seed):
    rng=random.Random(seed)
    p=payload([A],location='коридор');d=p['world_delta']
    d['transitions']=[dict(actor_id=A,to_location='коридор',from_location='кабинет',evidence=QUOTE),dict(actor_id=B,to_location='ординаторская',evidence=QUOTE)]
    d['characters']=[dict(id=A,location='коридор',situation='В коридоре',evidence=QUOTE),dict(id=B,location='ординаторская',situation='Закончила разговор',evidence=QUOTE)]
    d['facts'].append(dict(id='other',text='Другой факт',evidence=QUOTE))
    for key in ('minute','order','location'):
        if rng.choice([True,False]):d['events'][0].pop(key,None)
    if rng.choice([True,False]):d['transitions'][0].pop('from_location')
    if rng.choice([True,False]):d['transitions']=d['transitions'][1:]
    for c in d['characters']:
        if rng.choice([True,False]):c.pop('location')
        else:c['location']='Устаревшее место'
    if rng.choice([True,False]):d['facts'].append(dict(id='unsupported',text='Нет источника',evidence='Совершенно иной текст'))
    if rng.choice([True,False]):d['facts'].append(dict(id='missing',text='Нет evidence'))
    if rng.choice([True,False]):p['scene'].pop('time')
    else:p['scene']['time']='День 1 01:00'  # Redundant label cannot override elapsed.
    for records in d.values():rng.shuffle(records)
    return p


@pytest.mark.parametrize('seed',range(100))
def test_tolerable_variations_have_zero_repair_rate(db,seed,record_property):
    repo,_,sid=db;setup(repo,sid)
    state,diag=save_turn(repo,sid,variation(seed))
    w=state['world'];assert w['characters'][A]['location']=='коридор' and w['characters'][B]['location']=='ординаторская'
    assert w['knowledge'][B+':f']['status']=='known'
    assert 'f' in w['facts'] and 'other' in w['facts']
    assert 'missing' not in w['facts'] and 'unsupported' not in w['facts']
    repair_rate=len(diag['repairs'])/1
    record_property('repair_rate',repair_rate)
    assert repair_rate==0


@pytest.mark.parametrize('defect',['unknown_actor','malformed_array','conflicting_id','movement_unknown_actor','off_camera_ambiguity','unknown_fact','scene_unknown_actor'])
def test_structural_corruption_repair_then_atomic_failure(db,defect):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A]);d=p['world_delta']
    if defect=='unknown_actor':d['characters']=[dict(id='missing',situation='здесь',evidence=QUOTE)]
    if defect=='malformed_array':d['events']={}
    if defect=='conflicting_id':d['events'].append(deepcopy(d['events'][0]))
    if defect=='movement_unknown_actor':d['transitions']=[dict(actor_id='missing',to_location='x',evidence=QUOTE)]
    if defect=='off_camera_ambiguity':d['transitions']=[dict(actor_id=B,to_location=loc,evidence=QUOTE) for loc in ('X','Y')]
    if defect=='unknown_fact':d['knowledge'][0]['fact_id']='missing'
    if defect=='scene_unknown_actor':p['scene']['present_ids'].append('missing')
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,QUOTE))==3
    assert repo.get_job(job)['status']=='error'
    assert repo.get_save(sid)['state']==before and repo.list_turns(sid)==[]
    assert len(json.loads(repo.get_job(job)['repair_diagnostics_json']))==1


def test_nonexistent_knowledge_event_is_rejected_without_losing_other_claims(db):
    repo,_,sid=db;setup(repo,sid);p=payload([A]);p['world_delta']['knowledge'][0]['source_event_id']='missing'
    state,diag=save_turn(repo,sid,p)
    assert B+':f' not in state['world']['knowledge'] and 'e' in state['world']['events']
    assert [w['code'] for w in diag['warnings']]==['knowledge_path_invalid']


def test_25_successive_commits_keep_canonical_graph_and_history(db,record_property):
    repo,_,sid=db;setup(repo,sid);repairs=0
    for i in range(25):
        before=repo.get_save(sid)['state'];actor=before['controlled_actor_id'] or B
        config={};kind='start' if i==0 else 'turn'
        if i in (8,10,17):
            kind='pov';actor=B if i in (8,10) else A;config={'actor_id':actor}
        if i==9:kind='background';actor=B;config={'camera_actor_id':B}
        location=('кабинет','коридор','холл','кабинет')[i%4]
        if i==10:location=before['scene_meta']['location']
        present=[actor]
        if i in (0,3,6,7):present=[A,B]
        p=payload(present,location,observer=kind=='background');p['scene'].pop('time');p['scene']['elapsed_minutes']=1
        d=p['world_delta'];d['transitions']=[]
        if i in (11,12,13,14):d.clear()  # Simple/empty turns.
        else:
            fid=f'f{i}';eid=f'e{i}'
            d['facts'][0]['id']=fid
            e=d['events'][0];e.update(id=eid,participants=[A,B],witnesses=[A,B],fact_ids=[fid])
            if kind=='background':e.update(participants=[B,C],witnesses=[B,C])
            for key in ('minute','order','location'):e.pop(key,None)
            d['knowledge'][0].update(fact_id=fid,source_event_id=eid)
            d['relationships']=[dict(source_id=actor,target_id=C,dimensions={'respect':i},context='После разговора',evidence=QUOTE)]
            d['characters']=[dict(id=actor,situation=f'После действия {i}',location='устаревшее',evidence=QUOTE)]
        if i==4:d['transitions']=[dict(actor_id=B,to_location='ординаторская',evidence=QUOTE)]
        if i==15:
            d['promotions']=[dict(id='new',name='Новый',fields={f:'Описание' for f in CARD_FIELDS},evidence=QUOTE)]
            p['scene']['present_ids'].append('new')
        if i==16:d['transitions']=[dict(actor_id='new',to_location=loc,order=order,evidence=QUOTE) for order,loc in [(2,'улица'),(1,'лифт')]]
        if i==20:
            d['characters'][0]['emotion']='не заданное игроком чувство'
            d['relationships'][0]['dimensions']['sympathy']=10
            d['knowledge'][0]['source_event_id']='missing'
        state,diag=save_turn(repo,sid,p,kind,config)
        repairs+=len(diag['repairs'])
        assert state['world_clock']['minute']==540+i+1
        if i==20:assert len(diag['warnings'])==3
        assert all(s==state['world']['scenes'][sid_] for sid_,s in before['world']['scenes'].items() if s.get('historical'))
    assert len(repo.list_turns(sid))==25
    record_property('repair_rate',repairs/25)
    assert repairs==0


def test_advertised_schema_excludes_runtime_owned_fields():
    definitions=WorldDelta.model_json_schema()['$defs']
    assert 'location' not in definitions['Character']['properties']
    assert 'from_location' not in definitions['Transition']['properties']
    assert not {'minute','order','location'} & set(definitions['Event']['required'])


@pytest.mark.parametrize('defect',['camera','live_membership','duplicate_card','event_fact','knowledge_witness','history','clock'])
def test_invariant_gate_rejects_corrupted_canonical_state(db,defect):
    from backend.services.world_delta_errors import StructuralDeltaError
    repo,_,sid=db;setup(repo,sid);state,_=save_turn(repo,sid,payload([A,B]))
    before=deepcopy(state);w=state['world']
    if defect=='camera':state['camera']['scene_id']='missing'
    if defect=='live_membership':w['scenes'][state['camera']['scene_id']]['participants'].append(C)
    if defect=='duplicate_card':state['characters'].append(deepcopy(state['characters'][0]))
    if defect=='event_fact':w['events']['e']['fact_ids']=['missing']
    if defect=='knowledge_witness':w['events']['e']['witnesses']=[]
    if defect=='history':w['scenes'][w['events']['e']['scene_id']]['location']='rewritten'
    if defect=='clock':state['world_clock']['minute']-=1
    with pytest.raises(StructuralDeltaError):assert_world_invariants(state,before)


def test_confirmed_draft_first_turn_preserves_departed_initial_member(api):
    from test_draft_world import make
    from test_engine import result, NARRATIVE
    from canonical_fixture import canonical
    client,app=api;path,draft=make(client)
    response=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert response.status_code==200,response.text
    repo=app.state.repository;sid=response.json()['save'];before=repo.get_save(sid)['state']
    assert before['world']['characters'][C]['location'] is None
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,canonical(result()),NARRATIVE))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    after=repo.get_save(sid)['state'];assert_world_invariants(after,before)
    assert after['world']['characters'][C]['location']=='Кухня'
    assert C not in after['world']['scenes'][after['camera']['scene_id']]['participants']
    diag=repo.turn_diagnostics(sid)[0]
    assert not diag['repairs'] and not diag['warnings']
    assert any(d['code']=='initial_location_derived_from_scene' and d['entity']==C for d in diag['derivations'])


def test_ambiguous_initial_missing_coordinate_remains_fatal(db):
    from state_updates import apply_world_updates
    from backend.services.world_delta_errors import StructuralDeltaError
    repo,_,sid=db;before=setup(repo,sid)
    before['world']['characters'][B]['location']=None
    before['world']['scenes']['conflict']=dict(before['world']['scenes']['office'],id='conflict',location='other',participants=[B])
    with pytest.raises(StructuralDeltaError,match='исходное место'):
        apply_world_updates(before,payload([A]),QUOTE,'',1,discard_unsupported=True)


def test_coordinate_derivation_does_not_grant_remote_edit_or_audience(db):
    from state_updates import apply_world_updates
    from backend.services.world_delta_errors import StructuralDeltaError
    repo,_,sid=db;before=setup(repo,sid)
    before['world']['characters'][C].update(location=None,scene_id=None)
    before['world']['scenes']['remote']=dict(before['world']['scenes']['office'],id='remote',location='other',participants=[C])
    p=payload([A,B])
    after,_,_,audience,_=apply_world_updates(before,p,QUOTE,'',1,discard_unsupported=True)
    assert_world_invariants(after,before)
    assert after['world']['characters'][C]['location']=='other' and C not in audience
    assert after['world']['scenes']['remote']['end_minute']==before['world']['scenes']['remote']['end_minute']
    assert after['world']['characters'][C]['minute']==before['world']['characters'][C]['minute']
    p['world_delta']['characters']=[dict(id=C,situation='Неподтверждённое участие',evidence=QUOTE)]
    with pytest.raises(StructuralDeltaError,match='не участвовал'):
        apply_world_updates(before,p,QUOTE,'',1,discard_unsupported=True)
