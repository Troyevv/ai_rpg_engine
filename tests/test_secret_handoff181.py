import json
import pytest
from fastapi.testclient import TestClient
from test_api import api
from backend.api.app import create_app
from backend.repositories.drafts import candidate_hash
from backend.runtime_v3.secrets import projection
from secret_handoff181_fixture import stage, SONYA, MAXIM, OWN


@pytest.mark.parametrize('own', [False, True])
def test_candidate_persistence_handoff_api_reload_cache(api, own):
    client, app = api; repo = app.state.repository
    wid = client.post('/api/workspaces',json={'name':'Сосновка 181'}).json()['id']
    source = stage(repo, wid, own)
    path = f'/api/workspaces/{wid}/draft'
    draft = client.get(path+'?author=true').json()
    preview = client.get(path+'?author=false')
    assert SONYA not in preview.text and MAXIM not in preview.text
    response = client.post(path+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert response.status_code == 200, response.text
    selected = response.json()
    assert selected['version_id'] == draft['version_id']
    assert selected['start_decision']['candidate_hash'] == candidate_hash(source)
    with repo.connect() as db:
        persisted = json.loads(db.execute("SELECT payload FROM world_parts WHERE world_id=? AND kind='world'",(selected['world'],)).fetchone()[0])
    assert persisted['facts'] == source['world']['facts']
    assert persisted['knowledge'] == source['world']['knowledge']
    # The same immutable world reuses the migration cache on the second launch.
    second = client.post(f"/api/worlds/{selected['world']}/saves",json={'name':'Повтор'}).json()['id']
    for sid in (selected['save'], second):
        for current in (client, TestClient(create_app(repo.path,recover=False))):
            response = current.get(f'/api/saves/{sid}')
            assert response.status_code == 200, response.text
            v = response.json(); slots = v['state']['story_secrets']['personal']
            assert len(slots['sonya']) == 2 and len(slots['maxim']) == 1
            assert all(set(r)=={'id','status'} and r['status']=='hidden' for r in slots['sonya'])
            assert slots['maxim'][0] in slots['sonya']
            for marker in (SONYA,MAXIM,'fact_sonya_love','fact_maxim_sale','protected181','AUTHOR_EVIDENCE_181','PRIVATE_NOTEBOOK_181','PRIVATE_DOCS_181'):
                assert marker not in response.text
            assert (OWN in response.text) == own
            assert not v['state']['notification_history']
            assert any(w['code']=='history_provenance_incomplete' for w in v['history_warnings'])
            canon = current.get(f'/api/saves/{sid}/author-state').json()['snapshot']['world_state']
            for fid in ('fact_sonya_love','fact_maxim_sale'):
                assert canon['facts'][fid]['story_secret']
                assert canon['facts'][fid]['secret_subject_ids'] == source['world']['facts'][fid]['secret_subject_ids']
                assert canon['knowledge']['ilya:'+fid]['status']=='unknown'
            assert projection(canon)['personal']['sonya'] == slots['sonya']
        rev = client.get(f'/api/saves/{sid}').json()['revision']
        switched = client.post(f'/api/saves/{sid}/protagonist',json=dict(revision=rev,operation_id=f'switch-{sid}',operation='temporary',actor_id='sonya'))
        assert switched.status_code==200,switched.text
        view = client.get(f'/api/saves/{sid}')
        assert SONYA in view.text and MAXIM not in view.text and OWN not in view.text
        assert not view.json()['state']['notification_history']
        for operation, actor in [('observe','sonya'),('resume','ilya')]:
            rev=client.get(f'/api/saves/{sid}').json()['revision']
            changed=client.post(f'/api/saves/{sid}/protagonist',json=dict(revision=rev,
                operation_id=f'{operation}-{sid}',operation=operation,actor_id=actor))
            assert changed.status_code==200,changed.text
            response=client.get(f'/api/saves/{sid}')
            assert SONYA not in response.text and MAXIM not in response.text
            assert (OWN in response.text)==(own and operation=='resume')
            assert not response.json()['state']['notification_history']
            if operation=='observe': assert not response.json()['state']['story_secrets']['personal']


def test_handoff_reveal_regeneration_rollback(api):
    from unittest.mock import patch
    import engine
    from test_narrative_test_world import CONFIG
    from secret_handoff181_fixture import payload
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Branches181'}).json()['id']
    stage(repo,wid);draft=client.get(f'/api/workspaces/{wid}/draft?author=true').json()
    start=client.post(f'/api/workspaces/{wid}/draft/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True)).json()
    sid=start['save'];initial=client.get(f'/api/saves/{sid}').json()['state']['story_secrets']
    data=payload(repo.get_snapshot(sid),False)
    def opening(**kw):yield json.dumps(data) if kw.get("response_format") else "Вечер в гостиной."
    jid=repo.begin_job(sid,"","start",CONFIG)
    with patch("engine.find_loaded_model",return_value={"config":{"context_length":32768}}),patch("engine.chat_stream",side_effect=opening):
        engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)["status"]=="saved",repo.get_job(jid)["error"]
    for reveal in (True,False):
        snap=repo.get_snapshot(sid)
        tid=repo.list_turns(sid)[-1]['id'] if not reveal else None
        if tid:
            with repo.connect() as db:snap=json.loads(db.execute('SELECT before_json FROM turns WHERE id=?',(tid,)).fetchone()[0])
        data=payload(snap,reveal)
        def stream(**kw):yield json.dumps(data,ensure_ascii=False) if kw.get('response_format') else 'Соня призналась Илье.'
        jid=repo.begin_job(sid,'Я слушаю Соню.','turn' if reveal else 'regenerate',dict(CONFIG,**({'target_turn_id':tid} if tid else {})))
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        result=client.get(f'/api/saves/{sid}').json()['state'];slots=result['story_secrets']['personal']
        assert (slots['sonya'][0]['status']=='known')==reveal
        assert slots['sonya'][0]['id']==initial['personal']['sonya'][0]['id']
        assert slots['ilya'][0]==slots['sonya'][0]
        assert slots['maxim'][0]['status']=='hidden'
        assert len(result['notification_history'])==int(reveal)
    repo.rollback_last(sid)
    assert client.get(f'/api/saves/{sid}').json()['state']['story_secrets']==initial


def test_sensitive_provenance_still_blocks_discoverable_slots():
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret_handoff181_fixture import candidate
    s=migrate_v2(inspect_candidate(candidate())[0]).snapshot['world_state']
    s['knowledge']['ilya:fact_sonya_love']['status']='suspected'
    assert projection(s)['personal']['sonya'][0]['status']=='hidden'
    # Condition privacy takes priority even if the same fact is item provenance.
    s['conditions']['c']=dict(fact_id='fact_sonya_love')
    slots=projection(s)['personal']
    assert 'ilya' not in slots and len(slots['sonya'])==1
    s['facts']['fact_maxim_sale']['origin_remote_event_id']='private-message'
    assert not projection(s)['personal']
