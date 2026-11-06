import json
import pytest
from backend.runtime_v3.remote_decision import parse, RemoteDecision
from test_communication_cycle import ready, dispatch, execute
import engine
from unittest.mock import patch


@pytest.mark.parametrize('raw', ['{}','"answer"','[]','{"action":"answer"}','', '{', '{"action":null}{}', '{"action":null,"extra":1}'])
def test_invalid_is_not_silence(raw):
    with pytest.raises(ValueError): parse(raw)


def test_flat_and_wrapper_are_equivalent():
    proposal=dict(actor_id='npc',action='answer',event_id='call',basis_ids=['call'])
    a, diagnostic=parse(json.dumps(proposal))
    b,_=parse(json.dumps({'action':proposal}))
    assert a==b and diagnostic['normalized_flat']
    assert parse('{"action":null}')[0] is None
    schema=RemoteDecision.model_json_schema()
    assert schema['required']==['action']
    assert '$defs' in schema


def test_error_does_not_finalize_call_and_retry_replaces_bad_frame(tmp_path):
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    before=repo.get_snapshot(sid)
    with patch('engine.chat_stream',return_value=iter(['{"action":"answer"}'])):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before
    assert len(repo.list_turns(sid))==1
    repo.retry_job(jid)
    execute(repo,jid)
    assert repo.get_job(jid)['status']=='saved'
    frame=json.loads(repo.get_job(jid)['context_json'])[0]
    assert frame['previous_attempt']['response']=='{"action":"answer"}'
    assert frame['accepted']
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==1


def test_production_prompt_schema_matches_parser():
    from backend.runtime_v3.remote_initiative import planning_context
    from test_remote_communication import phone
    from backend.runtime_v3.remote_decision import VERSION
    prompt=planning_context(phone(),[])[0]['content']
    schema=json.loads(prompt.split('Schema: ',1)[1])
    assert schema==RemoteDecision.model_json_schema()
    assert schema['required']==['action']
    for marker in ('Example (substitute only listed IDs): ', 'No action example: '):
        sample,_=json.JSONDecoder().raw_decode(prompt.split(marker,1)[1])
        parse(json.dumps(sample))
    assert parse('{"action":null}')[1]['contract']==VERSION


@pytest.mark.parametrize('raw',['{}','{"action":null,"action":{}}','{"action":{"actor_id":"a","action":"answer","event_id":"bad","basis_ids":["bad"]}}'])
def test_failed_call_preserves_durable_command(tmp_path,raw):
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call');before=repo.get_snapshot(sid)
    with patch('engine.chat_stream',return_value=iter([raw])):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before
    assert len(repo.list_turns(sid))==1


def test_failed_schema_after_read_replays_only_accepted_step(tmp_path):
    from test_communication_cycle import decision
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid);before=repo.get_snapshot(sid);calls=[]
    def provider(**kw):
        calls.append(kw)
        yield decision(kw['messages']) if len(calls)==1 else '{}'
    with patch('engine.chat_stream',side_effect=provider):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    assert repo.get_snapshot(sid)==before
    frames=json.loads(repo.get_job(jid)['context_json']);assert frames[0]['accepted'] and not frames[1]['accepted']
    repo.retry_job(jid)
    assert len(execute(repo,jid))==2  # remaining reply + semantic extraction; accepted read is replayed
    assert repo.get_job(jid)['status']=='saved'
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==2


