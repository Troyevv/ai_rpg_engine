import json
from threading import Event
from unittest.mock import patch
import pytest
import engine
from engine_storage import ExistingJob
from test_remote_communication import phone, command
from test_narrative_test_world import CONFIG
from backend.runtime_v3.communication import run, options_for


def decision(messages, outcome='answer'):
    options = json.loads(messages[1]['content'])['options']
    o = options[0]
    action = o['actions'][0]
    if action == 'answer':
        action = outcome
    if outcome == 'silent' or (outcome == 'read_only' and action == 'send'):
        return '{"action":null}'
    p = dict(actor_id=o['actor_id'], action=action, basis_ids=o['basis_ids'])
    if 'event_id' in o:
        p['event_id'] = o['event_id']
    if action == 'send':
        p.update(o['paths'][0], content='Да, увидимся завтра.')
    return json.dumps(dict(action=p), ensure_ascii=False)


@pytest.mark.parametrize('outcome,expected,calls', [('answer','answered',1),('decline','declined',1),('silent','missed',1)])
def test_call_outcomes_are_canonical_and_bounded(outcome, expected, calls):
    s = command(phone(), 'call', contact_id='a-b')
    event = next(iter(s['world_state']['remote_events']))
    request = dict(source_event_id=event, owner_id='a', request_id='cycle-test')
    before = s['world_state']['meta']['world_time']
    after, batch, report = run(s, request, lambda i,m: decision(m,outcome), Event())
    assert report['outcome'] == expected and report['decisions'] == calls
    assert report['elapsed_minutes'] == (2 if outcome == 'silent' else 1)
    assert after['world_state']['meta']['world_time'] == before+report['elapsed_minutes']
    assert after['world_state']['camera'] == s['world_state']['camera']
    assert after['world_state']['characters']['b']['location_id'] == 'away'
    assert after['world_state']['meta']['interaction_focus'] == ('call' if expected == 'answered' else 'physical')


@pytest.mark.parametrize('outcome,accepted', [('answer',['read','send']),('read_only',['read']),('silent',[])])
def test_direct_read_reply_without_reverse_contact(outcome, accepted):
    s = phone()
    del s['world_state']['contacts']['b-a']
    s = command(s, 'send', contact_id='a-b', content='До завтра?')
    event = next(iter(s['world_state']['remote_events']))
    after, _, report = run(s, dict(source_event_id=event,owner_id='a',request_id='text-cycle'), lambda i,m: decision(m,outcome), Event())
    assert report['accepted'] == accepted
    assert report['decisions'] <= 2 and report['elapsed_minutes'] == 1
    assert 'b-a' not in after['world_state']['contacts']
    events = list(after['world_state']['remote_events'].values())
    if 'send' in accepted:
        assert events[1]['content'] == 'Да, увидимся завтра.'
        assert events[1]['conversation_id'] == events[0]['conversation_id']
        assert events[1]['delivered_to'] == ['a']


def ready(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    repo = Repository(tmp_path/'communication.sqlite')
    sid = load_fixture(repo,'phone')['save']
    jid = repo.begin_job(sid,'','start',CONFIG)
    repo.job_progress(jid,'validating',narrative='Начало.',complete=True)
    repo.save_context(jid,[],repo.get_snapshot(sid))
    repo.commit_job(jid,repo.get_snapshot(sid),[],{})
    return repo,sid


def dispatch(repo,sid,action='send',operation='send-once'):
    save=repo.get_save(sid)
    return repo.begin_job(sid,'','communication',dict(CONFIG,expected_revision=save['revision'],remote_command=dict(action=action,operation_id=operation,contact_id=save['state']['phone']['contacts'][0]['id'],content='До завтра?')))


def execute(repo,jid,outcome='answer',fail_at=None):
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if fail_at == len(calls):
            raise RuntimeError('Deterministic provider outage')
        yield decision(kwargs['messages'],outcome)
    with patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return calls


def test_job_atomic_dispatch_retry_replays_read_and_no_duplicate_send(tmp_path):
    repo,sid=ready(tmp_path)
    jid=dispatch(repo,sid)
    original=repo.get_snapshot(sid)
    assert len(original['world_state']['remote_events'])==1
    with pytest.raises(ExistingJob) as duplicate:
        dispatch(repo,sid)
    assert duplicate.value.job_id==jid
    assert len(execute(repo,jid,fail_at=2))==2
    assert repo.get_job(jid)['status']=='error'
    assert repo.get_snapshot(sid)==original
    with pytest.raises(ValueError,match='не обработано'):
        dispatch(repo,sid,operation='second-action')
    assert repo.get_snapshot(sid)==original
    repo.retry_job(jid,CONFIG)
    assert len(execute(repo,jid))==1
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid)
    assert len(after['world_state']['remote_events'])==2
    assert after['world_state']['meta']['world_time']==original['world_state']['meta']['world_time']+1
    with pytest.raises(ExistingJob):
        dispatch(repo,sid)
    assert repo.get_snapshot(sid)==after
    assert len(repo.list_turns(sid))==2


