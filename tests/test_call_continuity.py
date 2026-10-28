"""Actual API -> jobs -> extraction -> atomic History -> read projections."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from test_phone122 import setup,execute,CONFIG
from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.calendar import scheduled_window
from call_continuity_fixture import OFFER,ASSENT,KNOCK,DEMAND,END,response


def connected(tmp_path):
    repo,client,sid=setup(tmp_path)
    with patch('engine.launch'):
        r=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,command=dict(action='call',contact_id='phone-qa_kirill-qa-vera',operation_id='continuity-call')))
    assert r.status_code==200,r.text
    execute(repo,r.json()['job']['id'])
    call=next(e for e in repo.get_snapshot(sid)['world_state']['remote_events'].values() if e['channel']=='VOICE_CALL')
    return repo,client,sid,call['id']


def turn(repo,client,sid,text,transform=None,jid=None,fail=False):
    if jid is None:
        with patch('engine.launch'):
            r=client.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',text=text,interaction_channel='call',config=CONFIG,revision=repo.get_save(sid)['revision']))
        assert r.status_code==200,r.text
        jid=r.json()['id']
    calls=[]
    def provider(**kw):
        if kw['messages'][0]['content'].startswith('Select at most ONE'):
            yield '{"action":null}';return
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        extraction=bool(kw.get('response_format'));calls.append('extraction' if extraction else 'narrative')
        if extraction and fail:raise RuntimeError('extraction outage')
        value=response(current,text,'completed' if extraction else None)
        if extraction and transform:value=transform(value,current)
        yield json.dumps(value,ensure_ascii=False) if extraction else value
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=provider):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return jid,calls


def saved(repo,jid):
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']


def test_full_call_atomic_continuity_calendar_reload_next_turn(tmp_path):
    repo,client,sid,cid=connected(tmp_path)
    start=repo.get_snapshot(sid)['world_state']['meta']['world_time']
    ids=[]
    for text,physical in [(OFFER,KNOCK),('Я скоро освобожусь.',DEMAND),('Тогда до встречи.','')]:
        jid,calls=turn(repo,client,sid,text);saved(repo,jid);ids.append(jid)
        assert calls==['narrative','extraction']
        view=client.get(f'/api/saves/{sid}').json()
        route=view['turns'][-1]['presentation']
        assert route['physical_text']==physical
        assert physical not in route['call_text'] if physical else True
        assert view['physical_choice_source'] is not None
        if physical:
            assert route['physical_events'][0]['id']
            assert route['physical_events'][0]['source_record_id']
            choice=next(t for t in view['turns'] if t['id']==view['physical_choice_source']['turn_id'])
            assert choice['choices'][0]['interaction_channel']=='physical'
        if text!= 'Тогда до встречи.':assert view['state']['phone']['events'][-1]['status']=='answered'
    state=repo.get_snapshot(sid)['world_state']
    assert state['remote_events'][cid]['status']=='ended'
    assert state['meta']['world_time']==start+6
    assert not state['camera']['remote_interactions']
    plan=state['scheduled_events']['office-meeting']
    assert scheduled_window(state,plan)['start_minute']==start+60
    assert plan['call_evidence'][0]['quote']==OFFER and plan['call_evidence'][1]['quote']==ASSENT
    date=view['state']['world_clock']['projection']['date']
    calendar=client.get(f'/api/saves/{sid}/calendar?start_date={date}&end_date={date}').json()
    assert 'office-meeting' in json.dumps(calendar)
    with repo.connect() as db:h,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    physical=[e for e in h['events'] if e.get('physical_text')]
    assert [e['physical_text'] for e in physical]==[KNOCK,DEMAND]
    assert [e['minute'] for e in physical]==[start+2,start+4]
    ended=[e for e in h['events'] if e.get('remote',{}).get('status')=='ended']
    assert len(ended)==1 and ended[0]['narrative_evidence']==END
    fresh=Repository(repo.path)
    assert fresh.get_snapshot(sid)==repo.get_snapshot(sid)
    # The next ordinary generation actually receives physical continuity.
    jid=repo.begin_job(sid,'Ответить Виктории.','turn',dict(CONFIG,interaction_channel='physical'))
    seen=[]
    def ordinary(**kw):
        if kw['messages'][0]['content'].startswith('Select at most ONE'):yield '{"action":null}';return
        seen.append(kw['messages'])
        if not kw.get('response_format'):yield 'Виктория ждёт ответа за дверью.';return
        camera=state['camera']
        yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0)))
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=ordinary):engine.run_job(repo.path,jid,engine.Worker())
    saved(repo,jid)
    assert DEMAND in json.dumps(seen[0],ensure_ascii=False)
    assert 'office-meeting' in json.dumps(seen[0],ensure_ascii=False)


@pytest.mark.parametrize('speech',['До свидания.','Может, встретимся?'])
def test_no_event_goodbye_manual_end_and_read_are_clock_free(tmp_path,speech):
    repo,client,sid,cid=connected(tmp_path)
    old=client.get(f'/api/saves/{sid}').json()['physical_choice_source']
    jid,_=turn(repo,client,sid,speech);saved(repo,jid)
    view=client.get(f'/api/saves/{sid}').json()
    assert view['turns'][-1]['presentation']['physical_text']==''
    assert view['physical_choice_source']==old
    assert repo.get_snapshot(sid)['world_state']['remote_events'][cid]['status']=='answered'
    assert not repo.get_snapshot(sid)['world_state']['scheduled_events']
    minute=repo.get_snapshot(sid)['world_state']['meta']['world_time']
    r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(action='end',event_id=cid,operation_id='manual-continuity-end')))
    assert r.status_code==200
    for _ in range(3):client.get(f'/api/saves/{sid}')
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==minute


def test_extraction_failure_retry_variants_rollback(tmp_path):
    repo,client,sid,cid=connected(tmp_path);before=repo.get_snapshot(sid)
    jid,calls=turn(repo,client,sid,OFFER,fail=True)
    assert repo.get_job(jid)['status']=='error' and repo.get_snapshot(sid)==before
    assert client.get(f'/api/jobs/{jid}').json()['presentation'].get('physical_text') is None
    repo.retry_job(jid,CONFIG)
    _,calls=turn(repo,client,sid,OFFER,jid=jid);saved(repo,jid)
    assert calls==['extraction']
    first=repo.get_snapshot(sid);t=repo.list_turns(sid)[-1]
    regen=repo.begin_job(sid,'','regenerate',CONFIG)
    turn(repo,client,sid,OFFER,jid=regen);saved(repo,regen)
    repo.select_variant(sid,t['id'],t['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==first['world_state']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']
    # A new sibling after rollback cannot inherit the abandoned offer/event.
    sibling,_=turn(repo,client,sid,'До свидания.');saved(repo,sibling)
    with repo.connect() as db:history,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    from backend.runtime_v3.call_continuity import sources
    evidence=sources(repo.get_snapshot(sid)['world_state'],history,'Новая реплика.','Продолжим.',99)
    assert OFFER not in [r['content'] for r in evidence.values()]
    assert not any(e.get('physical_text') for e in history['events'])


@pytest.mark.parametrize('fault',['missing_projection','forged_projection','missing_choices','player_end','unknown_call'])
def test_invalid_mixed_claims_never_partially_commit(tmp_path,fault):
    repo,client,sid,cid=connected(tmp_path);before=repo.get_snapshot(sid)
    def corrupt(value,current):
        if fault=='missing_projection':value.pop('physical_projections')
        if fault=='forged_projection':value['physical_projections'][0]['text']='Виктория вошла.'
        if fault=='missing_choices':value['choices']=[]
        if fault in ('player_end','unknown_call'):
            value['call_lifecycle_changes']=[dict(call_id=cid if fault=='player_end' else 'wrong',actor_id='qa_kirill',assertion='completed_end',evidence=KNOCK)]
        return value
    jid,_=turn(repo,client,sid,OFFER,corrupt)
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('fault',['missing_assent','forged_source','missing_player_source','wrong_time_anchor'])
def test_voice_agreement_rejects_incomplete_or_forged_history(tmp_path,fault):
    repo,client,sid,cid=connected(tmp_path)
    jid,_=turn(repo,client,sid,OFFER);saved(repo,jid)
    before=repo.get_snapshot(sid)
    def corrupt(value,current):
        plan=value['scheduled_event_changes'][0]
        if fault=='missing_assent':plan['call_evidence']=plan['call_evidence'][:1]
        if fault=='forged_source':plan['call_evidence'][0]['source_id']='other-branch:player'
        if fault=='missing_player_source':plan.pop('player_source_id')
        if fault=='wrong_time_anchor':plan['call_time_source_id']=plan['call_evidence'][1]['source_id']
        return value
    jid,_=turn(repo,client,sid,'Тогда до встречи.',corrupt)
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before
    assert repo.get_snapshot(sid)['world_state']['remote_events'][cid]['status']=='answered'


def test_npc_proposal_player_assent_and_new_evidence_for_reschedule(tmp_path):
    from types import SimpleNamespace
    from backend.runtime_v3.call_continuity import commitment_sources
    repo,client,sid,cid=connected(tmp_path)
    state=repo.get_snapshot(sid)['world_state']
    actor=state['camera']['controlled_actor_id']
    sources={
        'proposal':dict(id='proposal',call_id=cid,role='narrative',actor_id=None,content='Встретимся через час?',world_time=10),
        'assent':dict(id='assent',call_id=cid,role='player',actor_id=actor,content='Да, согласен.',world_time=12),
    }
    resolver=SimpleNamespace(before=state,protected_actor_id=actor,call_sources=sources)
    plan=dict(id='meeting',assertion='agreed',character_ids=[actor,'qa_vera'],call_evidence=[
        dict(source_id='proposal',actor_id='qa_vera',quote='Встретимся через час?',assertion='proposal'),
        dict(source_id='assent',actor_id=actor,quote='Да, согласен.',assertion='assent')])
    assert len(commitment_sources(resolver,plan))==2
    state['scheduled_events']['meeting']=deepcopy(plan)
    plan['assertion']='rescheduled'
    plan['call_evidence'].reverse()
    assert not commitment_sources(resolver,plan)
    plan['assertion']='cancelled'
    plan['decision_actor_id']='qa_vera'
    assert not commitment_sources(resolver,plan)



def test_repair_cannot_hide_missing_physical_projection(tmp_path):
    repo,client,sid,cid=connected(tmp_path);before=repo.get_snapshot(sid)
    attempts=0
    def omit(value,current):
        nonlocal attempts
        attempts+=1
        value.pop('physical_projections')
        if attempts>1:
            value['events']=[]
            value['choices']=[]
            value['final_scene'].pop('situation',None)
            value['final_scene'].pop('situation_evidence',None)
        return value
    jid,_=turn(repo,client,sid,OFFER,omit)
    assert attempts==2
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==before


def test_legacy_confirmed_physical_card_is_not_erased(tmp_path):
    from backend.runtime_v3.surfaces import committed_route
    repo,client,sid,cid=connected(tmp_path)
    job=dict(kind='turn',before_json=json.dumps(repo.get_snapshot(sid)),
        config_json=json.dumps(dict(interaction_channel='call')),narrative='Катя говорит.\n'+KNOCK)
    event=dict(interaction_channel='physical',witnesses=['qa_kirill'],text='Стук.',evidence=KNOCK)
    route=committed_route(job,dict(events=[event]))
    assert route['physical_text']=='Стук.'
    assert route['physical_events']==[]
    assert KNOCK not in route['call_text']


def test_npc_first_proposal_waits_for_player_assent_across_real_jobs(tmp_path):
    repo,client,sid,cid=connected(tmp_path)
    minute=repo.get_snapshot(sid)['world_state']['meta']['world_time']
    jid,_=turn(repo,client,sid,'Что предлагаешь?');saved(repo,jid)
    assert not repo.get_snapshot(sid)['world_state']['scheduled_events']
    jid,_=turn(repo,client,sid,'Да, согласен.');saved(repo,jid)
    state=repo.get_snapshot(sid)['world_state'];plan=state['scheduled_events']['office-meeting']
    assert plan['call_evidence'][0]['actor_id']=='qa_vera'
    assert plan['call_evidence'][1]['quote']=='Да, согласен.'
    assert scheduled_window(state,plan)['start_minute']==minute+60
    assert state['remote_events'][cid]['status']=='answered'
    anchor=state['meta']['world_time']
    jid,_=turn(repo,client,sid,'Перенесём на два часа?');saved(repo,jid)
    state=repo.get_snapshot(sid)['world_state']
    assert list(state['scheduled_events'])==['office-meeting']
    assert scheduled_window(state,state['scheduled_events']['office-meeting'])['start_minute']==anchor+120
    jid,_=turn(repo,client,sid,'Отменяем встречу.');saved(repo,jid)
    state=repo.get_snapshot(sid)['world_state']
    assert list(state['scheduled_events'])==['office-meeting']
    assert state['scheduled_events']['office-meeting']['status']=='cancelled'
