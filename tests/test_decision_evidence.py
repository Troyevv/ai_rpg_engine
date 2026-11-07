"""#233: equivalent Social/001 replay; the external QA archive is unavailable."""
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
from test_narrative_test_world import CONFIG

ACTION = ('Я согласен сейчас сортировать фотографии по датам, оставляя оригинал карты на месте. '
          'Прошу Веру показать первую пачку.')
NARRATIVE = 'Вера приносит папку и показывает первую пачку фотографий. Ася спрашивает о датах.'
EVENT = 'event_3c1a7f0e5b2d94a6c8e1'


def social_turn(state, *, quote=ACTION):
    camera = state['camera']
    return dict(
        final_scene=dict(location_id=camera['location_id'], elapsed_minutes=1,
                         present_character_ids=camera['present_character_ids']),
        events=[dict(id=EVENT, text=NARRATIVE, evidence=ACTION, medium='conversation',
                     participants=[ACTOR_ID, 'qa_vera'], witnesses=[ACTOR_ID, 'qa_vera'],
                     player_assertion='completed_interaction', player_evidence=quote)],
        continuity_beats=[dict(source_event_id=EVENT, actor_id=ACTOR_ID,
                               target_ids=['qa_vera'], basis_ids=['qa_map'], kind='decision',
                               status='resolved', decision_actor_id=ACTOR_ID, evidence=ACTION)],
    )


def events(repo, snapshot):
    with repo.connect() as db:
        history, _ = read_history(db, snapshot['history_head'])
    return [e for e in history['events'] if e.get('local_id', '').startswith(EVENT)]


def test_social_missing_beat_quote_repairs_without_reauthoring(tmp_path):
    repo = Repository(tmp_path / 'social.sqlite')
    sid = load_fixture(repo, 'knowledge')['save']
    before = repo.get_snapshot(sid)
    raw = social_turn(before['world_state'])
    fixed = deepcopy(raw)
    fixed['continuity_beats'][0]['player_evidence'] = ACTION
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    calls = execute(repo, job, raw, NARRATIVE, repaired=fixed)
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    result = repo.get_job(job)
    assert result['status'] == 'saved', result['error']
    diagnostics = json.loads(result['repair_diagnostics_json'])
    assert len(diagnostics) == 1
    assert diagnostics[0]['path'] == 'continuity_beats[0].player_evidence'
    assert diagnostics[0]['action'] == 'extraction_repair'
    assert diagnostics[0]['path'] in calls[-1]['messages'][0]['content']
    repo = Repository(repo.path)
    event, = events(repo, repo.get_snapshot(sid))
    beat, = event['continuity']
    assert beat['source_event_id'] == event['id']
    assert beat['player_evidence'] == event['player_evidence'] == ACTION
    assert result['narrative'] == NARRATIVE


@pytest.fixture
def game(tmp_path):
    repo = Repository(tmp_path / 'decisions.sqlite')
    sid = load_fixture(repo, 'knowledge')['save']
    return repo, sid, repo.get_snapshot(sid)


def supported(state, quote=ACTION):
    raw = social_turn(state, quote=quote)
    raw['continuity_beats'][0].update(player_evidence=quote, evidence=quote)
    raw['events'][0]['evidence'] = quote
    return raw


@pytest.mark.parametrize('action,status', [
    (ACTION, 'resolved'),
    ('Я отказываюсь сортировать фотографии.', 'rejected'),
    ('Я решил отложить сортировку до завтра.', 'resolved'),
])
def test_explicit_decision_is_saved_without_extra_call(game, action, status):
    repo, sid, before = game
    raw = supported(before['world_state'], action)
    raw['continuity_beats'][0]['status'] = status
    job = repo.begin_job(sid, action, 'turn', CONFIG)
    assert len(execute(repo, job, raw, NARRATIVE)) == 2
    assert repo.get_job(job)['status'] == 'saved'
    event, = events(Repository(repo.path), repo.get_snapshot(sid))
    beat, = event['continuity']
    assert (beat['player_evidence'], beat['status']) == (action, status)
    assert json.loads(repo.get_job(job)['repair_diagnostics_json']) == []


