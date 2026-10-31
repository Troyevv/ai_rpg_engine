"""Public authored sources + real resolver/API/jobs/SQLite; only provider HTTP is faked."""
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
from backend.services.letter_sources import parse
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_remote_communication import phone
from test_narrative_phone138 import payload, wait
from test_narrative_test_world import CONFIG

SECRET = 'SEALED-130: Встреча у башни, пароль — янтарь.'
PUBLIC = 'Гонец забрал запечатанное письмо.'

def authored(*artifacts):
    return PUBLIC + ''.join('\n\n```letter\n'+a['content']+'\n```' for a in artifacts)


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
    a = dict(a, id='letter-1')
    return StateResolver(snap['world_state'],authored(a),'Жду.').resolve(payload(snap['world_state'],[extracted(a)]))


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
        StateResolver(s,PUBLIC,'',letter_sources=[a]).resolve(payload(s,[]))
    with pytest.raises(StructuralDeltaError):
        parse('```letter\n'+SECRET)
    assert parse(PUBLIC)==[]
    assert parse(authored(a))[0]['content']==SECRET


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
        self.artifacts=[];self.rows=[];self.elapsed=1;self.fail_extraction=False;self.bad=False;self.calls=[];self.gate=None;self.entered=None;self.delay=0;self.finish_gate=None;self.chunk_size=7
    def create(self, **kw):
        extraction=bool(kw.get('response_format'))
        self.calls.append('extraction' if extraction else 'narrative')
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        if extraction:
            if self.fail_extraction:raise RuntimeError('fixture extraction failure')
            value=json.dumps(dict(final_scene=dict(location_id=current['camera']['location_id'],present_character_ids=current['camera']['present_character_ids'],elapsed_minutes=self.elapsed),remote_events=self.rows),ensure_ascii=False)
            chunks=[NS(choices=[NS(delta=NS(content=value),finish_reason='stop')])]
        else:
            assert 'tools' not in kw and 'tool_choice' not in kw
            value=authored(*self.artifacts)
            if self.bad:value=value[:-3]
            def prose():
                import time
                yield NS(choices=[NS(delta=NS(content=PUBLIC+'\n\n'),finish_reason=None)])
                if self.gate is not None:
                    self.entered.set()
                    assert self.gate.wait(10)
                for i in range(len(PUBLIC)+2,len(value),self.chunk_size):
                    if self.delay:time.sleep(self.delay)
                    yield NS(choices=[NS(delta=NS(content=value[i:i+self.chunk_size]),finish_reason=None)])
                if self.finish_gate is not None: assert self.finish_gate.wait(30)
                yield NS(choices=[NS(delta=NS(content=''),finish_reason='stop')])
            chunks=prose()
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
            r=c.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text='' if kind=='start' else 'Жду.',revision=repo.get_save(sid)['revision'],config=extra.pop('config',CONFIG),**extra))
            assert r.status_code==200,r.text
            return wait(repo,r.json()['id'])
        yield repo,c,sid,p,turn


def assert_unread(c,sid,jid):
    # Reader-visible prose is allowed. The character's mail and Knowledge are gated.
    mail=c.get(f'/api/saves/{sid}/correspondence').json()
    assert all('content' not in e for e in mail if not e.get('outgoing'))
    view=c.get(f'/api/saves/{sid}').json()
    assert SECRET not in json.dumps(view.get('world',{}),ensure_ascii=False)


