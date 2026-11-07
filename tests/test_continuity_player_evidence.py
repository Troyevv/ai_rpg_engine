"""#203: equivalent Extraction to the live Vera/library failure on checkpoint #78."""
from copy import deepcopy

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import ACTOR_ID, load_fixture
from runtime_v3_fixture import execute
from test_narrative_test_world import CONFIG

ACTION = 'У Веры я спрашиваю только о библиотеке. Личное письмо Олега не обсуждаю.'
NARRATIVE = 'Вера предлагает уточнить, что именно интересует, и упоминает фонд старых карт.'
EVENT_ID = 'ev_turn2_vera_library'


def library_turn(state, kind='question', action=ACTION):
    camera = state['camera']
    event = dict(id=EVENT_ID, text=NARRATIVE, evidence=NARRATIVE, medium='conversation',
                 participants=[ACTOR_ID, 'qa_vera'], witnesses=[ACTOR_ID, 'qa_vera'],
                 player_assertion='completed_interaction', player_evidence=action)
    beat = dict(source_event_id=EVENT_ID, actor_id=ACTOR_ID, target_ids=['qa_vera'],
                basis_ids=['qa_map'], kind=kind, status='open',
                evidence='Кирилл спрашивает Веру о библиотеке; Вера предлагает уточнить.')
    from runtime_v3_fixture import player_action
    raw = dict(final_scene=dict(location_id=camera['location_id'], elapsed_minutes=1,
                                 present_character_ids=camera['present_character_ids']),
                events=[event], continuity_beats=[beat])
    return player_action(raw, ACTOR_ID, ['qa_vera'], action, EVENT_ID)


@pytest.fixture(scope='module')
def state(tmp_path_factory):
    repo = Repository(tmp_path_factory.mktemp('checkpoint') / 'knowledge.sqlite')
    return repo.get_snapshot(load_fixture(repo, 'knowledge')['save'])['world_state']


@pytest.mark.parametrize(('kind', 'action'), [
    ('question', ACTION),
    ('proposal', 'Вера, предлагаю сходить в библиотеку.'),
    ('information', 'Сообщаю Вере часы работы библиотеки.'),
])
def test_dialogue_uses_accepted_player_interaction(state, kind, action):
    raw = library_turn(state, kind, action)
    out = StateResolver(state, NARRATIVE, action).resolve(raw)
    event, = out.history['events']
    beat, = event['continuity']
    assert beat['kind'] == kind
    assert beat['source_event_id'] == event['id']
    assert event['player_interaction'] and event['player_evidence'] == action
    assert out.state['knowledge'] == state['knowledge']


@pytest.mark.parametrize(('event_change', 'beat_change', 'code'), [
    ({}, {'source_event_id': 'previous_turn'}, 'continuity_beat_evidence'),
    ({'medium': 'invalid'}, {}, 'continuity_beat_evidence'),
    ({'participants': ['qa_vera']}, {}, 'continuity_beat_evidence'),
    ({}, {'target_ids': ['qa_oleg']}, 'continuity_beat_evidence'),
    ({'medium': 'message', 'author_id': 'qa_vera'}, {}, 'continuity_player_interaction_unconfirmed'),
    ({'player_evidence': 'Текст другого хода.'}, {}, 'continuity_player_interaction_unconfirmed'),
    ({'player_assertion': ''}, {}, 'continuity_player_interaction_unconfirmed'),
    ({}, {'player_evidence': 'Я согласен.'}, 'continuity_player_interaction_unconfirmed'),
    ({'evidence': ''}, {}, 'continuity_player_interaction_unconfirmed'),
    ({}, {'basis_ids': ['unknown']}, 'continuity_basis_invalid'),
    ({}, {'basis_ids': ['qa_private_letter']}, 'continuity_basis_unavailable'),
    ({}, {'basis_ids': ['qa_oleg_job']}, 'continuity_basis_unavailable'),
])
def test_bad_dialogue_annotation_dropped(state, event_change, beat_change, code):
    raw = library_turn(state)
    raw['events'][0].update(event_change)
    raw['continuity_beats'][0].update(beat_change)
    before = deepcopy(state)
    if any(key in event_change for key in ('participants', 'author_id', 'player_evidence')):
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(state, NARRATIVE, ACTION).resolve(raw)
        assert exc.value.code in ('player_action_event_mismatch', 'player_action_completion_invalid')
        assert state == before
        return
    out = StateResolver(state, NARRATIVE, ACTION).resolve(raw)
    warning, = [w for w in out.warnings if w['section'] == 'continuity_beats']
    assert (warning['code'], warning['action']) == (code, 'drop_record')
    assert len(out.history['events']) == (event_change.get('medium') != 'invalid')
    assert all('continuity' not in e for e in out.history['events'])
    assert state == before and out.state['knowledge'] == before['knowledge']


@pytest.mark.parametrize('change', [
    {'kind': 'decision'},
    {'kind': 'opportunity', 'player_evidence': NARRATIVE},
    {'actor_id': 'qa_vera', 'decision_actor_id': ACTOR_ID},
])
def test_event_never_authorizes_a_separate_player_decision(state, change):
    raw = library_turn(state)
    raw['continuity_beats'][0].update(change)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, NARRATIVE, ACTION).resolve(raw)
    assert error.value.code == 'continuity_external_decision' and error.value.repairable
    assert error.value.diagnostic('test')['path'] == 'continuity_beats[0].player_evidence'


