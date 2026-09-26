import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from canonical_fixture import canonical, fixture_sequence
from storage import Storage
from backend.services.world import normalize, knowledge_for, timeline
from backend.services.world_delta import apply_delta
from backend.services.director import Director, observe
from backend.services.pov import transition, controlled
from context_builder import build_context
from test_engine import db, CONFIG, NARRATIVE, result
from test_runtime import generate
from test_pov_documents import generate_background

QUOTE='Она рассказала о встрече и договорилась прийти позднее.'


def delta():
    return {
        'facts':[dict(id='meeting',text='Встреча состоялась.',secret=True,character_ids=['character_3','character_4'],evidence=QUOTE)],
        'events':[dict(id='disclosure',text='Рассказ о встрече.',participants=['character_3','character_4'],witnesses=['character_4'],fact_ids=['meeting'],medium='conversation',evidence=QUOTE)],
        'knowledge':[dict(actor_id='character_4',fact_id='meeting',status='known',source_event_id='disclosure',evidence=QUOTE)],
        'relationships':[dict(source_id='character_3',target_id='character_4',dimensions={'trust':20.0,'fear':-4.0},context='Доверие выросло.',evidence=QUOTE)],
        'characters':[dict(id='character_3',intentions=['Прийти позднее'],goals=['Встреча'],emotion='Спокойствие',evidence=QUOTE)],
        'threads':[dict(id='visit',description='Визит',character_ids=['character_3','character_4'],status='developing',state='Договорились',relevance=0.8,last_event_id='disclosure',evidence=QUOTE)],
        'scheduled_events':[dict(id='appointment',due_minute=1200,type='meeting',participants=['character_3','character_4'],description='Визит',status='pending',evidence=QUOTE)]}


def ready(repo,sid):
    generate(repo,sid,'start');generate_background(repo,sid)
    return repo.get_save(sid)['state']


def test_world_knowledge_relationships_schedule_and_context(db):
    repo,_,sid=db;state=ready(repo,sid)
    after=apply_delta(state,delta(),QUOTE,'',2)
    world=after['world']
    assert controlled(after) is None and after['camera']['mode']=='observer'
    assert knowledge_for(world,'character_1')==[]
    assert any(k['fact_id']=='meeting' for k in knowledge_for(world,'character_4'))
    assert world['relationships']['character_3:character_4']['dimensions']['trust']==20
    assert 'character_4:character_3' not in world['relationships']
    assert world['characters']['character_1']['location']=='Кухня'
    assert len([s for s in world['scenes'].values() if s['status']=='active'])>=2
    pov=transition(after,'character_1')
    messages=build_context(pov,repo.list_turns(sid),'Смотрю вокруг','pov',32768,2000)
    actor=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('POV и знания')))
    assert not actor['actor_knowledge']
    objective=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Objective world')))
    assert 'meeting' not in {f['id'] for f in objective['facts']}
    assert objective['threads']==[]
    assert not any(e['id']=='disclosure' for e in timeline(pov,'actor'))
    assert any(e['id']=='disclosure' for e in timeline(pov,'player'))
    after['world_clock']['minute']=1200
    plan=Director().plan(after,'background')
    assert plan['due_event_ids']==['appointment']
    assert after['world']['scheduled_events']['appointment']['status']=='pending'


@pytest.mark.parametrize('bad', ['absent_knowledge','missing_source','future_resolution','absent_intention','unknown_fact','evidence','past_due','nan','duplicate'])
def test_invalid_delta_is_atomic(db,bad):
    repo,_,sid=db;state=ready(repo,sid);before=deepcopy(state);change=delta()
    if bad=='absent_knowledge':change['knowledge'][0]['actor_id']='character_1'
    if bad=='missing_source':change['knowledge'][0]['source_event_id']='old_event'
    if bad=='future_resolution':change['scheduled_events'][0]['status']='resolved'
    if bad=='absent_intention':change['characters'][0]['id']='character_1'
    if bad=='unknown_fact':change['knowledge'][0]['fact_id']='unknown'
    if bad=='evidence':change['facts'][0]['evidence']='Несуществующая цитата'
    if bad=='past_due':change['scheduled_events'][0]['due_minute']=0
    if bad=='nan':change['relationships'][0]['dimensions']['trust']=float('nan')
    if bad=='duplicate':change['facts']*=2
    with pytest.raises(ValueError):apply_delta(state,change,QUOTE,'',2)
    assert state==before and repo.get_save(sid)['state']==before


