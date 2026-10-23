"""Semantic reviewer contract and real-worker failure/readiness boundaries."""
import json
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.usefixtures('legacy_generation_v5')
from test_api import api
from test_world_generation import fake_stages,submit,wait
from backend.services.generation_semantics import validate,groups,SemanticConflict


def review(claim_id='c',verdict='preserved',path='/accepted/relations'):
    return {'findings':[dict(claim_id=claim_id,verdict=verdict,evidence_paths=[path],explanation='Quoted evidence') ]}


@pytest.mark.parametrize('raw',[
    {'findings':[]},review('wrong'),
    {'findings':review()['findings']*2},review(path='/claims/0'),
    review(path='/accepted/missing'),
])
def test_review_cannot_omit_claims_or_cite_nonexistent_or_source_evidence(raw):
    with pytest.raises(ValueError):validate(raw,{'claims':[{'id':'c'}],'accepted':{'relations':[]}})


def test_review_negative_verdict_is_not_a_retryable_schema_error():
    with pytest.raises(SemanticConflict):
        validate(review(verdict='conflict'),{'claims':[{'id':'c'}],'accepted':{'relations':[]}})


def test_review_is_bounded_and_does_not_duplicate_executable_checks():
    claim=dict(id='c',classification='explicit',section='family',field='adoption',rules=[])
    result=groups({'claims':[dict(claim,id=str(i)) for i in range(19)]+[dict(claim,id='bound',rules=[{}])]})
    assert [len(g['claims']) for g in result]==[8,8,3]
    assert all(c['id']!='bound' for g in result for c in g['claims'])


def test_semantic_conflict_preserves_stages_without_publishing_or_repeated_review(api):
    client,app=api;calls=[];fixture=fake_stages(calls)
    def provider(**kwargs):
        for chunk in fixture(**kwargs):
            if calls[-1]=='review':
                result=json.loads(chunk)
                result['findings'][0]['verdict']='conflict'
                yield json.dumps(result)
            else:yield chunk
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        wid,jid=submit(client);job=wait(client,jid)
    assert job['status']=='paused'
    assert 'generation/semantic/' in job['error']
    assert calls.count('review')==1
    assert 'diagnostic' not in app.state.repository.inspect_generation_checkpoint(jid,'review_life_0',False)
    assert app.state.repository.inspect_generation_checkpoint(jid,'review_life_0',True)['diagnostic']['findings'][0]['verdict']=='conflict'
    assert app.state.repository.inspect_generation_checkpoint(jid,'opening',True)['status']=='completed'
    assert client.get(f'/api/workspaces/{wid}/draft').json()['state'] is None


def test_semantic_basis_blocks_post_review_canonical_change_at_start(api):
    client,app=api;repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages([])):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    path=f'/api/workspaces/{wid}/draft'
    # Simulate an existing author-editor update, keeping provenance intact.
    with repo.connect() as db:
        record=json.loads(repo._draft_head(db,wid)['content'])
        state=record['state'];scene=state['world']['scenes'][state['camera']['scene_id']]
        scene['text']='Героиня уже приехала домой.'
        repo._write_draft(db,wid,state,'author_fixture',generated=True,generation=record['generation'])
    draft=client.get(path+'?author=true').json()
    response=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert response.status_code==409,response.text
    assert 'semantic' in response.text


def test_definite_transient_rejection_retries_but_streamed_failure_does_not(api):
    from requests import HTTPError,Response
    client,_=api;fixture=fake_stages([]);attempts=[]
    def provider(**kwargs):
        stage=kwargs['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        attempts.append(stage)
        if len(attempts)==1:
            response=Response();response.status_code=503
            raise HTTPError('Unavailable',response=response)
        yield from fixture(**kwargs)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        _,jid=submit(client);assert wait(client,jid)['status']=='saved'
    assert attempts.count('interpret')==2
    attempts.clear()
    def partial(**kwargs):
        attempts.append('called')
        yield '{'
        response=Response();response.status_code=503
        raise HTTPError('Stream failed',response=response)
    with patch('backend.services.preparation.chat_stream',side_effect=partial):
        _,jid=submit(client);assert wait(client,jid)['status']=='failed'
    assert len(attempts)==1


@pytest.mark.parametrize('section,field,source,creation,verdict',[
    ('setting','country','История происходит в Японии.',{'geography':'Франция'},'conflict'),
    ('role','jurisdiction','Анна работает адвокатом, юрисдикция не указана.',{},'unresolved'),
])
def test_structured_conflict_and_material_jurisdiction_uncertainty_pause_with_source_intact(api,section,field,source,creation,verdict):
    from test_api import REMOTE
    from test_world_interpretation import BRIEF
    client,app=api;calls=[];fixture=fake_stages(calls);seen=[]
    brief=BRIEF+' '+source
    def provider(**kwargs):
        data=json.loads(kwargs['messages'][-1]['content'])
        for chunk in fixture(**kwargs):
            result=json.loads(chunk)
            if calls[-1]=='interpret':
                result['claims'].append(dict(classification='explicit',section=section,field=field,
                    description=source,spans=[dict(start=len(BRIEF)+1,end=len(brief),quote=source)]))
            if calls[-1]=='review':
                for claim,finding in zip(data['claims'],result['findings']):
                    if claim['field']==field:
                        seen.append(data)
                        finding.update(verdict=verdict,explanation='Нужно явно согласовать географию или юрисдикцию.')
            yield json.dumps(result,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Conflict'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json={
            'task':'world_staged','text':brief,'revision':0,'creation':creation,'config':REMOTE,'api_key':'test'})
        assert response.status_code==200,response.text
        jid=response.json()['id'];assert wait(client,jid)['status']=='paused'
    assert len(seen)==1
    if creation:assert seen[0]['creation_settings']['geography']=='Франция'
    plan=app.state.repository.inspect_generation_checkpoint(jid,'interpret',True)['artifact']
    assert plan['brief']==brief
    assert next(c for c in plan['claims'] if c['field']==field and c['classification']=='explicit')['spans'][0]['quote']==source
    assert client.get(f'/api/workspaces/{wid}/draft').json()['state'] is None


