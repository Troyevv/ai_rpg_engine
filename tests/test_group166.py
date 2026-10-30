"""PR166 follow-up: event/spontaneous pacing and actual group communication jobs."""
import json
from copy import deepcopy
from threading import Event
from unittest.mock import patch

import pytest
from backend.runtime_v3.group_planning import opportunities, record_attempt, pending
from backend.runtime_v3.remote_initiative import stage
from backend.runtime_v3.communication import run
from backend.runtime_v3.models import Motivation, Relationship
from test_group152 import group, provider
from test_remote_communication import command


@pytest.mark.parametrize('change',['thread','relationship','intention','message'])
def test_new_canonical_context_bypasses_time_and_old_context_is_consumed(change):
    s,gid=group();record_attempt(s,gid,'initial',{})
    s['world_state']['meta']['turn_id']+=1
    assert not opportunities(s['world_state'])
    state=s['world_state']
    if change=='thread':state['threads']['topic']['state']='Новый этап обсуждения'
    elif change=='relationship':state['relationships']['b:c']=Relationship(source_id='b',target_id='c',context='Сблизились').model_dump()
    elif change=='intention':state['characters']['b']['intentions'].append(Motivation(id='new-intent',text='Спросить про работу').model_dump())
    else:s=command(s,'send',conversation_id=gid,content='Есть новости.')
    assert opportunities(s['world_state'])
    gen,calls=provider(gid,silent=True)
    out=stage(s,gen,'fresh-context')
    assert len(calls)==1
    if change!='message':assert not out['world_state']['remote_events']
    out.pop('_remote_batch');out['world_state']['meta']['turn_id']+=1
    assert not opportunities(out['world_state'])
    out['world_state']['meta']['world_time']+=30
    assert opportunities(out['world_state'])


def test_spontaneous_without_intention_thread_or_event_and_null_attempt_is_paced():
    s,gid=group();s['world_state']['threads']={}
    calls=[]
    def spontaneous(stage_name,messages,*args,**kwargs):
        calls.append(stage_name)
        if stage_name=='remote_group_semantics':return iter(['{"requests":[]}'])
        data=json.loads(messages[1]['content']);option=data['groups'][0]
        assert not any(a['intentions'] for a in option['actors'])
        return iter([json.dumps(dict(action=None,group_series=dict(conversation_id=gid,messages=[
            dict(actor_id='b',content='Как дела с работой?',basis_ids=option['basis']['b']),
            dict(actor_id='c',content='Сегодня наконец выходной!',basis_ids=option['basis']['c'],read_previous=True)])))])
    out=stage(s,spontaneous,'spontaneous')
    assert len(out['world_state']['remote_events'])==2 and len(calls)==2
    out.pop('_remote_batch');out['world_state']['meta']['turn_id']+=1
    assert stage(out,spontaneous,'no-loop')==out and len(calls)==2
    out['world_state']['meta']['world_time']+=30
    gen,calls=provider(gid,silent=True)
    declined=stage(out,gen,'decline-spontaneous')
    assert len(calls)==1 and declined['world_state']['remote_events']==out['world_state']['remote_events']


def test_group_message_bypasses_cooldown_multiple_speakers_and_returning_speaker():
    s,gid=group();record_attempt(s,gid,'previous-attempt',{})
    s=command(s,'send',conversation_id=gid,content='Как дела?')
    source=list(s['world_state']['remote_events'])[-1]
    calls=[]
    def generate(index,messages):
        calls.append(messages)
        return json.dumps(dict(messages=[dict(actor_id=a,content=f'Реплика {i}',basis_ids=[source],read_previous=i>0)
            for i,a in enumerate(['b','c','b','c','b','c'])]))
    after,batch,report=run(s,dict(source_event_id=source,owner_id='a',request_id='group-react-six'),generate,Event())
    assert len(calls)==1 and report['accepted']==['send']*6
    rows=list(after['world_state']['remote_events'].values())
    assert len(rows)==7 and rows[0]['read_by']==['b','c']
    assert 'c' in rows[1]['read_by'] and 'b' in rows[2]['read_by']
    assert after['world_state']['camera']==s['world_state']['camera']
    assert not opportunities(after['world_state'])


