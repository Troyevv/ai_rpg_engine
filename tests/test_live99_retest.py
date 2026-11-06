import json
import sqlite3
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