def test_api_jobs_provider_sqlite_retry_regenerate_rollback_and_open(api):
    repo,c,sid,p,turn=api
    job=turn('start');assert job['status']=='saved',job['error']
    a=artifact('qa_vera','qa_kirill');p.artifacts=[a];p.rows=[extracted(a)];p.fail_extraction=True
    before=repo.get_snapshot(sid);job=turn();assert job['status']=='error',job
    assert_unread(c,sid,job['id'])
    assert repo.get_snapshot(sid)==before
    p.fail_extraction=False;calls=p.calls.count('narrative')
    r=c.post(f"/api/jobs/{job['id']}/retry",json={'config':CONFIG});assert r.status_code==200,r.text
    job=wait(repo,job['id']);assert job['status']=='saved',job['error']
    assert p.calls.count('narrative')==calls
    first=repo.get_snapshot(sid);e=next(iter(first['world_state']['remote_events'].values()))
    assert e['content']==SECRET and e['status']=='in_transit'
    revision = repo.get_save(sid)['revision']
    turns = repo.list_turns(sid)
    with pytest.raises(ValueError, match='уже сохранён'):
        repo.commit_job(job['id'], first, [], {})
    assert repo.get_snapshot(sid) == first
    assert repo.get_save(sid)['revision'] == revision and repo.list_turns(sid) == turns
    assert_unread(c,sid,job['id'])
    fresh=Repository(repo.path);assert fresh.get_snapshot(sid)==first
    job=turn('regenerate');assert job['status']=='saved',job['error']
    assert repo.get_snapshot(sid)['world_state']['remote_events']==first['world_state']['remote_events']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)['world_state']==before['world_state']
    job=turn();assert job['status']=='saved',job['error']
    p.rows=[];p.artifacts=[]
    job=turn(time_skip={'duration':5,'reason':'Жду почту'});assert job['status']=='saved',job['error']
    assert next(iter(repo.get_snapshot(sid)['world_state']['remote_events'].values()))['status']=='in_transit'
    job=turn(time_skip={'duration':10,'reason':'Жду почту'});assert job['status']=='saved',job['error']
    assert_unread(c,sid,job['id'])
    current=repo.get_snapshot(sid);e=next(iter(current['world_state']['remote_events'].values()))
    assert e['status']=='delivered' and not e['read_by']
    command=dict(action='read',event_id=e['id'],operation_id='open-canonical-letter')
    revision=repo.get_save(sid)['revision']
    read_calls=list(p.calls)
    for _ in range(2):
        r=c.post(f'/api/saves/{sid}/phone',json=dict(revision=revision,command=command));assert r.status_code==200,r.text
    assert p.calls==read_calls
    assert c.get(f'/api/saves/{sid}/correspondence').json()[0]['content']==SECRET
    with repo.connect() as db:h,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    assert len([x for x in h['events'] if x.get('remote',{}).get('status')=='delivered' and not x['remote']['read_by']])==1
    job=turn();assert job['status']=='saved',job['error']


def test_incomplete_letter_never_commits_a_fictitious_send(api):
    repo,c,sid,p,turn=api;p.bad=True;p.artifacts=[artifact('qa_vera','qa_kirill')]
    before=repo.get_snapshot(sid);job=turn('start')
    assert job['status']=='error'
    assert SECRET in job['narrative']
    assert repo.get_snapshot(sid)==before
    assert_unread(c,sid,job['id'])


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
    p.artifacts=[artifact('qa_vera','qa_kirill',aid=f'letter-{i+1}') for i in range(3)]
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
    assert_unread(c,sid,jid)
    assert Repository(repo.path).get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']


@pytest.mark.parametrize('text', ['```letter\n', '```letter\ntext', '```letter\n\n```'])
def test_full_letter_source_required(text):
    with pytest.raises(StructuralDeltaError):parse(text)


def test_markdown_source_is_complete_literal_and_not_prose_guessing():
    text='Dear friend,\n\n«Quotation», punctuation and `inline code`.\nYours, NPC'
    assert parse('He wrote: "a summary".')==[]
    assert parse('```python\nnot a letter\n```')==[]
    assert parse(authored(dict(content=text)))[0]['content']==text


