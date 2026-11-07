"""Stage C Crisis/010 equivalent replay. Only the two provider stages are scripted."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_api import api
from test_extraction_revision137 import run
from test_narrative_test_world import ordinary_job
from test_remote_communication import phone, incoming, command

ACTION = 'Я, Нина, спрашиваю Веру о состоянии Кирилла и предлагаю практическую помощь.'
TEXT = 'Нина предлагает помощь. Вера отвечает Нине в библиотеке.'
NINA, VERA = 'qa_nina', 'qa_vera'


@pytest.fixture
def crisis(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo)['save']
    ordinary_job(repo, sid, 'start')
    repo.transition_protagonist(sid, repo.get_save(sid)['revision'], 'switch-nina', 'permanent', NINA)
    return client, repo, sid


def physical(state):
    camera = state['camera']
    assert set(camera['present_character_ids']) == {NINA, 'qa_marina', 'qa_asya', 'qa_zoya'}
    assert camera['controlled_actor_id'] == NINA and not camera['remote_interactions']
    assert state['characters'][VERA]['location_id'] != camera['location_id']
    return dict(final_scene=dict(location_id=camera['location_id'], present_character_ids=camera['present_character_ids'][:],
                                 elapsed_minutes=1, remote_interactions=[]),
                events=[dict(id='crisis010', text=TEXT, medium='conversation', location_id=camera['location_id'],
                             participants=[NINA, VERA], witnesses=[NINA, VERA, 'qa_asya', 'qa_marina', 'qa_zoya'])],
                scene_actions=[dict(actor_id=NINA, target_ids=[VERA], source_event_id='crisis010',
                                    phase='start', modality='speech', response='open')],
                character_changes=[dict(id=VERA, situation=TEXT, source_event_id='crisis010')])


def history(repo, snapshot):
    with repo.connect() as db:
        return read_history(db, snapshot['history_head'])[0]


@pytest.mark.parametrize('corrected', [False, True])
def test_crisis010_atomic_repair_reload_and_lineage(crisis, corrected):
    client, repo, sid = crisis
    before = repo.get_snapshot(sid)
    original = history(repo, before)
    turns = repo.list_turns(sid)
    variants = repo.variants(turns[-1]['node_id'])
    bad = physical(before['world_state'])
    good = deepcopy(bad)
    event = good['events'][0]
    event.update(text='Нина предлагает помощь.', participants=[NINA])
    event['witnesses'].remove(VERA)
    job, calls = run(client, sid, [bad, good if corrected else bad], TEXT, 'turn', ACTION)
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [(d['code'], d['path'], d['source_ids']) for d in diagnostics] == [
        ('event_presence_invalid', 'events[0].participants[1]', ['crisis010', VERA])
    ] * (1 if corrected else 2)
    assert diagnostics[0]['path'] in calls[-1]['messages'][0]['content']
    fresh = Repository(repo.path)
    saved = fresh.get_snapshot(sid)
    assert history(fresh, before) == original
    if not corrected:
        assert job['status'] == 'error'
        assert saved == before and fresh.list_turns(sid) == turns
        assert fresh.variants(turns[-1]['node_id']) == variants
        return

    assert job['status'] == 'saved', job.get('error')
    accepted = history(fresh, saved)
    row, = [e for e in accepted['events'] if e.get('local_id') == 'crisis010']
    assert row['participants'] == [NINA] and row['witnesses'] == event['witnesses']
    assert 'scene_action' not in row
    assert saved['world_state']['characters'][VERA] == before['world_state']['characters'][VERA]
    assert saved['world_state']['knowledge'] == before['world_state']['knowledge']
    turn = fresh.list_turns(sid)[-1]
    quiet = dict(final_scene=good['final_scene'])
    sibling, _ = run(client, sid, [quiet], 'Нина ждёт.', 'regenerate')
    assert sibling['status'] == 'saved'
    assert history(fresh, fresh.get_snapshot(sid))['events'] == original['events']
    fresh.select_variant(sid, turn['id'], turn['active_variant_id'], fresh.get_save(sid)['revision'])
    assert fresh.get_snapshot(sid) == saved
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid) == before
    branch, _ = run(client, sid, [quiet], 'Нина садится за стол.', 'turn', 'Сажусь за стол.')
    assert branch['status'] == 'saved' and history(fresh, saved) == accepted
    assert history(fresh, fresh.get_snapshot(sid))['events'] == original['events']


def test_false_witness_cannot_receive_a_secret(crisis):
    _, repo, sid = crisis
    state = repo.get_snapshot(sid)['world_state']
    bad = physical(state)
    bad['events'][0].update(participants=[NINA], fact_ids=['qa_private_letter'])
    bad['knowledge_gained'] = [dict(actor_id=VERA, fact_id='qa_private_letter', source_event_id='crisis010')]
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(state, TEXT, ACTION).resolve(bad)
    assert exc.value.diagnostic('extraction')['path'] == 'events[0].witnesses[1]'
    bad['events'][0]['witnesses'].remove(VERA)
    result = StateResolver(state, TEXT, ACTION).resolve(bad)
    assert result.state['knowledge'] == state['knowledge']
    assert not result.history['knowledge_acquisitions']


def test_intention_completed_arrival_and_subsequent_departure(crisis):
    _, repo, sid = crisis
    state = repo.get_snapshot(sid)['world_state']
    raw = physical(state)
    lid = raw['final_scene']['location_id']
    with pytest.raises(StructuralDeltaError, match=VERA):
        StateResolver(state, 'Вера собирается прийти в библиотеку.', ACTION).resolve(raw)
    planned = dict(raw, movements=[dict(actor_id=VERA, to_location_id=lid, assertion='planned')])
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(state, 'Вера собирается прийти.', ACTION).resolve(planned)
    assert exc.value.diagnostic('extraction')['path'] == 'movements[0].assertion'
    raw['final_scene']['present_character_ids'].append(VERA)
    raw['movements'] = [dict(actor_id=VERA, assertion='completed_arrival',
                             from_location_id=state['characters'][VERA]['location_id'], to_location_id=lid)]
    arrived = StateResolver(state, TEXT, ACTION).resolve(raw)
    assert arrived.state['characters'][VERA]['location_id'] == lid
    assert arrived.state['characters'][VERA]['situation'] == TEXT
    raw['events'][0]['order'] = 1
    assert StateResolver(state, TEXT, ACTION).resolve(raw).history['events'][0]['order'] == 1
    del raw['movements']
    assert StateResolver(arrived.state, TEXT, ACTION).resolve(raw).history['events'][0]['location_id'] == lid
    raw['final_scene']['present_character_ids'].remove(VERA)
    raw.pop('character_changes')
    left = StateResolver(arrived.state, 'После разговора Вера уходит.', ACTION).resolve(raw)
    assert left.state['characters'][VERA]['location_id'] is None
    assert left.history['events'][0]['participants'] == [NINA, VERA]


def test_call_requires_answered_channel():
    snap = incoming(phone(), 'call', '')
    eid, = snap['world_state']['remote_events']
    ringing = snap['world_state']
    answered = command(snap, 'answer', event_id=eid)
    ended = command(answered, 'end', event_id=eid)
    raw = dict(final_scene=dict(location_id='home', present_character_ids=ringing['camera']['present_character_ids']),
               events=[dict(id='call', text='Ответ из другого дома', medium='conversation',
                            participants=['a', 'b'], witnesses=['a', 'b'])])
    state = answered['world_state']
    with pytest.raises(StructuralDeltaError):
        StateResolver(state, '', '').resolve(raw)
    raw['events'][0].update(interaction_channel='call', order=2)
    row, = StateResolver(state, '', '').resolve(raw).history['events']
    assert row['interaction_channel'] == 'call' and row['witnesses'] == ['a', 'b']
    disabled = deepcopy(state)
    disabled['meta']['communication'].update(voice_call=False, text_message=False)
    for unavailable in (ringing, ended['world_state'], disabled):
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(unavailable, '', '').resolve(raw)
        assert exc.value.diagnostic('extraction')['path'] == 'events[0].interaction_channel'


@pytest.mark.parametrize('closed', [False, True])
def test_channel_repair_cannot_invent_connection(api, closed):
    from test_phone122 import execute as answer_call
    from runtime_v3_fixture import execute
    from test_narrative_test_world import CONFIG
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone-office')['save']
    ordinary_job(repo, sid, 'start')
    with patch('engine.launch'):
        response = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
            revision=repo.get_save(sid)['revision'], config=CONFIG,
            command=dict(action='call', contact_id='phone-qa_kirill-qa-vera', operation_id='start-226')))
    assert response.status_code == 200, response.text
    answer_call(repo, response.json()['job']['id'])
    call, = repo.get_snapshot(sid)['world_state']['remote_events']

    if closed:
        response = client.post(f'/api/saves/{sid}/phone', json=dict(
            revision=repo.get_save(sid)['revision'], command=dict(action='end', event_id=call, operation_id='close-call-before-repair-226')))
        assert response.status_code == 200, response.text
    before = repo.get_snapshot(sid)
    camera = before['world_state']['camera']
    assert VERA not in camera['present_character_ids']
    assert before['world_state']['characters'][VERA]['location_id'] != camera['location_id']
    actors = [camera['controlled_actor_id'], VERA]
    bad = dict(final_scene=dict(location_id=camera['location_id'], present_character_ids=camera['present_character_ids']),
               events=[dict(id='voice', text='Я тебя слышу.', medium='conversation', participants=actors,
                            witnesses=actors)])
    repaired = deepcopy(bad)
    repaired['events'][0]['interaction_channel'] = 'call'
    jid = repo.begin_job(sid, 'Ты меня слышишь?', 'turn', CONFIG)
    calls = execute(repo, jid, bad, 'Вера отвечает: «Я тебя слышу».', repaired)
    assert len(calls) == 3
    assert 'events[0].participants[1]' in calls[-1]['messages'][0]['content']
    saved = Repository(repo.path).get_snapshot(sid)
    if closed:
        assert repo.get_job(jid)['status'] == 'error' and saved == before
    else:
        assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
        voice, = [e for e in history(repo, saved)['events'] if e.get('local_id') == 'voice']
        assert voice['interaction_channel'] == 'call' and voice['witnesses'] == actors


def test_linked_message_roles_come_from_the_accepted_send():
    from test_narrative_phone138 import resolve, message
    snap = phone()
    row = dict(id='delivery', text='Доставлено сообщение.', medium='message', author_id='b',
               participants=['b', 'a'], witnesses=['b'])
    remote = [message(source_event_id='delivery')]
    result = resolve(snap, remote, events=[row])
    assert next(e for e in result.history['events'] if e.get('local_id') == 'delivery')['witnesses'] == ['b']
    for changed, field in [(dict(author_id='a'), 'author_id'), (dict(witnesses=['child']), 'witnesses[0]')]:
        with pytest.raises(StructuralDeltaError) as exc:
            resolve(snap, remote, events=[dict(row, **changed)])
        assert exc.value.diagnostic('extraction')['path'] == 'events[0].' + field


@pytest.mark.parametrize('repair_order', [False, True])
def test_crossing_routes_cannot_publish_a_conversation_or_knowledge(crisis, repair_order):
    client, repo, sid = crisis
    before = repo.get_snapshot(sid)
    original = history(repo, before)
    state = before['world_state']
    library = state['camera']['location_id']
    home = state['characters'][VERA]['location_id']
    action = 'Я иду домой к Вере.'
    fact = 'qa_news_at_meeting'
    prose = 'Нина приходит домой к Вере. Вера говорит о письме и уходит в библиотеку.'
    raw = dict(
        final_scene=dict(location_id=home, present_character_ids=[NINA], elapsed_minutes=2),
        movements=[
            dict(actor_id=NINA, from_location_id=library, to_location_id=home,
                 player_assertion='explicit_choice', player_evidence=action),
            dict(actor_id=VERA, from_location_id=home, to_location_id=library)],
        facts=[dict(id=fact, text='В письме есть новости.', visibility='secret')],
        events=[dict(id='exchange', text='Они говорят о письме.', medium='conversation',
                     location_id=home, participants=[NINA, VERA], witnesses=[NINA, VERA], fact_ids=[fact])],
        knowledge_gained=[dict(actor_id=NINA, fact_id=fact, source_event_id='exchange')])

    # Same actors, locations, fact and scene; only the supported sequence differs.
    ordered = deepcopy(raw)
    ordered['movements'][0]['order'] = 1
    ordered['events'][0]['order'] = 2
    ordered['movements'][1]['order'] = 3
    job, _ = run(client, sid, [raw, ordered if repair_order else raw], prose, 'turn', action)
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [d['path'] for d in diagnostics] == ['events[0].participants[1]'] * (1 if repair_order else 2)
    fresh = Repository(repo.path)
    assert history(fresh, before) == original
    saved = fresh.get_snapshot(sid)
    if not repair_order:
        assert job['status'] == 'error' and saved == before
        return
    assert job['status'] == 'saved', job.get('error')
    row, = [e for e in history(fresh, saved)['events'] if e.get('local_id') == 'exchange']
    assert row['order'] == 2 and row['location_id'] == home
    assert saved['world_state']['knowledge'][NINA + ':' + fact]['source_event_id'] == row['id']
    assert saved['world_state']['characters'][VERA]['location_id'] == library
    fresh.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid) == before
    assert history(fresh, before) == original


@pytest.mark.parametrize('meeting_order,accepted', [(0, False), (1, False), (2, True), (3, False),
                                                     (4, False), (5, False), (6, True), (None, True)])
def test_multiple_moves_use_the_same_phase_for_every_role(crisis, meeting_order, accepted):
    _, repo, sid = crisis
    s = repo.get_snapshot(sid)['world_state']
    library = s['camera']['location_id']
    home = s['characters'][VERA]['location_id']
    # Vera visits, leaves, then visits again. Input array deliberately reversed.
    raw = physical(s)
    raw['final_scene']['present_character_ids'].append(VERA)
    raw['movements'] = [dict(actor_id=VERA, from_location_id=a, to_location_id=b, order=n)
                        for n, a, b in [(5, home, library), (3, library, home), (1, home, library)]]
    if meeting_order is not None:
        raw['events'][0]['order'] = meeting_order
    if accepted:
        assert StateResolver(s, TEXT, ACTION).resolve(raw).history['events'][0]['location_id'] == library
    else:
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(s, TEXT, ACTION).resolve(raw)
        assert exc.value.code == 'event_presence_invalid'


@pytest.mark.parametrize('arrival,departure,accepted', [(3, 1, False), (2, 2, False), (1, 3, True),
                                                       (None, None, False), (None, 3, False)])
def test_an_unordered_event_still_needs_one_shared_scene(crisis, arrival, departure, accepted):
    _, repo, sid = crisis
    s = repo.get_snapshot(sid)['world_state']
    raw = physical(s)
    library = s['camera']['location_id']
    home = s['characters'][VERA]['location_id']
    # Asya only witnesses. She leaves for home while Vera comes from there.
    raw['final_scene']['present_character_ids'].remove('qa_asya')
    raw['final_scene']['present_character_ids'].append(VERA)
    raw['movements'] = [dict(actor_id=cid, to_location_id=loc, **({'order': n} if n is not None else {}))
                        for cid, loc, n in [(VERA, library, arrival), ('qa_asya', home, departure)]]
    if accepted:
        assert StateResolver(s, TEXT, ACTION).resolve(raw).history['events'][0]['witnesses'] == raw['events'][0]['witnesses']
    else:
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(s, TEXT, ACTION).resolve(raw)
        assert exc.value.diagnostic('extraction')['path'] == 'events[0].witnesses[2]'


def test_unknown_destination_does_not_keep_a_witness_for_a_later_arrival(crisis):
    _, repo, sid = crisis
    s = repo.get_snapshot(sid)['world_state']
    raw = physical(s)
    raw['final_scene']['present_character_ids'].remove('qa_asya')
    raw['final_scene']['present_character_ids'].append(VERA)
    raw['movements'] = [dict(actor_id=VERA, to_location_id=s['camera']['location_id'], order=1)]
    raw['events'][0]['order'] = 2
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s, TEXT, ACTION).resolve(raw)
    assert exc.value.diagnostic('extraction')['path'] == 'events[0].witnesses[2]'
    raw['events'][0]['witnesses'].remove('qa_asya')
    result = StateResolver(s, TEXT, ACTION).resolve(raw)
    assert result.state['characters']['qa_asya']['location_id'] is None
    assert all(m['actor_id'] != 'qa_asya' for m in result.history['movements'])
