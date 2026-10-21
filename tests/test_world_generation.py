"""End-to-end staged Preparation API with deterministic, free provider fixtures."""
import json
import time
import pytest
from unittest.mock import patch

from test_api import api, REMOTE
from test_world_interpretation import BRIEF, interpretation


def fake_stages(calls):
    def stream(**kwargs):
        stage=kwargs['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kwargs['messages'][-1]['content'])
        calls.append(stage)
        if stage=='interpret': result=interpretation()
        elif stage=='setting':
            result={'campaign':{'title':'Пятница'}, 'entities':[
                dict(key=str(i),existing_id=row['id'],name=row['name'],kind=row['kind'],tier=row['tier'])
                for i,row in enumerate(data['interpretation']['entities'])]+[
                    dict(key='road',kind='location',name='Дорога к станции')]}
        else:
            names={row['name']:row['id'] for row in data['registry']}
            anna,mira,road=[names[name] for name in ('Анна','Мира','Дорога к станции')]
            if stage=='places': result={'locations':{road:dict(id=road,name='Дорога к станции')}}
            elif stage=='characters':
                result={'characters':{},'cards':{}}
                for row in data['registry']:
                    cid=row['id']
                    if cid not in data['assigned_ids']: continue
                    result['characters'][cid]=dict(id=cid,display_name=row['name'],location_id=road if cid==mira else None)
                    result['cards'][cid]=dict(id=cid,name=row['name'],fields={})
            elif stage=='life': result={'objective_relations':{'adoption':dict(id='adoption',kind='adoptive_parent',source_id=anna,target_id=mira)}}
            elif stage=='lore': result={'facts':{'adoption':dict(id='adoption',text='Мира удочерена',visibility='secret',character_ids=[anna,mira])},
                'knowledge':{cid+':adoption':dict(actor_id=cid,fact_id='adoption',status='known',evidence='Вчера' if cid==mira else 'Ранее') for cid in (anna,mira)}}
            elif stage=='opening': result={'world_time':6120,'camera':dict(mode='actor',controlled_actor_id=mira,pov_actor_id=mira,location_id=road,
                present_character_ids=[mira],situation='Мира идёт с сумками к станции.')}
            else: raise AssertionError(stage)
        yield json.dumps(result,ensure_ascii=False)
    return stream


def wait(client,jid):
    for _ in range(500):
        value=client.get('/api/jobs/'+jid).json()
        if not value['live'] and value['status'] not in ('generating','pause_requested'): return value
        time.sleep(.01)
    raise AssertionError('staged generation timed out')


def submit(client):
    workspace=client.post('/api/workspaces',json={'name':'Staged'}).json()
    response=client.post(f"/api/workspaces/{workspace['id']}/draft/generate",json={
        'task':'world_staged','text':BRIEF,'revision':0,'config':REMOTE,'api_key':'stage-test-key'})
    assert response.status_code==200,response.text
    return workspace['id'],response.json()['id']


def test_staged_api_assembles_playable_draft_and_tracks_each_request(api):
    client,app=api;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        wid,jid=submit(client)
        result=wait(client,jid)
    assert result['status']=='saved',result
    assert calls==['interpret','setting','places','characters','life','lore','opening']
    assert result['generation']['overall_progress']==1
    assert result['narrative']==''
    path=f'/api/workspaces/{wid}/draft'
    draft=client.get(path+'?author=true').json()
    assert draft['state']['world_clock']['minute']==6120
    assert not draft['validation']['errors']
    saved=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert saved.status_code==200,saved.text
    snapshot=app.state.repository.get_snapshot(saved.json()['save'])
    assert snapshot['world_state']['camera']['situation']=='Мира идёт с сумками к станции.'
    assert snapshot['campaign']['initial_world']['brief']==BRIEF
    with app.state.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM llm_requests').fetchone()[0]==7
        assert db.execute("SELECT count(*) FROM preparation_units WHERE status='completed'").fetchone()[0]==8
        assert 'stage-test-key' not in '\n'.join(db.iterdump())


def test_pause_resume_reuses_completed_units_and_keeps_existing_draft(api):
    import threading
    client,app=api;calls=[];entered=threading.Event();release=threading.Event()
    fixture=fake_stages(calls)
    def stream(**kwargs):
        for text in fixture(**kwargs):
            if calls[-1]=='characters': entered.set();release.wait(5)
            yield text
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        wid,jid=submit(client)
        assert entered.wait(3)
        progress=client.get(f'/api/jobs/{jid}/generation').json()
        response=client.post(f'/api/jobs/{jid}/generation/pause',json={'revision':progress['revision']})
        assert response.status_code==200,response.text
        assert response.json()['status']=='pause_requested'
        release.set()
        paused=wait(client,jid)
        assert paused['status']=='paused',paused
        assert calls==['interpret','setting','places','characters']
        assert client.get(f'/api/workspaces/{wid}/draft').json()['state'] is None
        resumed=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':paused['generation']['revision']})
        assert resumed.status_code==200,resumed.text
        done=wait(client,jid)
        assert done['status']=='saved',done
    assert calls==['interpret','setting','places','characters','life','lore','opening']


def test_checkpoint_inspection_is_author_only_and_read_only(api):
    client,_=api;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='saved'
    public=client.get(f'/api/jobs/{jid}/generation/checkpoints/interpret').json()
    assert 'artifact' not in public
    assert 'удочер' not in json.dumps(public,ensure_ascii=False)
    author=client.get(f'/api/jobs/{jid}/generation/checkpoints/interpret?author=true').json()
    assert author['artifact']['brief']==BRIEF
    assert author['read_only']
    assert client.get(f'/api/jobs/{jid}').json()['status']=='saved'


def test_restart_resumes_safe_checkpoint_using_encrypted_provider_credential(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    path=tmp_path/'restart.sqlite3';calls=[]
    fixture=fake_stages(calls)
    failed=False
    def stream(**kwargs):
        nonlocal failed
        if '\nStage: lore' in kwargs['messages'][0]['content'] and not failed:
            failed=True
            raise RuntimeError('Temporary provider outage')
        yield from fixture(**kwargs)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        first=create_app(path)
        with TestClient(first) as client:
            wid,jid=submit(client)
            assert wait(client,jid)['status']=='failed'
            # Simulate a process lost between completed requests, not an
            # uncertain in-flight provider call (tested separately).
            with first.state.repository.connect() as db:
                db.execute("UPDATE preparation_jobs SET status='generating' WHERE id=?",(jid,))
                db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
        second=create_app(path)
        with TestClient(second) as client:
            for _ in range(500):
                job=client.get('/api/jobs/'+jid).json()
                if job['status']=='saved': break
                time.sleep(.01)
            assert job['status']=='saved',job
            assert client.get(f'/api/workspaces/{wid}/draft').json()['version_id'] is not None
    assert calls==['interpret','setting','places','characters','life','lore','opening']


def test_restart_without_credentials_keeps_valid_checkpoints_and_makes_no_request(tmp_path,monkeypatch):
    from backend.repositories.preparation import Repository
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    path=tmp_path/'no-key.sqlite3';repo=Repository(path)
    w=repo.create_workspace('Recover')
    jid=repo.begin_preparation(w['id'],'draft_world_staged',BRIEF,{**REMOTE,'_draft_task':'world_staged','_draft_input':BRIEF},0)
    assert repo.generation_status(jid) is not None
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('No credentials, no provider call')) as provider:
        with TestClient(create_app(path)) as client:
            for _ in range(100):
                job=client.get('/api/jobs/'+jid).json()
                if job['status']=='waiting_for_credentials': break
                time.sleep(.01)
            assert job['status']=='waiting_for_credentials',job
            assert repo.generation_resources(jid,['brief'])=={'brief':BRIEF}
        provider.assert_not_called()


def test_duplicate_submission_reuses_job_and_does_not_repeat_provider_requests(api):
    client,app=api;calls=[]
    wid=client.post('/api/workspaces',json={'name':'Idempotent'}).json()['id']
    body={'task':'world_staged','text':BRIEF,'revision':0,'config':REMOTE,'api_key':'test-key','request_id':'create-once'}
    path=f'/api/workspaces/{wid}/draft/generate'
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        first=client.post(path,json=body)
        duplicate=client.post(path,json=body)
        assert first.status_code==duplicate.status_code==200
        assert first.json()['id']==duplicate.json()['id']
        assert wait(client,first.json()['id'])['status']=='saved'
        completed=client.post(path,json=body)
        assert completed.status_code==200 and completed.json()['id']==first.json()['id']
        assert client.post(path,json={**body,'text':'different'}).status_code==409
    assert len(calls)==7
    with app.state.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM preparation_jobs').fetchone()[0]==1


def test_queued_job_captures_scenario_and_prompts_atomically_before_worker(tmp_path):
    import pytest
    from backend.repositories.preparation import Repository
    repo=Repository(tmp_path/'queue.sqlite3')
    wid=repo.create_workspace('Scenario')['id']
    config={**REMOTE,'_draft_task':'world_staged','_draft_input':'Opening', '_use_idea':True}
    with pytest.raises(ValueError,match='Сценариста'):
        repo.begin_preparation(wid,'draft_world_staged','Opening',config,0)
    with repo.connect() as db:
        assert db.execute('SELECT count(*) FROM preparation_jobs').fetchone()[0]==0
        db.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('Original scenario',wid))
    jid=repo.begin_preparation(wid,'draft_world_staged','Opening',config,0)
    with repo.connect() as db:
        db.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('Later scenario',wid))
    restarted=Repository(tmp_path/'queue.sqlite3')
    assert restarted.recover_generations()==[jid]
    inputs=restarted.generation_resources(jid,['brief','prompt'])
    assert inputs['brief']=='Opening\n\nOriginal scenario'
    assert inputs['prompt']['version']
    assert inputs['prompt']['schemas']['characters']


