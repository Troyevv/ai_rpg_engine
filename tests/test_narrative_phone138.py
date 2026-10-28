"""#138: semantic fixtures feed the real Resolver/Remote; API tests mock only provider IO."""
from copy import deepcopy
import json
import time

import pytest
from fastapi.testclient import TestClient

import engine
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.runtime_v3.models import Character, WorldHistoryV3, identity
from backend.runtime_v3.raw import RawTurnResult, extraction_schema, prompt_schema
from backend.runtime_v3.remote import apply, projection, context_projection
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.repository import read_history
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_remote_communication import phone
from test_narrative_test_world import CONFIG

TEXT = 'Ты завтра свободен?'
PROSE = 'В комнате пахло кофе. Телефон завибрировал: Вера написала «Ты завтра свободен?».'


def message(**changes):
    return dict(sender_id='b', recipient_ids=['a'], channel='TEXT_MESSAGE', content=TEXT, **changes)


def payload(state, rows=(), elapsed=1):
    return dict(final_scene=dict(location_id=state['camera']['location_id'],
        present_character_ids=state['camera']['present_character_ids'], elapsed_minutes=elapsed), remote_events=list(rows))


def resolve(snap, rows=(), elapsed=1, **fields):
    state = snap['world_state']
    return StateResolver(state, PROSE, 'Жду.', require_elapsed=True).resolve(dict(payload(state, rows, elapsed), **fields))


def test_t01_t05_t06_message_prose_unread_read_and_no_colocation():
    snap=phone(); before=deepcopy(snap)
    out=resolve(snap,[message()]); event=next(iter(out.state['remote_events'].values()))
    assert event['content']==TEXT and event['sender_id']=='b' and event['recipient_ids']==['a']
    assert event['status']=='delivered' and event['read_by']==[]
    assert out.history['turns'][0]['narrative']==PROSE
    assert out.state['knowledge']==before['world_state']['knowledge']
    assert out.state['characters']['b']['location_id']=='away'
    assert out.state['camera']==before['world_state']['camera']
    snap['world_state']=out.state
    ui=projection(snap);assert ui['events'][0]['unread'] and ui['events'][0]['content'] is None
    assert TEXT not in json.dumps(context_projection(out.state),ensure_ascii=False)
    read,batch=apply(snap,dict(action='read',event_id=event['id'],operation_id='read-message-138'))
    assert projection(read)['events'][0]['content']==TEXT
    fid=identity('communicated_text',event['id'])
    assert read['world_state']['knowledge']['a:'+fid]['status']=='known'
    assert out.state['remote_events'][event['id']]['read_by']==[]
    assert before==phone()


@pytest.mark.parametrize('action,status',[('answer','answered'),('decline','declined'),('ignore','missed')])
def test_t02_phone_controls(action,status):
    snap=phone();out=resolve(snap,[dict(sender_id='b',recipient_ids=['a'],channel='VOICE_CALL')])
    e=next(iter(out.state['remote_events'].values()));assert e['status']=='ringing'
    snap['world_state']=out.state
    after,_=apply(snap,dict(action=action,event_id=e['id'],operation_id='player-'+action))
    assert after['world_state']['remote_events'][e['id']]['status']==status
    assert after['world_state']['characters']['b']['location_id']=='away'


@pytest.mark.parametrize('prose',['Не позвонил.','Может, написать?','Хочет написать завтра.',
    'Вчера она написала: «Привет».','Говорят, кто-то звонил.','Телефон лежал на столе.', 'Ему снился звонок.'])
def test_t03_extractor_classifies_non_events_not_python(prose):
    s=phone()['world_state']
    out=StateResolver(s,prose,'').resolve(payload(s))
    assert out.state['remote_events']=={} and not out.history['events']