@pytest.mark.parametrize('silent_answer',[False,True])
def test_api_jobs_meeting_retry_variants_reload_and_cost(tmp_path,silent_answer):
    import engine
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from test_phone122 import dispatch
    from group152_provider import response, HELLO, QUESTION, ACCEPT
    from context_builder import estimate
    app=create_app(tmp_path/'group166.sqlite',recover=False);repo=app.state.repository;client=TestClient(app)
    sid=load_fixture(repo,'phone')['save'];calls=[];fail=[False]
    def stream(**kwargs):
        ms=kwargs['messages'];calls.append(ms)
        if fail[0] and ms[0]['content'].startswith('Remote semantic extraction/'):
            fail[0]=False;raise RuntimeError('controlled extraction outage')
        if silent_answer and ms[0]['content'].startswith('Group communication reaction/') and json.loads(ms[1]['content'])['source_message']['content']==ACCEPT:
            yield '{"messages":[]}'
        else:
            yield response(ms,bool(kwargs.get('response_format')))
    def execute(jid,ok=True):
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
        assert repo.get_job(jid)['status']==('saved' if ok else 'error'),repo.get_job(jid)['error']
    def turn(kind='turn'):
        jid=repo.begin_job(sid,'Смотрю на дождь.' if kind=='turn' else '',kind,CONFIG);execute(jid);return jid
    def phone(action,**extra):
        r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(
            action=action,conversation_id='qa-group',operation_id=f'group166-{action}-{repo.get_save(sid)["revision"]}',**extra)))
        assert r.status_code==200,r.text
    def state():return repo.get_snapshot(sid)['world_state']
    turn('start');phone('join',member_ids=['qa_timur','qa_oleg'])
    before=deepcopy(state())
    jid=dispatch(repo,client,sid,HELLO,'hello-group166','qa-group');fail[0]=True;execute(jid,False)
    assert len(state()['remote_events'])==1 # command durable; replies still atomic
    author_count=sum(m[0]['content'].startswith('Group communication reaction/') for m in calls)
    repo.retry_job(jid,CONFIG);execute(jid)
    assert sum(m[0]['content'].startswith('Group communication reaction/') for m in calls)==author_count==1
    assert [e['sender_id'] for e in state()['remote_events'].values()]==['qa_kirill','qa_timur','qa_oleg','qa_timur']
    assert state()['camera']==before['camera'] and not state()['scheduled_events']
    n=len(calls);execute(jid);assert len(calls)==n
    original=repo.list_turns(sid)[-1]
    turn('regenerate')
    assert len(state()['remote_events'])==4
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    # The communication source is consumed. A short next turn cannot trigger
    # another response; after 30 world minutes spontaneous discussion is allowed.
    turn();assert len(state()['remote_events'])==4
    turn();assert len(state()['remote_events'])==6 and pending(state(),'qa-group')
    assert not state()['scheduled_events'] # invitation is not consent
    phone('read');assert pending(state(),'qa-group')
    silent_before=deepcopy(state()['remote_events']);turn()
    assert state()['remote_events']==silent_before and pending(state(),'qa-group')
    jid=dispatch(repo,client,sid,ACCEPT,'accept-group166','qa-group');n=len(calls);execute(jid)
    assert len(calls)-n==3 # existing response extraction + one group author + consequences
    assert not pending(state(),'qa-group') and len(state()['remote_events'])==(7 if silent_answer else 10)
    plan=state()['scheduled_events']['group152-meeting']
    assert plan['status']=='pending' and set(plan['character_ids'])=={'qa_kirill','qa_oleg'}
    assert plan['remote_source_ids'] and plan['location_id'] is None
    assert repo.get_save(sid)['state']['world']['scheduled_events']
    saved=deepcopy(state());assert Repository(repo.path).get_snapshot(sid)['world_state']==saved
    turn();assert state()['remote_events']==saved['remote_events']
    repo.rollback_last(sid);assert state()==saved
    # Deterministic telemetry, not provider-billed tokens.
    logs=repo.request_log(job_id=jid)
    assert len(logs)==3 and all(r['status']=='complete' for r in logs)
    print('GROUP166_COST',[(r['stage'],r.get('diagnostics',{}).get('estimated_tokens'),r.get('max_tokens')) for r in logs])
    print('GROUP166_ALL_INPUT_ESTIMATES',[(m[0]['content'].split('.')[0][:36],estimate(m)) for m in calls if m[0]['content'].startswith(('Select at most ONE','Group response extraction/','Group communication reaction/','Remote semantic extraction/'))])
    print('GROUP166_INPUT_ESTIMATES',[estimate(m) for m in calls[-5:] if m[0]['content'].startswith(('Group communication reaction/','Remote semantic extraction/'))])


