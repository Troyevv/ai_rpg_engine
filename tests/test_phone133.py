"""PR #133: real SDK payload/HTTP boundary; controlled transport, NOT live DeepSeek."""
import json
from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI

import engine
from llm import chat_stream, ProviderHTTPError
from test_phone122 import setup, read, dispatch, execute
from test_narrative_test_world import CONFIG, ordinary_job
from test_communication_cycle import decision
from phone_semantic_fixture import extract

GREETING='Привет. Ты занята сегодня?'
REPLY='Привет. Ещё в офисе, разгребаю бумаги. А что, есть планы?'
CONFIG_DS={**CONFIG,'provider':'deepseek','model':'deepseek-flash'}


def sdk_factory(handler):
    return lambda **kw: OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def sse(value):
    chunk=dict(id='contract-test',object='chat.completion.chunk',created=1,model='deepseek-flash',
        choices=[dict(index=0,delta=dict(content=value),finish_reason='stop')])
    return httpx.Response(200,headers={'content-type':'text/event-stream'},content='data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n')


def rejection():
    return httpx.Response(400,json={'error':{'type':'invalid_request_error','param':'messages',
        'message':"messages must contain the word json to use response_format json_object"}})


def test_json_contract_failure_before_fix_and_real_sdk_payload_after(tmp_path):
    repo,client,sid=setup(tmp_path)
    jid=dispatch(repo,client,sid,GREETING)
    execute(repo,jid)
    prompts=next(f['messages'] for f in json.loads(repo.get_job(jid)['context_json']) if f['stage']=='remote_semantics')
    old=deepcopy(prompts)
    old[0]['content']=old[0]['content'].replace('Return one valid JSON object matching the supplied schema. ','')
    data=json.loads(old[1]['content']);data.pop('example_json_output');old[1]['content']=json.dumps(data,ensure_ascii=False)
    assert not any('json' in m['content'].lower() for m in old)
    captured=[]
    def transport(request):
        payload=json.loads(request.content);captured.append(payload)
        assert request.url.path=='/chat/completions'
        assert payload['model']=='deepseek-flash'
        assert payload['response_format']=={'type':'json_object'}
        assert payload['thinking']=={'type':'disabled'}
        assert payload['stream_options']=={'include_usage':True}
        assert payload['max_tokens']==CONFIG_DS['update_tokens']
        assert 'json_schema' not in payload
        assert len(request.content)<32000  # actual two-message fixture payload
        if not any('json' in m['content'].lower() for m in payload['messages']):return rejection()
        return sse(json.dumps(extract(json.loads(payload['messages'][1]['content']))))
    with patch('llm.OpenAI',side_effect=sdk_factory(transport)):
        with pytest.raises(ProviderHTTPError) as failed:
            list(chat_stream('deepseek-flash',old,provider='deepseek',api_key='test-only-key',max_tokens=CONFIG_DS['update_tokens'],response_format={'type':'json_object'}))
        assert failed.value.status_code==400
        assert failed.value.diagnostic['reason']=='json_instruction_required'
        result=''.join(chat_stream('deepseek-flash',prompts,provider='deepseek',api_key='test-only-key',max_tokens=CONFIG_DS['update_tokens'],response_format={'type':'json_object'},require_complete=True))
    assert json.loads(result)['final_scene']
    assert len(captured)==2  # SDK retries remain disabled.