def test_group_shares_budget_and_does_not_touch_other_source():
    s=command(phone(),'create_group',label='Группа',member_ids=['b','child'])
    gid=next(iter(s['world_state']['conversations']))
    s=command(s,'send',conversation_id=gid,content='Встретимся?')
    eid=list(s['world_state']['remote_events'])[-1]
    after,_,report=run(s,dict(source_event_id=eid,owner_id='a',request_id='group-cycle'),lambda i,m:decision(m),Event())
    assert report['decisions']==2
    assert report['accepted']==['read','send']
    assert report['elapsed_minutes']==1
    s=command(s,'edit_contact',contact_id='a-b',blocked=True)
    assert all(o['actor_id']!='b' for o in options_for(s,eid,set()))


def test_regenerate_variants_and_stale_retry(tmp_path):
    repo,sid=ready(tmp_path)
    jid=dispatch(repo,sid,'call')
    execute(repo,jid)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    original=repo.get_snapshot(sid)
    original_turn=repo.list_turns(sid)[-1]
    original_variant=original_turn['active_variant_id']
    regen=repo.begin_job(sid,'','regenerate',CONFIG)
    execute(repo,regen,'decline')
    assert repo.get_job(regen)['status']=='saved',repo.get_job(regen)['error']
    declined=repo.get_snapshot(sid)
    assert list(declined['world_state']['remote_events'].values())[0]['status']=='declined'
    assert declined['world_state']['meta']['world_time']==original['world_state']['meta']['world_time']
    repo.select_variant(sid,original_turn['id'],original_variant,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==original['world_state']
    repo.rollback_last(sid)
    restored=repo.get_snapshot(sid)
    assert list(restored['world_state']['remote_events'].values())[0]['status']=='ringing'
    with pytest.raises(ValueError):
        repo.retry_job(jid,CONFIG)
    with pytest.raises(ValueError,match='другой ветке'):
        dispatch(repo,sid,'call')


def test_unavailable_cannot_be_forced_and_no_unrelated_read():
    from backend.runtime_v3.models import Condition
    s=command(phone(),'call',contact_id='a-b')
    eid=next(iter(s['world_state']['remote_events']))
    s['world_state']['conditions']['unavailable']=Condition(id='unavailable',actor_id='b',description='Без сознания',effects=dict(conscious=False),evidence='QA',source_turn=0).model_dump()
    after,_,report=run(s,dict(source_event_id=eid,owner_id='a',request_id='unavailable'),lambda *args:pytest.fail('Unavailable actor must not invoke provider'),Event())
    assert report['unavailable'] and report['decisions']==0 and report['outcome']=='missed'
    s=command(phone(),'send',contact_id='a-b',content='Исходное сообщение')
    eid=next(iter(s['world_state']['remote_events']))
    for i in range(6):s=command(s,'send',contact_id='a-b',content='Постороннее',operation_id=f'other-message-{i}')
    after,_,report=run(s,dict(source_event_id=eid,owner_id='a',request_id='source-bound'),lambda i,m:decision(m),Event())
    assert after['world_state']['remote_events'][eid]['read_by']==['b']
    assert all(not e['read_by'] for k,e in after['world_state']['remote_events'].items() if k!=eid)


def test_cancelled_worker_cannot_commit_or_mutate_new_owner(tmp_path):
    repo,sid=ready(tmp_path);jid=dispatch(repo,sid,'call')
    engine.stop(repo,jid)
    snap=repo.get_snapshot(sid);eid=next(iter(snap['world_state']['remote_events']))
    repo.remote_action(sid,repo.get_save(sid)['revision'],dict(action='end',event_id=eid,operation_id='explicit-end'))
    ended=repo.get_snapshot(sid)
    assert not execute(repo,jid)
    assert repo.get_snapshot(sid)==ended
    with pytest.raises(ValueError):repo.retry_job(jid,CONFIG)
