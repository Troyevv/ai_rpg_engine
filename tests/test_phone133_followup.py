"""Real API/jobs with adversarial provider output, not a live LLM test."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_phone122 import setup,dispatch,execute,read,CONFIG
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import scheduled_window


@pytest.mark.parametrize('field', ['player_assertion','player_evidence','player_source_id'])
@pytest.mark.parametrize('conversation',[None,'qa-group'])
def test_agency_repair_only_semantics_and_canonical_sources(tmp_path,field,conversation):
    repo,client,sid=setup(tmp_path)
    jid=dispatch(repo,client,sid,conversation=conversation)
    before=repo.get_snapshot(sid)
    attempts=[]
    def malformed(value,data):
        row=value['scheduled_event_changes'][0]
        authored=next(e for e in data['accepted_messages'] if e['sender_id']==data['controlled_actor_id'])
        row['player_source_id']=authored['id']
        if not attempts:
            if field=='player_assertion':row.pop(field)
            elif field=='player_evidence':
                row.pop('player_source_id');row[field]='NPC confirmation, not player input'
            else:row[field]=data['accepted_messages'][-1]['id']
        attempts.append(data)
        return value
    assert execute(repo,jid,transform=malformed)==['decision','decision','semantic','semantic']
    job=repo.get_job(jid)
    assert job['status']=='saved',job['error']
    warning=attempts[1]['repair']['diagnostics'][0]
    assert warning['code']=='controlled_actor_unsupported' and warning['evidence_field']==field
    assert attempts[1]['accepted_messages']==attempts[0]['accepted_messages']
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==2 and len(state['scheduled_events'])==1
    assert state['meta']['world_time']==before['world_state']['meta']['world_time']+1
    plan=state['scheduled_events']['phone-meeting']
    assert scheduled_window(state,plan)['start_minute']==before['world_state']['meta']['world_time']+120
    read(repo,client,sid)
    assert 'phone-meeting' in repo.get_save(sid)['state']['world']['scheduled_events']
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    assert client.get(f'/api/saves/{sid}').status_code==200
    assert len(repo.get_snapshot(sid)['world_state']['scheduled_events'])==1


def test_valid_identity_binds_exact_player_text_without_inventing_assertion(tmp_path):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    def typo(value,data):
        row=value['scheduled_event_changes'][0]
        row['player_source_id']=data['accepted_messages'][0]['id']
        row['player_evidence']='paraphrased quotation'
        return value
    assert execute(repo,jid,transform=typo)==['decision','decision','semantic']
    assert repo.get_job(jid)['status']=='saved'


def test_invalid_optional_intention_does_not_discard_meeting_or_messages(tmp_path):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    def invalid(value,data):
        value['character_changes']=[{'intentions_updates':[{'source_event_id':[]}]},
            dict(id='qa_kirill',intentions_updates=[dict(text='invented',evidence='invented',source_event_id=data['accepted_messages'][-1]['id'])])]
        return value
    assert execute(repo,jid,transform=invalid)==['decision','decision','semantic']
    job=repo.get_job(jid)
    assert job['status']=='saved',job['error']
    assert json.loads(job['warnings_json'])
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==2 and len(state['scheduled_events'])==1
    assert not any(i['text']=='invented' for i in state['characters']['qa_kirill']['intentions'])


def test_repair_cannot_erase_rejected_meeting_and_retry_replays_only_repair(tmp_path):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    before=deepcopy(repo.get_snapshot(sid));attempt=0
    def invalid(value,data):
        nonlocal attempt
        attempt+=1
        if attempt==1:value['scheduled_event_changes'][0].pop('player_assertion')
        else:value['scheduled_event_changes']=[]
        return value
    assert execute(repo,jid,transform=invalid)==['decision','decision','semantic','semantic']
    assert repo.get_job(jid)['status']=='error'
    assert 'commitment_repair_omission' in repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)==before
    with patch('engine.launch'):
        r=client.post(f'/api/jobs/{jid}/retry',json={'config':CONFIG})
    assert r.status_code==200,r.text
    assert execute(repo,jid)==['semantic']
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events'])==2 and len(state['scheduled_events'])==1
    assert state['meta']['world_time']==before['world_state']['meta']['world_time']+1

@pytest.mark.parametrize('conversation',[None,'qa-group'])
@pytest.mark.parametrize('player_proposes',[True,False])
def test_one_hour_meeting_in_either_direction_without_narrative_recap(tmp_path,conversation,player_proposes):
    import engine
    from test_communication_cycle import decision
    repo,client,sid=setup(tmp_path)
    proposal='Встретимся через час?'
    def run(jid,reply):
        def provider(**kw):
            ms=kw['messages'];data=json.loads(ms[1]['content'])
            if not ms[0]['content'].startswith('Remote semantic extraction/'):
                yield decision(ms).replace('Да, увидимся завтра.',reply);return
            rows=data['accepted_messages']
            offer=next((e for e in rows if e['content']==proposal),None)
            assent=next((e for e in rows if offer and e['ordinal']>offer['ordinal'] and e['sender_id']!=offer['sender_id'] and e['content']=='Да, согласен.'),None)
            raw=dict(final_scene=data['final_scene'])
            if assent:
                player=offer if offer['sender_id']==data['controlled_actor_id'] else assent
                raw['scheduled_event_changes']=[dict(id='one-hour',description='Встреча',assertion='agreed',
                    character_ids=[offer['sender_id'],assent['sender_id']],temporal={'minute_offset':60},
                    evidence=assent['content'],remote_source_ids=[offer['id'],assent['id']],remote_time_source_id=offer['id'],
                    player_assertion='explicit_choice',player_source_id=player['id'],player_evidence=player['content'])]
            yield json.dumps(raw,ensure_ascii=False)
        with patch('engine.chat_stream',side_effect=provider):
            engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    jid=dispatch(repo,client,sid,proposal if player_proposes else 'Привет.',conversation=conversation)
    run(jid,'Да, согласен.' if player_proposes else proposal)
    if not player_proposes:
        assert not repo.get_snapshot(sid)['world_state']['scheduled_events']
        read(repo,client,sid)
        jid=dispatch(repo,client,sid,'Да, согласен.','phone133-assent',conversation)
        run(jid,'До встречи.')
    read(repo,client,sid)
    state=repo.get_snapshot(sid)['world_state'];plan=state['scheduled_events']['one-hour']
    offer=next(e for e in state['remote_events'].values() if e['content']==proposal)
    assert scheduled_window(state,plan)['start_minute']==offer['world_time']+60
    assert 'one-hour' in repo.get_save(sid)['state']['world']['scheduled_events']
    assert all(t['kind']=='communication' for t in repo.list_turns(sid)[1:])


def test_stop_call_generation_does_not_end_call_or_commit_late_text(tmp_path):
    import engine
    from threading import Event,Thread
    repo,client,sid=setup(tmp_path)
    with patch('engine.launch'):
        res=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,
            command=dict(action='call',contact_id='phone-qa_kirill-qa-vera',operation_id='stop-call')))
    assert res.status_code==200,res.text
    execute(repo,res.json()['job']['id'])
    before=repo.get_snapshot(sid)
    with patch('engine.launch'):
        res=client.post(f'/api/saves/{sid}/turns',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,
            text='Алло?',kind='turn',interaction_channel='call'))
    assert res.status_code==200,res.text
    jid=res.json()['id'];entered=Event();release=Event();handle=engine.Worker()
    def provider(**kw):
        entered.set();assert release.wait(10)
        yield 'Поздний ответ после остановки.'
    with patch('engine.chat_stream',side_effect=provider),patch('engine.find_loaded_model',return_value={'config':{}}):
        with engine.REGISTRY_LOCK:engine.WORKERS[jid]=handle
        worker=Thread(target=engine.run_job,args=(repo.path,jid,handle));worker.start()
        try:
            assert entered.wait(10)
            result=client.post(f'/api/jobs/{jid}/stop',json={})
            assert result.status_code==200,result.text
        finally:release.set();worker.join(10)
        assert not worker.is_alive()
    assert repo.get_job(jid)['status']=='stopped'
    assert repo.get_snapshot(sid)==before
    assert next(e for e in before['world_state']['remote_events'].values() if e['channel']=='VOICE_CALL')['status']=='answered'

@pytest.mark.parametrize('proof',['missing_assertion','partial_quote'])
def test_canonical_identity_does_not_invent_player_choice(tmp_path,proof):
    repo,client,sid=setup(tmp_path);jid=dispatch(repo,client,sid)
    before=repo.get_snapshot(sid)
    def unsupported(value,data):
        row=value['scheduled_event_changes'][0]
        if proof=='missing_assertion':
            row['player_source_id']=data['accepted_messages'][0]['id'];row.pop('player_assertion')
        else:
            row['player_evidence']='через два часа'
        return value
    assert execute(repo,jid,transform=unsupported)==['decision','decision','semantic','semantic']
    assert repo.get_job(jid)['status']=='error'
    assert 'controlled_actor_unsupported' in repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)==before
