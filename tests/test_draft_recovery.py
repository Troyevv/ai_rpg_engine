"""Failure recovery uses the real author/version/confirm path and controlled replies."""
import json
from copy import deepcopy
from threading import Event
from unittest.mock import patch
import pytest
from test_initial_draft_v4 import rich, REMOTE, SHORT, api, wait_job
from backend.services import draft_initial as initial, draft_repair as repair, draft_completeness as review
from backend.services.draft_response import response, TransportError
from backend.repositories.preparation import Repository
from llm import ProviderHTTPError


def test_gregorian_lengths_without_repair():
    raw=rich();raw['world_clock']['calendar']['profile']={'system':'gregorian','month_lengths':[31,28,31,30,31,30,31,31,30,31,30,31]}
    before=deepcopy(raw)
    state,report=initial.inspect_candidate(raw)
    assert not report['errors'],report
    assert state['world_clock']['calendar']['profile']['month_lengths']==[]
    assert raw==before


def test_three_independent_references_one_patch():
    raw=rich();valid=deepcopy(raw)
    raw['protagonist_id']='missing';raw['controlled_actor_id']='missing';raw['world']['roles']['job']['organization_id']='missing'
    _,report=initial.inspect_candidate(raw)
    paths={d['path'] for d in report['diagnostics']}
    required={'/protagonist_id','/controlled_actor_id','/world/roles/job/organization_id'}
    assert required<=paths
    _,allowed=repair.request(json.dumps(raw),report['diagnostics'])
    fixed=json.loads(repair.apply(json.dumps(raw),json.dumps({'patches':[
        {'path':'/protagonist_id','value':valid['protagonist_id']},
        {'path':'/controlled_actor_id','value':valid['controlled_actor_id']},
        {'path':'/world/roles/job/organization_id','value':valid['world']['roles']['job']['organization_id']}]}),allowed))
    assert fixed==valid


@pytest.mark.parametrize('path',['/items/-1','/items/01','/items/+0','/bad~2key'])
def test_patch_rejects_invalid_pointers(path):
    with pytest.raises(ValueError):repair.apply('{"items":[1,2]}',json.dumps({'patches':[{'path':path,'value':9}]}),[path])


def test_root_review_and_recommendation():
    raw=rich()
    issues=review.parse(json.dumps({'issues':[{'path':'/controlled_actor_id','message':'Выбрать героя','related_paths':['/protagonist_id'],'severity':'recommendation'}]}),raw)
    assert issues[0]['severity']=='recommendation'
    raw['world']['roles']['job']['organization_id']='missing'
    raw['world']['roles']['a/b~c']=raw['world']['roles'].pop('job');raw['world']['roles']['a/b~c']['id']='a/b~c'
    _,report=initial.inspect_candidate(raw)
    assert '/world/roles/a~1b~0c/organization_id' in {d['path'] for d in report['diagnostics']}


def test_condition_effects_and_symmetric_duplicates():
    raw=rich();cid=raw['protagonist_id']
    raw['world']['conditions']={'ill':dict(id='ill',actor_id=cid,description='Усталость',effects={'can_act':True})}
    relation=next(iter(raw['world']['objective_relations'].values()))
    raw['world']['objective_relations']['duplicate']=dict(relation,id='duplicate')
    _,report=initial.inspect_candidate(raw)
    paths={d['path'] for d in report['diagnostics']}
    assert '/world/conditions/ill/effects/can_act' in paths
    assert any(d['category']=='duplicate' for d in report['diagnostics'])


def test_failed_generation_manual_edit_start_turn_reload(api):
    client,app=api;w=client.post('/api/workspaces',json={'name':'recovery'}).json();url=f"/api/workspaces/{w['id']}/draft"
    raw=rich();original=raw['protagonist_id'];raw['protagonist_id']='missing';raw['controlled_actor_id']='missing'
    calls=[]
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(raw) if len(calls)==1 else '{"patches":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='error'
    d=client.get(url+'?author=true').json();assert d['candidate']==initial.normalize(raw)
    assert client.get(url).json()['candidate'] is None
    assert client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']}).status_code==409
    for path in ('/protagonist_id','/controlled_actor_id'):
        r=client.patch(url+'/candidate',json={'revision':d['revision'],'path':path,'value':original})
        assert r.status_code==200,r.text
        d=r.json()
    assert not d['validation']['errors'],d['validation']
    assert d['candidate']['world']['facts']==raw['world']['facts']
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert started.status_code==200,started.text
    sid=started.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid);job=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        play(repo,job,raw_for(before));assert repo.get_job(job)['status']=='saved'
        repo=Repository(repo.path)
    assert len(calls)==3
    stale=client.patch(url+'/candidate',json={'revision':0,'path':'/protagonist_id','value':original})
    assert stale.status_code==409


def test_malformed_review_resume_does_not_regenerate(api):
    client,app=api;w=client.post('/api/workspaces',json={'name':'review'}).json();url=f"/api/workspaces/{w['id']}/draft";calls=[]
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(rich()) if len(calls)==1 else '{"bad":true}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='error'
    d=client.get(url+'?author=true').json()
    assert d['candidate'] and any('не завершена' in e for e in d['validation']['errors'])
    def correct(**kw):
        assert kw['messages'][0]['content'].startswith(review.MARKER)
        yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=correct) as provider:
        r=client.post(url+'/resume',json={'api_key':'test','revision':d['revision'],'max_tokens':2048});assert r.status_code==200,r.text
        assert wait_job(client,jid)['status']=='saved'
        assert provider.call_count==1
    cfg=json.loads(app.state.repository.preparation_job(jid)['config_json']);assert cfg['max_tokens']==2048