@pytest.mark.parametrize('change,path', [
    ({'player_evidence': ''}, 'player_evidence'),
    ({'player_evidence': 'Прошу Веру показать первую пачку.'}, 'player_evidence'),
    ({'player_evidence': 'Да, передаю оригинал.'}, 'player_evidence'),
    ({'player_evidence': None}, None),
    ({'source_event_id': 'old_or_absent_event'}, 'source_event_id'),
    ({'decision_actor_id': 'qa_vera'}, 'decision_actor_id'),
    ({'decision_actor_id': None}, 'decision_actor_id'),
    ({'actor_id': 'qa_oleg'}, 'source_event_id'),
    ({'evidence': 'Я согласен'}, 'evidence'),
    ({'status': 'open'}, 'status'),
])
def test_unconfirmed_decision_is_atomic_after_one_repair(game, change, path):
    repo, sid, before = game
    raw = supported(before['world_state'])
    raw['continuity_beats'][0].update(change)
    turns = repo.list_turns(sid)
    revision = repo.get_save(sid)['revision']
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    calls = execute(repo, job, raw, NARRATIVE)
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    result = repo.get_job(job)
    assert result['status'] == 'error'
    diagnostics = json.loads(result['repair_diagnostics_json'])
    assert len(diagnostics) == 2
    assert all(d['code'] == 'continuity_external_decision' for d in diagnostics)
    assert diagnostics[0]['path'] == 'continuity_beats[0]' + ('.' + path if path else '')
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == turns
    assert repo.get_save(sid)['revision'] == revision
    with patch('engine.chat_stream', side_effect=AssertionError('abandon must not call LLM')):
        repo.abandon_job(sid, job, revision, result['attempt_epoch'])
    assert repo.get_snapshot(sid) == before


@pytest.mark.parametrize('event_change', [
    {'player_assertion': ''},
    {'player_evidence': 'Прошу Веру показать первую пачку.'},
    {'medium': 'message', 'author_id': 'qa_vera'},
])
def test_event_quote_and_authorship_must_confirm_decision(game, event_change):
    repo, sid, before = game
    raw = supported(before['world_state'])
    raw['events'][0].update(event_change)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(before['world_state'], NARRATIVE, ACTION).resolve(raw)
    assert error.value.code == 'continuity_external_decision'
    assert repo.get_snapshot(sid) == before


@pytest.mark.parametrize('action,kind', [
    ('Вера, как будем сортировать фотографии?', 'question'),
    ('Предлагаю сортировать фотографии по датам.', 'proposal'),
    ('Я подумаю, ответа пока нет.', 'information'),
    ('Я хочу потом заняться фотографиями.', 'information'),
])
def test_input_without_decision_cannot_borrow_invented_consent(game, action, kind):
    repo, sid, before = game
    bad = supported(before['world_state'], action)
    bad['continuity_beats'][0]['player_evidence'] = 'Я согласен сейчас сортировать фотографии.'
    fixed = deepcopy(bad)
    fixed['continuity_beats'][0].update(kind=kind, status='open', decision_actor_id=None,
                                       player_evidence='')
    job = repo.begin_job(sid, action, 'turn', CONFIG)
    assert len(execute(repo, job, bad, NARRATIVE, repaired=fixed)) == 3
    assert repo.get_job(job)['status'] == 'saved'
    event, = events(repo, repo.get_snapshot(sid))
    assert event['continuity'][0]['kind'] == kind
    assert event['continuity'][0]['decision_actor_id'] is None


@pytest.mark.parametrize('decision', [False, True])
def test_npc_proposal_or_independent_decision_needs_no_player_quote(game, decision):
    repo, sid, before = game
    raw = social_turn(before['world_state'])
    raw['events'][0].pop('player_assertion')
    raw['events'][0].pop('player_evidence')
    text = 'Вера решила убрать свои фотографии.' if decision else 'Вера предлагает разобрать фотографии.'
    raw['events'][0].update(text=text, evidence=text)
    raw['continuity_beats'][0].update(actor_id='qa_vera', target_ids=[ACTOR_ID], evidence=text,
        kind='decision' if decision else 'proposal', status='resolved' if decision else 'open',
        decision_actor_id='qa_vera' if decision else None)
    if decision:
        raw['scene_actions'] = [dict(source_event_id=EVENT, actor_id='qa_vera', target_ids=[ACTOR_ID],
                                    phase='end', modality='other', evidence=text)]
    job = repo.begin_job(sid, 'Слушаю.', 'turn', CONFIG)
    assert len(execute(repo, job, raw, text)) == 2
    assert repo.get_job(job)['status'] == 'saved'
    event, = events(repo, repo.get_snapshot(sid))
    assert event['continuity'][0]['player_evidence'] == ''
    assert event['continuity'][0]['decision_actor_id'] != ACTOR_ID