def test_t04_multiple_events_exact_time_order_and_one_clock():
    snap=phone();start=snap['world_state']['meta']['world_time']
    out=resolve(snap,[message(minute=start+1),dict(message(minute=start+2),content='И ещё одно.'),
        dict(sender_id='b',recipient_ids=['a'],channel='VOICE_CALL',minute=start+4)],elapsed=4)
    rows=list(out.state['remote_events'].values())
    assert [r['world_time'] for r in rows]==[start+1,start+2,start+4]
    assert [r['ordinal'] for r in rows]==[1,2,3]
    assert out.state['meta']['world_time']==start+4 and rows[-1]['status']=='ringing'
    assert [e['minute'] for e in out.history['events']]==[start+1,start+2,start+4]


@pytest.mark.parametrize('status,ended_at',[('ended',1),('missed',2)])
def test_t05_completed_call_and_canonical_timeout(status,ended_at):
    snap=phone();start=snap['world_state']['meta']['world_time']
    out=resolve(snap,[dict(sender_id='b',recipient_ids=['a'],channel='VOICE_CALL',minute=start,
        status=status,ended_at=start+ended_at)],elapsed=2)
    e=next(iter(out.state['remote_events'].values()))
    assert e['status']==status and e['updated_at']==start+ended_at
    assert len(out.history['events'])==2
    timeout=resolve(snap,[dict(sender_id='b',recipient_ids=['a'],channel='VOICE_CALL',minute=start)],elapsed=2)
    assert next(iter(timeout.state['remote_events'].values()))['status']=='missed'


def test_t07_existing_thread_groups_and_unknown_identity():
    snap=phone();out=resolve(snap,[message()]);snap['world_state']=out.state
    first=next(iter(out.state['remote_events'].values()))
    out=resolve(snap,[message()]);assert len(out.state['conversations'])==1
    assert len(out.state['contacts'])==3
    assert list(out.state['remote_events'].values())[-1]['conversation_id']==first['conversation_id']
    group,_=apply(snap,dict(action='create_group',operation_id='create-group-138',member_ids=['b','child'],label='Группа'))
    gid=next(c['id'] for c in group['world_state']['conversations'].values() if c['group'])
    out=resolve(group,[dict(message(conversation_id=gid),recipient_ids=['a','child'])])
    assert list(out.state['remote_events'].values())[-1]['recipient_ids']==['a','child']
    with pytest.raises(StructuralDeltaError):resolve(group,[message(conversation_id=gid)])
    snap=phone();snap['world_state']['contacts']['a-b']['identity_visible']=False
    out=resolve(snap,[message()]);snap['world_state']=out.state
    assert projection(snap)['events'][0]['sender']['name']=='Неизвестный участник'


def test_t07_explicit_new_contact_uses_remote_contract_no_inferred_address():
    snap=phone();del snap['world_state']['contacts']['b-a']
    with pytest.raises(StructuralDeltaError):resolve(snap,[message()])
    out=resolve(snap,[message(established_contact=dict(label='Сохранённый адрес',address='explicit-123'))])
    created=[c for c in out.state['contacts'].values() if c['owner_id']=='b']
    assert len(created)==1 and created[0]['address']=='explicit-123' and created[0]['character_id']=='a'
    assert len(out.state['characters'])==len(snap['world_state']['characters'])


@pytest.mark.parametrize('change',[{'content':''},{'sender_id':'missing'},{'recipient_ids':['missing']},
    {'sender_id':'a','recipient_ids':['b']},{'contact_id':'a-b'}, {'conversation_id':'missing'},
    {'minute':True},{'minute':999999},{'read_by':['a']},{'status':'answered'}])
def test_t08_structural_conflicts_repairable_atomic(change):
    snap=phone();before=deepcopy(snap)
    with pytest.raises(StructuralDeltaError) as err:resolve(snap,[dict(message(),**change)])
    assert err.value.repairable and err.value.path['section']=='remote_events'
    assert snap==before


