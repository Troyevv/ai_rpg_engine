"""#129: canonical routing, private projections and actual API/job lineage."""
import json
from copy import deepcopy
from threading import Event
from unittest.mock import patch

import pytest
import engine
from test_remote_communication import phone, command
from test_communication_cycle import decision
from test_phone122 import setup, execute
from test_narrative_test_world import CONFIG, ordinary_job
from backend.runtime_v3.remote import apply, projection, recipient_eligible
from backend.runtime_v3.protagonist import transition
from backend.runtime_v3.communication import run
from backend.repositories.preparation import Repository


def strangers():
    s = phone()
    s['world_state']['contacts'] = {}
    s['world_state']['objective_relations'] = {}
    return s


@pytest.mark.parametrize('action', ['send', 'call'])
def test_t01_t02_no_contact_acquaintance_device_or_address(action):
    s = strangers()
    before = deepcopy(s)
    after = command(s, action, character_id='b', content='Привет.')
    event = next(iter(after['world_state']['remote_events'].values()))
    assert event['recipient_ids'] == ['b'] and event['contact_id'] is None
    assert event['destination'] == 'b'
    assert after['world_state']['contacts'] == {}
    assert after['world_state']['knowledge'] == before['world_state']['knowledge']
    assert s == before
    assert {r['id'] for r in projection(after)['recipients']} == {'b', 'child', 'baby'}


@pytest.mark.parametrize('route', ['character_id', 'contact_id', 'conversation_id'])
def test_t03_dead_recipient_all_routes_reject_history_survives(route):
    s = command(phone(), 'send', contact_id='a-b', content='Старое сообщение')
    event = next(iter(s['world_state']['remote_events'].values()))
    s['world_state']['characters']['b']['life_status'] = 'dead'
    target = dict(character_id='b', contact_id='a-b', conversation_id=event['conversation_id'])[route]
    before = deepcopy(s)
    for action in ('send', 'call'):
        with pytest.raises(ValueError, match='Адресат'):
            command(s, action, **{route: target}, content='Новое')
    p = projection(s)
    assert p['events'][0]['content'] == 'Старое сообщение'
    assert not p['contacts'][0]['can_send'] and not p['conversations'][0]['can_send']
    assert 'b' not in {r['id'] for r in p['recipients']}
    assert s == before


@pytest.mark.parametrize('outcome,expected', [('silent', 'missed'), ('decline', 'declined'), ('answer', 'answered')])
def test_t04_no_number_does_not_force_answer(outcome, expected):
    s = command(strangers(), 'call', character_id='b')
    eid = next(iter(s['world_state']['remote_events']))
    after, _, report = run(s, dict(source_event_id=eid, owner_id='a', request_id='129-cycle'),
                           lambda i, messages: decision(messages, outcome), Event())
    assert report['outcome'] == expected and report['decisions'] == 1
    assert not report.get('unavailable')
    assert after['world_state']['contacts'] == {}


def test_t05_switch_does_not_transfer_messages_or_knowledge():
    s = command(strangers(), 'send', character_id='b', content='ONLY A AND B')
    before = deepcopy(s['world_state']['knowledge'])
    other, _ = transition(s, 'temporary', 'child', 'switch')
    view = projection(other)
    assert view['events'] == [] and view['conversations'] == []
    assert 'ONLY A AND B' not in json.dumps(view)
    assert 'Приватное письмо' not in json.dumps(view, ensure_ascii=False)
    assert {r['id'] for r in view['recipients']} == {'a', 'b', 'baby'}
    assert other['world_state']['knowledge'] == before
    assert all(set(r) == {'id', 'subject', 'can_send', 'can_call'} for r in view['recipients'])


