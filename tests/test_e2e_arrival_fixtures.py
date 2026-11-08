"""Run the real browser fixture provider through jobs without a browser.

The fixture server replaces module globals; isolate it in a subprocess so these
transport controls cannot alter other tests or production providers.
"""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('scenario', ['family-capabilities','provenance-campaign','departure223','berezovsk-002','berezovsk-005','background','entry','optional-annotation','retry','semantic-retry','doorway','office','imported-json','imported-text'])
def test_browser_arrival_controls_commit_with_provenance(tmp_path, scenario):
    run=subprocess.run([sys.executable,__file__,str(tmp_path/'game.sqlite'),scenario],
                       capture_output=True,text=True,timeout=60)
    assert run.returncode==0,run.stdout+run.stderr


def exercise(path, scenario):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import e2e_server as fixture
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.repository import read_history
    from test_engine import CONFIG
    from test_worlds import summary
    import engine

    repo=Repository(path)
    if scenario=='family-capabilities':
        import json,os,runpy
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        def check_endpoint(app,**kwargs):
            with TestClient(app) as client:
                for checkpoint,count in [('family',6),('family-incapacitated',0)]:
                    response=client.post('/test/family-seed',params=dict(checkpoint=checkpoint))
                    assert response.status_code==200,response.text
                    sid=response.json()['save']
                    assert len(json.loads(app.state.repository.list_turns(sid)[-1]['choices_json']))==count
                    assert client.get(f'/api/saves/{sid}').status_code==200
        with patch.dict(os.environ,{'E2E_DB_PATH':path}),patch('uvicorn.run',side_effect=check_endpoint) as launch:
            runpy.run_path(str(Path(__file__).parent/'e2e_server.py'),run_name='__main__')
        assert launch.call_count==1
        return
    if scenario in ('provenance-campaign','departure223'):
        import json
        from test_narrative_test_world import ordinary_job
        if scenario=='provenance-campaign':
            from test_action_provenance_repair import archived,seed_archived
            sid=seed_archived(repo,'campaign')['save']
            data=archived('campaign');action=data['player_input']
            fixture.provenance238_case='campaign';fixture.provenance238_repeat=True
            config=dict(CONFIG,model='provenance-test',provider='local',thinking='off',
                context_length=40960,update_tokens=4096,recent_turns=6,memory_batch=4)
        else:
            from devtools.narrative_test_world import load_fixture
            sid=load_fixture(repo,'phone')['save'];ordinary_job(repo,sid,'start')
            fixture.phone_mode='departure223'
            data=json.loads((Path(__file__).parent/'fixtures/movement/phone001.json').read_text())
            action=data['player_input'];config=CONFIG
        before=repo.get_snapshot(sid)
        jid=repo.begin_job(sid,action,'turn',config)
        engine.run_job(path,jid,engine.Worker())
        job=repo.get_job(jid);calls=repo.request_log(job_id=jid)
        if scenario=='provenance-campaign':
            assert job['status']=='error'
            assert sorted(r['stage'] for r in calls)==['extraction','extraction_repair','narrative'],job['error']
            assert repo.get_snapshot(sid)==before
        else:
            assert job['status']=='saved',job['error']
            snap=Repository(path).get_snapshot(sid)
            assert snap['world_state']['characters']['qa_timur']['location_id'] is None
            with repo.connect() as db:history,_=read_history(db,snap['history_head'])
            assert any(m['actor_id']=='qa_timur' and m['source_event_id'] for m in history['movements'])
            repo.rollback_last(sid);assert repo.get_snapshot(sid)==before
        return
    if scenario.startswith('berezovsk-'):
        import json
        from copy import deepcopy
        from test_berezovsk_followup248 import DATA,LTA,CONFIG,grounded_control,compound_control
        from test_integrated_repair247 import seed
        case=scenario[-3:];data=deepcopy(DATA[case]);sid=seed(repo,data)['save']
        snapshot=deepcopy(LTA['snapshot']);snapshot['world_state']=data['before']
        snapshot['history_head']=repo.get_snapshot(sid)['history_head']
        with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
        before=repo.get_snapshot(sid)
        answers=([grounded_control(data)] if case=='002' else
                 [json.loads(r) for r in data['responses']['D']]+[compound_control(data)])
        fixture.berezovsk_followup=dict(data=data,responses=answers,attempt=0)
        config=dict(CONFIG,model='berezovsk-followup-test')
        jid=repo.begin_job(sid,data['player_input'],'turn',config)
        engine.run_job(path,jid,engine.Worker())
        if case=='005':
            assert repo.get_job(jid)['status']=='error' and repo.get_snapshot(sid)==before
            repo.retry_job(jid,config)
            engine.run_job(path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        fresh=Repository(path)
        if case=='002':assert len(json.loads(fresh.list_turns(sid)[-1]['choices_json']))==5
        else:assert fresh.get_snapshot(sid)['world_state']['characters']['char_alexey']['location_id']=='loc_home_viktor'
        assert fresh.get_snapshot(sid)['world_state']['knowledge']==before['world_state']['knowledge']
        calls=repo.request_log(job_id=jid)
        assert len(calls)==(2 if case=='002' else 4)
        assert sum(r['stage']=='narrative' for r in calls)==1
        fresh.rollback_last(sid);assert fresh.get_snapshot(sid)==before
        return
    if scenario.startswith('imported-'):
        from fastapi.testclient import TestClient
        from backend.api.app import create_app
        import json
        with TestClient(create_app(path)) as client:
            workspace=client.post('/api/workspaces',json={'name':'Source'}).json()
            url=f"/api/workspaces/{workspace['id']}/draft"
            assert client.post(url+'/import',json={'revision':workspace['revision'],'text':summary()}).status_code==200
            draft=client.get(url+'?author=true').json()
            for field,value in [('location','Кухня'),('participants',[draft['state']['controlled_actor_id']])]:
                response=client.patch(url,json=dict(revision=draft['revision'],operation='patch',kind='scene',
                    entity_id=draft['state']['camera']['scene_id'],field=field,value=value,warnings_ack=True))
                assert response.status_code==200,response.text
                draft=response.json()
            content=json.dumps(draft['state']) if scenario=='imported-json' else client.get(url+'/export',params=dict(version_id=draft['version_id'],format='md')).text
            target=client.post('/api/workspaces',json={'name':'Imported'}).json()
            url=f"/api/workspaces/{target['id']}/draft"
            response=client.post(url+'/import',json={'revision':target['revision'],'text':content,'format':'json' if scenario=='imported-json' else 'text'})
            assert response.status_code==200,response.text
            draft=client.get(url+'?author=true').json()
            response=client.post(url+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
            assert response.status_code==200,response.text
            sid=response.json()['save']
        config=CONFIG
    elif scenario=='office':
        from devtools.narrative_test_world import load_fixture
        sid=load_fixture(repo,'phone-office')['save']
        fixture.phone_mode='office-authority136'
        config=CONFIG
    elif scenario=='background':
        sid=repo.create_save(repo.save_world('Fixture',summary()),'Fixture')
        config=CONFIG
    else:
        from fastapi.testclient import TestClient
        from backend.api.app import create_app
        from test_runtime_handoff import imported
        with TestClient(create_app(path)) as client:sid=imported(client)
        fixture.handoff_provider=dict(scenario=scenario,narratives=0,extractions=0)
        config=dict(CONFIG,model='handoff-test',context_length=131072)
    jid=repo.begin_job(sid,'','start',config)
    engine.run_job(path,jid,engine.Worker())
    if scenario in ('retry','semantic-retry'):
        assert repo.get_job(jid)['status']=='error'
        repo.retry_job(jid,config)
        engine.run_job(path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
        assert fixture.handoff_provider['narratives']==1
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    if scenario=='office':
        # Exercise the same doorway return used after the browser's phone scene:
        # Leaving camera membership alone preserves known geography. Doorway
        # observation is not a departure; actual arrivals still need provenance.
        for text in ('Спрашиваю, как дела.','Подождать у двери.','Продолжить после звонка.'):
            jid=repo.begin_job(sid,text,'turn',config)
            engine.run_job(path,jid,engine.Worker())
            assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
            state=repo.get_snapshot(sid)['world_state']
            if text=='Подождать у двери.':
                assert state['characters']['qa_marina']['location_id']==state['camera']['location_id']
            elif text=='Продолжить после звонка.':
                assert state['camera']['observed_character_ids']==['qa_marina']
                assert state['characters']['qa_marina']['location_id']==state['camera']['location_id']
    if scenario=='background':
        repo.switch_actor(sid,'character_2',repo.get_save(sid)['revision'])
        jid=repo.begin_job(sid,'','background',config)
        engine.run_job(path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    snap=Repository(path).get_snapshot(sid)
    with repo.connect() as db:history,_=read_history(db,snap['history_head'])
    if scenario=='background':
        assert snap['world_state']['camera']['controlled_actor_id'] is None
        assert {k['actor_id'] for k in snap['world_state']['knowledge'].values()}=={'character_3','character_4'}
    if scenario.startswith('imported-'):
        camera=snap['world_state']['camera']
        assert camera['present_character_ids']==[camera['controlled_actor_id']]
        assert not history['movements']
    elif scenario=='doorway':
        assert 'viktoria_solovyova' in snap['world_state']['camera']['observed_character_ids']
        assert not history['movements']
    else:
        moved=({'character_3','character_4'} if scenario=='background' else
               {'qa_marina'} if scenario=='office' else {'viktoria_solovyova'})
        routes=[m for m in history['movements'] if m['actor_id'] in moved]
        assert {m['actor_id'] for m in routes}==moved
        assert all(m.get('source_event_id') for m in routes)
        assert {m['source_event_id'] for m in routes}<={e['id'] for e in history['events']}


if __name__=='__main__':exercise(sys.argv[1],sys.argv[2])
