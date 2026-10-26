"""QA-03: prerequisite boundaries through real engine/Resolver/persistence."""
from copy import deepcopy

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import scheduled_boundary
from backend.runtime_v3.commitments import commitment_ready
from backend.runtime_v3.continuity import compression_limit
from backend.runtime_v3.long_term import plan
from devtools.narrative_test_world import load_fixture
from test_temporal_guard import run
from test_narrative_test_world import CONFIG


def prepared(tmp_path):
    repo = Repository(tmp_path / 'readiness.sqlite')
    sid = load_fixture(repo, 'commitments')['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    proof = 'Переносим поездку на следующую неделю, на среду в 18:00.'
    record = dict(id='qa_friday_trip', assertion='rescheduled',
        temporal=dict(day_offset=6, time='18:00'), evidence=proof,
        player_evidence=proof, player_assertion='explicit_choice')
    job, _ = run(repo, sid, 0, text=proof, player_input=proof, extra=dict(scheduled_event_changes=[record]))
    assert job['status'] == 'saved', job['error']
    s = repo.get_snapshot(sid)['world_state']
    assert s['meta']['world_time'] == 5563
    assert scheduled_boundary(s, s['scheduled_events']['qa_friday_trip']) == 14040
    assert scheduled_boundary(s, s['scheduled_events']['qa_sunday_return']) == 9720
    return repo, sid


def test_dependency_does_not_interrupt_skip(tmp_path):
    repo, sid = prepared(tmp_path)
    before = repo.get_snapshot(sid)
    job, _ = run(repo, sid, 0, config=dict(CONFIG, time_skip=dict(duration=7200)))
    assert job['status'] == 'saved', job['error']
    after = repo.get_snapshot(sid)
    assert after['world_state']['meta']['world_time'] == 12763
    assert after['last_time_skip']['interruption_event_id'] is None
    assert_plans_unchanged(before['world_state'], after['world_state'])
    assert Repository(repo.path).get_snapshot(sid) == after
    turn = repo.list_turns(sid)[-1]
    job, _ = run(repo, sid, 0, kind='regenerate')
    assert job['status'] == 'saved', job['error']
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time'] == 12763
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    # A rejected job must not commit its attempted cancellation or a new variant.
    turns = deepcopy(repo.list_turns(sid))
    proof = 'Отменяем поездку.'
    job, _ = run(repo, sid, 10080, text=proof, player_input=proof,
        extra=dict(scheduled_event_changes=[dict(
            id='qa_friday_trip', assertion='cancelled', evidence=proof,
            player_evidence=proof, player_assertion='explicit_choice')]))
    assert job['status'] == 'error'
    assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == turns
    assert Repository(repo.path).get_snapshot(sid) == before
    # Resolve the pending saved narrative before the next branch turn.
    assert run(repo, sid, 1,retry=job['id'])[0]['status'] == 'saved'
    repo = Repository(repo.path)
    assert run(repo, sid, 1)[0]['status'] == 'saved'
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time'] == 5565


@pytest.mark.parametrize('assertion,ready', [('blocked', False), ('cancelled', False), ('occurred', True)])
def test_accepted_prerequisite_outcome_unlocks_all_consumers(tmp_path, assertion, ready):
    repo, sid = prepared(tmp_path)
    text = {'blocked': 'Машина сломалась, поездка пока невозможна.',
        'cancelled': 'Отменяем поездку.', 'occurred': 'Мы уже съездили в сад.'}[assertion]
    job, _ = run(repo, sid, 0, text=text, player_input=text, extra=dict(scheduled_event_changes=[dict(
        id='qa_friday_trip', assertion=assertion, evidence=text,
        player_evidence=text, player_assertion='explicit_choice')]))
    assert job['status'] == 'saved', job['error']
    repo = Repository(repo.path)
    before = repo.get_snapshot(sid)
    s = before['world_state']
    assert commitment_ready(s, s['scheduled_events']['qa_sunday_return']) == ready
    report = plan(before, dict(amount=2, unit='weeks', max_llm_calls=0))
    assert (report.interruption or {}).get('source_id') == ('qa_sunday_return' if ready else 'qa_friday_trip' if assertion == 'blocked' else None)
    limit = compression_limit(s, {s['camera']['controlled_actor_id']}, max_minutes=7200)
    assert limit['max_minutes'] == (4157 if ready else 7200)
    assert limit['boundary_ids'] == (['qa_sunday_return'] if ready else [])
    assert repo.get_snapshot(sid) == before
    job, _ = run(repo, sid, 0, config=dict(CONFIG, time_skip=dict(duration=7200)))
    assert job['status'] == 'saved', job['error']
    after = repo.get_snapshot(sid)
    assert after['world_state']['meta']['world_time'] == (9720 if ready else 12763)
    assert_plans_unchanged(s, after['world_state'])
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    repo.rollback_last(sid)  # Revert outcome: the prerequisite is pending again.
    s = Repository(repo.path).get_snapshot(sid)['world_state']
    assert not commitment_ready(s, s['scheduled_events']['qa_sunday_return'])


def assert_plans_unchanged(before, after):
    old, new = deepcopy(before['scheduled_events']), deepcopy(after['scheduled_events'])
    # The independent NPC school-break candidate records its background attempt.
    # No date, status, evidence, identity or dependency may change.
    old['qa_school_break'].pop('last_attempt_minute', None)
    new['qa_school_break'].pop('last_attempt_minute', None)
    assert new == old


def test_lta_job_ignores_dependent_boundary_and_persists(tmp_path):
    import engine
    repo, sid = prepared(tmp_path)
    before = repo.get_snapshot(sid)
    config = dict(CONFIG, long_term_advance=dict(amount=2, unit='weeks', max_llm_calls=0))
    jid = repo.begin_job(sid, '', 'long_term', config)
    engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    after = repo.get_snapshot(sid)
    # Unlike the five-day skip, this interval reaches the rescheduled parent.
    assert after['world_state']['meta']['world_time'] == 14040
    assert after['last_long_term_advance']['interruption']['source_id'] == 'qa_friday_trip'
    assert_plans_unchanged(before['world_state'], after['world_state'])
    assert Repository(repo.path).get_snapshot(sid) == after
    jid = repo.begin_job(sid, '', 'regenerate', CONFIG)
    engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)['world_state'] == after['world_state']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
