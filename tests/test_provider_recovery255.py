"""Free provider controls: interruptions, per-attempt provenance and recovery."""
from copy import deepcopy
import fcntl
import hashlib
import json
import sqlite3
import time
from types import SimpleNamespace as NS
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import pytest
import engine
import llm
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.services.usage import tracked_stream
from devtools.live99 import budget as budgets
from test_engine import db, CONFIG
from test_structured_extraction255 import events

pytestmark = pytest.mark.extraction_v6
SECRET = 'credential-must-not-appear-in-diagnostics'
PREFIX = '{"scene":{},"scene_steps":[{"id":"unfinished'
TEXT = 'За окном шумит дождь.'
RESULT = '{"scene":{"elapsed_minutes":1},"scene_steps":[]}'
USAGE = dict(prompt_tokens=120, completion_tokens=30, prompt_cache_hit_tokens=0)


class Stream:
    def __init__(self, seq, error=None):
        self.seq=seq;self.error=error;self.closed=False
        self.response=NS(headers={'x-request-id':'req_test255','Authorization':SECRET})
    def __iter__(self):
        yield from self.seq
        if self.error: raise self.error
    def close(self):self.closed=True


def guard_for(path):
    b=budgets.Budget(path/'budget.sqlite');budgets.action_ledger(path)
    b.authorize_stage_c(path)
    return budgets.Budget(b.path,stage_c=path)


def digest(guard,rid):
    return hashlib.sha256((guard.path.parent/'provider-streams'/f'{rid:06d}.jsonl').read_bytes()).hexdigest()


def wait(client,jid):
    for _ in range(400):
        job=client.get('/api/jobs/'+jid).json()
        if job['status'] not in ('generating','extracting','validating') and not engine.live(jid):return job
        time.sleep(.025)
    raise AssertionError('Job did not finish')


@pytest.mark.parametrize('problem',['connection','missing_terminal','terminal_mismatch','length','sdk_decode'])
def test_original_failure_metadata_precedes_adapter_translation(db,problem):
    repo,_,sid=db;cfg=dict(CONFIG,provider='deepseek',model='deepseek-flash',_extraction_contract=6)
    jid=repo.begin_job(sid,'','start',cfg)
    seq=[dict(type='response.created',response={'id':'resp_255','status':'in_progress'}),
         dict(type='response.output_text.delta',delta=PREFIX)]
    error=httpx.ReadError('echo '+SECRET) if problem=='connection' else ValueError('decode '+SECRET) if problem=='sdk_decode' else None
    if problem in ('terminal_mismatch','length'):
        seq=events(RESULT)
        seq[-1]['response']['id']='resp_255'
        if problem=='terminal_mismatch':seq[-1]['response']['output'][0]['content'][0]['text']='different'
        else:seq[-1].update(type='response.incomplete');seq[-1]['response'].update(status='incomplete',incomplete_details={'reason':'max_output_tokens'})
    stream=Stream(seq,error)
    from backend.runtime_v3.scene_steps import input_schema
    messages=[{'role':'system','content':'JSON Schema\n'+json.dumps(input_schema())}]
    with patch('llm.OpenAI') as factory:
        factory.return_value.responses.create.return_value=stream
        with pytest.raises(RuntimeError):
            list(tracked_stream(repo,llm.chat_stream,jid,'extraction',cfg,messages,
                provider='deepseek',model='deepseek-flash',api_key=SECRET,max_tokens=2000,require_complete=True))
    row,=repo.request_log(job_id=jid);trace=row['diagnostics']['provider_attempt']
    assert trace['request_id']==row['id'] and trace['attempt_epoch']==0
    assert trace['provider_response_id']=='resp_255' and not trace['stream_complete']
    assert SECRET not in json.dumps(row) and stream.closed
    if problem=='connection':assert trace['error']['type']=='ReadError'
    elif problem=='sdk_decode':assert trace['error']['type']=='ValueError'
    elif problem=='missing_terminal':assert trace['error']['code']=='missing_terminal_or_text'
    elif problem=='terminal_mismatch':assert trace['error']['code']=='terminal_mismatch' and row['input_tokens']==12
    else:assert row['finish_reason']=='length' and trace['provider_status']=='incomplete'