def test_t06_no_source_bound_knowledge_or_public_fact():
    snap=phone()
    fields=dict(facts=[dict(id='phone-secret',text=TEXT,visibility='secret')],
        events=[dict(id='delivery',text='Получено сообщение.',medium='message',participants=['a','b'],witnesses=['a'],fact_ids=['phone-secret'])],
        knowledge_gained=[dict(actor_id='a',fact_id='phone-secret',source_event_id='delivery')])
    with pytest.raises(StructuralDeltaError,match='Knowledge'):resolve(snap,[message(source_event_id='delivery')],**fields)
    fields['knowledge_gained']=[];fields['facts'][0]['visibility']='public'
    with pytest.raises(StructuralDeltaError):resolve(snap,[message(source_event_id='delivery')],**fields)


def test_t09_stable_identity_repeat_extraction_and_continuation():
    snap=phone();one=resolve(snap,[message()]);two=resolve(snap,[message()])
    assert one.state==two.state and one.history==two.history
    e=next(iter(one.state['remote_events'].values()));snap['world_state']=one.state
    out=resolve(snap,[message(existing_event_id=e['id'])])
    assert out.state['remote_events']==one.state['remote_events'] and not out.history['events']


def test_t12_no_phone_capability_and_prompt_schema():
    snap=phone();snap['world_state']['meta']['communication'].update(text_message=False,voice_call=False)
    with pytest.raises(StructuralDeltaError):resolve(snap,[message()])
    from backend.runtime_v3.context import build_context
    wire='\n'.join(m['content'] for m in build_context(snap,[],'Жду.','turn',131072,4096))
    assert 'communication_capabilities' in wire and '"text_message":false' in wire.replace(' ','')
    import jsonschema
    s=extraction_schema();raw=payload(phone()['world_state'],[message()])
    jsonschema.Draft202012Validator(s).validate(raw)
    jsonschema.Draft202012Validator(prompt_schema(communication=True)).validate(raw)


class Provider:
    def __init__(self):
        self.rows=[];self.elapsed=1;self.prose=PROSE;self.fail=False;self.repair=False;self.call_fixture=False;self.calls=[];self.requests=[]
    def __call__(self,**kw):
        self.requests.append(kw['messages'])
        if kw['messages'][0]['content'].startswith('Select at most ONE'):
            self.calls.append('remote_decision');yield '{"action":null}';return
        extraction=bool(kw.get('response_format'));self.calls.append('extraction' if extraction else 'narrative')
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        if self.call_fixture and current.get('communication',{}).get('focus')=='call':
            from call_continuity_fixture import response
            task=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущий ввод\n')))
            result=response(current,task['player_input'],'complete' if extraction else None)
            yield json.dumps(result,ensure_ascii=False) if extraction else result
            return
        if not extraction:yield self.prose;return
        if self.fail:raise RuntimeError('External provider unavailable')
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        raw=dict(final_scene=dict(location_id=current['camera']['location_id'],present_character_ids=current['camera']['present_character_ids'],elapsed_minutes=self.elapsed),remote_events=deepcopy(self.rows))
        if self.repair and self.calls.count('extraction')==1:raw['remote_events'][0]['content']=''
        yield json.dumps(raw,ensure_ascii=False)


def wait(repo,jid):
    for _ in range(1000):
        job=repo.get_job(jid)
        if job['status'] in ('saved','error','cancelled'):return job
        time.sleep(.01)
    raise AssertionError('Job timed out')


@pytest.fixture
def api138(tmp_path,monkeypatch):
    provider=Provider()
    monkeypatch.setattr(engine,'chat_stream',provider)
    monkeypatch.setattr(engine,'find_loaded_model',lambda *a,**kw:{'config':{'context_length':131072}})
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED','0')
    app=create_app(tmp_path/'phone138.sqlite',recover=False);repo=app.state.repository
    with TestClient(app) as client:
        seed=load_fixture(repo,'phone');sid=seed['save']
        def turn(kind='turn',text='Жду.',**extra):
            r=client.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text=text,revision=repo.get_save(sid)['revision'],config=CONFIG,**extra))
            assert r.status_code==200,r.text
            return wait(repo,r.json()['id'])
        provider.prose='Обычная сцена.'
        assert turn('start','')['status']=='saved'
        provider.calls=[];provider.prose=PROSE
        yield repo,client,sid,provider,turn