def test_api_deepseek_semantic_recovery_reuses_read_reply_and_saves_safe_diagnostic(tmp_path):
    repo,client,sid=setup(tmp_path)
    before=repo.get_snapshot(sid)['world_state']
    with patch('engine.launch'):
        response=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG_DS,api_key='test-only-key',command=dict(action='send',operation_id='http-regression',contact_id='phone-qa_kirill-qa-vera',content=GREETING)))
    assert response.status_code==200,response.text
    jid=response.json()['job']['id'];calls=[];fail=True
    def transport(request):
        payload=json.loads(request.content);ms=payload['messages']
        semantic=ms[0]['content'].startswith('Remote semantic extraction/')
        calls.append('semantic' if semantic else 'decision')
        if semantic:
            if fail:
                return httpx.Response(400,json={'error':{'type':'invalid_request_error','param':'messages',
                    'message':'messages JSON contract rejected; test-only-key; PRIVATE ECHO', 'code':'PRIVATE ECHO'}})
            return sse(json.dumps(extract(json.loads(ms[1]['content']))))
        value=json.loads(decision(ms,'answer'))
        if value.get('action',{}).get('action')=='send':value['action']['content']=REPLY
        return sse(json.dumps(value))
    def run():
        with patch('llm.OpenAI',side_effect=sdk_factory(transport)):
            engine.run_job(repo.path,jid,engine.Worker(api_key='test-only-key',epoch=repo.get_job(jid)['attempt_epoch']))
    run();assert repo.get_job(jid)['status']=='error'
    assert calls==['decision','decision','semantic']
    requests=repo.request_log(job_id=jid)
    diagnostic=next(r for r in requests if r['stage']=='remote_semantics')['diagnostics']['provider_error']
    assert diagnostic['http_status']==400 and diagnostic['request']['has_json_instruction']
    assert 'PRIVATE' not in json.dumps(diagnostic)
    assert 'test-only-key' not in json.dumps(diagnostic)
    state=repo.get_snapshot(sid)['world_state'];assert len(state['remote_events'])==1
    assert state['meta']['world_time']==before['meta']['world_time']
    fail=False
    with patch('engine.launch'):
        assert client.post(f'/api/jobs/{jid}/retry',json=dict(config=CONFIG_DS,api_key='test-only-key')).status_code==200
    run();assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert calls==['decision','decision','semantic','semantic']
    state=repo.get_snapshot(sid)['world_state'];assert len(state['remote_events'])==2
    assert [e['content'] for e in state['remote_events'].values()]==[GREETING,REPLY]
    assert state['meta']['world_time']==before['meta']['world_time']+1
    assert not state['scheduled_events']
    read(repo,client,sid)
    nextid=dispatch(repo,client,sid,'Спасибо!',operation='http-followup');execute(repo,nextid)
    assert repo.get_job(nextid)['status']=='saved'
    ordinary_job(repo,sid)
    with repo.connect() as db: dump='\n'.join(db.iterdump())
    assert 'test-only-key' not in dump and 'PRIVATE ECHO' not in dump


def test_physical_choices_follow_history_not_latest_phone_job(tmp_path):
    repo,client,sid=setup(tmp_path)
    initial=client.get(f'/api/saves/{sid}').json();source=initial['physical_choice_source'];assert source
    initial_count=len(initial['turns'])
    jid=dispatch(repo,client,sid,GREETING);execute(repo,jid)
    read(repo,client,sid)
    after=client.get(f'/api/saves/{sid}').json()
    assert len(after['turns'])==initial_count+1
    assert after['physical_choice_source']==source
    # Physical scene edits invalidate old choices without a synthetic turn.
    meta=repo.get_save(sid)['state']['scene_meta']
    repo.update_scene_meta(sid,dict(time=meta['time'],location='Другое место',present_ids=meta['present_ids']))
    assert client.get(f'/api/saves/{sid}').json()['physical_choice_source'] is None


def test_physical_choice_route_stops_at_mixed_event_and_variant_lineage():
    from backend.runtime_v3.surfaces import physical_choice_source
    state=dict(camera=dict(controlled_actor_id='a',pov_actor_id='a',location_id='room',present_character_ids=['a'],situation='quiet'),characters={'a':dict(location_id='room',life_status='alive')})
    turn=dict(id=1,kind='start',active_variant_id='v1',presentation={'surface':'physical'},after_json=json.dumps({'world_state':state}))
    remote=dict(id=2,kind='turn',active_variant_id='v2',presentation={'surface':'call'})
    assert physical_choice_source([turn,remote],state)==dict(turn_id=1,variant_id='v1')
    remote['presentation']['physical_text']='Someone entered.'
    assert physical_choice_source([turn,remote],state) is None
    assert physical_choice_source([turn],state)['variant_id']=='v1' # rollback
    turn['active_variant_id']='v3'
    assert physical_choice_source([turn],state)['variant_id']=='v3'
