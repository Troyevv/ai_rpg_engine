"""Controlled regressions reduced from the private Life248 provider evidence."""
from copy import deepcopy
import json
from threading import Event
import pytest
from llm import OutputLimitReached
from backend.services.draft_response import response, TransportError
from backend.services import draft_initial, draft_repair
from backend.runtime_v3.secrets import initialize_authored_secrets
from test_draft_response_v4 import JournalRepo, MESSAGES
from test_initial_draft_v4 import rich

CONFIG=dict(provider='deepseek', model='deepseek-flash', thinking='low', temperature=.8, max_tokens=24000)

class Receipts(JournalRepo):
    def request_log(self, **kw):
        return [dict(id='receipt', input_tokens=100, output_tokens=24000, cost_usd='.02883', finish_reason='length', usage_json=json.dumps(dict(prompt_tokens=100,completion_tokens=24000,completion_tokens_details=dict(reasoning_tokens=24000))))]

def exhausted():
    repo=Receipts(); journal={}
    def empty(*_):
        raise OutputLimitReached()
        yield
    with pytest.raises(TransportError,match='reasoning'):
        response(repo,'j',journal,'world',MESSAGES,CONFIG,131072,empty,Event())
    return repo,journal

def test_changed_output_recovers_without_erasing_receipts_or_repeating():
    repo,journal=exhausted();old=deepcopy(journal['responses']['world']);calls=[]
    def provider(messages,limit):calls.append((messages,limit));yield '{"recovered":true}'
    result=response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000),131072,provider,Event())
    assert json.loads(result)=={'recovered':True}
    assert len(calls)==1 and calls[0][1]==32000  # world ceiling, not repair sizing
    assert journal['responses']['world']==old
    assert journal['actual_tokens']==48200 and journal['reserved_tokens']==0
    assert response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000),131072,lambda *_:pytest.fail('paid replay'),Event())==result

@pytest.mark.parametrize('changes,context', [({},131072), ({},262144), ({'temperature':.1},131072)])
def test_ineffective_policy_change_does_not_retry(changes,context):
    repo,journal=exhausted();old=deepcopy(journal['responses']['world']['parts'])
    with pytest.raises(TransportError):response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,**changes),context,lambda *_:pytest.fail('same failed request'),Event())
    assert journal['responses']['world']['parts']==old

def secret_world(status='known'):
    return dict(characters={'a':{}}, facts={'f':dict(story_secret=True,secret_keeper_ids=['a'])},knowledge={'model_key':dict(actor_id='a',fact_id='f',status=status,evidence='Own relationship',source_event_id='original',revision=3)})

def test_secret_initialization_reuses_pair_and_preserves_provenance():
    world=secret_world();old=deepcopy(world)
    initialize_authored_secrets(world);initialize_authored_secrets(world)
    assert world==old

@pytest.mark.parametrize('status',['unknown','refuted','suspected'])
def test_secret_initialization_never_overrides_conflicting_pair(status):
    world=secret_world(status);old=deepcopy(world)
    with pytest.raises(ValueError):initialize_authored_secrets(world)
    assert world==old

def mixed_candidate():
    state=rich();cid=state['characters'][0]['id'];fid=next(iter(state['world']['facts']))
    state['characters'][0]['portrait_traits']={'hair':'short','clothing':'dress'}
    state['world']['knowledge']={'original':dict(actor_id=cid,fact_id=fid,status='known',evidence='Original'), 'duplicate':dict(actor_id=cid,fact_id=fid,status='known',evidence='')}
    return state

def test_portrait_and_knowledge_errors_share_bounded_repair_scope():
    raw=mixed_candidate();before=deepcopy(raw);_,report=draft_initial.inspect_candidate(raw)
    assert raw==before
    paths={d['path'] for d in report['diagnostics']}
    assert '/characters/0/portrait_traits' in paths
    assert '/world/knowledge/duplicate/evidence' in paths
    _,scope=draft_repair.request(json.dumps(raw),report['diagnostics'])
    answer=dict(patches=[dict(path='/characters/0/portrait_traits',value={'hair':'short'}),dict(path='/world/knowledge/duplicate/evidence',value='Original')])
    repaired=json.loads(draft_repair.apply(json.dumps(raw),json.dumps(answer),scope))
    _,report=draft_initial.inspect_candidate(repaired)
    assert not report['errors'], report
    assert repaired['characters'][0]['fields']==raw['characters'][0]['fields']
    assert raw==before
    answer['patches'][0]['value']['hair']='long'
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(raw),json.dumps(answer),scope)

def test_changed_policy_failure_does_not_reopen_old_policy_via_ignored_sampling():
    repo,journal=exhausted()
    def empty(*_):
        raise OutputLimitReached()
        yield
    with pytest.raises(TransportError):response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000),131072,empty,Event())
    with pytest.raises(TransportError):response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,temperature=.1),131072,lambda *_:pytest.fail('old failed wire policy'),Event())
    assert len(journal['responses'])==2


def test_partial_json_survives_empty_length_and_policy_recovery():
    repo=Receipts();journal={};calls=[]
    def partial(messages,limit):
        calls.append(messages)
        if len(calls)==1:yield '{"value":"'
        raise OutputLimitReached()
    with pytest.raises(TransportError):response(repo,'j',journal,'world',MESSAGES,CONFIG,131072,partial,Event())
    old=deepcopy(journal['responses']['world'])
    def suffix(messages,limit):
        assert messages[-2]['content']=='{"value":"'
        yield 'kept"}'
    assert response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000),131072,suffix,Event())=='{"value":"kept"}'
    assert journal['responses']['world']==old