@pytest.mark.parametrize('with_letter',[False,True])
@pytest.mark.parametrize('historical_only',[False,True])
def test_real_job_streams_before_provider_finishes_without_granting_knowledge(api,with_letter,historical_only):
    import threading
    repo,c,sid,p,turn=api
    if historical_only:
        with repo.connect() as db:
            snap=repo.get_snapshot(sid)
            snap['world_state']['meta']['communication'].update(text_message=False,voice_call=False)
            db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    assert turn('start')['status']=='saved'
    if with_letter:
        a=artifact('qa_vera','qa_kirill');p.artifacts=[a];p.rows=[extracted(a)]
    p.gate=threading.Event();p.entered=threading.Event()
    before=repo.get_snapshot(sid)
    response=c.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',text='Жду.',revision=repo.get_save(sid)['revision'],config=CONFIG))
    jid=response.json()['id']
    try:
        assert p.entered.wait(5)
        job=c.get(f'/api/jobs/{jid}').json()
        assert PUBLIC in job['narrative'] and not job['narrative_complete']
        assert repo.get_snapshot(sid)==before
    finally:p.gate.set()
    job=wait(repo,jid);assert job['status']=='saved',job['error']
    assert (SECRET in job['narrative']) == with_letter
    assert repo.get_snapshot(sid)['world_state']['knowledge']==before['world_state']['knowledge']
    events=repo.get_snapshot(sid)['world_state']['remote_events']
    assert len(events)==int(with_letter)
    if with_letter:assert next(iter(events.values()))['content']==SECRET


def test_legacy_completed_private_job_payload_can_still_bind():
    s=letters()['world_state'];a=artifact()
    out=StateResolver(s,PUBLIC,'',letter_sources=[a]).resolve(payload(s,[extracted(a)]))
    assert next(iter(out.state['remote_events'].values()))['content']==SECRET


def test_landline_reuses_voice_runtime_without_contact():
    s=letters();s['world_state']['meta']['communication'].update(voice_call=False,text_message=False,landline=True)
    s['world_state']['contacts']={}
    s,_=apply(s,dict(action='call',character_id='b',operation_id='landline-1939'))
    e=next(iter(s['world_state']['remote_events'].values()))
    assert e['channel']=='VOICE_CALL' and e['status']=='ringing'


def test_npc_read_does_not_grant_controlled_actor_knowledge():
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
    pov=next(m for m in messages if m['content'].startswith('Знания POV'))
    assert SECRET not in pov['content']
    assert SECRET in next(m['content'] for m in messages if m['content'].startswith('LETTER AUTHORING CONTRACT:'))
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
    assert_unread(c,sid,job['id'])


def test_long_term_authored_send_and_npc_read_receipts():
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
            return iter([authored(a)])
        current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
        return iter([json.dumps(dict(final_scene=dict(location_id=current['camera']['location_id'],present_character_ids=['b'],elapsed_minutes=0),
            events=[dict(id='write',text=PUBLIC,participants=['b'],witnesses=['b'],medium='action',advance_candidate_ids=kw['context_key'])],
            remote_events=[dict(sender_id='a',recipient_ids=['b'],channel='LETTER',existing_event_id=original['id'],reader_id='b'),extracted(a)]))])
    after,batch,report=run(s,dict(amount=10,unit='weeks',max_llm_calls=2),generate=generate,config=CONFIG)
    assert report['accepted'],report['diagnostics']
    assert len(calls)==2
    assert len(after['world_state']['remote_events'])==2
    assert after['world_state']['remote_events'][original['id']]['read_by']==['b']
    assert any(e['content']==SECRET for e in after['world_state']['remote_events'].values())


def test_structural_errors_keep_existing_safe_diagnostics():
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    s=letters();out=send(s);state=out.state
    next(iter(state['remote_events'].values()))['content']={'invalid_type':SECRET}
    with pytest.raises(StructuralDeltaError) as err:assert_world_state_v3_invariants(state)
    assert SECRET not in str(err.value)
    assert 'remote_events' in str(err.value) and 'string_type' in str(err.value)


def test_old_private_checkpoint_retries_without_regenerating_letter(api):
    repo,c,sid,p,turn=api
    assert turn('start')['status']=='saved'
    a=artifact('qa_vera','qa_kirill');p.artifacts=[a];p.rows=[extracted(a)];p.fail_extraction=True
    job=turn();assert job['status']=='error' and job['narrative_complete']
    with repo.connect() as db:
        db.execute('UPDATE game_jobs SET narrative=?,private_artifacts_json=? WHERE id=?',(PUBLIC,json.dumps([a]),job['id']))
    p.fail_extraction=False;calls=p.calls.count('narrative')
    assert c.post(f"/api/jobs/{job['id']}/retry",json={'config':CONFIG}).status_code==200
    job=wait(repo,job['id']);assert job['status']=='saved',job['error']
    assert p.calls.count('narrative')==calls
    assert next(iter(repo.get_snapshot(sid)['world_state']['remote_events'].values()))['content']==SECRET


