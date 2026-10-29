"""Private transport + real resolver/API/jobs/SQLite; only provider HTTP is faked."""
import json
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
import engine
import llm
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.runtime_v3.models import WorldHistoryV3, identity
from backend.runtime_v3.remote import apply, advance, correspondence_projection
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.long_term import advance_clock
from backend.runtime_v3.repository import read_history
from backend.services.private_artifacts import parse
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_remote_communication import phone
from test_narrative_phone138 import payload, wait
from test_narrative_test_world import CONFIG

SECRET = 'SEALED-130: Встреча у башни, пароль — янтарь.'
PUBLIC = 'Гонец забрал запечатанное письмо.'


def letters():
    snap = phone()
    snap['world_state']['meta']['communication'].update(letter=True, courier=True, telegram=True,
        delivery_minutes={'letter':30,'courier':20,'telegram':5})
    return snap


def artifact(sender='b', recipient='a', channel='LETTER', aid='letter-1'):
    return dict(id=aid,type='letter',channel=channel,sender_id=sender,recipient_id=recipient,content=SECRET)


def extracted(a):
    return dict(sender_id=a['sender_id'],recipient_ids=[a['recipient_id']],channel=a['channel'],artifact_id=a['id'])


def send(snap, a=None):
    a=a or artifact()
    return StateResolver(snap['world_state'],PUBLIC,'Жду.',private_artifacts=[a]).resolve(payload(snap['world_state'],[extracted(a)]))


@pytest.mark.parametrize('channel,delay',[('LETTER',30),('COURIER_LETTER',20),('TELEGRAM',5)])
def test_delivery_read_knowledge_and_idempotency(channel,delay):
    snap=letters();before=deepcopy(snap);out=send(snap,artifact(channel=channel));snap['world_state']=out.state
    e=next(iter(out.state['remote_events'].values()));due=e['world_time']+delay
    assert e['delivery_due_at']==due and e['status']=='in_transit' and not e['delivered_to']
    assert out.state['knowledge']==before['world_state']['knowledge']
    assert SECRET not in json.dumps(correspondence_projection(snap),ensure_ascii=False)
    batch=WorldHistoryV3().to_dict();advance_clock(snap,due-1,batch)
    assert not e['delivered_to']
    advance_clock(snap,due,batch);e=snap['world_state']['remote_events'][e['id']]
    assert e['delivered_to']==['a'] and not e['read_by']
    assert SECRET not in json.dumps(correspondence_projection(snap),ensure_ascii=False)
    count=len(batch['events']);advance_clock(snap,due+525600,batch)
    assert len(batch['events'])==count
    snap,h=apply(snap,dict(action='read',event_id=e['id'],operation_id='open-letter-130'))
    assert correspondence_projection(snap)[0]['content']==SECRET
    fid=identity('communicated_text',e['id']);assert snap['world_state']['knowledge']['a:'+fid]['status']=='known'
    twice,h2=apply(snap,dict(action='read',event_id=e['id'],operation_id='open-letter-again'))
    assert twice==snap and not h2['events']
    assert snap['world_state']['characters']['b']['location_id']=='away'


def test_missing_payload_author_agency_and_no_extractor_authorship():
    s=letters()['world_state'];a=artifact()
    with pytest.raises(StructuralDeltaError):
        StateResolver(s,PUBLIC,'').resolve(payload(s,[dict(extracted(a),content=SECRET)]))
    with pytest.raises(StructuralDeltaError):send(letters(),artifact(sender='a',recipient='b'))
    with pytest.raises(StructuralDeltaError):
        StateResolver(s,PUBLIC,'',private_artifacts=[a]).resolve(payload(s,[]))
    with pytest.raises(ValueError,match='private_artifact_payload_invalid') as err:
        parse('{"narrative":"ok","artifacts":'+SECRET)
    assert SECRET not in str(err.value)