def test_changed_policy_still_respects_aggregate_budget():
    repo,journal=exhausted();old=deepcopy(journal['responses']['world'])
    with pytest.raises(TransportError,match='бюджет токенов'):
        response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000,_draft_token_budget=24100),131072,lambda *_:pytest.fail('budget bypass'),Event())
    assert journal['responses']['world']==old


def test_unknown_response_never_recovers_by_changing_policy():
    repo,journal=exhausted();journal['pending']=dict(slot='world',text='unknown',offset=0)
    before=deepcopy(journal)
    with pytest.raises(TransportError):response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,max_tokens=32000),131072,lambda *_:pytest.fail('unknown outcome replay'),Event())
    assert journal==before


def test_invalid_portrait_consumption_is_atomic():
    from backend.services.draft_portraits import consume_authored_traits
    raw=mixed_candidate();raw['characters'][1]['portrait_traits']={'hair':'long'};old=deepcopy(raw)
    with pytest.raises(ValueError):consume_authored_traits(raw)
    assert raw==old

from unittest.mock import patch
from test_api import api, wait_job
from backend.repositories.preparation import Repository


def test_production_world_job_recovers_length_with_changed_limit_and_reload(api):
    from backend.services import draft_creative, draft_completeness
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Low recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    def empty(**kw):
        assert kw['thinking']=='low'
        kw['on_usage'](dict(prompt_tokens=100,completion_tokens=24000,completion_tokens_details=dict(reasoning_tokens=24000)))
        kw['on_finish']('length')
        raise OutputLimitReached()
        yield
    with patch('backend.services.preparation.chat_stream',side_effect=empty):
        q=client.post(url+'/generate',json=dict(revision=0,text='Семья возвращается домой.',config=dict(CONFIG,context_length=131072),api_key='test'))
        assert q.status_code==200,q.text
        jid=q.json()['id'];assert wait_job(client,jid)['status']=='error'
    before=json.loads(repo.preparation_job(jid)['response_journal']);old_requests=repo.request_log(job_id=jid)
    calls=[]
    def provider(**kw):
        calls.append(kw)
        system=kw['messages'][0]['content']
        if system.startswith(draft_creative.MARKER):
            payload=json.loads(kw['messages'][1]['content']);answer=dict(candidate_hash=payload['candidate_hash'],rationale='Controlled fixture, no artistic evaluation.',changes=[])
            assert kw['thinking']=='low'
        elif system.startswith(draft_completeness.MARKER):
            answer={'issues':[]};assert kw['thinking']=='off'
        else:
            assert len(calls)==1 and kw['max_tokens']==32000 and kw['thinking']=='low'
            answer=rich()
        kw['on_usage'](dict(prompt_tokens=100,completion_tokens=100));kw['on_finish']('stop')
        yield json.dumps(answer,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        q=client.post(url+'/resume',json=dict(revision=0,max_tokens=32000,api_key='test'))
        assert q.status_code==200,q.text
        job=wait_job(client,jid);assert job['status']=='saved',job
    after=json.loads(repo.preparation_job(jid)['response_journal'])
    assert after['responses']['world']==before['responses']['world']
    assert after['actual_tokens']==before['actual_tokens']+600
    assert len(calls)==3
    final=client.get(url+'?author=true').json()
    q=client.post(url+'/confirm',json=dict(revision=final['revision'],version_id=final['version_id'],accept_warnings=True));assert q.status_code==200,q.text
    sid=q.json()['save'];assert repo.get_snapshot(sid)==Repository(repo.path).get_snapshot(sid)
    assert [x for x in repo.request_log(job_id=jid) if x['id'] in {v['id'] for v in old_requests}]==old_requests


def test_deepseek_wire_low_length_reports_reasoning_usage_without_visible_json():
    import httpx
    from openai import OpenAI
    import llm
    received=[];usage=[];finish=[];visible=[]
    def handler(request):
        body=json.loads(request.content);received.append(body)
        assert body['thinking']=={'type':'enabled'} and body['reasoning_effort']=='low'
        assert body['max_tokens']==24000 and 'temperature' not in body
        assert body['response_format']=={'type':'json_object'}
        chunks=[dict(id='test',object='chat.completion.chunk',created=0,model='deepseek-flash',choices=[dict(index=0,delta={'reasoning_content':'test reasoning'},finish_reason=None)]),
                dict(id='test',object='chat.completion.chunk',created=0,model='deepseek-flash',choices=[dict(index=0,delta={},finish_reason='length')],usage=dict(prompt_tokens=10957,completion_tokens=24000,total_tokens=34957,completion_tokens_details=dict(reasoning_tokens=24000)))]
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
    def client(**kw):return OpenAI(api_key='test',base_url='https://offline.test',http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with patch('llm.OpenAI',side_effect=client),pytest.raises(OutputLimitReached):
        for chunk in llm.chat_stream('deepseek-flash',MESSAGES,provider='deepseek',api_key='test',thinking='low',max_tokens=24000,require_complete=True,response_format={'type':'json_object'},on_usage=usage.append,on_finish=finish.append):visible.append(chunk)
    assert len(received)==1 and visible==[] and finish==['length']
    assert usage[0]['completion_tokens_details']['reasoning_tokens']==usage[0]['completion_tokens']==24000