def test_queue_resolution_and_knowledge_revocation(db):
    repo,_,sid=db;state=apply_delta(ready(repo,sid),delta(),QUOTE,'',2)
    resolution={'events':[dict(id='arrival',text='Пришла.',participants=['character_3'],witnesses=['character_3'],fact_ids=[],medium='action',evidence=QUOTE)],
                'scheduled_events':[{**delta()['scheduled_events'][0],'status':'resolved','resolved_event_id':'arrival'}]}
    with pytest.raises(ValueError,match='раньше срока'):apply_delta(state,resolution,QUOTE,'',3)
    state['world_clock']['minute']=1201
    after=apply_delta(state,resolution,QUOTE,'',3)
    assert after['world']['scheduled_events']['appointment']['resolved_event_id']=='arrival'
    changed=apply_delta(after,{'facts':[{**delta()['facts'][0],'text':'Сведения о встрече оказались ложными.'}]},QUOTE,'',4)
    assert changed['world']['knowledge']['character_4:meeting']['status']=='unknown'


def test_commit_variant_rollback_rebuild_world_projection(db):
    repo,_,sid=db;ready(repo,sid)
    before=repo.get_save(sid)['state']
    from test_pov_documents import background
    def run(with_delta,kind='background'):
        jid=repo.begin_job(sid,'',kind,CONFIG)
        def stream(**kw):
            if kw.get('response_format'):
                change=background()
                if with_delta:
                    change['relationships']=[]
                    change['world_delta']=delta()
                yield json.dumps(canonical(change,fixture_sequence(repo,jid)),ensure_ascii=False)
            else:yield QUOTE+' '+__import__('test_pov_documents').SECRET
        with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    run(True)
    first=repo.list_turns(sid)[-1]
    active=first['active_variant_id']
    assert 'meeting' in repo.get_save(sid)['state']['world']['facts']
    run(False,'regenerate')
    assert 'meeting' not in repo.get_save(sid)['state']['world']['facts']
    with repo.connect() as conn:
        assert not conn.execute("SELECT 1 FROM world_entities WHERE save_id=? AND entity_id='meeting'",(sid,)).fetchone()
    repo.select_variant(sid,first['id'],active,repo.get_save(sid)['revision'])
    assert 'meeting' in repo.get_save(sid)['state']['world']['facts']
    with repo.connect() as conn:
        assert conn.execute("SELECT 1 FROM world_entities WHERE save_id=? AND entity_id='meeting'",(sid,)).fetchone()
    repo.rollback_last(sid)
    assert repo.get_save(sid)['state']==before


def test_migration_idempotent_and_no_historical_rewrite(db):
    repo,_,sid=db;generate(repo,sid,'start')
    with repo.connect() as conn:
        old=dict(conn.execute('SELECT * FROM turns WHERE save_id=?',(sid,)).fetchone())
        state=json.loads(old['after_json']);state.pop('world');state.pop('camera')
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state),sid))
        conn.execute("DELETE FROM schema_migrations WHERE name='living_world_v2'")
    first=Storage(repo.path).get_save(sid)
    second=Storage(repo.path).get_save(sid)
    assert first==second and first['state']['world']['version']==2
    with repo.connect() as conn:
        assert dict(conn.execute('SELECT * FROM turns WHERE save_id=?',(sid,)).fetchone())==old


def test_observer_cannot_act_and_pov_gap_keeps_other_points(db):
    repo,_,sid=db;state=ready(repo,sid)
    with pytest.raises(ValueError,match='наблюдает'):repo.begin_job(sid,'Привет','turn',CONFIG)
    state['world_clock']['minute']+=60
    point=deepcopy(state['world']['characters']['character_3'])
    target=transition(state,'character_1')
    assert Director().plan(target,'pov')['elapsed_unobserved_minutes']==65
    assert target['world']['characters']['character_3']==point
    observer=observe(state,actor_id='character_3')
    assert observer['scene']==state['scene'] and observer['controlled_actor_id'] is None


