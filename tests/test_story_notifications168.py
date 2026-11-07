import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.models import Knowledge, Thread
from backend.runtime_v3.notifications import record_story_changes, story_notifications, read_story_receipts
from backend.runtime_v3.repository import committed_snapshot, read_history, append_history
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.selectors import ui_view
from test_story_secrets178 import fixture, incoming, classify, read
from test_goals_values import raw
from test_runtime_v3_storage import connection
from story_notifications_fixture import seed, payload, TEXT
from test_narrative_test_world import CONFIG


def reveal(snap, *, new=False, status='known', actor='a', witness=True):
    s=snap['world_state']
    facts=[]
    fid='fresh' if new else 'plot'
    if new:facts=[dict(id=fid,text='Скрытое авторство',visibility='secret',story_secret=True,secret_subject_ids=['b'],evidence='Признание')]
    return StateResolver(s,'Признание','').resolve(raw(s,facts=facts,
        events=[dict(id='source',text='Признание',evidence='Признание',participants=['a','b'],witnesses=[actor] if witness else [],fact_ids=[fid],medium='conversation')],
        knowledge_gained=[dict(actor_id=actor,fact_id=fid,status=status,source_event_id='source',evidence='Признание')]))


@pytest.mark.parametrize('new,prior,kind',[(False,None,'secret_revealed'),(False,'suspected','secret_revealed'),(True,None,'secret_new')])
def test_confirmation_requires_atomic_commit(tmp_path,new,prior,kind):
    before=fixture(together=True)
    if prior:before['world_state']['knowledge']['a:plot']=Knowledge(actor_id='a',fact_id='plot',status=prior).model_dump()
    result=reveal(before,new=new)
    assert not ui_view(dict(before,world_state=result.state),result.history)['notification_history']
    db=connection(tmp_path/'db')
    with pytest.raises(RuntimeError):
        with db:
            committed_snapshot(db,before,result)
            raise RuntimeError('variant failed')
    assert read_story_receipts(db,None)==[]
    assert db.execute('select count(*) from world_history_v3').fetchone()[0]==0
    with db:after=committed_snapshot(db,before,result)
    events=story_notifications(result.state,read_story_receipts(db,after['history_head']))
    assert len(events)==1 and events[0]['kind']==kind
    assert events[0]['slot_id']
    assert events[0]['character_ids']==['b']
    # A sibling variant has a distinct presentation identity, same canonical slot.
    with db:sibling=committed_snapshot(db,before,result)
    other=story_notifications(result.state,read_story_receipts(db,sibling['history_head']))[0]
    assert other['id']!=events[0]['id'] and other['slot_id']==events[0]['slot_id']
    assert read_story_receipts(db,before.get('history_head'))==[]


@pytest.mark.parametrize('status,actor',[('suspected','a'),('known','b')])
def test_no_notice_for_suspicion_or_other_mind(status,actor):
    before=fixture(together=True);r=reveal(before,status=status,actor=actor)
    record_story_changes(before['world_state'],r.state,r.history,'commit')
    assert not story_notifications(r.state,r.history['state_changes'])


def test_control_switch_and_repeat_do_not_create_openings():
    before=fixture(together=True);r=reveal(before)
    record_story_changes(r.state,r.state,r.history,'repeat')
    assert not story_notifications(r.state,r.history['state_changes'])
    r.state['camera']['controlled_actor_id']='b'
    record_story_changes(before['world_state'],r.state,r.history,'switch')
    assert not story_notifications(r.state,r.history['state_changes'])


@pytest.mark.parametrize('source,witness,existing,expect_notice',[(True,True,False,True),(False,True,False,False),(True,False,False,False),(True,True,True,False)])
def test_thread_needs_witnessed_origin_not_participation(source,witness,existing,expect_notice):
    before=fixture(together=True);s=before['world_state']
    if existing:s['threads']['t']=Thread(id='t',description='Старая линия').model_dump()
    r=StateResolver(s,'Разговор','').resolve(raw(s,
        events=[dict(id='e',text='Разговор',evidence='Разговор',participants=['a','b'],witnesses=['a'] if witness else ['b'],fact_ids=[])],
        thread_changes=[dict(id='t',description='Линия',character_ids=['a'],stakes_for=['a'],source_event_id='e' if source else 'missing',evidence='Разговор')]))
    record_story_changes(s,r.state,r.history,'commit')
    events=story_notifications(r.state,r.history['state_changes'])
    assert bool(events)==expect_notice
    view=ui_view(dict(before,world_state=r.state),r.history)
    assert ('t' in view['world']['threads'])==(expect_notice or existing)


