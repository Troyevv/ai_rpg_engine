"""Stage C Crisis/010 equivalent replay. Only the two provider stages are scripted."""
from copy import deepcopy
import json

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
    raw['final_scene']['present_character_ids'].append(VERA)
    raw['movements'] = [dict(actor_id=VERA, assertion='completed_arrival',
                             from_location_id=state['characters'][VERA]['location_id'], to_location_id=lid)]
    arrived = StateResolver(state, TEXT, ACTION).resolve(raw)
    assert arrived.state['characters'][VERA]['location_id'] == lid
    assert arrived.state['characters'][VERA]['situation'] == TEXT
    del raw['movements']
    assert StateResolver(arrived.state, TEXT, ACTION).resolve(raw).history['events'][0]['location_id'] == lid
    raw['final_scene']['present_character_ids'].remove(VERA)
    raw.pop('character_changes')
    left = StateResolver(arrived.state, 'После разговора Вера уходит.', ACTION).resolve(raw)
    assert left.state['characters'][VERA]['location_id'] is None
    assert left.history['events'][0]['participants'] == [NINA, VERA]


def test_repair_to_call_requires_answered_channel(tmp_path):
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
    raw['events'][0]['interaction_channel'] = 'call'
    row, = StateResolver(state, '', '').resolve(raw).history['events']
    assert row['interaction_channel'] == 'call' and row['witnesses'] == ['a', 'b']
    disabled = deepcopy(state)
    disabled['meta']['communication'].update(voice_call=False, text_message=False)
    for unavailable in (ringing, ended['world_state'], disabled):
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(unavailable, '', '').resolve(raw)
        assert exc.value.diagnostic('extraction')['path'] == 'events[0].interaction_channel'
