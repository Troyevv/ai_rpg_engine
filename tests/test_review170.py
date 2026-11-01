"""Issue 170: synthetic fixture or local private export, controlled provider."""
import json
import os
from copy import deepcopy
from decimal import Decimal
from threading import Event
from unittest.mock import patch
import pytest
from test_api import api, wait_job
from test_draft_response_v4 import JournalRepo, MESSAGES
from review170_fixture import exported, restore
from backend.repositories.preparation import Repository
from backend.services.draft_response import response, TransportError, review_config, empty_diagnostic
from backend.services.draft_generation import review_signature
from backend.services import draft_completeness as review
from llm import OutputLimitReached

CONFIG=dict(provider='deepseek',model='deepseek-flash',thinking='high',temperature=.7,max_tokens=24000,context_length=65536)


@pytest.mark.skipif(not os.environ.get('RPG_REVIEW170_EXPORT'),reason='Private export is not published; set RPG_REVIEW170_EXPORT for original evidence')
def test_real_export_evidence():
    data=exported();requests=[r for r in data['requests'] if r['stage']=='draft_world_validation']
    assert len(requests)==5
    assert len(data['candidate_snapshot']['characters'])==len(data['candidate_snapshot']['locations'])==11
    assert data['current_diagnostics']==[]
    for r in requests:
        assert r['finish_reason']=='length'
        usage=json.loads(r['usage_json'])
        assert usage['completion_tokens_details']['reasoning_tokens']==r['output_tokens']
    parts=[p for k,v in data['responses'].items() if k.startswith('completeness_') for p in v['parts']]
    assert len(parts)==5 and all(p['text']=='' for p in parts)
    assert all(empty_diagnostic(p)['code']=='reasoning_budget_exhausted' for p in parts)


@pytest.mark.parametrize('reason,reasoning,code', [('length',10984,'reasoning_budget_exhausted'),('length',None,'empty_output_limit'),('stop',0,'provider_empty_response')])
def test_empty_terminal_is_diagnosed_once(reason,reasoning,code):
    class Repo(JournalRepo):
        def request_log(self,**kw):return [dict(id='actual',input_tokens=24032,output_tokens=10984,cost_usd='.006695424',finish_reason=reason,usage_json=json.dumps({'completion_tokens_details':{'reasoning_tokens':reasoning}}))]
    repo=Repo();journal={};calls=[]
    def provider(*args):
        calls.append(args)
        if reason=='length':raise OutputLimitReached()
        yield ''
    for _ in range(2):
        with pytest.raises(TransportError):response(repo,'j',journal,'completeness_same_review',MESSAGES,CONFIG,65536,provider,Event())
    assert len(calls)==1
    record=journal['responses']['completeness_same_review']
    assert record['failure']['code']==code and len(record['parts'])==1
    assert journal['actual_tokens']==35016 and Decimal(journal['actual_cost'])==Decimal('.006695424')
    assert journal['pending'] is None and journal['reserved_tokens']==0


def test_legacy_empty_parts_do_not_trigger_a_sixth_call():
    journal=exported();slot=next(k for k,v in journal['responses'].items() if k.startswith('completeness_') and len(v['parts'])==4)
    before=deepcopy(journal['responses'][slot]['parts'])
    with pytest.raises(TransportError,match='reasoning'):
        response(JournalRepo(),'j',journal,slot,MESSAGES,CONFIG,65536,lambda *_:pytest.fail('blind repeat'),Event())
    assert journal['responses'][slot]['parts']==before


def test_signature_uses_effective_policy_and_sampling():
    assert review_config(CONFIG)['thinking']=='off' and CONFIG['thinking']=='high'
    signature=review_signature(MESSAGES,CONFIG)
    # Requested High/Off do not change the fixed review stage policy.
    assert signature==review_signature(MESSAGES,dict(CONFIG,thinking='off'))
    for changes in [dict(model='deepseek-v4-pro'),dict(temperature=.2),dict(max_tokens=4096),dict(context_length=32768),dict(_draft_stage_output_limits={'review':2048})]:
        assert signature!=review_signature(MESSAGES,dict(CONFIG,**changes))
    with patch('backend.services.draft_response.REVIEW_POLICY',2):
        assert signature!=review_signature(MESSAGES,CONFIG)


def test_compact_request_keeps_candidate_and_contract():
    state=exported()['candidate_snapshot'];messages=review.messages(state,'author')
    payload=json.loads(messages[1]['content'])
    assert payload['candidate']['world']==state['world']
    assert payload['candidate']['characters']==state['characters']
    assert 'title' in payload['record_schemas']['roles']['properties']
    assert payload['report_schema']['$defs']['ReviewIssue']['allOf']==review.report_schema()['$defs']['ReviewIssue']['allOf']


