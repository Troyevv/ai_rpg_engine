"""#152: canonical series, semantic agency, persistence and bounded provider cost."""
import json
from copy import deepcopy
import pytest
from backend.runtime_v3.models import Character, Thread, assert_world_state_v3_invariants
from backend.runtime_v3.remote import apply, projection
from backend.runtime_v3.remote_initiative import stage
from backend.runtime_v3.group_planning import pending, opportunities, context
from backend.runtime_v3.remote_semantics import resolve
from test_remote_communication import phone, command


def group():
    s = phone()
    s['world_state']['characters']['c'] = Character(id='c', display_name='C', life_status='alive').model_dump()
    s = command(s, 'create_group', label='Общая переписка', member_ids=['b', 'c'])
    gid = next(iter(s['world_state']['conversations']))
    s['world_state']['threads']['topic'] = Thread(id='topic', description='Обсудить фотографии', character_ids=['b','c']).model_dump()
    return s, gid


def provider(gid, *, question=True, silent=False):
    calls = []
    def generate(name, messages, limit, temperature, **kwargs):
        calls.append((name, messages, limit))
        data = json.loads(messages[1]['content'])
        if name == 'remote_group_semantics':
            value = dict(requests=[dict(message_index=1, target_id='a', evidence='Ты придёшь?',
                expires_at=data['world_time']+120)] if question else [])
        elif silent:
            value = dict(action=None, group_series=None)
        else:
            value = dict(action=None, group_series=dict(conversation_id=gid,messages=[
                dict(actor_id='b',content='Покажешь свои фотографии?',basis_ids=['topic']),
                dict(actor_id='c',content='Покажу завтра. Ты придёшь?' if question else 'Покажу завтра. А помнишь А?',basis_ids=['topic'],read_previous=True),
                dict(actor_id='b',content='Принесу альбом.',basis_ids=['topic'],read_previous=True)]))
        return iter([json.dumps(value, ensure_ascii=False)])
    return generate, calls


def staged(question=True):
    s,gid=group();gen,calls=provider(gid,question=question)
    out=stage(s,gen,'group-152-op')
    assert not any(r['kind']=='remote_rejected' for r in out['_remote_batch']['state_changes']),out['_remote_batch']
    return out,gid,calls


def test_t01_t02_t04_series_stops_at_question_and_knowledge_is_local():
    before,gid=group();out,_,calls=staged()
    rows=list(out['world_state']['remote_events'].values())
    assert len(rows)==2 and [r['sender_id'] for r in rows]==['b','c']
    assert rows[0]['read_by']==['c'] and rows[1]['read_by']==[]
    assert all(r['world_time']==before['world_state']['meta']['world_time'] for r in rows)
    assert all('a' in r['recipient_ids'] for r in rows)
    assert [r['ordinal'] for r in rows]==[1,2]
    assert len(pending(out['world_state'],gid))==1
    assert out['world_state']['camera']==before['world_state']['camera']
    assert out['world_state']['characters']==before['world_state']['characters']
    assert len(calls)==2 and [c[0] for c in calls]==['remote_initiative','remote_group_semantics']
    assert not projection(out)['conversations'][0]['awaiting_response'] # no semantic preview before reading
    assert all(r['content'] is None for r in projection(out)['events'])


def test_t02_t05_mention_is_not_pause_three_distinct_events():
    out,gid,calls=staged(False)
    rows=list(out['world_state']['remote_events'].values())
    assert len(rows)==3 and [r['sender_id'] for r in rows]==['b','c','b']
    assert not pending(out['world_state'],gid)
    assert rows[1]['read_by']==['b']
    assert len({r['operation_id'] for r in rows})==3


def test_t03_silence_cooldown_and_no_reason():
    s,gid=group();s['world_state']['threads']={}
    gen,calls=provider(gid,silent=True)
    empty=stage(s,gen,'empty-152')
    assert len(calls)==1 and not empty['world_state']['remote_events']
    calls.clear()
    s,gid=group();out=stage(s,gen,'silent-152')
    assert not out['world_state']['remote_events'] and len(calls)==1
    out.pop('_remote_batch');out['world_state']['meta']['turn_id']+=1
    assert stage(out,gen,'silent-153')==out and len(calls)==1
    out['world_state']['meta']['turn_id']+=1;out['world_state']['meta']['world_time']+=30
    assert opportunities(out['world_state'])


