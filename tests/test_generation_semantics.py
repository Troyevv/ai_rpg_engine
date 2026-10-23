"""Semantic reviewer contract and real-worker failure/readiness boundaries."""
import json
from unittest.mock import patch
import pytest
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
