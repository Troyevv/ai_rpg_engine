"""Issue #122: actual API/job/Resolver/projection boundaries, no paid provider."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
import engine
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import scheduled_window
from backend.runtime_v3.player_calendar import visible_calendar_state
from backend.runtime_v3.remote_semantics import messages, resolve
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG, ordinary_job
from test_communication_cycle import decision
from phone_semantic_fixture import extract


def setup(tmp_path):
    app=create_app(tmp_path/'phone122.sqlite',recover=False)
    repo=app.state.repository;client=TestClient(app)
    sid=load_fixture(repo,'phone')['save']
    ordinary_job(repo,sid,'start')
    scene=repo.get_save(sid)['state']['scene_meta']
    repo.update_scene_meta(sid,dict(time='завтра 09:00',location=scene['location'],present_ids=scene['present_ids']))
    return repo,client,sid


def dispatch(repo,client,sid,text='Встретимся через два часа?',operation='phone122-offer',conversation=None):
    payload=dict(revision=repo.get_save(sid)['revision'], config=CONFIG,
        command=dict(action='send',operation_id=operation,contact_id='phone-qa_kirill-qa-vera',content=text))
    if conversation:
        payload['command'].pop('contact_id');payload['command']['conversation_id']=conversation
    with patch('engine.launch'):
        r=client.post(f'/api/saves/{sid}/phone/dispatch',json=payload)
    assert r.status_code==200,r.text
    return r.json()['job']['id']


def execute(repo,jid,fail_semantic=False,transform=None,outcome='answer'):
    calls=[]
    def stream(**kwargs):
        ms=kwargs['messages'];semantic=ms[0]['content'].startswith('Remote semantic extraction/')
        calls.append('semantic' if semantic else 'decision')
        if semantic:
            if fail_semantic: raise RuntimeError('semantic provider outage')
            data=json.loads(ms[1]['content']);value=extract(data)
            if transform:value=transform(value,data)
            yield json.dumps(value,ensure_ascii=False)
        else:yield decision(ms,outcome).replace('Да, увидимся завтра.','Да, договорились.')
    with patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return calls


def read(repo,client,sid):
    p=repo.get_save(sid)['state']['phone']
    r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='read',conversation_id=p['events'][-1]['conversation_id'],operation_id='phone122-read-'+str(repo.get_save(sid)['revision']))))
    assert r.status_code==200,r.text


def test_api_jobs_meeting_unread_read_calendar_reload_next_turn(tmp_path):
    repo,client,sid=setup(tmp_path)
    jid=dispatch(repo,client,sid);before=repo.get_snapshot(sid)
    assert execute(repo,jid)==['decision','decision','semantic']
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state'];plan=state['scheduled_events']['phone-meeting']
    assert plan['status']=='pending'
    assert scheduled_window(state,plan)['start_minute']==before['world_state']['meta']['world_time']+120
    assert not visible_calendar_state(state)['scheduled_events']
    assert not repo.get_save(sid)['state']['world']['scheduled_events']
    after=client.get(f'/api/saves/{sid}').json()
    assert after['turns'][-1]['presentation']['surface']=='phone'
    assert after['job']['presentation']['surface']=='phone'
    read(repo,client,sid)
    state=repo.get_snapshot(sid)['world_state']
    assert list(visible_calendar_state(state)['scheduled_events'])==['phone-meeting']
    date=repo.get_save(sid)['state']['world_clock']['projection']['date']
    from backend.runtime_v3.player_calendar import player_calendar
    assert player_calendar(state,date,date)['scheduled']
    reloaded=Repository(repo.path)
    assert reloaded.get_snapshot(sid)==repo.get_snapshot(sid)
    ordinary_job(reloaded,sid)
    assert len(reloaded.get_snapshot(sid)['world_state']['scheduled_events'])==1


def test_semantic_retry_keeps_accepted_checkpoints_and_clock_exactly_once(tmp_path):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    before=repo.get_snapshot(sid)
    assert execute(repo,jid,True)==['decision','decision','semantic']
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before
    with patch('engine.launch'):
        response=client.post(f'/api/jobs/{jid}/retry',json={'config':CONFIG})
    assert response.status_code==200,response.text
    assert execute(repo,jid)==['semantic']
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==2 and len(state['scheduled_events'])==1
    assert state['meta']['world_time']==before['world_state']['meta']['world_time']+1
    original_turn=repo.list_turns(sid)[-1]
    variant=original_turn['active_variant_id']
    regen=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,regen)
    assert repo.get_job(regen)['status']=='saved',repo.get_job(regen)['error']
    repo.select_variant(sid,original_turn['id'],variant,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==state
    repo.rollback_last(sid)
    assert not repo.get_snapshot(sid)['world_state']['scheduled_events']
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==1


def test_authored_intention_keeps_exact_text_and_remote_source(tmp_path):
    repo,client,sid=setup(tmp_path)
    text='Я планирую встретиться с Верой.'
    jid=dispatch(repo,client,sid,text);execute(repo,jid)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state']
    row=next(r for r in state['characters']['qa_kirill']['intentions'] if r['text']==text)
    assert row['source_event_id'] in state['remote_events']
    assert row['evidence']==text and row['status']=='active'
    assert not state['scheduled_events']


@pytest.mark.parametrize('temporal,precision', [({'day_offset':1},'day'),({'weekday':4,'day_period':'evening'},'period'),({'minute_offset':120},'exact')])
def test_relative_windows_anchor_to_proposal_not_reply_or_read(tmp_path,temporal,precision):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    def change(value,data):
        value['scheduled_event_changes'][0]['temporal']=temporal
        return value
    execute(repo,jid,transform=change)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state'];plan=state['scheduled_events']['phone-meeting']
    assert plan['time_reference_minute']==state['remote_events'][plan['remote_source_ids'][0]]['world_time']
    assert scheduled_window(state,plan)['precision']==precision
    before=deepcopy(plan);read(repo,client,sid)
    assert repo.get_snapshot(sid)['world_state']['scheduled_events']['phone-meeting']==before


def test_full_message_evidence_survives_long_thread_and_invalid_semantic_is_atomic(tmp_path):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid, 'Подробности. '*100+'Встретимся через два часа?')
    before=repo.get_snapshot(sid)
    def invalid(value,data):
        value['scheduled_event_changes'][0]['character_ids'].append('unknown')
        return value
    execute(repo,jid,transform=invalid)
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before
    repo.retry_job(jid,CONFIG);execute(repo,jid)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert len(repo.get_snapshot(sid)['world_state']['scheduled_events'])==1


@pytest.mark.parametrize('outcome,text', [('silent','Встретимся через два часа?'),('read_only','Встретимся через два часа?'),('answer','Может быть, как-нибудь встретимся?')])
def test_unconfirmed_and_hypothetical_messages_do_not_create_plan(tmp_path,outcome,text):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid,text)
    execute(repo,jid,outcome=outcome)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert not repo.get_snapshot(sid)['world_state']['scheduled_events']


def test_reschedule_cancel_one_id_and_no_read_side_effects(tmp_path):
    repo,client,sid=setup(tmp_path);execute(repo,dispatch(repo,client,sid));read(repo,client,sid)
    original=repo.get_snapshot(sid)['world_state']['scheduled_events']['phone-meeting']
    for i,assertion in enumerate(('rescheduled','cancelled')):
        text='Перенесём на завтра.' if i==0 else 'Я отменяю встречу.'
        def transform(value,data):
            authored=next(e for e in data['accepted_messages'] if e['id']==data['source_event_id'])
            reply=data['accepted_messages'][-1]
            row=dict(id='phone-meeting',assertion=assertion,evidence=text,
                remote_source_ids=[authored['id'],reply['id']],remote_time_source_id=authored['id'],
                player_assertion='explicit_choice',player_evidence=text)
            if assertion=='rescheduled':row['temporal']={'day_offset':1,'day_period':'evening'}
            return dict(final_scene=data['final_scene'],scheduled_event_changes=[row])
        jid=dispatch(repo,client,sid,text,'phone122-change-'+str(i));execute(repo,jid,transform=transform)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        read(repo,client,sid)
        state=repo.get_snapshot(sid)['world_state'];assert len(state['scheduled_events'])==1
        plan=state['scheduled_events']['phone-meeting']
        assert plan['status']==('pending' if i==0 else 'cancelled')
        if i==0:assert scheduled_window(state,plan)['start_minute']!=scheduled_window(state,original)['start_minute']
        copy=deepcopy(state);read(repo,client,sid)
        assert repo.get_snapshot(sid)['world_state']==copy


def test_full_smoke_skip_stops_at_meeting_then_evidence_resolves_and_next_turn(tmp_path):
    from runtime_v3_fixture import execute as narrative_job
    repo,client,sid=setup(tmp_path);execute(repo,dispatch(repo,client,sid));read(repo,client,sid)
    repo=Repository(repo.path)
    state=repo.get_snapshot(sid)['world_state'];deadline=scheduled_window(state,state['scheduled_events']['phone-meeting'])['start_minute']
    def run(text,records,skip=None):
        camera=repo.get_snapshot(sid)['world_state']['camera']
        payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),scheduled_event_changes=records)
        with patch('engine.launch'):
            res=client.post(f'/api/saves/{sid}/turns',json=dict(text=text,kind='turn',config=CONFIG,revision=repo.get_save(sid)['revision'],**({'time_skip':dict(duration=skip,reason='Дождаться встречи')} if skip else {})))
        assert res.status_code==200,res.text
        jid=res.json()['id']
        def provider(**kw):
            if kw['messages'][0]['content'].startswith('Select at most ONE'):
                yield '{"action":null}';return
            current=next((m['content'] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')),None)
            camera=json.loads(current.split('\n',1)[1])['camera'] if current else payload['final_scene']
            raw=deepcopy(payload)
            if camera.get('controlled_actor_id') is None:
                raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0))
            yield json.dumps(raw,ensure_ascii=False) if kw.get('response_format') else text
        with patch('engine.find_loaded_model',return_value={'config':{}}), patch('engine.chat_stream',side_effect=provider):
            engine.run_job(repo.path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    run('Жду встречи.',[],240)
    state=repo.get_snapshot(sid)['world_state']
    assert state['meta']['world_time']==deadline
    assert state['scheduled_events']['phone-meeting']['status']=='pending'
    text='Кирилл и Вера встретились, обсудили планы и разошлись.'
    run(text,[dict(id='phone-meeting',assertion='occurred',evidence=text)])
    assert repo.get_snapshot(sid)['world_state']['scheduled_events']['phone-meeting']['status']=='resolved'
    ordinary_job(repo,sid)
    assert len(repo.get_snapshot(sid)['world_state']['scheduled_events'])==1


def test_ten_long_messages_keep_plan_and_full_source_context(tmp_path):
    repo,client,sid=setup(tmp_path)
    execute(repo,dispatch(repo,client,sid,'Подробности. '*80+'Встретимся через два часа?'))
    for i in range(10):
        jid=dispatch(repo,client,sid,'Дополнение '+str(i)+'. '+'Текст. '*80,'phone122-long-'+str(i))
        execute(repo,jid)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==22 and len(state['scheduled_events'])==1
    source=next(reversed(state['remote_events']))
    wire=json.loads(messages(repo.get_snapshot(sid),source)[1]['content'])
    assert len(wire['accepted_messages'])==22
    assert wire['accepted_messages'][0]['content'].endswith('Встретимся через два часа?')


def test_group_agreement_only_assenting_pair_and_actor_owned_projection(tmp_path):
    repo,client,sid=setup(tmp_path);snapshot=repo.get_snapshot(sid)
    conversation=snapshot['world_state']['conversations']['qa-group']
    for cid in ('qa_timur','qa_asya'):
        conversation['members'].append(dict(actor_id=cid,joined_at=snapshot['world_state']['meta']['world_time'],provenance='QA explicit membership',left_at=None))
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    jid=dispatch(repo,client,sid,conversation='qa-group');execute(repo,jid)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state'];plan=state['scheduled_events']['phone-meeting']
    assert len(plan['character_ids'])==2 and 'qa_kirill' in plan['character_ids']
    assenting=next(cid for cid in plan['character_ids'] if cid!='qa_kirill')
    state['camera']['controlled_actor_id']=next(cid for cid in ('qa_asya','qa_vera','qa_timur') if cid not in plan['character_ids'])
    assert not visible_calendar_state(state)['scheduled_events']
    state['camera']['controlled_actor_id']=assenting
    assert len(visible_calendar_state(state)['scheduled_events'])==1


def test_call_agreement_mixed_physical_event_and_owner_switch(tmp_path):
    from runtime_v3_fixture import execute as narrative_job
    repo,client,sid=setup(tmp_path)
    with patch('engine.launch'):
        res=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,
            command=dict(action='call',contact_id='phone-qa_kirill-qa-vera',operation_id='phone122-call')))
    assert res.status_code==200,res.text
    execute(repo,res.json()['job']['id'])
    snapshot=repo.get_snapshot(sid);state=snapshot['world_state'];call=next(iter(state['remote_events'].values()))
    assert call['status']=='answered'
    camera=state['camera'];speech='Давай встретимся завтра.'
    physical='За дверью раздался стук.'
    answer='Вера ответила по телефону: «Да, договорились».'
    raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),events=[
        dict(id='voice',text=answer,evidence=answer,participants=['qa_kirill','qa_vera'],witnesses=['qa_kirill','qa_vera'],medium='conversation',interaction_channel='call'),
        dict(id='knock',text=physical,evidence=physical,participants=['qa_kirill'],witnesses=['qa_kirill'],medium='observation',interaction_channel='physical')],
        scheduled_event_changes=[dict(id='call-meeting',description='Встреча после звонка',character_ids=['qa_kirill','qa_vera'],temporal=dict(day_offset=1),assertion='agreed',evidence=answer,player_assertion='explicit_choice',player_evidence=speech)])
    jid=repo.begin_job(sid,speech,'turn',dict(CONFIG,interaction_channel='call'))
    narrative_job(repo,jid,raw,answer+'\n\n'+physical)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    projection=repo.list_turns(sid)[-1]['presentation']
    assert projection['surface']=='call' and projection['call_id']==call['id']
    assert projection['physical_text']==physical and projection['call_text']==answer
    state=repo.get_snapshot(sid)['world_state']
    assert state['scheduled_events']['call-meeting']['remote_call_id']==call['id']
    assert len(visible_calendar_state(state)['scheduled_events'])==1
    res=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(action='end',event_id=call['id'],operation_id='phone122-end')))
    assert res.status_code==200,res.text
    ordinary_job(repo,sid)
    repo.switch_actor(sid,'qa_timur',repo.get_save(sid)['revision'])
    view=client.get(f'/api/saves/{sid}').json()
    assert not any(t['presentation']['surface'] in ('call','phone') for t in view['turns'])
    assert 'call-meeting' not in view['state']['world']['scheduled_events']
    assert answer not in client.get(f'/api/jobs/{jid}').text


def test_autonomous_incoming_reply_uses_ordinary_extraction_without_recap(tmp_path):
    repo,client,sid=setup(tmp_path)
    execute(repo,dispatch(repo,client,sid),outcome='read_only')
    assert not repo.get_snapshot(sid)['world_state']['scheduled_events']
    calls=[]
    def provider(**kw):
        ms=kw['messages'];calls.append(ms[0]['content'])
        if ms[0]['content'].startswith('Select at most ONE'):
            options=json.loads(ms[1]['content'])['options']
            option=next(o for o in options if o['actor_id']=='qa_vera' and 'send' in o['actions'])
            yield json.dumps(dict(action=dict(actor_id='qa_vera',action='send',basis_ids=option['basis_ids'],**option['paths'][0],content='Да, договорились.')),ensure_ascii=False);return
        if not kw.get('response_format'):
            yield 'В комнате тихо.';return
        current=json.loads(next(m['content'].split('\n',1)[1] for m in ms if m['content'].startswith('Текущее состояние / GM-only\n')))
        rows=current['communication']['accepted_semantic_messages'];camera=current['camera']
        value=extract(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),accepted_messages=rows,controlled_actor_id='qa_kirill'))
        yield json.dumps(value,ensure_ascii=False)
    jid=repo.begin_job(sid,'Посмотреть в окно.','turn',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=provider):
        engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert 'Встреча по договорённости' not in client.get(f'/api/saves/{sid}').text
    assert len(calls)==3  # one remote decision, Narrative, existing Extraction
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['scheduled_events'])==1
    assert not visible_calendar_state(state)['scheduled_events']
    assert repo.list_turns(sid)[-1]['assistant_text']=='В комнате тихо.'
    read(repo,client,sid)
    assert len(visible_calendar_state(repo.get_snapshot(sid)['world_state'])['scheduled_events'])==1