def test_player_api_send_preserves_exact_authorship_without_llm(api):
    repo,c,sid,p,turn=api
    assert turn('start')['status']=='saved'
    calls=list(p.calls);content='Мой текст.\n\nБез продолжения за меня.\nПодпись игрока.'
    revision=repo.get_save(sid)['revision']
    command=dict(action='send',channel='LETTER',character_id='qa_vera',content=content,operation_id='player-exact-130')
    for _ in range(2):
        r=c.post(f'/api/saves/{sid}/correspondence',json=dict(revision=revision,command=command))
        assert r.status_code==200,r.text
    assert p.calls==calls
    events=repo.get_snapshot(sid)['world_state']['remote_events']
    assert len(events)==1 and next(iter(events.values()))['content']==content
    assert not next(iter(events.values()))['read_by']


def test_author_correspondence_is_inside_the_context_budget():
    from backend.runtime_v3.context import build_context
    from backend.services.letter_sources import author_context, CONTRACT
    from context_builder import estimate
    snap=letters()
    for _ in range(6):
        a=artifact(recipient='child');a['content']='Полный текст для адресата. '*1400
        snap['world_state']=send(snap,a).state
    advance_clock(snap,snap['world_state']['meta']['world_time']+100,WorldHistoryV3().to_dict())
    original = deepcopy(snap)
    messages=build_context(snap,[],'Жду.','turn',24000,2000)
    assert estimate(messages)<=24000-2000-256
    author=next(m for m in messages if m['content'].startswith(CONTRACT))
    assert len(author['content'])<len(author_context(snap['world_state'])['content'])
    assert sum(CONTRACT in m['content'] for m in messages)==1
    assert snap == original


@pytest.mark.parametrize('source_id', ['letter-0', 'letter-2', 'letter-01', 'missing'])
def test_invalid_source_id_cannot_create_letter(source_id):
    snap = letters(); before = deepcopy(snap)
    a = artifact()
    with pytest.raises(StructuralDeltaError):
        StateResolver(snap['world_state'], authored(a), '').resolve(
            payload(snap['world_state'], [dict(extracted(a), artifact_id=source_id)]))
    assert snap == before


def test_multiple_full_sources_are_bound_without_loss():
    snap = letters()
    first = artifact(); first['content'] = 'Я' * 30997 + '\n\nЯ'
    second = artifact(channel='TELEGRAM', aid='letter-2')
    second['content'] = '  Привет, друг!\r\n\r\nДо встречи.  '
    text = authored(first) + '\n\n```python\nignored\n```\n\n' + authored(second)
    sources = parse(text)
    assert [x['content'] for x in sources] == [first['content'], second['content']]
    result = StateResolver(snap['world_state'], text, '').resolve(
        payload(snap['world_state'], [extracted(first), extracted(second)]))
    assert sorted(e['content'] for e in result.state['remote_events'].values()) == sorted([first['content'], second['content']])


def test_letter_rendering_is_literal_prose_not_code():
    from character_links import linked_markdown
    text = '<script>alert(1)</script>\n**Literal** & `text`'
    html = linked_markdown(authored(dict(content=text)) + '\n\n```python\nx = 1\n```', [])
    assert '<blockquote class="narrative-letter"' in html
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert '**Literal** &amp; `text`' in html
    assert 'language-letter' not in html and '```letter' not in html
    assert '<code class="language-python">' in html


def long_letter(size):
    suffix = '\nКонец.  \r\n'
    return ('  Дорогой друг!\r\n\r\n' + ('Жизнь — не список ограничений. 🕯️\n' * size))[:size-len(suffix)] + suffix