def test_production_retry_keeps_original_error_and_narrative_then_commit_reload_rollback(db,tmp_path,monkeypatch):
    repo,_,sid=db;guard=guard_for(tmp_path);cfg=dict(CONFIG,provider='deepseek',model='deepseek-flash')
    initial=repo.get_snapshot(sid);revision=repo.get_save(sid)['revision'];response_calls=[]
    def responses(**kwargs):
        response_calls.append(deepcopy(kwargs))
        if len(response_calls)==1:
            return Stream([dict(type='response.created',response={'id':'resp_broken255','status':'in_progress'}),
                dict(type='response.output_text.delta',delta=PREFIX)],httpx.ReadError('socket '+SECRET))
        return Stream(events(RESULT))
    chat=Stream([NS(usage=USAGE, choices=[NS(finish_reason='stop',delta=NS(content=TEXT))])])
    with patch('llm.OpenAI') as factory, patch('engine.chat_stream',guard.wrap(llm.chat_stream)), TestClient(create_app(repo.path)) as client:
        factory.return_value.chat.completions.create.return_value=chat
        factory.return_value.responses.create.side_effect=responses
        reply=client.post(f'/api/saves/{sid}/turns',json=dict(kind='start',text='',revision=revision,config=cfg,api_key=SECRET));assert reply.status_code==200
        jid=reply.json()['id'];job=wait(client,jid);assert job['status']=='error' and repo.get_snapshot(sid)==initial
        first=repo.request_log(job_id=jid);broken=first[0];trace=broken['diagnostics']['provider_attempt']
        assert trace['error']['type']=='ReadError' and trace['reservation_id']==2
        assert trace['attempt_epoch']==0 and trace['revision']==revision and broken['response_text']==PREFIX
        original_job=repo.get_job(jid)
        body=dict(config=cfg,api_key=SECRET,revision=revision,attempt_epoch=job['attempt_epoch'])
        assert client.post('/api/jobs/'+jid+'/retry',json=dict(body,revision=revision+1)).status_code==409
        assert client.post('/api/jobs/'+jid+'/retry',json=dict(body,attempt_epoch=job['attempt_epoch']+1)).status_code==409
        assert client.post('/api/jobs/'+jid+'/retry',json=body).status_code==200
        job=wait(client,jid);assert job['status']=='error' and 'Unknown paid outcome' in job['error']
        assert len(response_calls)==1 and repo.request_log(job_id=jid)[1:]==first
        rejected=repo.request_log(job_id=jid)[0]['diagnostics']['provider_attempt']
        assert rejected['attempt_epoch']==1 and rejected['dispatch_started'] is False and 'reservation_id' not in rejected
        with sqlite3.connect(guard.path) as d:assert d.execute('select input,output,settled from reservations where id=2').fetchone()==(budgets.CONTEXT,4096,0)
        sha=digest(guard,2)
        with (tmp_path/'server.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with pytest.raises(BlockingIOError):guard.charge_unknown(2,stream_sha256=sha,reason='Explicit test decision')
        with pytest.raises(ValueError,match='Changed'):guard.charge_unknown(2,stream_sha256='wrong',reason='Explicit test decision')
        resolution=guard.charge_unknown(2,stream_sha256=sha,reason='Explicit authored test; charge full reserve without claiming usage')
        assert resolution['usage_known'] is False and digest(guard,2)==sha
        # A late callback cannot erase the conservative decision/history.
        guard.settle(2,USAGE)
        with sqlite3.connect(guard.path) as d:assert d.execute('select input,output,settled from reservations where id=2').fetchone()==(budgets.CONTEXT,4096,2)
        with pytest.raises(ValueError,match='not unresolved'):guard.charge_unknown(2,stream_sha256=sha,reason='Again')
        with monkeypatch.context() as cap:
            cap.setattr(budgets,'LIMIT_CALLS',2)
            with pytest.raises(RuntimeError,match='exhausted'):guard.reserve(4096)
        body['attempt_epoch']=job['attempt_epoch']
        assert client.post('/api/jobs/'+jid+'/retry',json=body).status_code==200
        job=wait(client,jid);assert job['status']=='saved',job['error']
        assert factory.return_value.chat.completions.create.call_count==1 and len(response_calls)==2
        assert response_calls[1]==response_calls[0]  # Same actual provider schema/input/params.
        current=repo.get_job(jid)
        assert current['narrative']==TEXT and current['before_json']==original_job['before_json'] and current['context_json']==original_job['context_json']
        assert json.loads(current['config_json'])['_extraction_contract']==6
        assert next(x for x in repo.request_log(job_id=jid) if x['id']==broken['id'])==broken
        saved=repo.get_snapshot(sid)
        assert len(repo.list_turns(sid))==1
        assert client.post('/api/jobs/'+jid+'/retry',json=dict(body,attempt_epoch=2)).status_code==409
    with patch('llm.OpenAI',side_effect=AssertionError('Reload must be free')),TestClient(create_app(repo.path)) as client:
        assert client.get(f'/api/saves/{sid}').status_code==200
        assert repo.get_snapshot(sid)==saved
        rev=repo.get_save(sid)['revision']
        assert client.post(f'/api/saves/{sid}/rollback',json={'revision':rev-1}).status_code==409
        assert client.post(f'/api/saves/{sid}/rollback',json={'revision':rev}).status_code==200
        assert repo.get_snapshot(sid)['world_state']==initial['world_state'] and not repo.list_turns(sid)
    assert SECRET not in json.dumps(repo.request_log(job_id=jid))
    audit=[json.loads(x) for x in (tmp_path/'provider-streams/000002.jsonl').read_text().splitlines()]
    assert audit[0]['attempt']['request_id']==broken['id'] and audit[-1]['attempt']['error']['type']=='ReadError'
    assert audit[-1]['usage'] is None and SECRET not in json.dumps(audit)


@pytest.mark.parametrize('operation',['cancel','abandon','stale_save'])
def test_interrupted_v6_cannot_commit_after_cancel_abandon_or_changed_save(db,operation):
    repo,_,sid=db;cfg=dict(CONFIG,provider='deepseek',model='deepseek-flash');before=repo.get_snapshot(sid)
    jid=repo.begin_job(sid,'','start',cfg)
    def broken(**kwargs):
        if kwargs.get('response_format'):
            yield PREFIX
            raise httpx.ReadError('interrupted')
        yield TEXT
    with patch('engine.chat_stream',side_effect=broken):engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='error'
    recorded=repo.request_log(job_id=jid);job=repo.get_job(jid)
    if operation=='abandon':
        repo.abandon_job(sid,jid,job['revision'],job['attempt_epoch'])
        with pytest.raises(ValueError):repo.retry_job(jid)
    elif operation=='stale_save':
        # Existing canonical edit, not mutation of the failed job's immutable before.
        repo.update_scene_meta(sid,{'time':'19:00','location':'Двор','present_ids':['character_1']})
        with pytest.raises(ValueError,match='устарел'):repo.retry_job(jid)
    else:
        repo.retry_job(jid);worker=engine.Worker(epoch=repo.get_job(jid)['attempt_epoch'])
        def cancelled(**kwargs):
            assert kwargs.get('response_format')
            yield RESULT
            repo.job_progress(jid,'stopped');worker.cancelled.set()
        with patch('engine.chat_stream',side_effect=cancelled):engine.run_job(repo.path,jid,worker)
        assert repo.get_snapshot(sid)==before
    assert not repo.list_turns(sid)
    assert all(next(x for x in repo.request_log(job_id=jid) if x['id']==r['id'])==r for r in recorded)


def test_conservative_resolution_does_not_renew_money_or_forge_usage(tmp_path,monkeypatch):
    guard=guard_for(tmp_path)
    @guard.wrap
    def broken(provider,model,max_tokens,on_usage):
        yield PREFIX
        raise RuntimeError('unknown terminal')
    with pytest.raises(RuntimeError):list(broken('deepseek',budgets.MODEL,4096,lambda _:None))
    with pytest.raises(RuntimeError,match='Unknown'):guard.reserve(4096)
    guard.charge_unknown(1,stream_sha256=digest(guard,1),reason='Retain full original reserve')
    with sqlite3.connect(guard.path) as d:
        inp,out,settled,resolution=d.execute('select input,output,settled,resolution_json from reservations').fetchone()
        assert (inp,out,settled)==(budgets.CONTEXT,4096,2)
        assert json.loads(resolution)['usage_known'] is False
    monkeypatch.setattr(budgets,'LIMIT_NUSD',inp*budgets.INPUT+out*budgets.OUTPUT)
    with pytest.raises(RuntimeError,match='exhausted'):guard.reserve(4096)