def test_triggered_simulation_is_bounded_and_does_not_move_camera(db):
    from backend.services.simulation import simulate
    from threading import Event
    repo,_,sid=db;state=apply_delta(ready(repo,sid),delta(),QUOTE,'',2)
    # Return to the protagonist, advance time enough for the off-camera appointment.
    state=transition(state,'character_1')
    before=deepcopy(state);state['world_clock']['minute']=1200
    state['scene_meta']['time']='День 1 20:00'
    point=deepcopy(state['world']['characters']['character_1'])
    calls=[]
    def generator(stage,messages,*args,**kw):
        calls.append(stage)
        if stage=='world_simulation':yield QUOTE
        else:
            yield json.dumps({'scene':{'text':'NPC спокойно встретились.','time':'День 1 20:00','location':'Подвал','present_ids':['character_3','character_4']},'choices':[],
                'world_delta':{'events':[dict(id='arrived',text='Состоялся визит.',participants=['character_3','character_4'],witnesses=['character_3','character_4'],fact_ids=[],medium='observation',evidence=QUOTE)],
                'scheduled_events':[{**delta()['scheduled_events'][0],'status':'resolved','resolved_event_id':'arrived'}]}})
    after=simulate(before,state,3,32768,CONFIG,generator,Event())
    assert calls==['world_simulation','world_simulation_delta']
    assert after['controlled_actor_id']=='character_1' and after['camera']==state['camera']
    assert after['scene']==state['scene']
    assert after['world']['characters']['character_1']==point
    assert after['world']['scheduled_events']['appointment']['status']=='resolved'
    assert not after['world']['events']['arrived']['player_observed']
    assert not any(e['id']=='arrived' for e in timeline(after,'player'))
    assert 'arrived' not in {e['id'] for e in timeline(after,'actor')}
    record=after['world']['scene_records'][after['world']['events']['arrived']['source_record_id']]
    assert record['narrative']==QUOTE
    assert knowledge_for(after['world'],'character_1')==[]
    assert simulate(after,after,4,32768,CONFIG,generator,Event())==after
    assert len(calls)==2


def test_parallel_event_time_has_explicit_interval(db):
    repo,_,sid=db;state=ready(repo,sid)
    state['world_clock']['minute']=1200
    state['world']['scenes'][state['camera']['scene_id']]['start_minute']=1200
    change=delta();change['events'][0]['minute']=1150
    after=apply_delta(state,change,QUOTE,'',2,since=1105)
    assert after['world']['events']['disclosure']['minute']==1150
    assert after['world']['scenes'][after['world']['events']['disclosure']['scene_id']]['start_minute']==1150
    assert after['world']['scenes'][after['camera']['scene_id']]['start_minute']==1200
    assert after['world_clock']['minute']==1200
    with pytest.raises(ValueError,match='интервала'):apply_delta(state,change,QUOTE,'',2,since=1160)

from test_api import api, new_save


def test_camera_api_and_playback_are_separate_from_control(api):
    client, app=api;repo=app.state.repository
    _,save=new_save(client);sid=save['id'];generate(repo,sid,'start')
    before=repo.get_save(sid)
    turn=repo.list_turns(sid)[0]
    playback=client.get(f'/api/saves/{sid}/playback/{turn["id"]}')
    assert playback.status_code==200 and playback.json()['mode']=='playback'
    assert repo.get_save(sid)==before
    assert client.get(f'/api/saves/{sid}/timeline?visibility=actor').status_code==200
    with patch('engine.launch'):
        response=client.post(f'/api/saves/{sid}/camera',json={'actor_id':'character_1','revision':before['revision'],'config':CONFIG})
    assert response.status_code==200,response.text
    jid=response.json()['id']
    config=json.loads(repo.get_job(jid)['config_json'])
    assert config['camera_direct'] is True
    assert repo.get_save(sid)==before
    def stream(**kw):
        if kw.get('response_format'):
            payload=result();payload['choices']=[]
            yield json.dumps(canonical(payload,fixture_sequence(repo,jid)))
        else:yield NARRATIVE
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_save(sid)
    assert after['state']['controlled_actor_id'] is None
    assert after['state']['camera']['scope']=='scene'
    assert after['state']['scene_meta']['present_ids']==['character_1','character_2']
    before_playback=repo.get_save(sid)
    records=before_playback['state']['world']['scene_records']
    assert client.get(f'/api/saves/{sid}/scene-records/{next(iter(records))}').status_code==200
    assert repo.get_save(sid)==before_playback