def test_t06_t07_read_and_ordinary_turn_not_response_expiry_no_answer():
    out,gid,_=staged();out=command(out,'read',conversation_id=gid)
    assert pending(out['world_state'],gid)
    assert projection(out)['conversations'][0]['awaiting_response']
    from backend.runtime_v3.resolver import StateResolver
    state=out['world_state'];camera=state['camera']
    result=StateResolver(state,'В комнате тихо.','Жду.').resolve(dict(final_scene=dict(
        location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1)))
    assert pending(result.state,gid)
    result.state['meta']['world_time']+=120
    assert not pending(result.state,gid)
    assert all(not (r.get('response_request') or {}).get('resolved_by') for r in result.state['remote_events'].values())


@pytest.mark.parametrize('answer,assertion',[('Да, приду.','answered'),('Нет, не приду.','refused')])
def test_t06_explicit_response_through_existing_semantic_resolver(answer,assertion):
    out,gid,_=staged();out=command(out,'read',conversation_id=gid)
    request=pending(out['world_state'],gid)[0]
    out=command(out,'send',conversation_id=gid,content=answer)
    response=list(out['world_state']['remote_events'].values())[-1]
    state=out['world_state'];c=state['camera']
    raw=dict(final_scene=dict(location_id=c['location_id'],present_character_ids=c['present_character_ids'],elapsed_minutes=0),
        group_response_changes=[dict(request_event_id=request['id'],response_event_id=response['id'],assertion=assertion,evidence=answer)])
    after,batch=resolve(out,response['id'],raw)
    assert not pending(after['world_state'],gid)
    assert after['world_state']['remote_events'][request['id']]['response_request']['resolved_by']==response['id']
    assert any(r.get('kind')=='group_response' for r in batch['state_changes'])
    again,_=resolve(after,response['id'],raw)
    assert again['world_state']==after['world_state']


def test_t08_t09_privacy_legacy_membership_death_and_no_control():
    out,gid,_=staged();state=out['world_state']
    assert all('Ты придёшь?' not in json.dumps(a,ensure_ascii=False) for g in context(out,[dict(conversation_id=gid,actor_ids=['b','c'],basis={'b':['topic']})]) for a in g['actors'] if a['id']=='b')
    state['characters']['c']['life_status']='dead'
    assert not pending(state,gid)
    legacy=phone()['world_state']
    assert assert_world_state_v3_invariants(legacy)
    s,gid=group();s['world_state']['camera'].update(controlled_actor_id=None,mode='observer')
    gen,calls=provider(gid,question=False)
    assert len(stage(s,gen,'no-controlled')['world_state']['remote_events'])==3


def test_t10_t11_idempotent_staged_snapshot_and_large_time_jump():
    out,gid,calls=staged(False)
    def forbidden(*args,**kwargs):raise AssertionError('extra call')
    assert stage(out,forbidden,'group-152-op') is out
    loaded=json.loads(json.dumps(out));loaded.pop('_remote_batch')
    loaded['world_state']=assert_world_state_v3_invariants(loaded['world_state'])
    assert not opportunities(loaded['world_state'])
    loaded['world_state']['meta']['world_time']+=525600
    loaded['world_state']['meta']['turn_id']+=2
    gen,calls=provider(gid,question=False)
    after=stage(loaded,gen,'after-one-year')
    assert len(calls)==2 and len(after['world_state']['remote_events'])==6