def qa_message(**kw):return dict(sender_id='qa_vera',recipient_ids=['qa_kirill'],channel='TEXT_MESSAGE',content=TEXT,**kw)


def test_t08_t09_api_repair_retry_regenerate_rollback_branch_reload(api138):
    repo,client,sid,p,turn=api138;p.rows=[qa_message()];p.repair=True
    before=repo.get_snapshot(sid)
    job=turn();assert job['status']=='saved',job['error']
    assert p.calls==['narrative','extraction','extraction']
    first=repo.get_snapshot(sid);assert len(first['world_state']['remote_events'])==1
    original=repo.list_turns(sid)[-1]
    assert repo.request_log(job_id=job['id'])[0]
    p.repair=False;p.calls=[]
    job=turn('regenerate','');assert job['status']=='saved',job['error']
    assert repo.get_snapshot(sid)['world_state']['remote_events']==first['world_state']['remote_events']
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==first['world_state']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)['world_state']==before['world_state']
    p.calls=[];p.fail=True
    job=turn();assert job['status']=='error' and repo.get_snapshot(sid)['world_state']==before['world_state']
    p.fail=False
    r=client.post(f"/api/jobs/{job['id']}/retry",json={'config':CONFIG});assert r.status_code==200,r.text
    job=wait(repo,job['id']);assert job['status']=='saved',job['error']
    assert p.calls==['narrative','extraction','extraction']
    fresh=Repository(repo.path);assert fresh.get_snapshot(sid)==repo.get_snapshot(sid)
    with repo.connect() as db:h,_=read_history(db,fresh.get_snapshot(sid)['history_head'])
    delivered=[e for e in h['events'] if e.get('remote',{}).get('channel')=='TEXT_MESSAGE']
    assert len(delivered)==1
    p.rows=[];job=turn();assert job['status']=='saved' and len(repo.get_snapshot(sid)['world_state']['remote_events'])==1


def test_t08_api_unrepairable_delivery_is_not_published(api138):
    repo,client,sid,p,turn=api138;p.rows=[dict(qa_message(),content='')]
    before=repo.get_snapshot(sid);job=turn()
    assert job['status']=='error' and repo.get_snapshot(sid)==before
    assert p.calls==['narrative','extraction','extraction']
    assert len(repo.list_turns(sid))==1
    assert 'remote_events' in job['repair_diagnostics_json']


def test_t10_t13_real_api_jobs_sqlite_full_journey(api138):
    repo,client,sid,p,turn=api138
    p.rows=[qa_message()];job=turn();assert job['status']=='saved',job['error']
    assert p.calls==['narrative','extraction']
    snap=repo.get_snapshot(sid);e=next(iter(snap['world_state']['remote_events'].values()))
    assert e['content']==TEXT and not e['read_by']
    def device(action,**kw):
        r=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],command=dict(action=action,operation_id=f'138-{action}-{repo.get_save(sid)["revision"]}',**kw)))
        assert r.status_code==200,r.text
    device('read',event_id=e['id'])
    device('send',conversation_id=e['conversation_id'],content='Да, свободен.')
    p.rows=[dict(sender_id='qa_vera',recipient_ids=['qa_kirill'],channel='VOICE_CALL')];p.prose='Вера звонит Кириллу.'
    job=turn();assert job['status']=='saved',job['error']
    call=list(repo.get_snapshot(sid)['world_state']['remote_events'].values())[-1]
    assert call['status']=='ringing'
    device('answer',event_id=call['id'])
    p.rows=[];p.call_fixture=True
    for text in ('Встретимся через час?','Я скоро освобожусь.','Тогда до встречи.'):
        job=turn(text=text,interaction_channel='call');assert job['status']=='saved',job['error']
    assert repo.get_snapshot(sid)['world_state']['scheduled_events']['office-meeting']['status']=='pending'
    fresh=Repository(repo.path);assert fresh.get_snapshot(sid)==repo.get_snapshot(sid)
    job=turn();assert job['status']=='saved',job['error']
    final=repo.get_snapshot(sid)['world_state']
    assert len(final['remote_events'])==3 and final['remote_events'][call['id']]['status']=='ended'
    assert final['characters']['qa_vera']['location_id']==snap['world_state']['characters']['qa_vera']['location_id']


