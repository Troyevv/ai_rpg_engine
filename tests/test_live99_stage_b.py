import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from devtools.live99.budget import Budget, CONTEXT, INPUT, OUTPUT, action_ledger, reserve_action
from devtools.live99.stage_b import operations


def authorized(tmp_path):
    ledger = Budget(tmp_path / 'budget.sqlite')
    old = ledger.reserve(2000)
    ledger.settle(old, dict(prompt_tokens=1000, completion_tokens=100))
    ledger.cap_additional('old-retest', 500_000_000)
    action_ledger(tmp_path)
    reserve_action(tmp_path, tmp_path / 'old', {'kind': 'turn'}, 1)
    run = tmp_path / 'stage-b'
    auth = ledger.authorize_stage_b(run)
    return Budget(ledger.path, run), auth


def test_stage_b_keeps_old_receipts_and_cannot_renew_or_rebind(tmp_path):
    ledger, auth = authorized(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        before = db.execute('SELECT * FROM reservations').fetchall()
        caps = db.execute('SELECT * FROM spending_caps').fetchall()
    assert ledger.authorize_stage_b(tmp_path / 'stage-b') == auth
    with pytest.raises(ValueError, match='cannot renew'):
        ledger.authorize_stage_b(tmp_path / 'another-directory')
    with sqlite3.connect(ledger.path) as db:
        assert db.execute('SELECT * FROM reservations').fetchall() == before
        assert db.execute('SELECT * FROM spending_caps').fetchall() == caps
        assert db.execute('SELECT count(*) FROM qa_actions').fetchone()[0] == 1


def test_unknown_outcome_stops_other_groups_and_resume(tmp_path):
    ledger, _ = authorized(tmp_path)
    rid = ledger.reserve(4096)
    ledger.settle(rid, {'prompt_tokens': 1})
    with pytest.raises(RuntimeError, match='Unknown paid outcome'):
        Budget(ledger.path, tmp_path / 'stage-b').reserve(2000)
    with pytest.raises(ValueError, match='mismatched'):
        Budget(ledger.path, tmp_path / 'other').reserve(2000)


def test_additional_two_dollars_includes_repairs_and_retains_old_cap(tmp_path):
    ledger, _ = authorized(tmp_path)
    # Six maximally charged completed streams leave less than a seventh full-window reserve.
    for _ in range(6):
        rid = ledger.reserve(32000)
        ledger.settle(rid, dict(prompt_tokens=900000, completion_tokens=32000))
    spent = 6 * (900000 * INPUT + 32000 * OUTPUT)
    assert spent < 2_000_000_000 < spent + CONTEXT * INPUT + 32000 * OUTPUT
    with pytest.raises(RuntimeError, match='exhausted'):
        Budget(ledger.path, tmp_path / 'stage-b').reserve(32000)
    # The previous $0.50 authorization was neither deleted nor raised.
    with pytest.raises(RuntimeError, match='exhausted'):
        Budget(ledger.path).reserve(2000)


def test_stage_b_concurrent_dispatch_cannot_race_unknown_guard(tmp_path):
    ledger, _ = authorized(tmp_path)
    def dispatch(_):
        try:
            return ledger.reserve(2000)
        except RuntimeError:
            return None
    with ThreadPoolExecutor(4) as pool:
        assert len([r for r in pool.map(dispatch, range(8)) if r]) == 1


def test_stage_b_action_ceiling_is_incremental_and_not_refunded(tmp_path):
    ledger, auth = authorized(tmp_path)
    for i in range(100):
        reserve_action(tmp_path, tmp_path / str(i), {'kind': 'turn'}, auth[2]+100)
    assert action_ledger(tmp_path) == 101
    with pytest.raises(RuntimeError, match='exhausted'):
        reserve_action(tmp_path, tmp_path / 'extra', {}, auth[2]+100)
    assert ledger.authorize_stage_b(tmp_path / 'stage-b') == auth


def test_plan_has_six_groups_real_lineage_and_semantic_lta_budget():
    plan = operations()
    assert len(plan) == 6 and sum(map(len, plan.values())) == 90
    assert [op['kind'] for op in plan['campaign'][:5]] == ['turn','regenerate','variant','rollback','turn']
    assert plan['phone'][0]['kind'] == 'phone-retry'
    assert all(op['model_budget'] >= 2 for ops in plan.values() for op in ops if op['kind']=='lta')
    assert all(op.get('action') or op['kind'] != 'turn' for ops in plan.values() for op in ops)


def test_prepare_links_immutable_parent_and_retains_all_old_saves(tmp_path, monkeypatch):
    from devtools.live99 import run, stage_b
    from devtools.live99.evidence import snapshot
    from backend.repositories.preparation import Repository
    parent, child = tmp_path / 'parent', tmp_path / 'child'
    run.prepare(parent)
    original = json.loads((parent / 'manifest.json').read_text())
    repo = Repository(parent / 'game.sqlite')
    sid = original['seeds']['phone']['save']
    initial = repo.begin_job(sid, '', 'start', dict(provider='deepseek', model='deepseek-flash'))
    repo.job_progress(initial, 'validating', narrative='Начало.', complete=True)
    repo.save_context(initial, [], repo.get_snapshot(sid))
    repo.commit_job(initial, repo.get_snapshot(sid), [], {})
    job = repo.begin_job(sid, 'original phone failure', 'communication',
                         dict(provider='deepseek', model='deepseek-flash', expected_revision=repo.get_save(sid)['revision'], remote_command=dict(
                             action='send', operation_id='qa-stage-b-test',
                             character_id='qa_vera', content='До завтра?')))
    repo.job_progress(job, 'error', error='Saved phone contract failure')
    before = {case: snapshot(parent / 'game.sqlite', seed['save']) for case, seed in original['seeds'].items()}
    monkeypatch.setattr(stage_b, 'qa_only', lambda *_: None)
    stage_b.prepare(parent, child, 'qa-sha', 'master-sha')
    manifest = json.loads((child / 'manifest.json').read_text())
    stage_b.validate(child, manifest)
    assert (child / 'budget.sqlite').resolve() == parent / 'budget.sqlite'
    assert manifest['seeds']['family']['save'] != original['seeds']['family']['save']
    for case, seed in original['seeds'].items():
        assert snapshot(parent / 'game.sqlite', seed['save']) == before[case]
        assert snapshot(child / 'game.sqlite', seed['save']) == before[case]
    (parent / 'manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='Historical evidence changed'):
        stage_b.validate(child, manifest)