def test_author_edit_revalidation_reuses_generation_and_keeps_user_changes(api):
    from test_api import REMOTE
    client,app=api;repo=app.state.repository;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    path=f'/api/workspaces/{wid}/draft'
    draft=repo.draft(wid,True);scene=draft['state']['camera']['scene_id']
    changed=client.patch(path,json=dict(revision=draft['revision'],operation='patch',kind='scene',entity_id=scene,field='text',value='Мира идёт с сумками к станции. Прохладный ветер.',warnings_ack=True))
    assert changed.status_code==200,changed.text
    edited=repo.draft(wid,True);calls.clear()
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        response=client.post(path+'/generate',json=dict(task='world_review',revision=edited['revision'],config=REMOTE,api_key='test'))
        assert response.status_code==200,response.text
        review_id=response.json()['id'];result=wait(client,review_id)
        assert result['status']=='saved',result
    assert calls==['review']
    final=repo.draft(wid,True)
    from backend.services.initial_world_v2 import normalize
    assert normalize(final['state']).snapshot==normalize(edited['state']).snapshot
    assert final['source_text']==edited['source_text']
    saved=repo.confirm_draft(wid,final['revision'],final['version_id'])
    assert 'Прохладный ветер' in repo.get_snapshot(saved['save'])['world_state']['camera']['situation']
    assert repo.inspect_generation_checkpoint(jid,'opening',True)['artifact']['camera']['situation']=='Мира идёт с сумками к станции.'


def test_unchanged_author_review_is_zero_call_and_can_be_reviewed_again(api):
    from test_api import REMOTE
    client,app=api;repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages([])):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    for _ in range(2):
        draft=repo.draft(wid,True)
        with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('unchanged review must reuse evidence')) as provider:
            response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_review',revision=draft['revision'],config=REMOTE,api_key='test'))
            assert response.status_code==200,response.text
            result=wait(client,response.json()['id']);assert result['status']=='saved',result
            provider.assert_not_called()
        current=repo.draft(wid,True)
        assert current['state']==draft['state']
        assert repo.confirm_draft(wid,current['revision'],current['version_id'])['save']


def test_failed_author_review_preserves_edited_draft_and_can_cancel(api):
    from test_api import REMOTE
    client,app=api;repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages([])):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    draft=repo.draft(wid,True);path=f'/api/workspaces/{wid}/draft'
    response=client.patch(path,json=dict(revision=draft['revision'],operation='patch',kind='scene',entity_id=draft['state']['camera']['scene_id'],field='text',value='Мира уже приехала домой.',warnings_ack=True))
    assert response.status_code==200,response.text
    edited=repo.draft(wid,True);calls=[];fixture=fake_stages(calls)
    def reject(**kwargs):
        for chunk in fixture(**kwargs):
            result=json.loads(chunk);result['findings'][0]['verdict']='conflict';yield json.dumps(result)
    with patch('backend.services.preparation.chat_stream',side_effect=reject):
        body=dict(task='world_review',revision=edited['revision'],config=REMOTE,api_key='test',request_id='review-once')
        response=client.post(path+'/generate',json=body)
        assert response.status_code==200,response.text
        review_id=response.json()['id'];assert wait(client,review_id)['status']=='paused'
        assert client.post(path+'/generate',json=body).json()['id']==review_id
    assert calls==['review']
    assert repo.draft(wid,True)['version_id']==edited['version_id']
    cp=repo.inspect_generation_checkpoint(review_id,'opening',True)
    response=client.patch(path,json=dict(revision=repo.generation_status(review_id)['revision'],operation='patch',kind='checkpoint',generation_job=review_id,generation_unit='opening',artifact_version=cp['artifact_version'],field='/world_time',value=999))
    assert response.status_code==409 and 'редакторе автора' in response.text
    assert client.post(f'/api/jobs/{review_id}/stop',json={}).status_code==200
    assert repo.draft(wid,True)['state']==edited['state']
    assert client.post(path+'/confirm',json={'revision':edited['revision'],'version_id':edited['version_id']}).status_code==409