@pytest.mark.parametrize('channel', ['LETTER', 'COURIER_LETTER', 'TELEGRAM'])
@pytest.mark.parametrize('size', [10000, 35000])
def test_unlimited_player_letters_api_sqlite_and_repeated_send(api, channel, size):
    repo, c, sid, provider, turn = api
    with repo.connect() as db:
        snap = repo.get_snapshot(sid)
        snap['world_state']['meta']['communication'].update(courier=True, telegram=True)
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    content = long_letter(size)
    command = dict(action='send', channel=channel, character_id='qa_vera', content=content,
                   operation_id='long-player-letter130')
    revision = repo.get_save(sid)['revision']
    for _ in range(2):
        response = c.post(f'/api/saves/{sid}/correspondence', json=dict(command=command, revision=revision))
        assert response.status_code == 200, response.text
    mail = c.get(f'/api/saves/{sid}/correspondence').json()
    assert len(mail) == 1 and mail[0]['content'] == content
    fresh = Repository(repo.path).get_snapshot(sid)
    assert next(iter(fresh['world_state']['remote_events'].values()))['content'] == content
    assert provider.calls == []


def test_dozen_long_npc_letters_one_job_exact_lifecycle_reload_and_rollback(api):
    repo, c, sid, provider, turn = api
    assert turn('start')['status'] == 'saved'
    before = repo.get_snapshot(sid)
    sources = [dict(artifact('qa_vera', 'qa_kirill', aid=f'letter-{i+1}'),
                    content=long_letter(10000 if i == 0 else 35000) if i < 2 else f'  Письмо {i}.\nПодпись.  ')
               for i in range(40)]
    provider.artifacts = sources
    provider.rows = [extracted(a) for a in sources]
    job = turn()
    assert job['status'] == 'error' and 'Контекст v3 не помещается' in job['error']
    assert job['narrative'] == authored(*sources) and repo.get_snapshot(sid) == before
    narrative_calls = provider.calls.count('narrative')
    large_config = dict(CONFIG, context_length=131072)
    response = c.post(f"/api/jobs/{job['id']}/retry", json={'config':large_config})
    assert response.status_code == 200, response.text
    job = wait(repo, job['id'])
    assert job['status'] == 'saved', job['error']
    assert provider.calls.count('narrative') == narrative_calls
    sent = repo.get_snapshot(sid)
    expected = [a['content'] for a in sources]
    events = list(sent['world_state']['remote_events'].values())
    assert [e['content'] for e in events] == expected
    assert len(events) == 40 and all(e['provenance'] and e['operation_id'] for e in events)
    assert sent['world_state']['knowledge'] == before['world_state']['knowledge']
    assert job['narrative'] == authored(*sources)
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(sid) == sent
    assert fresh.list_turns(sid)[-1]['assistant_text'] == authored(*sources)
    provider.artifacts = []; provider.rows = []
    assert turn(config=large_config, time_skip={'duration':20, 'reason':'Жду доставку'})['status'] == 'saved'
    calls = list(provider.calls)
    for e, content in zip(events, expected):
        revision = repo.get_save(sid)['revision']
        command = dict(action='read', event_id=e['id'], operation_id='open-long-'+e['id'])
        for _ in range(2):
            response = c.post(f'/api/saves/{sid}/correspondence', json=dict(revision=revision, command=command))
            assert response.status_code == 200, response.text
        mail = c.get(f'/api/saves/{sid}/correspondence').json()
        assert next(x for x in mail if x['id'] == e['id'])['content'] == content
    assert provider.calls == calls
    saved = Repository(repo.path).get_snapshot(sid)
    assert [e['content'] for e in saved['world_state']['remote_events'].values()] == expected
    assert all(e['read_by'] == ['qa_kirill'] for e in saved['world_state']['remote_events'].values())
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state'] == sent['world_state']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state'] == before['world_state']


def test_152_modern_message_text_is_preserved_without_literary_cap():
    from backend.runtime_v3.remote_models import RemoteCommand, ExtractedRemoteEvent
    text = 'x' * 10000
    assert RemoteCommand(action='send', operation_id='modern-long152', content=text).content == text
    assert ExtractedRemoteEvent(channel='TEXT_MESSAGE', sender_id='b', recipient_ids=['a'], content=text).content == text