def test_batch_year_chronology_death_and_no_forced_reply():
    snap=letters()
    for n,channel in enumerate(('LETTER','TELEGRAM','COURIER_LETTER')):
        out=send(snap,artifact(channel=channel,aid=f'a{n}'));snap['world_state']=out.state
    s=snap['world_state'];now=s['meta']['world_time'];batch=WorldHistoryV3().to_dict()
    advance_clock(snap,now+525600,batch)
    events=[e for e in batch['events'] if e.get('remote_interaction_id')]
    assert len(events)==3 and [e['minute'] for e in events]==sorted(e['minute'] for e in events)
    assert len(snap['world_state']['remote_events'])==3
    assert all(not e['read_by'] for e in snap['world_state']['remote_events'].values())
    snap=letters();out=send(snap);snap['world_state']=out.state
    snap['world_state']['characters']['a']['life_status']='dead'
    snap['world_state']['meta']['world_time']+=100
    advance(snap['world_state'],WorldHistoryV3())
    e=next(iter(snap['world_state']['remote_events'].values()))
    assert e['status']=='undeliverable' and not e['read_by'] and not e['delivered_to']


class HTTPProvider:
    def __init__(self):
        self.artifacts=[];self.rows=[];self.elapsed=1;self.fail_extraction=False;self.bad=False;self.calls=[]
    def create(self, **kw):
        extraction=bool(kw.get('response_format'))
        self.calls.append('extraction' if extraction else 'narrative')
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        if extraction:
            if self.fail_extraction:raise RuntimeError('fixture extraction failure')
            value=json.dumps(dict(final_scene=dict(location_id=current['camera']['location_id'],present_character_ids=current['camera']['present_character_ids'],elapsed_minutes=self.elapsed),remote_events=self.rows),ensure_ascii=False)
            chunks=[NS(choices=[NS(delta=NS(content=value),finish_reason='stop')])]
        elif kw.get('tools'):
            value=json.dumps(dict(narrative=PUBLIC,artifacts=self.artifacts),ensure_ascii=False)
            if self.bad:value=value[:-2]
            # Split inside UTF-8 text, JSON escapes, field names, private content.
            chunks=[NS(choices=[NS(delta=NS(content=None,tool_calls=[NS(index=0,function=NS(name='publish_narrative' if i==0 else None,arguments=value[i:i+7]))]),finish_reason=None)]) for i in range(0,len(value),7)]
            chunks.append(NS(choices=[NS(delta=NS(content=None,tool_calls=[]),finish_reason='tool_calls')]))
        else:
            chunks=[NS(choices=[NS(delta=NS(content=PUBLIC),finish_reason='stop')])]
        stream=MagicMock();stream.__iter__.return_value=iter(chunks);return stream


@pytest.fixture
def api(tmp_path,monkeypatch):
    p=HTTPProvider();client=MagicMock();client.chat.completions.create.side_effect=p.create
    monkeypatch.setattr(llm,'OpenAI',lambda **kw:client)
    monkeypatch.setattr(engine,'find_loaded_model',lambda *a,**kw:{'config':{'context_length':131072}})
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED','0')
    app=create_app(tmp_path/'letters.sqlite',recover=False);repo=app.state.repository
    with TestClient(app) as c:
        sid=load_fixture(repo,'phone')['save']
        with repo.connect() as db:
            snap=json.loads(db.execute('SELECT state_json FROM saves WHERE id=?',(sid,)).fetchone()[0])
            snap['world_state']['meta']['communication'].update(letter=True,delivery_minutes={'letter':10})
            db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
        def turn(kind='turn',**extra):
            r=c.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text='' if kind=='start' else 'Жду.',revision=repo.get_save(sid)['revision'],config=CONFIG,**extra))
            assert r.status_code==200,r.text
            return wait(repo,r.json()['id'])
        yield repo,c,sid,p,turn


def assert_private(c,sid,jid):
    for url in (f'/api/saves/{sid}',f'/api/jobs/{jid}',f'/api/jobs/{jid}/events',f'/api/saves/{sid}/accounting',f'/api/saves/{sid}/archive',f'/api/saves/{sid}/correspondence'):
        r=c.get(url);assert r.status_code==200,r.text
        assert SECRET not in r.text,(url,r.text)