@pytest.mark.parametrize('context_length',[65536,262144])
def test_context_preflight_can_resume_with_larger_budget(api,context_length):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'context recovery'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    source=SHORT+'\n'+('Подробность. '*2500)
    config=dict(REMOTE,context_length=32768)
    with patch('backend.services.preparation.chat_stream') as provider:
        created=client.post(url+'/generate',json={'revision':0,'text':source,'config':config,'api_key':'test'})
        assert created.status_code==200,created.text
        jid=created.json()['id']
        failed=wait_job(client,jid)
        assert failed['status']=='error' and 'Контекст 32768' in failed['error']
        assert failed['resumable'] and not failed['unknown_outcome']
        provider.assert_not_called()
    before=json.loads(app.state.repository.preparation_job(jid)['response_journal'])
    assert source in before['messages'][-1]['content']
    assert not before.get('pending') and not before.get('reserved_tokens')
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            yield '{"issues":[]}'
        else:
            assert kw['messages']==before['messages']
            yield json.dumps(rich())
    d=client.get(url+'?author=true').json()
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        resumed=client.post(url+'/resume',json={'revision':d['revision'],'context_length':context_length,'api_key':'test'})
        assert resumed.status_code==200,resumed.text
        assert wait_job(client,jid)['status']=='saved'
    assert len(calls)==2
    saved=app.state.repository.preparation_job(jid)
    assert json.loads(saved['config_json'])['context_length']==context_length
    assert client.get(url+'?author=true').json()['source_text']==source


def test_review_context_resume_keeps_completed_world(api):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'review context recovery'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    raw=rich()
    raw['characters'][0]['fields']['Биография']='Деталь. '*5000
    with patch('backend.services.preparation.chat_stream',return_value=iter([json.dumps(raw)])) as provider:
        created=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'})
        jid=created.json()['id']
        failed=wait_job(client,jid)
        assert failed['status']=='error' and 'Контекст 32768' in failed['error']
        assert provider.call_count==1
    repo=app.state.repository
    before=json.loads(repo.preparation_job(jid)['response_journal'])['responses']['world']
    d=client.get(url+'?author=true').json()
    assert d['candidate']['characters'][0]['fields']['Биография']==raw['characters'][0]['fields']['Биография']
    def review_only(**kw):
        assert kw['messages'][0]['content'].startswith(review.MARKER)
        yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=review_only) as provider:
        resumed=client.post(url+'/resume',json={'revision':d['revision'],'context_length':65536,'api_key':'test'})
        assert resumed.status_code==200,resumed.text
        assert wait_job(client,jid)['status']=='saved'
        assert provider.call_count==1
    assert json.loads(repo.preparation_job(jid)['response_journal'])['responses']['world']==before
    assert client.get(url+'?author=true').json()['state']['characters'][0]['fields']['Биография']==raw['characters'][0]['fields']['Биография']


@pytest.mark.parametrize('status',[429,503])
def test_confirmed_http_retry_keeps_category(status):
    class Repo:
        def save_response_journal(self,*a):pass
        def preparation_progress(self,*a):pass
        def draft_phase(self,*a):pass
    calls=[];journal={}
    def generate(*args):
        calls.append(args)
        if len(calls)==1:raise ProviderHTTPError('rejected',status)
        yield '{}'
    with patch.object(Event,'wait',return_value=False):
        assert response(Repo(),'job',journal,'world',[{'role':'user','content':'idea'}],REMOTE,32768,generate,Event())=='{}'
    assert len(calls)==2 and journal['pending'] is None
    assert journal['http_failures'][0]['status']==status


def test_creative_new_facts_and_optional_recommendations_are_accepted(api):
    client,app=api;w=client.post('/api/workspaces',json={'name':'creative'}).json();url=f"/api/workspaces/{w['id']}/draft"
    raw=rich();calls=[]
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            assert 'Отсутствие в исходном тексте не ошибка' in kw['messages'][0]['content']
            yield json.dumps({'issues':[{'path':'/world/roles/extra','message':'Можно добавить хобби','severity':'recommendation'}]})
        else:yield json.dumps(raw)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='saved'
    final=client.get(url+'?author=true').json()
    assert len(calls)==2
    for section in ('facts','knowledge','roles','objective_relations'):
        assert final['state']['world'][section]==initial.normalize(raw)['world'][section]
    assert final['state']['characters']==initial.inspect_candidate(raw)[0]['characters']


def test_unknown_request_explicit_resume_preserves_history_and_manual_revision(tmp_path):
    repo=Repository(tmp_path/'unknown.sqlite');w=repo.create_workspace('unknown')
    cfg=dict(REMOTE,_draft_task='world',_draft_input=SHORT,_draft_token_budget=30000)
    jid=repo.begin_preparation(w['id'],'draft_world',SHORT,cfg,0)
    repo.save_draft_candidate(jid,rich(),[])
    repo.save_response_journal(jid,{'pending':{'slot':'review','text':'partial'},'reserved_tokens':999})
    repo.preparation_progress(jid,'','error')
    d=repo.draft(w['id'],True)
    repo.edit_candidate(w['id'],d['revision'],'/campaign/title','Manual title')
    d=repo.draft(w['id'],True)
    with pytest.raises(ValueError,match='неизвестен'):repo.resume_draft_response(jid,revision=d['revision'])
    updated=repo.resume_draft_response(jid,revision=d['revision'],config_changes={'max_tokens':4096},acknowledge_unknown=True)
    journal=json.loads(repo.preparation_job(jid)['response_journal'])
    assert journal['unknown_attempts'][0]['text']=='partial'
    assert journal['reserved_tokens']==999 and updated['_draft_token_budget']==30000
    assert json.loads(journal['candidate_text'])['campaign']['title']=='Manual title'
