import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from devtools.live99 import budget, retest
from devtools.live99.evidence import write


def test_linked_run_and_original_share_nonrenewable_incremental_cap(tmp_path):
    original = tmp_path / 'original'
    linked = tmp_path / 'linked'
    original.mkdir()
    linked.mkdir()
    ledger = budget.Budget(original / 'budget.sqlite')
    old = ledger.reserve(1200)
    ledger.settle(old, {'prompt_tokens': 1000, 'completion_tokens': 100})
    baseline = 1000 * budget.INPUT + 100 * budget.OUTPUT
    ceiling = ledger.cap_additional('retest', 500_000_000)
    assert ceiling == baseline + 500_000_000
    (linked / 'budget.sqlite').symlink_to(ledger.path)
    resumed = budget.Budget(linked / 'budget.sqlite')
    # Both processes reserve against the same additional cap, including unknown outcomes.
    def attempt(instance):
        try:
            return instance.reserve(1200)
        except RuntimeError:
            return None
    with ThreadPoolExecutor(2) as pool:
        assert len([r for r in pool.map(attempt, (resumed, ledger)) if r]) == 1
    assert resumed.cap_additional('retest', 500_000_000) == ceiling
    with pytest.raises(RuntimeError, match='exhausted'):
        ledger.reserve(1200)
    # A second name cannot remove the first cap or bypass the global $2 limit.
    resumed.cap_additional('another', 2_000_000_000)
    with pytest.raises(RuntimeError, match='exhausted'):
        resumed.reserve(1200)


def test_linked_actions_keep_old_names_and_do_not_refund_lost_artifacts(tmp_path):
    original, linked = tmp_path / 'original', tmp_path / 'linked'
    original.mkdir()
    linked.mkdir()
    budget.Budget(original / 'budget.sqlite')
    folder = original / 'knowledge/000'
    folder.mkdir(parents=True)
    write(folder / 'intent.json', {'kind': 'turn'})
    assert budget.action_ledger(original) == 1
    (linked / 'budget.sqlite').symlink_to(original / 'budget.sqlite')
    budget.reserve_action(linked, linked / 'knowledge/000', {'kind': 'turn'}, 2)
    (folder / 'intent.json').unlink()
    assert budget.action_ledger(original) == budget.action_ledger(linked) == 2
    with pytest.raises(RuntimeError, match='exhausted'):
        budget.reserve_action(linked, linked / 'knowledge/001', {'kind': 'turn'}, 2)


def test_backup_preserves_wal_data_without_mutating_original(tmp_path):
    original, copied = tmp_path / 'original.sqlite', tmp_path / 'copy.sqlite'
    with sqlite3.connect(original) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE history(id INTEGER PRIMARY KEY, data TEXT)')
        db.execute('INSERT INTO history VALUES(1,?)', (json.dumps({'secret': 'fixture'}),))
        db.commit()
        retest.backup(original, copied)
        with sqlite3.connect(copied) as clone:
            assert clone.execute('SELECT * FROM history').fetchall() == db.execute('SELECT * FROM history').fetchall()
            clone.execute('INSERT INTO history VALUES(2,?)', ('new branch',))
        assert db.execute('SELECT count(*) FROM history').fetchone() == (1,)


def test_recovery_import_does_not_require_optional_browser():
    subprocess.run([sys.executable, '-c', '''
import importlib.abc, sys
class DenyBrowser(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('playwright'):
            raise ModuleNotFoundError('Browser deliberately unavailable')
sys.meta_path.insert(0, DenyBrowser())
import devtools.live99.run, devtools.live99.retest
'''], check=True)


@pytest.mark.parametrize('mutated', [False, True])
def test_ui_recovery_requires_unchanged_jobs_and_keeps_attempts(tmp_path, monkeypatch, mutated):
    parent, linked = tmp_path / 'parent', tmp_path / 'linked'
    parent.mkdir()
    linked.mkdir()
    budget.Budget(parent / 'budget.sqlite')
    for directory in (parent, linked):
        with sqlite3.connect(directory / 'game.sqlite') as db:
            db.execute('CREATE TABLE game_jobs(id INTEGER, status TEXT)')
            db.execute('CREATE TABLE llm_requests(id INTEGER)')
    before = {'snapshot': {'stable': True}}
    for case in ('knowledge', 'phone'):
        folder = linked / case / '000'
        folder.mkdir(parents=True)
        write(folder / 'result.json', dict(status='held-for-review', error='Locator.click: Timeout'))
        write(folder / 'before.json.gz', before)
        write(folder / 'after.json.gz', before)
    monkeypatch.setattr(retest, 'validate', lambda *_: None)
    monkeypatch.setattr(retest, 'snapshot', lambda *_: before)
    manifest = dict(parent=str(parent), baseline_reservations=[], action_limit=25,
                    seeds={c: {'save': i} for i, c in enumerate(('knowledge', 'phone'))})
    if mutated:
        with sqlite3.connect(linked / 'game.sqlite') as db:
            db.execute("INSERT INTO game_jobs VALUES(1,'generating')")
        with pytest.raises(ValueError, match='job or request changed'):
            retest.review_unsubmitted(linked, manifest)
    else:
        retest.review_unsubmitted(linked, manifest)
        receipt = json.loads((linked / 'unsubmitted-review.json').read_text())
        assert receipt['action_limit'] == 27 and len(receipt['evidence']) == 6
        assert (linked / 'phone/000/result.json').is_file()
        with pytest.raises(ValueError, match='already reviewed'):
            retest.review_unsubmitted(linked, manifest)


@pytest.mark.parametrize('new_request', [False, True])
def test_context_review_cannot_automatically_repeat_paid_extraction(tmp_path, monkeypatch, new_request):
    folder = tmp_path / 'knowledge/000/retries/001'
    folder.mkdir(parents=True)
    write(folder / 'result.json', dict(status='held-for-review', error='Контекст v3 не помещается',
                                       save=4, job_id='original'))
    write(folder / 'before.json.gz', {'stable': True})
    write(tmp_path / 'unsubmitted-review.json', {'action_limit': 27})
    with sqlite3.connect(tmp_path / 'game.sqlite') as db:
        db.execute('CREATE TABLE game_jobs(id TEXT, narrative_complete INTEGER)')
        db.execute("INSERT INTO game_jobs VALUES('original',1)")
        db.execute('CREATE TABLE llm_requests(id TEXT, job_id TEXT)')
        db.execute('INSERT INTO llm_requests VALUES(?,?)', ('new' if new_request else 'old', 'original'))
    monkeypatch.setattr(retest, 'validate', lambda *_: None)
    monkeypatch.setattr(retest, 'snapshot', lambda *_: {'stable': True})
    monkeypatch.setattr(retest, 'probe_context', lambda *_: dict(input_estimate=28000, hard_input_limit=36608,
                                                                context_length=40960))
    manifest = dict(baseline_request_ids=['old'])
    if new_request:
        with pytest.raises(ValueError, match='already dispatched'):
            retest.review_context(tmp_path, manifest)
    else:
        retest.review_context(tmp_path, manifest)
        receipt = json.loads((tmp_path / 'knowledge-context-review.json').read_text())
        assert receipt['action_limit'] == 28 and receipt['probe']['context_length'] == 40960
        with pytest.raises(ValueError, match='already reviewed'):
            retest.review_context(tmp_path, manifest)