def test_api_jobs_provider_sqlite_retry_regenerate_rollback_and_open(api):
    repo,c,sid,p,turn=api
    job=turn('start');assert job['status']=='saved',job['error']
    a=artifact('qa_vera','qa_kirill');p.artifacts=[a];p.rows=[extracted(a)];p.fail_extraction=True
    before=repo.get_snapshot(sid);job=turn();assert job['status']=='error',job
    assert_private(c,sid,job['id'])
    assert repo.get_snapshot(sid)==before
    p.fail_extraction=False;calls=p.calls.count('narrative')
    r=c.post(f"/api/jobs/{job['id']}/retry",json={'config':CONFIG});assert r.status_code==200,r.text
    job=wait(repo,job['id']);assert job['status']=='saved',job['error']
    assert p.calls.count('narrative')==calls
    first=repo.get_snapshot(sid);e=next(iter(first['world_state']['remote_events'].values()))
    assert e['content']==SECRET and e['status']=='in_transit'
    assert_private(c,sid,job['id'])
    fresh=Repository(repo.path);assert fresh.get_snapshot(sid)==first
    job=turn('regenerate');assert job['status']=='saved',job['error']
    assert repo.get_snapshot(sid)['world_state']['remote_events']==first['world_state']['remote_events']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)['world_state']==before['world_state']
    job=turn();assert job['status']=='saved',job['error']
    p.rows=[];p.artifacts=[]
    job=turn(time_skip={'duration':5,'reason':'Жду почту'});assert job['status']=='saved',job['error']
    assert next(iter(repo.get_snapshot(sid)['world_state']['remote_events'].values()))['status']=='in_transit'
    job=turn(time_skip={'duration':10,'reason':'Жду почту'});assert job['status']=='saved',job['error']
    assert_private(c,sid,job['id'])
    current=repo.get_snapshot(sid);e=next(iter(current['world_state']['remote_events'].values()))
    assert e['status']=='delivered' and not e['read_by']
    command=dict(action='read',event_id=e['id'],operation_id='open-canonical-letter')
    revision=repo.get_save(sid)['revision']
    for _ in range(2):
        r=c.post(f'/api/saves/{sid}/phone',json=dict(revision=revision,command=command));assert r.status_code==200,r.text
    assert c.get(f'/api/saves/{sid}/correspondence').json()[0]['content']==SECRET
    with repo.connect() as db:h,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    assert len([x for x in h['events'] if x.get('remote',{}).get('status')=='delivered' and not x['remote']['read_by']])==1
    job=turn();assert job['status']=='saved',job['error']


def test_malformed_private_transport_never_commits_or_publishes(api):
    repo,c,sid,p,turn=api;p.bad=True;p.artifacts=[artifact('qa_vera','qa_kirill')]
    before=repo.get_snapshot(sid);job=turn('start')
    assert job['status']=='error' and not job['narrative_complete']
    assert repo.get_snapshot(sid)==before
    assert_private(c,sid,job['id'])


def test_npc_explicit_read_reply_or_silence_and_player_invitation():
    snap=letters()
    snap,_=apply(snap,dict(action='send',channel='LETTER',character_id='b',content='Приходи завтра.',operation_id='player-letter-130'))
    e=next(iter(snap['world_state']['remote_events'].values()))
    assert snap['world_state']['scheduled_events']=={}
    read=dict(sender_id='a',recipient_ids=['b'],channel='LETTER',existing_event_id=e['id'],reader_id='b')
    with pytest.raises(StructuralDeltaError):
        StateResolver(snap['world_state'],'Он читает.','').resolve(payload(snap['world_state'],[read],elapsed=0))
    advance_clock(snap,e['delivery_due_at'],WorldHistoryV3().to_dict())
    out=StateResolver(snap['world_state'],'Он прочитал письмо и убрал его.','').resolve(payload(snap['world_state'],[read],elapsed=0))
    assert len(out.state['remote_events'])==1 and out.state['remote_events'][e['id']]['read_by']==['b']
    assert out.state['scheduled_events']=={}
    snap['world_state']=out.state
    a=artifact()
    out=send(snap,a)
    assert len(out.state['remote_events'])==2
    response=list(out.state['remote_events'].values())[-1]
    assert response['status']=='in_transit' and response['content']==SECRET