def test_t12_real_api_jobs_sqlite_reload_rollback_regenerate_cost(tmp_path):
    from unittest.mock import patch
    import engine
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from test_phone122 import dispatch
    from group152_provider import response, FIRST, QUESTION, ANSWER, CONTINUED
    app=create_app(tmp_path/'group152.sqlite',recover=False)
    repo=app.state.repository;client=TestClient(app)
    sid=load_fixture(repo,'phone')['save']
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs['messages'][0]['content'].split('.')[0])
        if kwargs['messages'][0]['content'].startswith('Group response extraction/'):
            conflict=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(
                action='leave',conversation_id='qa-group',operation_id='concurrent-group-change')))
            assert conflict.status_code==409, conflict.text
        yield response(kwargs['messages'],bool(kwargs.get('response_format')))
    def execute(jid):
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}), patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    def turn(kind='turn'):
        jid=repo.begin_job(sid,'Смотрю на дождь.' if kind=='turn' else '',kind,CONFIG)
        execute(jid)
        return jid
    turn('start')
    r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='join',conversation_id='qa-group',operation_id='join-group-152',member_ids=['qa_timur','qa_oleg'])))
    assert r.status_code==200,r.text
    before=repo.get_snapshot(sid)
    jid=turn();state=repo.get_snapshot(sid)['world_state']
    assert [e['content'] for e in state['remote_events'].values()]==[FIRST,QUESTION]
    assert pending(state,'qa-group') and len(calls)==6 # start 2 + author/semantic/narrative/extraction 4
    assert state['camera']==before['world_state']['camera']
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    count=len(calls);execute(jid);assert len(calls)==count # duplicate completed job is no-op
    original=repo.list_turns(sid)[-1]
    turn('regenerate')
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==2
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='read',conversation_id='qa-group',operation_id='read-group-152')))
    assert r.status_code==200,r.text
    assert pending(repo.get_snapshot(sid)['world_state'],'qa-group')
    jid=dispatch(repo,client,sid,ANSWER,'answer-group-152','qa-group');execute(jid)
    assert not pending(repo.get_snapshot(sid)['world_state'],'qa-group')
    turn();state=repo.get_snapshot(sid)['world_state']
    assert CONTINUED in [e['content'] for e in state['remote_events'].values()]
    expected=deepcopy(state)
    reloaded=Repository(repo.path);assert reloaded.get_snapshot(sid)['world_state']==expected
    turn();assert len(repo.get_snapshot(sid)['world_state']['remote_events'])<=len(expected['remote_events'])+3
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==expected
    count=len(calls)
    jid=repo.begin_job(sid,'','long_term',dict(CONFIG,long_term_advance=dict(amount=1,unit='years',max_llm_calls=0)))
    execute(jid)
    advanced=repo.get_snapshot(sid)
    assert advanced['last_long_term_advance']['llm_calls']==0 and len(calls)==count
    assert advanced['world_state']['remote_events']==expected['remote_events']
    assert advanced['world_state']['conversations']==expected['conversations']
    turn()
    assert len(repo.get_snapshot(sid)['world_state']['remote_events']) <= len(expected['remote_events'])+3
    events=deepcopy(repo.get_snapshot(sid)['world_state']['remote_events'])
    jid=repo.begin_job(sid,'Пропускаю неделю.','turn',dict(CONFIG,time_skip=dict(duration=10080)))
    execute(jid)
    assert repo.get_snapshot(sid)['world_state']['remote_events']==events
    assert not any(r['stage'] in ('remote_initiative','remote_group_semantics') for r in repo.request_log(job_id=jid))


def test_t04_other_groups_and_direct_conversations_are_independent():
    out,gid,_=staged()
    out=command(out,'create_group',operation_id='second-group-152',member_ids=['b','c'],label='Другая группа')
    other=next(c['id'] for c in out['world_state']['conversations'].values() if c['id']!=gid)
    out['world_state']['meta']['turn_id']+=1
    assert [o['conversation_id'] for o in opportunities(out['world_state'])]==[other]
    direct,_=apply(out,dict(action='send',contact_id='b-a',content='Личное сообщение.',operation_id='direct-independent'),actor_id='b',autonomous=True)
    assert pending(direct['world_state'],gid)
    with pytest.raises(ValueError,match='group_awaiting_response'):
        apply(out,dict(action='send',conversation_id=gid,content='Продолжение.',operation_id='bypass-wait'),actor_id='b',autonomous=True)


def test_t07_invalid_response_sources_cannot_clear_pending():
    out,gid,_=staged();out=command(out,'read',conversation_id=gid)
    request=pending(out['world_state'],gid)[0]
    out=command(out,'send',character_id='b',content='Нет.',operation_id='wrong-chat-response')
    response=list(out['world_state']['remote_events'].values())[-1]
    c=out['world_state']['camera']
    raw=dict(final_scene=dict(location_id=c['location_id'],present_character_ids=c['present_character_ids'],elapsed_minutes=0),
        group_response_changes=[dict(request_event_id=request['id'],response_event_id=response['id'],assertion='refused',evidence='Нет.')])
    after,batch=resolve(out,response['id'],raw)
    assert pending(after['world_state'],gid)
    assert not any(r.get('kind')=='group_response' for r in batch['state_changes'])