def test_provider_error_never_exposes_private_prompt_or_key_and_is_not_auto_retried(api):
    client,app=api
    with patch('backend.services.preparation.chat_stream',side_effect=ValueError('private adoption story / stage-test-key')) as provider:
        _,jid=submit(client)
        result=wait(client,jid)
    assert result['status']=='failed'
    assert provider.call_count==1
    assert 'provider request failed' in result['error']
    assert 'private adoption' not in json.dumps(result)
    assert 'stage-test-key' not in json.dumps(result)
    assert result['generation']['units'][0]['attempts']==1


def test_malformed_stage_retries_locally_without_repeating_accepted_inputs(api):
    client,app=api;calls=[];fixture=fake_stages(calls);failed=False
    def stream(**kwargs):
        nonlocal failed
        if '\nStage: life' in kwargs['messages'][0]['content'] and not failed:
            failed=True
            yield '{malformed'
            return
        yield from fixture(**kwargs)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client)
        done=wait(client,jid)
    assert done['status']=='saved',done
    assert calls==['interpret','setting','places','characters','life','lore','opening']
    assert next(row for row in done['generation']['units'] if row['stage']=='life')['attempts']==2
    with app.state.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM llm_requests').fetchone()[0]==8


@pytest.mark.parametrize('mutation,path', [
    ("UPDATE preparation_units SET status='stale' WHERE unit_id='lore'", 'lore'),
    ("UPDATE preparation_units SET stage='characters' WHERE unit_id='opening'", 'missing required stages'),
    ("UPDATE preparation_units SET input_manifest='{}' WHERE unit_id='life'", 'life'),
    ("UPDATE preparation_resources SET digest='changed' WHERE resource_key='brief'", 'interpret'),
    ("UPDATE preparation_resources SET artifact_id=(SELECT min(id) FROM document_versions) WHERE resource_key='places'", 'places'),
    ("UPDATE preparation_runs SET revision=revision+1", 'revision'),
])
def test_start_rechecks_generation_currency_after_author_edit(api,mutation,path):
    client,app=api;repo=app.state.repository;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='saved'
    draft=repo.draft(wid,author=True)
    repo.edit_draft(wid,draft['revision'],'patch',kind='campaign',field='title',value='Авторская версия')
    edited=repo.draft(wid,author=True)
    # Simulate superseded/corrupt persisted dependencies between publication
    # and confirmation. An author patch must retain its generation provenance.
    with repo.connect() as db:
        db.execute(mutation)
    with pytest.raises(ValueError,match='generation/readiness/?.*'+path):
        repo.confirm_draft(wid,edited['revision'],edited['version_id'])
    with repo.connect() as db:
        assert db.execute('SELECT count(*) FROM saves').fetchone()[0]==0
    assert repo.draft(wid,author=True)['state']['campaign']['title']=='Авторская версия'