def test_year_real_job_reload_and_rollback(api):
    repo,c,sid,p,turn=api
    assert turn('start')['status']=='saved'
    p.artifacts=[artifact('qa_vera','qa_kirill',aid=str(i)) for i in range(3)]
    p.rows=[extracted(a) for a in p.artifacts]
    job=turn();assert job['status']=='saved',job['error']
    before=repo.get_snapshot(sid)
    config=dict(CONFIG,long_term_advance=dict(amount=1,unit='years',max_llm_calls=0))
    jid=repo.begin_job(sid,'','long_term',config)
    engine.run_job(repo.path,jid,engine.Worker())
    job=repo.get_job(jid);assert job['status']=='saved',job['error']
    after=repo.get_snapshot(sid)
    assert after['last_long_term_advance']['llm_calls']==0
    assert all(e['status']=='delivered' and not e['read_by'] for e in after['world_state']['remote_events'].values())
    assert_private(c,sid,jid)
    assert Repository(repo.path).get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']


@pytest.mark.parametrize('fault',['raw','truncated','multiple','wrong_finish','disconnect','duplicate_key'])
def test_provider_transport_fail_closed_all_chunk_boundaries(monkeypatch,fault):
    value=json.dumps(dict(narrative=PUBLIC,artifacts=[artifact()]),ensure_ascii=False)
    if fault=='truncated':value=value[:-1]
    if fault=='duplicate_key':value='{"narrative":"'+PUBLIC+'","narrative":"'+SECRET+'","artifacts":[]}'
    def chunks():
        if fault=='raw':
            yield NS(choices=[NS(delta=NS(content=SECRET,tool_calls=None),finish_reason='stop')]);return
        for i,char in enumerate(value):
            yield NS(choices=[NS(delta=NS(content=None,tool_calls=[NS(index=1 if fault=='multiple' else 0,function=NS(name='publish_narrative' if i==0 else None,arguments=char))]),finish_reason=None)])
        if fault=='disconnect':raise RuntimeError('fixture disconnected: '+SECRET)
        yield NS(choices=[NS(delta=NS(content=None,tool_calls=[]),finish_reason='stop' if fault=='wrong_finish' else 'tool_calls')])
    stream=MagicMock();stream.__iter__.side_effect=chunks
    client=MagicMock();client.chat.completions.create.return_value=stream
    monkeypatch.setattr(llm,'OpenAI',lambda **kw:client)
    emitted=[];artifacts=[]
    with pytest.raises((RuntimeError,ValueError)) as err:
        for chunk in llm.chat_stream('model',[],on_private_result=artifacts.extend,require_complete=True):emitted.append(chunk)
    assert emitted==[] and artifacts==[] and SECRET not in str(err.value)
    stream.close.assert_called_once()


def test_landline_reuses_voice_runtime_without_contact():
    s=letters();s['world_state']['meta']['communication'].update(voice_call=False,text_message=False,landline=True)
    s['world_state']['contacts']={}
    s,_=apply(s,dict(action='call',character_id='b',operation_id='landline-1939'))
    e=next(iter(s['world_state']['remote_events'].values()))
    assert e['channel']=='VOICE_CALL' and e['status']=='ringing'


def test_npc_only_correspondence_does_not_leak_through_fact_or_patch_projection():
    from backend.runtime_v3.selectors import ui_view
    from backend.runtime_v3.surfaces import visible_changes
    from backend.runtime_v3.context import build_context
    from dataclasses import asdict
    s=letters();out=send(s,artifact(recipient='child'));s['world_state']=out.state
    e=next(iter(out.state['remote_events'].values()))
    advance_clock(s,e['delivery_due_at'],WorldHistoryV3().to_dict())
    s,h=apply(s,dict(action='read',event_id=e['id'],operation_id='npc-read-only130'),actor_id='child',autonomous=True)
    assert SECRET not in json.dumps(ui_view(s,h),ensure_ascii=False)
    messages=build_context(s,[],'Жду.','turn',131072,4096)
    assert SECRET not in json.dumps(messages,ensure_ascii=False)
    changes={'state_patch':{'upserts':{'remote_events':s['world_state']['remote_events'],'facts':s['world_state']['facts']}}}
    assert SECRET not in json.dumps(visible_changes(changes,s['world_state'],'a'),ensure_ascii=False)


def test_delivery_settings_not_regenerated_by_world_author():
    from backend.services.draft_initial import prompt_schema
    properties=prompt_schema()['properties']['world']['properties']['communication']['properties']
    assert 'delivery_minutes' not in properties