@pytest.mark.parametrize('bad_second', [False, True])
def test_multiple_beats_validate_individually_and_commit_atomically(game, bad_second):
    repo, sid, before = game
    first = 'Я согласен сортировать фотографии.'
    second = 'Я отказываюсь передавать оригинал карты.'
    raw = supported(before['world_state'], first)
    raw['events'].append(dict(raw['events'][0], id=EVENT + '_second', evidence=second, player_evidence=second))
    raw['continuity_beats'].append(dict(raw['continuity_beats'][0], source_event_id=EVENT + '_second',
        status='rejected', evidence=second, player_evidence=first if bad_second else second))
    job = repo.begin_job(sid, first + ' ' + second, 'turn', CONFIG)
    calls = execute(repo, job, raw, NARRATIVE)
    assert len(calls) == (3 if bad_second else 2)
    if bad_second:
        assert repo.get_job(job)['status'] == 'error'
        assert repo.get_snapshot(sid) == before
        assert json.loads(repo.get_job(job)['repair_diagnostics_json'])[0]['path'] == 'continuity_beats[1].player_evidence'
    else:
        assert repo.get_job(job)['status'] == 'saved'
        assert len(events(repo, repo.get_snapshot(sid))) == 2


def test_duplicate_beats_are_not_committed_twice(game):
    repo, sid, before = game
    raw = supported(before['world_state'])
    raw['continuity_beats'] *= 2
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    assert len(execute(repo, job, raw, NARRATIVE)) == 2
    assert repo.get_job(job)['status'] == 'saved'
    event, = events(repo, repo.get_snapshot(sid))
    assert len(event['continuity']) == 1


def test_background_cannot_acquire_decision_from_current_quote(game):
    _, _, before = game
    raw = supported(before['world_state'])
    raw['final_scene']['elapsed_minutes'] = 0
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(before['world_state'], NARRATIVE, ACTION, mode='background').resolve(raw)
    assert error.value.code == 'continuity_external_decision' and not error.value.repairable


def test_recovery_reload_regeneration_siblings_and_new_branch(game):
    repo, sid, before = game
    raw = social_turn(before['world_state'])
    fixed = supported(before['world_state'])
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    assert len(execute(repo, job, raw, NARRATIVE)) == 3
    assert repo.get_job(job)['status'] == 'error'
    assert repo.get_snapshot(sid) == before
    repo = Repository(repo.path)
    repo.retry_job(job)
    calls = execute(repo, job, fixed, 'THIS MUST NOT REPLACE THE PAID NARRATIVE')
    assert len(calls) == 1 and calls[0]['response_format']
    assert repo.get_job(job)['status'] == 'saved'
    original = repo.get_snapshot(sid)
    original_event, = events(repo, original)
    turn = repo.list_turns(sid)[-1]
    regen = repo.begin_job(sid, '', 'regenerate', CONFIG)
    assert len(execute(repo, regen, fixed, NARRATIVE + ' Вера улыбается.')) == 2
    assert repo.get_job(regen)['status'] == 'saved'
    sibling = repo.get_snapshot(sid)
    sibling_event, = events(repo, sibling)
    assert sibling_event['id'] != original_event['id']
    assert sibling_event['continuity'][0]['source_event_id'] == sibling_event['id']
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == original
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    branch = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    assert len(execute(repo, branch, fixed, NARRATIVE + ' За окном идёт дождь.')) == 2
    assert repo.get_job(branch)['status'] == 'saved'
    assert events(repo, original) == [original_event]
    assert events(repo, sibling) == [sibling_event]
    assert len(events(Repository(repo.path), repo.get_snapshot(sid))) == 1