def test_thread_cannot_expose_unknown_source_fact():
    before=fixture(together=True);s=before['world_state']
    r=StateResolver(s,'Разговор','').resolve(raw(s,
        events=[dict(id='e',text='Разговор',evidence='Разговор',participants=['a'],witnesses=['a'],fact_ids=['plot'])],
        thread_changes=[dict(id='t',description='NEVER: авторство романа',source_event_id='e',evidence='Разговор')]))
    record_story_changes(s,r.state,r.history,'commit')
    assert 'NEVER' not in json.dumps(ui_view(dict(before,world_state=r.state),r.history))


def test_remote_read_is_commit_source_and_bread_is_not(tmp_path):
    before=incoming(fixture(),content='Признание');eid=next(iter(before['world_state']['remote_events']))
    before,_=classify(before,eid);after,batch=read(before,eid)
    record_story_changes(before['world_state'],after['world_state'],batch,'reading')
    assert len(story_notifications(after['world_state'],batch['state_changes']))==1
    repeat,second=read(after,eid)
    record_story_changes(after['world_state'],repeat['world_state'],second,'repeat')
    assert not story_notifications(repeat['world_state'],second['state_changes'])
    before=incoming(fixture(),content='Купи хлеб');eid=next(iter(before['world_state']['remote_events']))
    after,batch=read(before,eid);record_story_changes(before['world_state'],after['world_state'],batch,'bread')
    assert not story_notifications(after['world_state'],batch['state_changes'])


def test_history_outlives_context_tail_and_projects_only_current_actor(tmp_path):
    db=connection(tmp_path/'db');before=fixture(together=True);r=reveal(before)
    with db:after=committed_snapshot(db,before,r)
    for _ in range(70):
        with db:after['history_head']=append_history(db,after['history_head'],{})
    history,_=read_history(db,after['history_head'])
    assert not story_notifications(r.state,history['state_changes'])
    records=read_story_receipts(db,after['history_head'])
    assert len(story_notifications(r.state,records))==1
    r.state['camera']['controlled_actor_id']='b'
    assert not story_notifications(r.state,records)
    # Old data, including known-at-start, never gains synthetic events on load.
    assert not ui_view(before)['notification_history']


