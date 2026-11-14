"""Semantic gold cases, not an LLM accuracy evaluation. Only provider output is scripted.

Phone fixtures are synthetic equivalents of the public Issue #223 cases. Exact
archive replays were run separately on private copies, never published here.
Missing arrival provenance is rejected; structurally consistent fiction still requires semantic review.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.raw import extraction_schema, repair_feedback
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_api import api
from test_departure_extraction import phone, active_history, departure, ACTION, NPC
from test_extraction_revision137 import run

FIXTURES = Path(__file__).parent / 'fixtures' / 'movement'


def replay(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


@pytest.mark.parametrize('name', ['phone001', 'phone006'])
def test_phone_equivalent_payload_and_omit_only_movement_control(phone, name):
    case = replay(name)
    _, repo, sid = phone
    before = repo.get_snapshot(sid)['world_state']
    original = deepcopy(before)
    if name == 'phone001':
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(before, case['narrative'], case['player_input'], require_player_agency=True).resolve(case['payload'])
        assert exc.value.code == 'movement_source_invalid'
    else:
        for raw in (case['payload'], case['repair']):
            with pytest.raises(StructuralDeltaError) as exc:
                StateResolver(before, case['narrative'], case['player_input']).resolve(raw)
            assert exc.value.code == 'movement_endpoint_invalid'
            assert exc.value.diagnostic('extraction')['path'] == 'movements[0].to_location_id'
    good = deepcopy(case['payload'])
    del good['movements']  # no other JSON changes, no fabricated arrival Event
    result = StateResolver(before, case['narrative'], case['player_input']).resolve(good)
    assert result.state['characters'][NPC]['location_id'] is None
    assert NPC not in result.state['camera']['present_character_ids']
    assert not result.history['movements']
    assert {e['local_id'] for e in result.history['events']} == {e['id'] for e in good['events']}
    assert result.state['knowledge'] == before['knowledge']
    assert before == original


@pytest.mark.parametrize('name', ['phone001', 'phone006'])
@pytest.mark.parametrize('mode', ['correct', 'repair', 'repeat'])
def test_phone_provider_jobs_contract_reload(phone, name, mode):
    client, repo, sid = phone
    case = replay(name)
    # Synthetic provider responses exercise the real production pipeline.
    before = repo.get_snapshot(sid)
    history = active_history(repo, before)
    turns = repo.list_turns(sid)
    good = deepcopy(case['payload'])
    # v4 represents the same documented departure explicitly; archive unchanged.
    exit_event = good['events'][0]
    exit_event.update(location_id=before['world_state']['camera']['location_id'], order=1)
    good['movements'] = [dict(actor_id=NPC, from_location_id=exit_event['location_id'], to_location_id=None,
        assertion='departure', source_event_id=exit_event['id'], order=1, evidence=exit_event['text'])]
    bad = deepcopy(case['payload'])
    for raw in (good, bad):
        # Explicit protocol annotation of these synthetic movement controls.
        # The on-disk historical fixtures remain unchanged.
        review = raw['player_agency']
        review['narrative_audit'] = [dict(narrative_evidence='Кирилл занимается фотографиями.',
            classification='authorized', player_action_id=a['id']) for a in review['actions']]
        for action in review['actions']:action['target_mode'] = 'reference'
        for event in raw.get('events', []):
            if 'minute' in event:
                event['minute'] = before['world_state']['meta']['world_time']
    # Phone001 has no structural trigger. A null endpoint exercises bounded repair,
    # not an imaginary semantic detector of the original valid workshop ID.
    bad['movements'][0]['to_location_id'] = None
    answers = [good] if mode == 'correct' else [bad, good if mode == 'repair' else bad]
    job, calls = run(client, sid, answers, case['narrative'], 'turn', case['player_input'])
    assert len(calls) == (2 if mode == 'correct' else 3)
    assert sum(not c.get('response_format') for c in calls) == 1
    for call in calls[1:]:
        system = call['messages'][0]['content']
        assert 'Movement intent/attempt causes no relocation' in system and 'completed_narrative' in system
        assert 'Plans/place creation/time/END absence prove no relocation/Knowledge.' in system
        assert json.dumps(case['narrative'], ensure_ascii=False) in '\n'.join(m['content'] for m in call['messages'])
    fresh = Repository(repo.path)
    if mode == 'repeat':
        assert job['status'] == 'error', job.get('error')
        assert fresh.get_snapshot(sid) == before
        assert fresh.list_turns(sid) == turns
        assert active_history(fresh, before) == history
        return
    assert job['status'] == 'saved', job.get('error')
    saved = fresh.get_snapshot(sid)
    assert saved['world_state']['characters'][NPC]['location_id'] is None
    assert saved['world_state']['knowledge'] == before['world_state']['knowledge']
    assert saved['world_state']['locations'] == before['world_state']['locations']
    for field in ('location_id', 'pov_actor_id', 'controlled_actor_id'):
        assert saved['world_state']['camera'][field] == before['world_state']['camera'][field]
    after = active_history(fresh, saved)
    assert after['movements'][:-1] == history['movements']
    assert after['movements'][-1]['actor_id'] == NPC and after['movements'][-1]['to_location_id'] is None
    new_events = after['events'][len(history['events']):]
    assert len(new_events) == len(good['events'])
    assert {e['local_id'] for e in new_events} == {e['id'] for e in good['events']}
    assert len({e['id'] for e in after['events']}) == len(after['events'])


# Human-reviewed gold outcomes: no keyword parser or simulated semantic classifier.
@pytest.mark.parametrize('narrative,leaves', [
    ('Тимур вышел из комнаты; за дверью стихли шаги.', True),
    ('Тимур попрощался и вышел из здания.', True),
    ('Тимур сказал: «Вечером поеду в мастерскую», затем ушёл.', True),
    ('Тимур сказал: «Собираюсь домой», но остался за столом.', False),
    ('Тимур пообещал приехать завтра. Сейчас он сидит рядом.', False),
    ('Тимур назвал мастерскую, куда хотел бы зайти. Разговор продолжился дома.', False),
    ('Тимур ушёл. Через минуту вернулся и сел за тот же стол.', False),
])
def test_gold_intent_departure_and_return_jobs(phone, narrative, leaves):
    client, repo, sid = phone
    before = repo.get_snapshot(sid)
    camera = before['world_state']['camera']
    raw = departure(camera)
    raw['events'][0]['text'] = narrative
    if not leaves:
        raw['movements'] = []
        raw['final_scene']['present_character_ids'] = camera['present_character_ids']
    job, calls = run(client, sid, [raw], narrative, 'turn', ACTION)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    saved = Repository(repo.path).get_snapshot(sid)
    assert saved['world_state']['characters'][NPC]['location_id'] == (None if leaves else camera['location_id'])
    assert (NPC in saved['world_state']['camera']['present_character_ids']) is not leaves
    assert saved['world_state']['knowledge'] == before['world_state']['knowledge']
    assert len(active_history(repo, saved)['movements']) - len(active_history(repo, before)['movements']) == int(leaves)


@pytest.mark.parametrize('legs', [1, 2])
@pytest.mark.parametrize('described_exit', [False, True])
def test_completed_arrivals_and_ordered_routes_jobs(phone, legs, described_exit):
    client, repo, sid = phone
    before = repo.get_snapshot(sid); state = before['world_state']; home = state['camera']['location_id']
    targets = [lid for lid in state['locations'] if lid != home][:legs]
    narrative = ('Тимур вышел из дома. ' if described_exit else '') + ' '.join(
        'Тимур добрался до ' + state['locations'][lid]['name'] + '.' for lid in targets)
    raw = departure(state['camera']); raw['events'] = []; raw['movements'] = []
    if described_exit:
        raw['events'].append(dict(id='exit', text='Тимур попрощался и вышел.', participants=[NPC], witnesses=['qa_kirill'], medium='observation', location_id=home, order=0))
    origin = home
    for i, target in enumerate(targets):
        raw['movements'].append(dict(actor_id=NPC, from_location_id=origin, to_location_id=target, assertion='completed_arrival', source_event_id=f'arrival-{i}', order=2*i+1, evidence=narrative))
        raw['events'].append(dict(id=f'arrival-{i}', text='Тимур прибыл.', participants=[NPC], witnesses=[], medium='action', location_id=target, order=2*i+1))
        origin = target
    job, calls = run(client, sid, [raw], narrative, 'turn', ACTION)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    saved = Repository(repo.path).get_snapshot(sid)
    assert saved['world_state']['characters'][NPC]['location_id'] == targets[-1]
    moves = active_history(repo, saved)['movements'][len(active_history(repo, before)['movements']):]
    assert [m['to_location_id'] for m in moves] == targets
    assert saved['world_state']['knowledge'] == state['knowledge']


def test_unknown_departure_then_later_appearance(phone):
    client, repo, sid = phone
    camera = repo.get_snapshot(sid)['world_state']['camera']
    job, _ = run(client, sid, [departure(camera)], 'Тимур вышел.', 'turn', ACTION)
    assert job['status'] == 'saved'
    before = repo.get_snapshot(sid)
    assert before['world_state']['characters'][NPC]['location_id'] is None
    target = next(lid for lid in before['world_state']['locations'] if lid != camera['location_id'])
    raw = dict(final_scene=dict(location_id=camera['location_id'], present_character_ids=[c for c in camera['present_character_ids'] if c != NPC], elapsed_minutes=1),
               movements=[dict(actor_id=NPC, from_location_id=None, to_location_id=target, assertion='completed_arrival', source_event_id='arrival')],
               events=[dict(id='arrival',text='Тимур появился в мастерской.',participants=[NPC],location_id=target,medium='action')])
    job, calls = run(client, sid, [raw], 'Тем временем Тимур появился в мастерской.', 'turn', ACTION)
    assert job['status'] == 'saved' and len(calls) == 2
    saved = Repository(repo.path).get_snapshot(sid)
    assert saved['world_state']['characters'][NPC]['location_id'] == target
    assert saved['world_state']['knowledge'] == before['world_state']['knowledge']


@pytest.mark.parametrize('target', [None, 'nonexistent'])
def test_strict_endpoint_diagnostic_and_repair_contract(phone, target):
    _, repo, sid = phone
    state = repo.get_snapshot(sid)['world_state']
    raw = departure(state['camera'])
    raw['movements'] = [dict(actor_id=NPC, to_location_id=target, assertion='completed_arrival')]
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(state, 'Тимур ушёл.', ACTION).resolve(raw)
    diagnostic = exc.value.diagnostic('extraction')
    assert diagnostic['code'] == 'movement_endpoint_invalid'
    assert diagnostic['path'] == 'movements[0].to_location_id'
    feedback = json.loads(repair_feedback(diagnostic, raw, state))
    assert 'future_intent/departure' in feedback['contract']
    assert 'newly registered endpoint' in feedback['contract']
    assert 'Сохрани подтверждённые этапы маршрута' in diagnostic['repair_reason']
    schema = extraction_schema()['properties']['movements']['items']
    assert 'future_intent' in schema['description']
    assert schema['properties']['to_location_id']['type'] == 'string'
    assert schema['properties']['assertion']['enum'] == ['completed_arrival']


@pytest.mark.parametrize('new_place,arrived', [(True, False), (True, True), (False, False)])
def test_location_existence_intent_and_arrival_are_independent(phone, new_place, arrived):
    client, repo, sid = phone
    before = repo.get_snapshot(sid); state = before['world_state']; home = state['camera']['location_id']
    target = 'new-darkroom' if new_place else next(lid for lid in state['locations'] if lid != home)
    narrative = 'В городе открылась фотолаборатория «Свет». ' if new_place else ''
    narrative += ('Тимур вышел из дома и добрался до фотолаборатории.' if arrived else
                  'Тимур говорит, что зайдёт туда завтра, и остаётся за столом.')
    raw = dict(final_scene=dict(location_id=home, present_character_ids=[c for c in state['camera']['present_character_ids'] if not arrived or c != NPC], elapsed_minutes=1))
    if new_place:
        raw['locations'] = [dict(id=target, name='Фотолаборатория «Свет»', evidence='В городе открылась фотолаборатория «Свет».')]
    if arrived:
        raw['movements'] = [dict(actor_id=NPC, from_location_id=home, to_location_id=target, assertion='completed_arrival', source_event_id='arrival', evidence='Тимур добрался до фотолаборатории.')]
    if arrived:
        raw['events'] = [dict(id='arrival',text='Тимур прибыл.',participants=[NPC],location_id=target,medium='action')]
    job, calls = run(client, sid, [raw], narrative, 'turn', ACTION)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    saved = Repository(repo.path).get_snapshot(sid); after = saved['world_state']
    assert target in after['locations']
    assert after['characters'][NPC]['location_id'] == (target if arrived else home)
    assert after['knowledge'] == state['knowledge']
    assert after['camera']['location_id'] == home
    moves = active_history(repo, saved)['movements'][len(active_history(repo, before)['movements']):]
    assert [m['to_location_id'] for m in moves] == ([target] if arrived else [])
