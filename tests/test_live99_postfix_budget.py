"""Real SQLite reservations: isolated source, inherited cap and explicit sublimit."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from devtools.live99.budget import Budget, reserve_action
from devtools.live99.postfix_budget import PostfixBudget, authorize_copy


def copied(tmp_path, *, spent_input=1000):
    source = tmp_path/'source.sqlite'
    Budget(source)
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE stage_c_followup_authorization (id INTEGER PRIMARY KEY, baseline_id INTEGER)')
        db.execute('INSERT INTO stage_c_followup_authorization VALUES(1,0)')
        db.execute('INSERT INTO reservations VALUES(1,?,10,1)', (spent_input,))
        rows=db.execute('SELECT * FROM reservations ORDER BY id').fetchall()
    original=source.read_bytes()
    directory=tmp_path/'run';directory.mkdir()
    (directory/'budget.sqlite').write_bytes(original)
    authorize_copy(directory, historical_baseline=0, historical_rows=rows)
    return PostfixBudget(directory), source, original, rows


def test_copy_preserves_source_and_historical_prefix_on_resume(tmp_path):
    ledger, source, original, rows=copied(tmp_path)
    rid=ledger.reserve(4096)
    ledger.settle(rid, dict(prompt_tokens=10000,completion_tokens=500))
    resumed=PostfixBudget(Path(ledger.run_directory))
    assert resumed.reserve(4096)==3
    assert source.read_bytes()==original
    with sqlite3.connect(ledger.path) as db:
        assert db.execute('SELECT * FROM reservations WHERE id=1').fetchall()==rows
    with pytest.raises(ValueError,match='changed|already authorized'):
        authorize_copy(Path(ledger.run_directory),historical_baseline=0,historical_rows=rows)


def test_concurrent_calls_and_unknown_receipts_fail_closed(tmp_path):
    ledger, *_=copied(tmp_path)
    def dispatch(_):
        try:return PostfixBudget(Path(ledger.run_directory)).reserve(4096)
        except RuntimeError:return None
    with ThreadPoolExecutor(4) as pool:
        assert [x for x in pool.map(dispatch,range(8)) if x is not None]==[2]
    ledger.settle(2,dict(completion_tokens=1))
    with pytest.raises(RuntimeError,match='Unknown paid outcome'):ledger.reserve(4096)


def test_all_36_calls_count_after_restart_even_with_tiny_usage(tmp_path):
    ledger,*_=copied(tmp_path)
    for _ in range(36):
        rid=ledger.reserve(100)
        ledger.settle(rid,dict(prompt_tokens=1,completion_tokens=1))
    with pytest.raises(RuntimeError,match='exhausted'):
        PostfixBudget(Path(ledger.run_directory)).reserve(100)


def test_subcap_reserves_full_provider_context_before_dispatch(tmp_path):
    ledger,*_=copied(tmp_path)
    rid=ledger.reserve(4096)
    ledger.settle(rid,dict(prompt_tokens=1_000_000,completion_tokens=1000))
    # Actual cost is below $0.60, but another full reservation would exceed it.
    with pytest.raises(RuntimeError,match='exhausted'):ledger.reserve(4096)


def test_inherited_allowance_is_not_renewed_by_new_subcap(tmp_path):
    ledger,*_=copied(tmp_path,spent_input=5_900_000)
    with pytest.raises(RuntimeError,match='exhausted'):ledger.reserve(4096)


@pytest.mark.parametrize('mutation', ['prefix','authorization','inherited'])
def test_changed_history_or_authorization_blocks_dispatch(tmp_path, mutation):
    ledger,*_=copied(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        if mutation=='prefix':db.execute('UPDATE reservations SET input=0 WHERE id=1')
        elif mutation=='authorization':db.execute('UPDATE postfix_authorization SET max_calls=37')
        else:db.execute('UPDATE stage_c_followup_authorization SET baseline_id=1')
    with pytest.raises(ValueError):ledger.reserve(4096)


def test_symlink_cannot_mutate_original_ledger(tmp_path):
    source=tmp_path/'source.sqlite';Budget(source)
    directory=tmp_path/'run';directory.mkdir();(directory/'budget.sqlite').symlink_to(source)
    with pytest.raises(ValueError,match='physical ledger copy'):PostfixBudget(directory)


def test_new_actions_do_not_collide_with_historical_relative_paths(tmp_path):
    ledger,*_=copied(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        db.execute('CREATE TABLE qa_actions(path TEXT PRIMARY KEY,intent TEXT NOT NULL)')
        db.execute("INSERT INTO qa_actions VALUES('crisis/000','original')")
    directory=Path(ledger.run_directory)
    reserve_action(directory,directory/'crisis/000',dict(kind='rollback'),2)
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT intent FROM qa_actions WHERE path='crisis/000'").fetchone()==('original',)
        assert db.execute('SELECT count(*) FROM qa_actions').fetchone()==(2,)
    with pytest.raises(RuntimeError,match='action budget'):reserve_action(directory,directory/'crisis/001',{},2)


def test_interrupted_stream_keeps_full_reservation_and_raw_evidence(tmp_path):
    ledger,*_=copied(tmp_path)
    @ledger.wrap
    def source(provider,model,max_tokens,on_usage):
        on_usage(dict(prompt_tokens=10,completion_tokens=1))
        yield 'partial'
        raise TimeoutError('interrupted')
    with pytest.raises(TimeoutError):list(source('deepseek','deepseek-flash',100,None))
    with pytest.raises(RuntimeError,match='Unknown paid outcome'):ledger.reserve(100)
    log=next((Path(ledger.run_directory)/'provider-streams').glob('*.jsonl'))
    assert json.loads(log.read_text().splitlines()[-1])['complete'] is False