def test_confirmed_generation_is_idempotent_after_dependencies_change(api):
    client,app=api;repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages([])):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='saved'
    draft=repo.draft(wid,author=True)
    result=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    with repo.connect() as db:
        db.execute("UPDATE preparation_units SET status='stale' WHERE job_id=?",(jid,))
    assert repo.confirm_draft(wid,draft['revision'],draft['version_id'])==result
    assert repo.get_snapshot(result['save'])['world_state']['camera']['situation']=='Мира идёт с сумками к станции.'


def test_later_stage_context_uses_current_canonical_personality_and_active_motives():
    from backend.runtime_v3.models import Character
    from backend.services.world_generation import _people
    actor=Character(id='a',personality={'items':{'voice':{'field':'communication','text':'Тихая и настойчивая','revision':2}}},
        values={'v':{'id':'v','text':'Честность'},'retired':{'id':'retired','text':'Богатство','status':'retired'}},
        goals=[{'id':'g','text':'Учиться'},{'id':'old','text':'Уехать','status':'completed'}]).model_dump()
    result=_people([{'characters':{'a':actor},'cards':{'a':{'name':'Анна','fields':{'Характер':'Устаревшая карточка'}}}}])[0]
    assert result['character']==''
    assert result['personality']['voice']['revision']==2
    assert result['personality']['voice']['text']=='Тихая и настойчивая'
    assert set(result['values'])=={'v'}
    assert [goal['id'] for goal in result['goals']]==['g']
    assert 'evidence' not in result['personality']
