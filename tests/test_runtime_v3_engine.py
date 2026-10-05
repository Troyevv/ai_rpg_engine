"""v3 through the real job/requests/commit/variant storage path."""
import json
from test_api import api
from unittest.mock import patch
import pytest
import engine
from test_engine import db,CONFIG
from backend.runtime_v3.models import assert_world_state_v3_invariants


def run(repo,job,raw):
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        yield json.dumps(raw,ensure_ascii=False) if kwargs.get('response_format') else 'Разговор продолжается.'
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,job,engine.Worker())
    return calls


def raw_for(snapshot):
    camera=snapshot['world_state']['camera']
    return dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
        choices=[dict(action='Действие '+str(i),speech='') for i in range(6)])


def test_real_job_commit_reload_timing_and_variant(db):
    repo,_,sid=db;snapshot=repo.get_snapshot(sid)
    job=repo.begin_job(sid,'','start',CONFIG)
    calls=run(repo,job,raw_for(snapshot))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert len(calls)==2
    after=repo.get_snapshot(sid);assert after['history_head']!=snapshot['history_head']
    assert_world_state_v3_invariants(after['world_state'])
    diag=repo.turn_diagnostics(sid)[0]
    assert len(diag['requests'])==2 and diag['timing']['total']>0
    selections={r['stage']:r['diagnostics']['selection'] for r in diag['requests']}
    assert selections['narrative']['mode']=='Narrative'
    assert selections['extraction']['mode']=='Extraction'
    assert selections['extraction']['narrative_continuity']==0
    first=repo.list_turns(sid)[0];old_variant=first['active_variant_id']
    job=repo.begin_job(sid,'','regenerate',CONFIG)
    run(repo,job,raw_for(snapshot))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    replay=repo.turn_diagnostics(sid)[0]
    assert next(r for r in replay['requests'] if r['stage']=='narrative')['diagnostics']['selection']==selections['narrative']
    second=repo.get_snapshot(sid)
    assert second['history_head']!=after['history_head']
    repo.select_variant(sid,first['id'],old_variant,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==snapshot


def test_manual_relationship_and_pov_are_canonical(db):
    repo,_,sid=db;snapshot=repo.get_snapshot(sid)
    actor=snapshot['world_state']['camera']['controlled_actor_id']
    target=next(cid for cid in snapshot['world_state']['characters'] if cid!=actor)
    repo.update_relationship(sid,actor,dict(target_id=target,context='Доверяет',dimensions={'trust':50},delete=False,revision=0))
    assert repo.get_snapshot(sid)['world_state']['relationships'][actor+':'+target]['dimensions']=={'trust':50}
    with pytest.raises(ValueError):repo.update_relationship(sid,target,dict(target_id=actor,context='Нет',dimensions={},delete=False,revision=1))
    repo.switch_actor(sid,target,1)
    repo.update_relationship(sid,target,dict(target_id=actor,context='Тепло',dimensions={'affection':20},delete=False,revision=2))
    assert repo.get_save(sid)['state']['controlled_actor_id']==target
    repo.update_relationship(sid,target,dict(target_id=actor,context='',dimensions={},delete=True,revision=3))
    assert target+':'+actor not in repo.get_snapshot(sid)['world_state']['relationships']


def test_unknown_camera_repair_once_then_fatal_preserves_save(db):
    repo,_,sid=db;before=repo.get_snapshot(sid);raw=raw_for(before)
    raw['final_scene']['present_character_ids']=['missing']
    job=repo.begin_job(sid,'','start',CONFIG)
    calls=run(repo,job,raw)
    assert len(calls)==3
    assert repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before and repo.list_turns(sid)==[]
    assert len(json.loads(repo.get_job(job)['repair_diagnostics_json']))==1


def test_100_jobs_through_engine_with_pov_background_and_reload(db):
    from storage import Storage
    from test_runtime_v3_storage import snapshot_fixture
    from backend.runtime_v3.repository import read_history
    repo,_,sid=db
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot_fixture()),sid))
    for step in range(100):
        repo=Storage(repo.path);before=repo.get_snapshot(sid)
        config=dict(CONFIG,recent_turns=100)
        if step==0:kind='start'
        elif step%10==2:kind='pov';config['actor_id']='b'
        elif step%10==3:kind='background';config['camera_actor_id']='c';config['camera_direct']=True
        elif before['world_state']['camera']['controlled_actor_id'] is None:kind='pov';config['actor_id']='a'
        else:kind='turn'
        job=repo.begin_job(sid,'Я подхожу к окну.' if kind=='turn' else '',kind,config)
        calls=[]
        def stream(**kw):
            calls.append(kw)
            if kw.get('on_usage'):kw['on_usage']({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':800})
            if not kw.get('response_format'):
                yield 'Разговор продолжается.';return
            block=next(m['content'] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only'))
            state=json.loads(block.split('\n',1)[1]);camera=state['camera']
            current=camera['controlled_actor_id'] or camera['present_character_ids'][0]
            raw=dict(final_scene=dict(location_id='hall' if step%2 else 'room',present_character_ids=[current],elapsed_minutes=1),
                character_changes=[dict(id=current,situation='У окна',emotion='ревнует',evidence='Разговор продолжается.')],
                facts=[dict(id='f'+str(step),text='Факт '+str(step),evidence='Разговор продолжается.')],
                events=[dict(id='e',text='Разговор',participants=[current],witnesses=[current],fact_ids=['f'+str(step)],medium='conversation',evidence='Разговор продолжается.')],
                knowledge_gained=[dict(actor_id=current,fact_id='f'+str(step),source_event_id='missing' if step%7==0 else 'e',evidence='Разговор продолжается.')],
                relationship_changes=[dict(source_id='b',target_id='c',context='Разговор',dimensions={'trust':step,'sympathy':10},evidence='Разговор продолжается.')])
            yield json.dumps(raw)
        with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,job,engine.Worker())
        assert repo.get_job(job)['status']=='saved',(step,repo.get_job(job)['error'])
        assert len(calls)==2
        snapshot=repo.get_snapshot(sid);assert_world_state_v3_invariants(snapshot['world_state'])
        if step==50:
            with repo.connect() as conn:conn.execute("UPDATE world_history_v3 SET payload_json='corrupted' WHERE id=?",(snapshot['history_head'],))
    assert len(repo.list_turns(sid))==100
    diag=repo.turn_diagnostics(sid)[0]
    assert len(diag['requests'])==2 and all(r['input_tokens']==1000 for r in diag['requests'])
    assert diag['warnings'] and not diag['repairs']
    with repo.connect() as conn:
        history,warnings=read_history(conn,snapshot['history_head'],limit=200)
    assert len(history['turns'])==99 and warnings


def test_optional_background_uses_v3_and_preserves_main_camera(db):
    from test_runtime_v3_storage import snapshot_fixture
    from backend.runtime_v3.models import ScheduledEvent
    repo,_,sid=db;snapshot=snapshot_fixture();s=snapshot['world_state']
    s['camera']['present_character_ids']=['a'];s['characters']['b']['location_id']='hall';s['characters']['c']['location_id']='hall'
    s['scheduled_events']['due']=ScheduledEvent(id='due',description='Встреча',character_ids=['b'],due_minute=1).model_dump()
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    job=repo.begin_job(sid,'','start',CONFIG);calls=[]
    def stream(**kw):
        calls.append(kw)
        if not kw.get('response_format'):yield 'Разговор продолжается.';return
        block=next(m['content'] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only'))
        current=json.loads(block.split('\n',1)[1]);camera=current['camera'];background=camera['mode']=='observer'
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0 if background else 1))
        if background:raw['character_changes']=[dict(id='b',situation='Закончил разговор',evidence='Разговор продолжается.')]
        yield json.dumps(raw)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert len(calls)==4
    after=repo.get_snapshot(sid)['world_state']
    assert after['camera']==s['camera']
    assert after['characters']['b']['situation']=='Закончил разговор'
    assert after['meta']['world_time']==1
    diag=repo.turn_diagnostics(sid)[0]
    assert 'background_simulation' in diag['timing']
    assert {r['stage'] for r in diag['requests']}=={'narrative','extraction','world_simulation','world_simulation_delta'}


def test_damaged_history_cannot_break_context_or_next_job(db):
    from backend.runtime_v3.repository import append_history
    repo,_,sid=db;before=repo.get_snapshot(sid)
    with repo.connect() as conn:
        before['history_head']=append_history(conn,before['history_head'],dict(events=[dict(id='broken',text='Bad',participants=[{}],witnesses=None,fact_ids=42,medium=[])],knowledge_acquisitions=[dict(source_event_id=['broken'])]))
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    assert repo.get_save(sid)['history_warnings']
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(run(repo,job,raw_for(before)))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']


def test_event_playback_uses_exact_history_record(api):
    from test_api import new_save
    from test_engine import run as run_legacy_fixture
    client,app=api;_,save=new_save(client);repo=app.state.repository;sid=save['id']
    job=repo.begin_job(sid,'','start',CONFIG);run_legacy_fixture(repo,job)
    before=repo.get_snapshot(sid)
    response=client.get(f'/api/saves/{sid}/timeline')
    assert response.status_code==200
    event=response.json()[-1]
    assert event['source_sequence']==repo.list_turns(sid)[0]['sequence']==0
    record=client.get(f"/api/saves/{sid}/scene-records/{event['source_record_id']}")
    assert record.status_code==200
    assert record.json()['narrative']==repo.list_turns(sid)[0]['assistant_text']
    assert repo.get_snapshot(sid)==before
