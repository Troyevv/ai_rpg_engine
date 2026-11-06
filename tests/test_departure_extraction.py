"""Phone/006 equivalent replay. Only the provider responses are scripted."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import ACTOR_ID, load_fixture
from runtime_v3_fixture import execute
from test_api import api
from test_extraction_revision137 import run
from test_narrative_test_world import CONFIG, ordinary_job
from test_phone122 import execute as answer_call


NPC = 'qa_timur'
ACTION = 'Я остаюсь на месте, занимаюсь своими фотографиями и даю другим возможность связаться со мной.'
DEPARTURE = 'Тимур складывает фотографии и уходит, дверь за ним закрывается.'


def active_history(repo, snapshot):
    with repo.connect() as db:
        return read_history(db, snapshot['history_head'])[0]


def departure(camera):
    return dict(
        final_scene=dict(location_id=camera['location_id'], elapsed_minutes=1,
                         present_character_ids=[cid for cid in camera['present_character_ids'] if cid != NPC]),
        events=[dict(id='departure', text=DEPARTURE, participants=[NPC], witnesses=[ACTOR_ID], medium='observation')],
    )


def null_arrival(camera):
    return dict(actor_id=NPC, to_location_id=None, from_location_id=camera['location_id'],
                assertion='completed_arrival', actor_evidence=DEPARTURE)


@pytest.fixture
def phone(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone')['save']
    ordinary_job(repo, sid, 'start')
    return client, repo, sid


@pytest.mark.parametrize('corrected', [False, True])
def test_phone006_repair_and_lineage(phone, corrected):
    client, repo, sid = phone
    before = repo.get_snapshot(sid)
    state = before['world_state']
    camera = state['camera']
    original_turns = repo.list_turns(sid)
    original_variants = repo.variants(original_turns[-1]['node_id'])
    original_history = active_history(repo, before)
    good = departure(camera)
    bad = dict(good, movements=[null_arrival(camera)])
    job, calls = run(client, sid, [bad, good if corrected else bad], DEPARTURE, 'turn', ACTION)
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    assert 'Departure without destination' in calls[1]['messages'][0]['content']
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [(d['code'], d['path'], d['source_ids']) for d in diagnostics] == [
        ('movement_endpoint_invalid', 'movements[0].to_location_id', [NPC])] * (1 if corrected else 2)
    repair = calls[-1]['messages'][0]['content']
    assert diagnostics[0]['path'] in repair and diagnostics[0]['repair_reason'] in repair
    assert 'сохрани Event ухода' in repair and 'Не угадывай ID' in repair
    repo = Repository(repo.path)
    if not corrected:
        assert job['status'] == 'error'
        assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == original_turns
        assert repo.variants(original_turns[-1]['node_id']) == original_variants
        assert active_history(repo, before) == original_history
        return

    assert job['status'] == 'saved', job.get('error')
    saved = repo.get_snapshot(sid)
    end = saved['world_state']
    assert end['camera']['present_character_ids'] == [ACTOR_ID, 'qa_vera']
    assert end['characters'][NPC] == dict(state['characters'][NPC], location_id=None, situation='')
    for key in ('locations', 'knowledge', 'contacts'):
        assert end[key] == state[key]
    for key in ('controlled_actor_id', 'pov_actor_id', 'location_id'):
        assert end['camera'][key] == camera[key]
    history = active_history(repo, saved)
    event, = [e for e in history['events'] if e.get('local_id') == 'departure']
    assert event['text'] == DEPARTURE and event['witnesses'] == [ACTOR_ID]
    assert history['movements'] == original_history['movements']
    assert any(c.get('entity') == NPC and c.get('kind') == 'scene_position' and c['location_id'] is None
               for c in history['state_changes'])
    assert NPC not in client.get(f'/api/saves/{sid}').json()['state']['scene_meta']['present_ids']

    # A sibling interprets an intention as an intention: Timur stays with the group.
    stay = dict(final_scene=dict(good['final_scene'], present_character_ids=camera['present_character_ids']))
    text = 'Тимур собирается уйти, но пока остаётся за столом.'
    turn = repo.list_turns(sid)[-1]
    sibling, _ = run(client, sid, [stay], text, 'regenerate')
    assert sibling['status'] == 'saved', sibling.get('error')
    alternative = repo.get_snapshot(sid)
    assert alternative['world_state']['characters'][NPC]['location_id'] == camera['location_id']
    assert alternative['world_state']['camera']['present_character_ids'] == camera['present_character_ids']
    assert active_history(repo, alternative)['events'] == original_history['events']
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == saved
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    branch, _ = run(client, sid, [good], DEPARTURE, 'turn', ACTION)
    assert branch['status'] == 'saved', branch.get('error')
    branched = repo.get_snapshot(sid)
    assert branched['history_head'] != saved['history_head']
    assert len([e for e in active_history(repo, branched)['events'] if e.get('local_id') == 'departure']) == 1
    assert active_history(repo, saved) == history


def test_departure_after_answered_call(phone):
    client, repo, sid = phone
    with patch('engine.launch'):
        result = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
            revision=repo.get_save(sid)['revision'], config=CONFIG,
            command=dict(action='call', contact_id='phone-qa_kirill-qa-vera', operation_id='call-before-departure')))
    assert result.status_code == 200, result.text
    jid = result.json()['job']['id']
    answer_call(repo, jid)
    assert repo.get_job(jid)['status'] == 'saved'
    call, = repo.get_snapshot(sid)['world_state']['remote_events'].values()
    assert call['status'] == 'answered'
    camera = repo.get_snapshot(sid)['world_state']['camera']
    reply = 'Вера отвечает по телефону: «Да, я тебя слышу».'
    voice = dict(final_scene=dict(location_id=camera['location_id'],
                                  present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
                 events=[dict(id='voice', text=reply, participants=[ACTOR_ID, 'qa_vera'],
                              witnesses=[ACTOR_ID, 'qa_vera'], medium='conversation', interaction_channel='call')])
    jid = repo.begin_job(sid, 'Ты меня слышишь?', 'turn', dict(CONFIG, interaction_channel='call'))
    execute(repo, jid, voice, reply)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert repo.list_turns(sid)[-1]['presentation']['call_text'] == reply
    result = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
                         command=dict(action='end', event_id=call['id'], operation_id='end-before-departure')))
    assert result.status_code == 200, result.text
    state = repo.get_snapshot(sid)['world_state']
    job, calls = run(client, sid, [departure(state['camera'])], DEPARTURE, 'turn', ACTION)
    assert job['status'] == 'saved' and len(calls) == 2
    after = repo.get_snapshot(sid)['world_state']
    assert after['characters'][NPC]['location_id'] is None and after['remote_events'] == state['remote_events']


def test_group_departure_preserves_another_confirmed_route(phone):
    client, repo, sid = phone
    state = repo.get_snapshot(sid)['world_state']
    camera = state['camera']
    away = next(loc for loc in state['locations'].values() if loc['id'] != camera['location_id'])
    text = f"Кирилл, Вера и Тимур обсуждают фотографии. {DEPARTURE} Вера добралась до места «{away['name']}»."
    good = departure(camera)
    good['final_scene']['present_character_ids'] = [ACTOR_ID]
    good['movements'] = [dict(actor_id='qa_vera', from_location_id=camera['location_id'],
                              to_location_id=away['id'], assertion='completed_arrival', evidence=text)]
    bad = deepcopy(good)
    bad['movements'].append(null_arrival(camera))
    job, calls = run(client, sid, [bad, good], text, 'turn', ACTION)
    assert job['status'] == 'saved', job.get('error')
    assert 'movements[1].to_location_id' in calls[-1]['messages'][0]['content']
    saved = repo.get_snapshot(sid)
    assert saved['world_state']['characters'][NPC]['location_id'] is None
    assert saved['world_state']['characters']['qa_vera']['location_id'] == away['id']
    move = active_history(repo, saved)['movements'][-1]
    assert (move['actor_id'], move['from_location_id'], move['to_location_id']) == (
        'qa_vera', camera['location_id'], away['id'])


def test_departure_cannot_move_player(phone):
    _, repo, sid = phone
    state = repo.get_snapshot(sid)['world_state']
    camera = state['camera']
    raw = departure(camera)
    raw['final_scene']['location_id'] = next(lid for lid in state['locations'] if lid != camera['location_id'])
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(state, DEPARTURE, ACTION).resolve(raw)
    assert exc.value.code == 'movement_agency'