def test_legacy_saved_rejected_recovery_archives_later_turns(tmp_path):
    from backend.runtime_v3.communication import run
    from backend.runtime_v3.remote_initiative import planning_context
    from backend.runtime_v3.communication import options_for
    from test_narrative_test_world import CONFIG, ordinary_job
    from threading import Event
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    job=repo.get_job(jid);before=repo.get_snapshot(sid);config=json.loads(job['config_json'])
    request=config['communication']
    after,batch,report=run(before,request,lambda *a:'{"action":null}',Event())
    report['rejected']=['legacy schema failure']
    messages=planning_context(before,options_for(before,request['source_event_id'],set()))
    messages[0]['content']='Legacy contradictory schema'
    repo.save_communication_context(jid,[dict(messages=messages,response='{"action":"answer"}')],before)
    repo.job_progress(jid,'validating',narrative='Вызов завершён без ответа. Решение связи отклонено проверкой; ответ не применён.',complete=True)
    repo.commit_job(jid,after,[],{'communication':report},history_batch=batch)
    old=repo.list_turns(sid)[-1];original=repo.get_snapshot(sid)
    ordinary_job(repo,sid)
    regen=repo.begin_job(sid,'','regenerate',dict(CONFIG,target_turn_id=old['id'],rollback_following=True))
    execute(repo,regen)
    assert repo.get_job(regen)['status']=='saved',repo.get_job(regen)['error']
    result=repo.get_snapshot(sid)
    assert len(result['world_state']['remote_events'])==1
    assert next(iter(result['world_state']['remote_events'].values()))['status']=='answered'
    assert original['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+2
    assert result['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+1
    repo.select_variant(sid,old['id'],old['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==original['world_state']


@pytest.mark.parametrize('flat',[False,True])
def test_wrapped_and_legacy_endpoint_identification_reach_canonical_apply(flat):
    from test_remote_communication import phone,command
    from backend.runtime_v3.remote_initiative import opportunities,accept
    s=command(phone(),'add_contact',label='Неизвестный',address='address-b')
    cid=list(s['world_state']['contacts'])[-1]
    s=command(s,'call',contact_id=cid);eid=list(s['world_state']['remote_events'])[-1]
    p=dict(actor_id='endpoint',action='identify',event_id=eid,basis_ids=[eid],speaker_name='Борис',existing_character_id='b')
    parsed,_=parse(json.dumps(p if flat else {'action':p}))
    linked,_=accept(s,parsed,opportunities(s['world_state']),'identify-test')
    assert linked['world_state']['remote_events'][eid]['status']=='answered'
    assert linked['world_state']['contacts'][cid]['character_id']=='b'


@pytest.mark.parametrize('raw',['{}','{"action":null}','{"action":"answer"}'])
def test_ordinary_optional_stage_uses_same_contract_without_remote_mutation(raw):
    from test_remote_communication import phone,command
    from backend.runtime_v3.remote_initiative import stage
    snap=command(phone(),'call',contact_id='a-b')
    result=stage(snap,lambda *a,**kw:iter([raw]),'ordinary-decision')
    assert result['world_state']==snap['world_state']
    kind=result['_remote_batch']['state_changes'][0]['kind']
    assert kind==('remote_no_action' if raw=='{"action":null}' else 'remote_rejected')


def test_private_communication_diagnostics_are_save_scoped(tmp_path):
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from devtools.narrative_test_world import load_fixture
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    other=load_fixture(repo,'phone')['save']
    client=TestClient(create_app(repo.path))
    view=client.get(f'/api/saves/{sid}/phone/diagnostics/{jid}')
    assert view.status_code==200 and view.json()['source']['owner_id']=='qa_kirill'
    assert view.json()['requests']==[]
    assert client.get(f'/api/saves/{other}/phone/diagnostics/{jid}').status_code>=400


def test_concurrent_retry_claims_only_one_attempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    with patch('engine.chat_stream',return_value=iter(['{}'])):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    def retry():
        try: repo.retry_job(jid);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:retry(),range(2)))==[False,True]
    execute(repo,jid)
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==1


def test_legacy_flat_checkpoint_replays_without_provider(tmp_path):
    from test_communication_cycle import decision
    from backend.runtime_v3.remote_initiative import planning_context
    from backend.runtime_v3.communication import options_for
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    before=repo.get_snapshot(sid);request=json.loads(repo.get_job(jid)['config_json'])['communication']
    messages=planning_context(before,options_for(before,request['source_event_id'],set()))
    raw=json.dumps(json.loads(decision(messages))['action'])
    repo.save_communication_context(jid,[dict(messages=messages,response=raw)],before)
    with patch('engine.chat_stream',side_effect=AssertionError('legacy frame should replay')):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    frame=json.loads(repo.get_job(jid)['context_json'])[0]
    assert frame['response']==raw and frame['accepted'] and frame['parser']['normalized_flat']


@pytest.mark.parametrize('field,value',[('action','invented'),('actor_id',17),('basis_ids',[]),('extra','conflict')])
def test_invalid_proposal_fields_not_repaired(field,value):
    p=dict(actor_id='npc',action='answer',event_id='call',basis_ids=['call']);p[field]=value
    with pytest.raises(ValueError):parse(json.dumps({'action':p}))


@pytest.mark.parametrize('flat', [False, True])
def test_legacy_group_journal_replays_decisions_and_semantics_after_reload(tmp_path, flat):
    from threading import Event
    from test_phone122 import setup, dispatch as phone_dispatch
    from test_communication_cycle import decision
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.communication import run
    from backend.runtime_v3.remote_semantics import messages as semantic_messages
    from phone_semantic_fixture import extract
    repo,client,sid=setup(tmp_path)
    jid=phone_dispatch(repo,client,sid,conversation='qa-group')
    before=repo.get_snapshot(sid)
    request=json.loads(repo.get_job(jid)['config_json'])['communication']
    frames=[]
    def recorded(index,messages):
        value=json.loads(decision(messages))
        if value['action']['action']=='send':value['action']['content']='Да, договорились.'
        response=json.dumps(value['action'] if flat else value,ensure_ascii=False)
        frames.append(dict(messages=messages,response=response)) # old checkpoint: no stage/contract
        return response
    after,_,_=run(before,request,recorded,Event(),legacy_group=True)
    prompts=semantic_messages(after,request['source_event_id'])
    response=json.dumps(extract(json.loads(prompts[1]['content'])),ensure_ascii=False)
    frames.append(dict(stage='remote_semantics',messages=prompts,response=response,accepted=True))
    repo.save_communication_context(jid,frames,before)
    repo=Repository(repo.path)
    with patch('engine.chat_stream',side_effect=AssertionError('all source-bound frames must replay')):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==2 and len(state['scheduled_events'])==1
    assert state['camera']==before['world_state']['camera']
    assert not repo.request_log(job_id=jid)
    journal=json.loads(repo.get_job(jid)['context_json'])
    assert [f['response'] for f in journal]==[f['response'] for f in frames]
    assert all(f['accepted'] for f in journal)
    assert all(f['parser']['normalized_flat']==flat for f in journal[:2])
