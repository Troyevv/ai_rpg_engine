"""Run the real browser fixture provider through jobs without a browser.

The fixture server replaces module globals; isolate it in a subprocess so these
transport controls cannot alter other tests or production providers.
"""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('scenario', ['background','entry','optional-annotation','retry','semantic-retry','doorway','office','imported-json','imported-text'])
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