@pytest.mark.parametrize('mutation',['leave','dead','incapacitated','channel','resolved_topic'])
def test_t09_stale_candidate_revalidated_without_partial_messages(mutation):
    from backend.runtime_v3.group_planning import GroupSeries,GroupSemantics,accept_series
    s,gid=group();options=opportunities(s['world_state'])
    if mutation=='leave':s=command(s,'remove',conversation_id=gid,member_ids=['b'])
    elif mutation=='dead':s['world_state']['characters']['b']['life_status']='dead'
    elif mutation=='incapacitated':s['world_state']['characters']['b']['capabilities']['conscious']=False
    elif mutation=='channel':s['world_state']['meta']['communication']['text_message']=False
    else:s['world_state']['threads']['topic']['status']='resolved'
    series=GroupSeries(conversation_id=gid,messages=[dict(actor_id='b',content='Привет.',basis_ids=['topic'])])
    before=deepcopy(s)
    with pytest.raises(ValueError):accept_series(s,series,GroupSemantics(requests=[]),options,'stale-group')
    assert s==before and not s['world_state']['remote_events']


def test_no_literary_length_cap_and_context_budget_no_provider_call():
    s,gid=group()
    long='Длинный художественный текст. '*1000
    after,_=apply(s,dict(action='send',conversation_id=gid,content=long,operation_id='long-group-text'),actor_id='b',autonomous=True)
    assert next(iter(after['world_state']['remote_events'].values()))['content']==long
    gen,calls=provider(gid)
    result=stage(s,gen,'small-context',context_limit=1000)
    assert not calls and not result['world_state']['remote_events']
    assert result['_remote_batch']['state_changes'][0]['code']=='group_context_budget'


def test_group_without_controlled_actor_membership_is_canonical_and_private():
    s,gid=group();s=command(s,'leave',conversation_id=gid)
    gen,calls=provider(gid,question=False)
    after=stage(s,gen,'npc-only-group')
    assert len(after['world_state']['remote_events'])==3
    assert projection(after)['events']==[]
    assert not any(k['actor_id']=='a' and k['fact_id'].startswith('communicated_text') for k in after['world_state']['knowledge'].values())


def test_t10_retry_reuses_staged_series_after_extraction_transport_failure(tmp_path):
    from unittest.mock import patch
    import engine
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from group152_provider import response
    app=create_app(tmp_path/'retry152.sqlite',recover=False);repo=app.state.repository;client=TestClient(app)
    sid=load_fixture(repo,'phone')['save']
    calls=[];fail=[True]
    def stream(**kwargs):
        system=kwargs['messages'][0]['content'];calls.append(system.split('.')[0])
        if not system.startswith(('Select at most ONE','Group response extraction/','Remote semantic extraction/')) and kwargs.get('response_format') and fail[0] and any('accepted_semantic_messages' in m['content'] for m in kwargs['messages']):
            fail[0]=False;raise RuntimeError('controlled transport failure')
        yield response(kwargs['messages'],bool(kwargs.get('response_format')))
    def execute(jid):
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    start=repo.begin_job(sid,'','start',CONFIG);execute(start)
    r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(
        action='join',conversation_id='qa-group',operation_id='join-retry-group',member_ids=['qa_timur','qa_oleg'])))
    assert r.status_code==200,r.text
    before=repo.get_snapshot(sid)
    jid=repo.begin_job(sid,'Смотрю в окно.','turn',CONFIG);execute(jid)
    assert repo.get_job(jid)['status']=='error' and repo.get_snapshot(sid)==before
    assert len([x for x in calls if x.startswith('Select at most ONE')])==1
    repo.retry_job(jid);execute(jid)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert len([x for x in calls if x.startswith('Select at most ONE')])==1
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==2


def test_group_backlog_never_becomes_per_npc_per_message_provider_calls():
    out,gid,_=staged(False);out.pop('_remote_batch')
    out['world_state']['meta']['turn_id']+=1
    gen,calls=provider(gid,question=False)
    assert stage(out,gen,'cooldown-next-turn')==out
    assert calls==[]