def test_offscreen_canonical_event_is_consumed_and_no_global_time_gate():
    s,gid=group();record_attempt(s,gid,'before-world-event',{})
    s['world_state']['meta']['turn_id']+=1
    event=dict(id='offscreen-work',participants=['b','c'],text='Обсудили работу без ГГ.',player_observed=False)
    gen,calls=provider(gid,question=False)
    out=stage(s,gen,'new-offscreen',history_events=[event])
    assert len(calls)==2 and len(out['world_state']['remote_events'])==3
    out.pop('_remote_batch');out['world_state']['meta']['turn_id']+=1
    assert not opportunities(out['world_state'],[event])
    assert not opportunities(out['world_state'],[event,event])
    assert opportunities(out['world_state'],[event,dict(event,id='another-event')])


def test_relationship_and_thread_consequences_use_common_resolver_and_receipts(tmp_path):
    from backend.runtime_v3.remote import apply
    from backend.runtime_v3.remote_semantics import resolve, relationship_sources
    from backend.runtime_v3.repository import relationship_reader, append_history
    from backend.repositories.preparation import Repository
    repo=Repository(tmp_path/'receipts.sqlite')
    s,gid=group()
    s,_=apply(s,dict(action='send',conversation_id=gid,content='Помогу с работой.',operation_id='offer-work'),actor_id='b',autonomous=True)
    eid=list(s['world_state']['remote_events'])[-1]
    s,_=apply(s,dict(action='read',event_id=eid,operation_id='read-work'),actor_id='c',autonomous=True)
    camera=s['world_state']['camera']
    payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),
        relationship_changes=[dict(source_id='c',target_id='b',dimensions=dict(trust=3),assertion='grounded_feelings',
            source_event_ids=[eid],rationale='Прочитал предложение помощи.',evidence='Помогу с работой.')],
        thread_changes=[dict(id='work-help',description='Совместная работа',character_ids=['b','c'],status='active',
            source_event_id=eid,evidence='Помогу с работой.')])
    query=relationship_reader(repo,None,candidates=relationship_sources(s))
    result,batch=resolve(s,eid,payload,relationship_query=query)
    assert result['world_state']['relationships']['c:b']['dimensions']['trust']==3
    assert 'work-help' in result['world_state']['threads']
    with repo.connect() as db:
        head=append_history(db,None,batch);db.commit()
    payload['relationship_changes'][0]['dimensions']['trust']=5
    query=relationship_reader(repo,head,candidates=relationship_sources(result))
    warnings=[]
    again,_=resolve(result,eid,payload,warnings,relationship_query=query)
    assert again['world_state']['relationships']['c:b']['dimensions']['trust']==3
    assert any(w['code']=='relationship_source_invalid' for w in warnings)
    # Delivery alone cannot make a participant feel something about unread text.
    payload['relationship_changes'][0].update(source_id='a',target_id='b')
    warnings=[];resolve(s,eid,payload,warnings,relationship_query=relationship_reader(repo,None,candidates=relationship_sources(s)))
    assert any(w['code']=='relationship_source_invalid' for w in warnings)


def test_legacy_group_journal_contract_and_cancelled_new_cycle():
    from test_communication_cycle import decision
    s,gid=group();s=command(s,'send',conversation_id=gid,content='Привет.')
    source=list(s['world_state']['remote_events'])[-1]
    request=dict(source_event_id=source,owner_id='a',request_id='legacy-group-cycle')
    prompts=[]
    def generate(i,m):prompts.append(m);return decision(m)
    after,_,report=run(s,request,generate,Event(),legacy_group=True)
    assert report['accepted']==['read','send'] and len(prompts)==2
    assert all(not m[0]['content'].startswith('Group communication reaction/') for m in prompts)
    cancelled=Event();cancelled.set()
    assert run(s,request,lambda *args:pytest.fail('cancelled call'),cancelled) is None