def test_t06_t07_group_legacy_labels_and_dead_members():
    s = command(phone(), 'create_group', member_ids=['b', 'child'], label='Старая группа')
    gid = next(iter(s['world_state']['conversations']))
    contacts = deepcopy(s['world_state']['contacts'])
    s = command(s, 'send', conversation_id=gid, content='Всем')
    s['world_state']['characters']['b']['life_status'] = 'dead'
    s = command(s, 'send', conversation_id=gid, content='Живым')
    assert list(s['world_state']['remote_events'].values())[-1]['recipient_ids'] == ['child']
    assert len(s['world_state']['conversations'][gid]['members']) == 3
    assert s['world_state']['contacts'] == contacts
    loaded = json.loads(json.dumps(s))
    assert projection(loaded) == projection(s)
    assert projection(s)['contacts'][0]['label'] == 'Saved b'


@pytest.mark.parametrize('target', ['missing', 'a'])
def test_invalid_and_self_targets(target):
    with pytest.raises(ValueError, match='Адресат'):
        command(strangers(), 'send', character_id=target, content='Текст')


def test_t08_profile_channels_and_unknown_life_fallback():
    s = strangers()
    for life in ('unknown', None):
        if life:
            s['world_state']['characters']['b']['life_status'] = life
        else:
            s['world_state']['characters']['b'].pop('life_status')
        assert recipient_eligible(s['world_state'], 'a', 'b', 'TEXT_MESSAGE')
    cfg = s['world_state']['meta']['communication']
    cfg.update(text_message=False, voice_call=False, letter=True)
    assert recipient_eligible(s['world_state'], 'a', 'b', 'LETTER')
    assert not recipient_eligible(s['world_state'], 'a', 'b', 'TEXT_MESSAGE')
    with pytest.raises(ValueError):
        command(s, 'send', character_id='b', content='Текст')


def api_strangers(tmp_path):
    repo, client, sid = setup(tmp_path)
    snap = repo.get_snapshot(sid)
    snap['world_state']['contacts'] = {}
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    return repo, client, sid


def dispatch(repo, client, sid, action='send', operation='129-api-send'):
    payload = dict(revision=repo.get_save(sid)['revision'], config=CONFIG,
                   command=dict(action=action, operation_id=operation,
                                character_id='qa_vera', content='Привет.'))
    with patch('engine.launch'):
        response = client.post(f'/api/saves/{sid}/phone/dispatch', json=payload)
    assert response.status_code == 200, response.text
    return response.json()['job']['id'], payload


@pytest.mark.parametrize('action', ['send', 'call'])
def test_t09_api_duplicate_retry_and_rollback(tmp_path, action):
    repo, client, sid = api_strangers(tmp_path)
    before = repo.get_snapshot(sid)
    jid, payload = dispatch(repo, client, sid, action)
    with patch('engine.launch'):
        duplicate = client.post(f'/api/saves/{sid}/phone/dispatch', json=payload)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()['job']['id'] == jid
    assert len(repo.get_snapshot(sid)['world_state']['remote_events']) == 1
    # Provider failure leaves the accepted original command; Retry must reuse it.
    with patch('engine.chat_stream', side_effect=RuntimeError('test outage')):
        engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)['status'] == 'error'
    with patch('engine.launch'):
        response = client.post(f'/api/jobs/{jid}/retry', json={'config': CONFIG})
    assert response.status_code == 200, response.text
    execute(repo, jid, outcome='silent')
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    after = repo.get_snapshot(sid)
    assert len(after['world_state']['remote_events']) == 1
    assert after['world_state']['contacts'] == {}
    assert Repository(repo.path).get_snapshot(sid) == after
    repo.rollback_last(sid)
    # Device command precedes the communication turn; rollback keeps that one
    # accepted attempt, reverting its processing, never creating a second send.
    rolled = repo.get_snapshot(sid)['world_state']
    assert len(rolled['remote_events']) == 1
    assert rolled['meta']['world_time'] == before['world_state']['meta']['world_time']