def test_t13_large_world_long_prose_bounded_context():
    snap=phone();s=snap['world_state']
    for i in range(110):s['characters'][f'extra-{i}']=Character(id=f'extra-{i}').model_dump()
    from backend.runtime_v3.context import build_context
    prose=PROSE+' Тихий дождь.'*2000
    messages=build_context(snap,[],'Жду.','turn',131072,4096,extraction_text=prose)
    wire='\n'.join(m['content'] for m in messages)
    assert prose in wire and 'remote_events' in wire
    assert len(json.dumps(context_projection(s)))<4000
    result=StateResolver(s,prose,'').resolve(payload(s,[message()]))
    assert len(result.state['remote_events'])==1 and len(result.state['characters'])==len(s['characters'])


def test_interleaved_call_message_end_preserves_chronology():
    snap=phone();start=snap['world_state']['meta']['world_time']
    out=resolve(snap,[dict(sender_id='b',recipient_ids=['a'],channel='VOICE_CALL',
        minute=start,status='ended',ended_at=start+1), message(minute=start),
        dict(message(minute=start+2),content='После отбоя.')],elapsed=2)
    assert [e['minute'] for e in out.history['events']]==[start,start,start+1,start+2]
    assert [e['remote']['status'] for e in out.history['events']]==['ringing','delivered','ended','delivered']
    assert out.state['meta']['world_time']==start+2


def test_repeated_established_address_reuses_contact_and_existing_player_message():
    snap=phone();row=message(established_contact=dict(label='Адрес',address='address-a'))
    first=resolve(snap,[row]);snap['world_state']=first.state
    second=resolve(snap,[row]);assert second.state['contacts']==first.state['contacts']
    snap['world_state']=second.state
    sent,_=apply(snap,dict(action='send',contact_id='a-b',content='Авторский ответ.',operation_id='138-player-reply'))
    event=list(sent['world_state']['remote_events'].values())[-1]
    out=resolve(sent,[dict(sender_id='a',recipient_ids=['b'],channel='TEXT_MESSAGE',content=event['content'],existing_event_id=event['id'])])
    assert out.state['remote_events']==sent['world_state']['remote_events']
    assert not out.history['events']


def test_late_rejection_rolls_back_remote_with_rest_of_turn(api138):
    repo,client,sid,p,turn=api138
    p.rows=[qa_message(),dict(sender_id='qa_vera',recipient_ids=['missing'],channel='VOICE_CALL')]
    before=repo.get_snapshot(sid);job=turn()
    assert job['status']=='error' and repo.get_snapshot(sid)==before
    with repo.connect() as db:h,_=read_history(db,before['history_head'])
    assert not any(e.get('remote') for e in h['events'])


def test_optional_annotation_and_time_skip_clock_do_not_block_delivery():
    snap=phone();state=snap['world_state'];start=state['meta']['world_time']
    raw=payload(state,[message(minute=start+2,source_event_id='optional-missing',evidence='')],elapsed=5)
    out=StateResolver(state,PROSE,'Жду.',runtime_time_skip=True).resolve(raw)
    assert out.state['meta']['world_time']==start+5
    assert next(iter(out.state['remote_events'].values()))['world_time']==start+2
    assert any(w['code']=='remote_optional_source_invalid' for w in out.warnings)