def test_existing_group_message_semantic_request_uses_same_lifecycle():
    out,gid=group()
    out,_=apply(out,dict(action='send',conversation_id=gid,content='Ты придёшь?',operation_id='existing-request'),actor_id='b',autonomous=True)
    e=list(out['world_state']['remote_events'].values())[-1];c=out['world_state']['camera']
    raw=dict(final_scene=dict(location_id=c['location_id'],present_character_ids=c['present_character_ids'],elapsed_minutes=0),
        group_request_changes=[dict(source_event_id=e['id'],target_id='a',evidence='Ты придёшь?',expires_at=e['world_time']+120)])
    after,batch=resolve(out,e['id'],raw)
    assert pending(after['world_state'],gid)[0]['id']==e['id']
    again,_=resolve(after,e['id'],raw)
    assert again['world_state']==after['world_state']


def test_expired_requests_do_not_accumulate_in_semantic_context():
    from backend.runtime_v3.remote_semantics import evidence_slice
    out,gid,_=staged();state=out['world_state'];request=pending(state,gid)[0]
    state['meta']['world_time']+=200
    for i in range(50):
        out,_=apply(out,dict(action='send',conversation_id=gid,content='Новая тема.',operation_id=f'expired-context-{i}'),actor_id='b',autonomous=True)
    rows=evidence_slice(out['world_state'],list(out['world_state']['remote_events'])[-1])
    assert len(rows)==24 and request['id'] not in {e['id'] for e in rows}


def test_t10_legacy_defaults_do_not_rewrite_input_snapshot():
    out,gid,_=staged()
    legacy=deepcopy(out['world_state'])
    for c in legacy['conversations'].values():c.pop('initiative_pacing',None)
    for e in legacy['remote_events'].values():e.pop('response_request',None)
    original=deepcopy(legacy)
    loaded=assert_world_state_v3_invariants(legacy)
    assert legacy==original
    assert loaded['conversations'][gid]['initiative_pacing'] is None
    assert all(e['response_request'] is None for e in loaded['remote_events'].values())
    assert not pending(loaded,gid)


def test_optional_semantic_outage_defers_whole_series_without_partial_knowledge():
    before,gid=group();gen,calls=provider(gid)
    def failing(stage_name,*args,**kwargs):
        if stage_name=='remote_group_semantics':raise RuntimeError('provider outage')
        return gen(stage_name,*args,**kwargs)
    result=stage(before,failing,'semantic-outage')
    assert not result['world_state']['remote_events']
    assert result['world_state']['knowledge']==before['world_state']['knowledge']
    assert result['_remote_batch']['state_changes'][0]['code']=='group_provider_failed'
    assert result['world_state']['conversations'][gid]['initiative_pacing']


def test_leave_and_rejoin_does_not_resurrect_a_pending_request():
    out,gid,_=staged()
    request=pending(out['world_state'],gid)[0]['id']
    out=command(out,'remove',conversation_id=gid,member_ids=['c'])
    out=command(out,'join',conversation_id=gid,member_ids=['c'])
    assert not pending(out['world_state'],gid)
    annotation=out['world_state']['remote_events'][request]['response_request']
    assert annotation['closed_reason']=='membership' and annotation['resolved_by'] is None


def test_competing_requests_keep_separate_sources_and_stable_order():
    out,gid=group()
    for i,actor in enumerate(['b','c']):
        out,_=apply(out,dict(action='send',conversation_id=gid,content=f'Вопрос {i}?',operation_id=f'competing-{i}'),actor_id=actor,autonomous=True)
    events=list(out['world_state']['remote_events'].values());c=out['world_state']['camera']
    raw=dict(final_scene=dict(location_id=c['location_id'],present_character_ids=c['present_character_ids'],elapsed_minutes=0),
        group_request_changes=[dict(source_event_id=e['id'],target_id='a',evidence=e['content'],expires_at=e['world_time']+120) for e in reversed(events)])
    after,_=resolve(out,events[-1]['id'],raw)
    assert [e['id'] for e in pending(after['world_state'],gid)]==[e['id'] for e in events]
    after=command(after,'read',conversation_id=gid)
    after=command(after,'send',conversation_id=gid,content='Нет, по первому вопросу.',operation_id='one-of-two-response')
    answer=list(after['world_state']['remote_events'].values())[-1]
    raw.pop('group_request_changes')
    raw['group_response_changes']=[dict(request_event_id=events[0]['id'],response_event_id=answer['id'],assertion='refused',evidence=answer['content'])]
    result,_=resolve(after,answer['id'],raw)
    assert [e['id'] for e in pending(result['world_state'],gid)]==[events[1]['id']]