def test_t10_start_turn_reload_next_turn_and_no_planning_poll(tmp_path):
    repo, client, sid = api_strangers(tmp_path)  # real Start Game
    ordinary_job(repo, sid)
    jid, _ = dispatch(repo, client, sid)
    execute(repo, jid, outcome='silent')
    assert repo.get_job(jid)['status'] == 'saved'
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(sid) == repo.get_snapshot(sid)
    from test_narrative_phone138 import Provider
    provider = Provider()
    jid = fresh.begin_job(sid, 'Жду.', 'turn', CONFIG)
    with patch('engine.chat_stream', provider), patch('engine.find_loaded_model', return_value={'config': {'context_length': 131072}}):
        engine.run_job(fresh.path, jid, engine.Worker())
    assert fresh.get_job(jid)['status'] == 'saved', fresh.get_job(jid)['error']
    assert provider.calls == ['remote_decision', 'narrative', 'extraction']
    assert len(fresh.get_snapshot(sid)['world_state']['remote_events']) == 1


# Run the real ordinary Narrative extraction + Retry/regeneration/variant/
# rollback journey with no stored routing contacts on either side.
from test_narrative_phone138 import api138


def test_no_contact_narrative_regenerate_retry_and_branch(api138):
    from test_narrative_phone138 import test_t08_t09_api_repair_retry_regenerate_rollback_branch_reload
    repo, client, sid, provider, turn = api138
    snap = repo.get_snapshot(sid)
    snap['world_state']['contacts'] = {}
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    test_t08_t09_api_repair_retry_regenerate_rollback_branch_reload(api138)
    saved = repo.get_snapshot(sid)
    branch = repo.create_save(repo.get_save(sid)['world_id'], '129 branch')
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(saved), branch))
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(branch)['world_state'] == saved['world_state']
    assert fresh.get_snapshot(branch)['world_state']['contacts'] == {}


def test_api_dead_target_keeps_history_and_rejects_new_attempt(tmp_path):
    repo, client, sid = api_strangers(tmp_path)
    jid, _ = dispatch(repo, client, sid)
    execute(repo, jid, outcome='silent')
    snap = repo.get_snapshot(sid)
    snap['world_state']['characters']['qa_vera']['life_status'] = 'dead'
    snap['world_state']['camera']['present_character_ids'] = [
        cid for cid in snap['world_state']['camera']['present_character_ids'] if cid != 'qa_vera']
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    before = repo.get_snapshot(sid)
    with patch('engine.launch'):
        response = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
            revision=repo.get_save(sid)['revision'], config=CONFIG,
            command=dict(action='call', operation_id='dead-api129', character_id='qa_vera')))
    assert response.status_code == 409, response.text
    assert repo.get_snapshot(sid) == before
    public = client.get(f'/api/saves/{sid}').json()['state']['phone']
    assert len(public['events']) == 1
    assert 'qa_vera' not in {r['id'] for r in public['recipients']}


def test_groups_without_contacts_use_same_eligibility():
    s = command(strangers(), 'create_group', member_ids=['b'], label='Новая группа')
    gid = next(iter(s['world_state']['conversations']))
    s = command(s, 'join', conversation_id=gid, member_ids=['child'])
    s = command(s, 'send', conversation_id=gid, content='Всем')
    assert next(iter(s['world_state']['remote_events'].values()))['recipient_ids'] == ['b', 'child']
    assert s['world_state']['contacts'] == {}


def test_incoming_npc_without_contact_is_event_first_and_unread():
    s = strangers()
    after, batch = apply(s, dict(action='send', operation_id='npc-no-contact129',
                                character_id='a', content='Самостоятельное сообщение'),
                         actor_id='b', autonomous=True)
    event = next(iter(after['world_state']['remote_events'].values()))
    assert batch['events'][0]['remote_interaction_id'] == event['id']
    assert event['read_by'] == []
    assert projection(after)['events'][0]['content'] is None
    assert after['world_state']['knowledge'] == s['world_state']['knowledge']
