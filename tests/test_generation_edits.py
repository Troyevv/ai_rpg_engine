import json
from unittest.mock import patch

import pytest
from test_api import api
from test_world_generation import fake_stages, submit, wait


def paused_world(client, repo, calls):
    commit=repo.commit_generation_unit
    def pause_after_opening(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening': repo.generation_control(jid,'pause')
        return result
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)), patch.object(repo,'commit_generation_unit',side_effect=pause_after_opening):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='paused'
    cp=repo.inspect_generation_checkpoint(jid,'core_0',True)
    cid=next(iter(cp['artifact']['characters']))
    body=dict(operation='patch',kind='character',generation_job=jid,generation_unit='core_0',
        artifact_version=cp['artifact_version'],revision=repo.generation_status(jid)['revision'],
        entity_id=cid,field='personality.traits',value='Сдержанная, но настойчивая',preview=True)
    return wid,jid,body,cp


def test_paused_character_patch_preview_cas_resume_and_start(api):
    client,app=api;repo=app.state.repository;calls=[]
    wid,jid,body,before=paused_world(client,repo,calls)
    path=f'/api/workspaces/{wid}/draft'
    with repo.connect() as db: count=db.execute('SELECT count(*) FROM document_versions').fetchone()[0]
    preview=client.patch(path,json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['stale_units']==['assembly','life','lore','opening']
    with repo.connect() as db: assert db.execute('SELECT count(*) FROM document_versions').fetchone()[0]==count
    accepted=client.patch(path,json={**body,'preview':False})
    assert accepted.status_code==200,accepted.text
    assert client.patch(path,json={**body,'preview':False}).status_code==409
    after=repo.inspect_generation_checkpoint(jid,'core_0',True)
    cid=body['entity_id']
    other=next(key for key in before['artifact']['characters'] if key!=cid)
    assert after['artifact']['characters'][other]==before['artifact']['characters'][other]
    assert after['artifact']['cards']==before['artifact']['cards']
    assert repo.generation_field_locks(jid,'core_0')
    assert 'Сдержанная' not in json.dumps(repo.generation_status(jid),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':accepted.json()['revision']})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert calls==['interpret','setting','places','characters','life','lore','opening','life','lore','opening']
    draft=repo.draft(wid,True)
    result=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    actor=repo.get_snapshot(result['save'])['world_state']['characters'][cid]
    assert actor['personality']['items']['author_traits']['text']==body['value']


def test_checkpoint_patch_rejects_foreign_workspace_source_fact_and_stale_artifact(api):
    client,app=api;repo=app.state.repository
    wid,jid,body,before=paused_world(client,repo,[])
    foreign=repo.create_workspace('Other')['id']
    assert client.patch(f'/api/workspaces/{foreign}/draft',json=body).status_code==409
    assert client.patch(f'/api/workspaces/{wid}/draft',json={**body,'field':'display_name','value':'Renamed'}).status_code==409
    plan=repo.inspect_generation_checkpoint(jid,'interpret',True)
    # Model a previously accepted explicit source constraint. This is deliberately
    # internal setup; clients cannot replace interpretation with arbitrary JSON.
    payload=plan['artifact']
    payload['claims'].append(dict(id='fixed-trait',classification='explicit',section='personality',subject_id=body['entity_id']))
    repo.revise_generation_checkpoint(jid,'interpret',payload,body['revision'],plan['artifact_version'],[],preview=False)
    # Already-invalidated character output is not editable through the API.
    assert client.patch(f'/api/workspaces/{wid}/draft',json=body).status_code==409
    with repo.connect() as db:
        db.execute("UPDATE preparation_units SET status='completed' WHERE job_id=? AND unit_id='core_0'",(jid,))
    body['revision']=repo.generation_status(jid)['revision']
    rejected=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert rejected.status_code==409 and 'fixed-trait' in rejected.text
    assert repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact']==before['artifact']


def test_explicit_canonical_character_facts_reject_generated_conflicts():
    from backend.services.generation_constraints import validate_character_facts
    plan={'claims':[dict(id='sex',classification='explicit',section='character',time_scope='',
        subject_id='a',field='biological_sex',value='female')]}
    with pytest.raises(ValueError,match='biological_sex'):
        validate_character_facts({'characters':{'a':{'biological_sex':'male'}}},plan)
    assert validate_character_facts({'characters':{'a':{'biological_sex':'female'}}},plan)


def test_staged_provider_cannot_commit_a_changed_explicit_character_fact(api):
    from test_world_interpretation import BRIEF
    from test_api import REMOTE
    client,app=api;calls=[];fixture=fake_stages(calls)
    brief=BRIEF+' Анна — женщина.'
    def contradictory(**kwargs):
        for raw in fixture(**kwargs):
            result=json.loads(raw)
            if calls[-1]=='interpret':
                result['claims'].append(dict(classification='explicit',section='character',field='biological_sex',
                    subject_key='anna',value='female',description='Анна — женщина.',
                    spans=[dict(start=len(BRIEF)+1,end=len(brief),quote='Анна — женщина.')]))
            if calls[-1]=='characters':
                for actor in result['characters'].values():
                    if actor['display_name']=='Анна': actor['biological_sex']='male'
            yield json.dumps(result,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Protected source'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=contradictory):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=brief,
            revision=0,config=REMOTE,api_key='free-fixture'))
        jid=response.json()['id'];result=wait(client,jid)
    assert result['status']=='failed'
    assert 'biological_sex' in result['error']
    assert calls.count('characters')==2
    assert app.state.repository.draft(wid,True)['state'] is None
    assert app.state.repository.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version'] is None