def run_turn(repo,sid,*,replaces=None,reveal_secret=True):
    snap=repo.get_snapshot(sid)
    if replaces:
        with repo.connect() as db:snap=json.loads(db.execute('select before_json from turns where id=?',(replaces,)).fetchone()[0])
    data=payload(snap,reveal_secret)
    def stream(**kwargs):yield json.dumps(data,ensure_ascii=False) if kwargs.get('response_format') else TEXT
    jid=repo.begin_job(sid,'Расскажи о рукописи.','regenerate' if replaces else 'turn',dict(CONFIG,target_turn_id=replaces) if replaces else CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    job=repo.get_job(jid);assert job['status']=='saved',job['error']
    return repo.get_save(sid)


def test_real_engine_commit_save_reload_regenerate_rollback(tmp_path):
    repo=Repository(tmp_path/'game.db');selected=seed(repo);sid=selected['save']
    before=repo.get_save(sid);assert not before['state']['notification_history']
    assert 'NEVER-EXPOSE' not in json.dumps(before)
    after=run_turn(repo,sid);events=after['state']['notification_history']
    assert [e['kind'] for e in events]==['secret_revealed','secret_new','thread_new']
    rows=after['state']['story_secrets']['personal']
    a=next(r for r in rows['qa_vera'] if r.get('fact_id')=='plot178')
    b=next(r for r in rows['qa_timur'] if r.get('fact_id')=='plot178')
    assert a['reveal_id']==b['reveal_id']==events[0]['id']
    assert Repository(repo.path).get_save(sid)['state']['notification_history']==events
    tid=repo.list_turns(sid)[-1]['id']
    variant=run_turn(repo,sid,replaces=tid,reveal_secret=False)
    assert [e['kind'] for e in variant['state']['notification_history']]==['thread_new']
    assert not set(e['id'] for e in events)&set(e['id'] for e in variant['state']['notification_history'])
    repo.rollback_last(sid)
    restored=repo.get_save(sid)
    assert not restored['state']['notification_history']
    assert all('reveal_id' not in r for r in restored['state']['story_secrets']['personal']['qa_vera'])


def test_retired_secret_retains_only_safe_acquisition_history():
    before=fixture(together=True);r=reveal(before)
    record_story_changes(before['world_state'],r.state,r.history,'commit')
    original=story_notifications(r.state,r.history['state_changes'])[0]
    r.state['knowledge']['a:plot']['status']='refuted'
    retired=story_notifications(r.state,r.history['state_changes'])
    assert len(retired)==1 and retired[0]['id']==original['id']
    assert retired[0]['available'] is False
    assert 'Соня скрывает' not in json.dumps(retired,ensure_ascii=False)
    assert 'slot_id' not in retired[0]


def test_background_thread_cannot_grant_controlled_actor_knowledge():
    before=fixture(together=True);s=before['world_state']
    r=StateResolver(s,'Разговор','',observed=False,mode='background').resolve(raw(s,
        events=[dict(id='e',text='Разговор',evidence='Разговор',participants=['a','b'],witnesses=['a','b'],fact_ids=[])],
        thread_changes=[dict(id='t',description='Закулисная линия',discovered_by=['a'],source_event_id='e',evidence='Разговор')]))
    record_story_changes(s,r.state,r.history,'commit')
    assert 'a' not in r.state['threads']['t']['discovered_by']
    assert not story_notifications(r.state,r.history['state_changes'])
    assert 't' not in ui_view(dict(before,world_state=r.state),r.history)['world']['threads']


def test_unseen_thread_revision_cannot_rewrite_observed_journal_or_api(tmp_path):
    before=fixture(together=True);db=connection(tmp_path/'threads.db')
    def update(snap,actor,description):
        s=snap['world_state']
        r=StateResolver(s,'Разговор','').resolve(raw(s,
            events=[dict(id='e',text='Разговор',evidence='Разговор',participants=['a','b'],witnesses=[actor],fact_ids=[])],
            thread_changes=[dict(id='t',description=description,state=description,character_ids=['a','b'],source_event_id='e',evidence='Разговор')]))
        with db:return committed_snapshot(db,snap,r)
    first=update(before,'a','Найти письмо')
    second=update(first,'b','NEVER-EXPOSE-THREAD-REVISION')
    history,_=read_history(db,second['history_head']);history['_story_receipts']=read_story_receipts(db,second['history_head'])
    view=ui_view(second,history)
    assert 'NEVER-EXPOSE-THREAD' not in json.dumps(view)
    assert view['world']['threads']['t']['description']=='Найти письмо'
    assert view['notification_history'][0]['text']=='Найти письмо'
    assert len(view['notification_history'])==1
    # A later witnessed update changes the visible revision, never its creation event.
    third=update(second,'a','Письмо найдено')
    history,_=read_history(db,third['history_head']);history['_story_receipts']=read_story_receipts(db,third['history_head'])
    view=ui_view(third,history)
    assert view['world']['threads']['t']['description']=='Письмо найдено'
    assert view['notification_history'][0]['text']=='Найти письмо'
    assert len(view['notification_history'])==1
    # Switching actor resolves that actor's observed history, not another mind.
    from backend.runtime_v3.protagonist import transition
    third,_=transition(third,'temporary','b','thread-view-b')
    view=ui_view(third,history)
    assert view['world']['threads']['t']['description']=='NEVER-EXPOSE-THREAD-REVISION'
    assert not view['notification_history']