def test_profile_delay_and_instant_override_no_location_or_contact():
    s=letters();s['world_state']['contacts']={};s['world_state']['characters']['b']['location_id']=None
    s['world_state']['meta']['communication']['delivery_policy']['telegram']='instant'
    s,_=apply(s,dict(action='send',channel='TELEGRAM',character_id='b',content='Текст игрока.',operation_id='instant-telegram-130'))
    e=next(iter(s['world_state']['remote_events'].values()))
    assert e['world_time']==e['delivery_due_at'] and e['status']=='delivered' and not e['read_by']


def test_delivery_before_later_death_uses_chronological_life_state():
    s=letters();s,_=apply(s,dict(action='send',channel='LETTER',character_id='b',content='Текст игрока.',operation_id='before-death130'))
    e=next(iter(s['world_state']['remote_events'].values()))
    data=payload(s['world_state'],[],elapsed=40)
    data['life_changes']=[dict(id='b',life_status='dead',evidence='В конце сцены умер.')]
    out=StateResolver(s['world_state'],'В конце сцены умер.','').resolve(data)
    assert out.state['characters']['b']['life_status']=='dead'
    assert out.state['remote_events'][e['id']]['status']=='delivered'
    assert not out.state['remote_events'][e['id']]['read_by']


def test_variant_branch_restores_original_payload_without_redelivery(api):
    repo,c,sid,p,turn=api;assert turn('start')['status']=='saved'
    a=artifact('qa_vera','qa_kirill');p.artifacts=[a];p.rows=[extracted(a)]
    job=turn();assert job['status']=='saved'
    node=repo.list_turns(sid)[-1];first=repo.get_snapshot(sid)
    p.artifacts=[];p.rows=[]
    job=turn('regenerate');assert job['status']=='saved',job['error']
    assert repo.get_snapshot(sid)['world_state']['remote_events']=={}
    alternate=repo.list_turns(sid)[-1]['active_variant_id']
    repo.select_variant(sid,node['id'],node['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==first['world_state']
    repo.select_variant(sid,node['id'],alternate,repo.get_save(sid)['revision'])
    assert not repo.get_snapshot(sid)['world_state']['remote_events']
    assert_private(c,sid,job['id'])


def test_long_term_authored_send_and_private_npc_read_receipts():
    from backend.runtime_v3.long_term import run
    from backend.runtime_v3.models import Thread
    s=letters();s['world_state']['threads']['post']=Thread(id='post',description='Написать письмо',character_ids=['b'],relevance=1).model_dump()
    s,_=apply(s,dict(action='send',channel='LETTER',character_id='b',content=SECRET,operation_id='letter-to-npc130'))
    original=next(iter(s['world_state']['remote_events'].values()))
    advance_clock(s,original['delivery_due_at'],WorldHistoryV3().to_dict())
    a=artifact(sender='b',recipient='child')
    calls=[]
    def generate(stage,messages,limit,temp,**kw):
        calls.append(stage)
        if stage=='long_term_narrative':
            kw['on_private_result']([a]);return iter([PUBLIC])
        current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
        return iter([json.dumps(dict(final_scene=dict(location_id=current['camera']['location_id'],present_character_ids=['b'],elapsed_minutes=0),
            events=[dict(id='write',text=PUBLIC,participants=['b'],witnesses=['b'],medium='action',advance_candidate_ids=kw['context_key'])],
            remote_events=[dict(sender_id='a',recipient_ids=['b'],channel='LETTER',existing_event_id=original['id'],reader_id='b'),extracted(a)]))])
    after,batch,report=run(s,dict(amount=10,unit='weeks',max_llm_calls=2),generate=generate,config=CONFIG)
    assert report['accepted'],report['diagnostics']
    assert len(calls)==2
    assert len(after['world_state']['remote_events'])==2
    assert after['world_state']['remote_events'][original['id']]['read_by']==['b']
    assert SECRET not in json.dumps(report,ensure_ascii=False)


def test_invalid_saved_payload_errors_do_not_echo_private_input():
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    s=letters();out=send(s);state=out.state
    next(iter(state['remote_events'].values()))['content']=SECRET*200
    with pytest.raises(StructuralDeltaError) as err:assert_world_state_v3_invariants(state)
    assert SECRET not in str(err.value)
    assert 'remote_events' in str(err.value) and 'string_too_long' in str(err.value)
