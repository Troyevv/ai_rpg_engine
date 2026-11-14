from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from devtools.live99 import budget
from devtools.live99.scenarios import CASES, QUOTAS


@pytest.mark.parametrize('cap,value', [('LIMIT_CALLS', 1),
                                       ('LIMIT_TOKENS', budget.CONTEXT + 500),
                                       ('LIMIT_NUSD', budget.CONTEXT * budget.INPUT + 500 * budget.OUTPUT)])
def test_unknown_charge_cannot_be_reused_on_resume(tmp_path, monkeypatch, cap, value):
    monkeypatch.setattr(budget, cap, value)
    path = tmp_path / 'budget.sqlite'
    ledger = budget.Budget(path)
    rid = ledger.reserve(500)
    ledger.settle(rid, {'completion_tokens': 1})
    with pytest.raises(RuntimeError, match='exhausted'):
        budget.Budget(path).reserve(500)


def test_concurrent_dispatch_reserves_before_send(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, 'LIMIT_CALLS', 1)
    ledger = budget.Budget(tmp_path / 'budget.sqlite')

    def attempt(_):
        try:
            return ledger.reserve(1024)
        except RuntimeError:
            return None

    with ThreadPoolExecutor(4) as executor:
        assert sorted(r for r in executor.map(attempt, range(8)) if r is not None) == [1]


def test_guard_passes_provider_usage_through_only_releases_after_complete_stream(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = budget.Budget(path)
    usage = {'prompt_tokens': 321, 'completion_tokens': 17}
    callbacks = []

    @ledger.wrap
    def source(provider, model, max_tokens, on_usage):
        on_usage(usage)
        yield 'chunk'

    for provider in ('local', 'compatible'):
        with pytest.raises(ValueError):
            list(source(provider, budget.MODEL, 2000, callbacks.append))
    stream = source('deepseek', budget.MODEL, 2000, callbacks.append)
    assert next(stream) == 'chunk'
    stream.close()
    assert list(source('deepseek', budget.MODEL, 2000, callbacks.append)) == ['chunk']
    assert callbacks == [usage, usage]
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT input,output,settled FROM reservations ORDER BY id').fetchall() == [
            (budget.CONTEXT, 2000, 0), (321, 17, 1)]


def test_six_risk_groups_fit_cumulative_stage_ceilings():
    assert len(CASES) == 6
    assert [sum(QUOTAS[s]) for s in 'ABC'] == [20, 100, 700]
    assert all(a < b < c for a, b, c in zip(*QUOTAS.values(), strict=True))

@pytest.mark.parametrize('receipt', [None, {'prompt_tokens':10957,'completion_tokens':24000}])
def test_length_without_visible_json_settles_only_verified_usage(tmp_path,receipt):
    from llm import OutputLimitReached
    path=tmp_path/'budget.sqlite';ledger=budget.Budget(path)
    @ledger.wrap
    def source(provider,model,max_tokens,on_usage):
        if receipt is not None:on_usage(receipt)
        raise OutputLimitReached()
        yield
    with pytest.raises(OutputLimitReached):list(source('deepseek',budget.MODEL,24000,lambda _:None))
    with sqlite3.connect(path) as db:
        expected=(10957,24000,1) if receipt else (budget.CONTEXT,24000,0)
        assert db.execute('SELECT input,output,settled FROM reservations').fetchone()==expected


def test_world_resume_ceiling_is_reserved_without_raising_ordinary_requests(tmp_path):
    ledger=budget.Budget(tmp_path/'budget.sqlite')
    rid=ledger.reserve(64000)
    with sqlite3.connect(ledger.path) as db:assert db.execute('SELECT output FROM reservations WHERE id=?',(rid,)).fetchone()[0]==64000
    with pytest.raises(ValueError):ledger.reserve(65537)