def test_real_saved_candidate_resume_integration(api):
    client,app=api;repo=app.state.repository;wid,jid=restore(repo)
    url=f'/api/workspaces/{wid}/draft';before=json.loads(repo.preparation_job(jid)['response_journal'])
    candidate=client.get(url+'?author=true').json()
    assert candidate['technical_valid'] and candidate['review']['status']=='failed'
    calls=[]
    def provider(**kw):
        calls.append(kw)
        assert kw['thinking']=='off' and kw['response_format']=={'type':'json_object'}
        assert kw['messages'][0]['content'].startswith(review.MARKER)
        assert kw['max_tokens']<=8192
        kw['on_usage'](dict(prompt_tokens=24000,completion_tokens=5,prompt_cache_hit_tokens=0))
        kw['on_finish']('stop')
        yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        resumed=client.post(url+'/resume',json={'revision':candidate['revision'],'api_key':'test'})
        assert resumed.status_code==200,resumed.text
        assert resumed.json()['attempt_epoch']==1
        assert wait_job(client,jid)['status']=='saved'
    assert len(calls)==1
    after=json.loads(repo.preparation_job(jid)['response_journal'])
    for slot,record in before['responses'].items():assert after['responses'][slot]==record
    assert after['actual_tokens']==before['actual_tokens']+24005
    final=client.get(url+'?author=true').json()
    assert final['review']['status']=='completed'
    assert final['state']==candidate['candidate']
    public=client.get(f'/api/jobs/{jid}').json()
    assert public['effective_config']['thinking']=='off' and public['pinned_config']['thinking']=='high'
    started=client.post(url+'/confirm',json={'revision':final['revision'],'version_id':final['version_id']})
    assert started.status_code==200,started.text
    sid=started.json()['save']
    from test_runtime_v3_engine import raw_for
    import engine
    from test_engine import CONFIG as RUNTIME
    for kind in ('start','turn'):
        snapshot=repo.get_snapshot(sid);job=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(RUNTIME,provider='deepseek',model='deepseek-flash',context_length=65536))
        def turn_provider(**kw):
            yield json.dumps(raw_for(snapshot)) if kw.get('response_format') else 'Разговор продолжается.'
        with patch('engine.chat_stream',side_effect=turn_provider):engine.run_job(repo.path,job,engine.Worker(api_key='test'))
        assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
        repo=Repository(repo.path)
    assert len(repo.list_turns(sid))==2


def test_failed_off_review_blocks_same_resume_but_retains_candidate(api):
    client,app=api;repo=app.state.repository;wid,jid=restore(repo);url=f'/api/workspaces/{wid}/draft'
    d=client.get(url+'?author=true').json()
    def empty(**kw):
        kw['on_finish']('length');kw['on_usage']({'prompt_tokens':24,'completion_tokens':10,'completion_tokens_details':{'reasoning_tokens':10}})
        yield ''
    with patch('backend.services.preparation.chat_stream',side_effect=empty) as provider:
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'}).status_code==200
        failed=wait_job(client,jid)
        assert failed['status']=='error' and not failed['resumable']
        d2=client.get(url+'?author=true').json()
        assert d2['candidate']==d['candidate'] and d2['technical_valid'] and d2['start_warning']
        again=client.post(url+'/resume',json={'revision':d2['revision'],'api_key':'test'})
        assert again.status_code==409
        assert provider.call_count==1


def test_empty_payload_cannot_repeat_by_changing_slot_or_epoch():
    journal={};repo=JournalRepo();calls=[]
    def provider(*args):
        calls.append(args);raise OutputLimitReached()
        yield
    for slot in ('repair_first_0','repair_first_1'):
        with pytest.raises(TransportError):response(repo,'j',journal,slot,MESSAGES,CONFIG,65536,provider,Event())
    assert len(calls)==1


def test_actual_sdk_payload_uses_disabled_thinking_for_review(api):
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock
    client,app=api;wid,jid=restore(app.state.repository)
    d=client.get(f'/api/workspaces/{wid}/draft?author=true').json()
    sdk=MagicMock();stream=MagicMock()
    stream.__iter__.return_value=iter([NS(choices=[NS(delta=NS(content='{"issues":[]}'),finish_reason='stop')],usage=None)])
    sdk.chat.completions.create.return_value=stream
    with patch('llm.OpenAI',return_value=sdk):
        r=client.post(f'/api/workspaces/{wid}/draft/resume',json={'revision':d['revision'],'api_key':'private-test'})
        assert r.status_code==200,r.text
        assert wait_job(client,jid)['status']=='saved'
    payload=sdk.chat.completions.create.call_args.kwargs
    assert payload['extra_body']=={'thinking':{'type':'disabled'}}
    assert 'reasoning_effort' not in payload and payload['temperature']==.7
    assert sdk.chat.completions.create.call_count==1
    assert payload['max_tokens']<=8192