def test_background_cannot_borrow_player_evidence(state):
    raw = library_turn(state)
    raw['final_scene']['elapsed_minutes'] = 0
    raw['continuity_beats'][0]['player_evidence'] = ACTION
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, NARRATIVE, ACTION, mode='background').resolve(raw)
    assert error.value.code == 'player_action_source_invalid'


def test_retry_reload_regenerate_and_rollback_preserve_event_lineage(tmp_path):
    repo = Repository(tmp_path / 'lineage.sqlite')
    sid = load_fixture(repo, 'knowledge')['save']
    initial = repo.get_snapshot(sid)
    timur = repo.begin_job(sid, 'Тимур, где сейчас работает Олег? Откуда ты об этом узнал?', 'turn', CONFIG)
    text = 'Тимур вспоминает, как Олег рассказывал ему о работе в мастерской.'
    first = library_turn(initial['world_state'])
    execute(repo, timur, dict(final_scene=first['final_scene'], events=[dict(
        id='timur_reply', text=text, evidence=text, medium='conversation',
        participants=[ACTOR_ID, 'qa_timur'], witnesses=[ACTOR_ID, 'qa_timur'],
    )]), text)
    assert repo.get_job(timur)['status'] == 'saved'
    before = repo.get_snapshot(sid)
    revision = repo.get_save(sid)['revision']
    turns = repo.list_turns(sid)
    raw = library_turn(before['world_state'])
    unsupported = deepcopy(raw)
    unsupported['continuity_beats'][0]['decision_actor_id'] = ACTOR_ID
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    assert len(execute(repo, job, unsupported, NARRATIVE)) == 3  # one bounded Extraction repair
    assert repo.get_job(job)['status'] == 'error'
    assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == turns
    assert repo.get_save(sid)['revision'] == revision

    repo.retry_job(job)
    calls = execute(repo, job, raw, NARRATIVE)
    assert len(calls) == 1 and calls[0]['response_format'], repo.get_job(job)['error']
    assert repo.get_job(job)['status'] == 'saved'
    assert repo.get_save(sid)['revision'] == revision + 1
    saved = repo.get_snapshot(sid)
    turn = repo.list_turns(sid)[-1]
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == saved

    def library_events(snapshot):
        with repo.connect() as db:
            history, _ = read_history(db, snapshot['history_head'])
        return [e for e in history['events'] if e.get('local_id') == EVENT_ID]

    original, = library_events(saved)
    annotation, = original['continuity']
    assert annotation['source_event_id'] == original['id']
    regen = repo.begin_job(sid, '', 'regenerate', CONFIG)
    variant_text = 'Вера рассказывает об отделе редких карт.'
    variant_raw = deepcopy(raw)
    variant_raw['events'][0].update(text=variant_text, evidence=variant_text)
    execute(repo, regen, variant_raw, variant_text)
    assert repo.get_job(regen)['status'] == 'saved'
    sibling = repo.get_snapshot(sid)
    alternate, = library_events(sibling)
    assert alternate['id'] != original['id']
    assert alternate['continuity'][0]['source_event_id'] == alternate['id']

    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == saved
    next_job = repo.begin_job(sid, 'Слушаю Веру.', 'turn', CONFIG)
    execute(repo, next_job, {'final_scene': raw['final_scene']}, 'Вера продолжает рассказ.')
    assert repo.get_job(next_job)['status'] == 'saved'
    assert library_events(repo.get_snapshot(sid)) == [original]
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == saved
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before and not library_events(before)
    assert library_events(sibling) == [alternate]


def test_another_accepted_event_cannot_lend_its_quote(state):
    raw = library_turn(state)
    unrelated = dict(raw['events'][0], id='unrelated')
    raw['events'][0].pop('player_assertion')
    raw['events'].append(unrelated)
    out = StateResolver(state, NARRATIVE, ACTION).resolve(raw)
    source, other = out.history['events']
    assert other['player_interaction'] and 'continuity' not in source
    assert any(w['code'] == 'continuity_player_interaction_unconfirmed' for w in out.warnings)


def test_legacy_beat_with_own_quote_still_works(state):
    raw = library_turn(state)
    raw['events'][0].pop('player_assertion')
    raw['events'][0].pop('player_evidence')
    raw['continuity_beats'][0]['player_evidence'] = ACTION
    out = StateResolver(state, NARRATIVE, ACTION).resolve(raw)
    event, = out.history['events']
    assert event['continuity'][0]['player_evidence'] == ACTION


def test_thread_membership_does_not_grant_discovery(state):
    hidden = deepcopy(state)
    hidden['threads']['qa_map']['discovered_by'] = ['qa_oleg']
    out = StateResolver(hidden, NARRATIVE, ACTION).resolve(library_turn(hidden))
    assert 'continuity' not in out.history['events'][0]
    assert any(w['code'] == 'continuity_basis_unavailable' for w in out.warnings)


def test_dialogue_receipt_cannot_retarget_to_a_bystander(state):
    raw = library_turn(state)
    raw['events'][0]['participants'].append('qa_timur')
    raw['continuity_beats'][0]['target_ids'] = ['qa_timur']
    out = StateResolver(state, NARRATIVE, ACTION).resolve(raw)
    event, = out.history['events']
    assert event['player_interaction'] and event['target_ids'] == ['qa_vera']
    assert 'continuity' not in event
    assert any(w['code'] == 'continuity_player_interaction_unconfirmed' for w in out.warnings)
