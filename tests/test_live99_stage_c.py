import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from devtools.live99.budget import Budget, CONTEXT, INPUT, OUTPUT, action_ledger, reserve_action
from devtools.live99 import stage_c


def authorization(tmp_path):
    path = tmp_path / 'budget.sqlite'
    old = Budget(path)
    old.settle(old.reserve(2000), dict(prompt_tokens=1000, completion_tokens=100))
    action_ledger(tmp_path)
    reserve_action(tmp_path, tmp_path / 'A', {'kind': 'turn'}, 10)
    old.cap_additional('old-retest', 500_000_000)
    old.authorize_stage_b(tmp_path / 'B')
    stage_b = Budget(path, tmp_path / 'B')
    stage_b.settle(stage_b.reserve(2000), dict(prompt_tokens=2000, completion_tokens=200))
    reserve_action(tmp_path, tmp_path / 'B', {'kind': 'turn'}, 10)
    directory = tmp_path / 'C'
    directory.mkdir()
    receipt = old.authorize_stage_c(directory)
    return Budget(path, stage_c=directory), directory, receipt


def test_stage_c_keeps_a_b_history_and_cannot_renew_retest_allowance(tmp_path):
    budget, directory, receipt = authorization(tmp_path)
    with sqlite3.connect(budget.path) as db:
        historical = db.execute('SELECT * FROM reservations').fetchall()
        stage_b = db.execute('SELECT * FROM stage_b_authorization').fetchall()
        caps = db.execute('SELECT * FROM spending_caps').fetchall()
    budget.settle(budget.reserve(4096), dict(prompt_tokens=3000, completion_tokens=300))
    assert Budget(budget.path).authorize_stage_c(directory) == receipt
    with pytest.raises(ValueError, match='cannot renew'):
        budget.authorize_stage_c(tmp_path / 'another-C')
    with sqlite3.connect(budget.path) as db:
        assert db.execute('SELECT * FROM reservations WHERE id<=?', (receipt[1],)).fetchall() == historical
        assert db.execute('SELECT * FROM stage_b_authorization').fetchall() == stage_b
        assert db.execute('SELECT * FROM spending_caps').fetchall() == caps
        assert db.execute('SELECT count(*) FROM qa_actions').fetchone()[0] == 2


def test_stage_c_retest_and_continuation_share_one_two_dollar_cap(tmp_path):
    budget, directory, _ = authorization(tmp_path)
    for _ in range(6):
        budget.settle(budget.reserve(32000), dict(prompt_tokens=900000, completion_tokens=32000))
    spent = 6 * (900000 * INPUT + 32000 * OUTPUT)
    assert spent < 2_000_000_000 < spent + CONTEXT * INPUT + 32000 * OUTPUT
    with pytest.raises(RuntimeError, match='exhausted'):
        Budget(budget.path, stage_c=directory).reserve(32000)


def test_postfix_followup_keeps_old_stage_c_and_has_one_bound_allowance(tmp_path):
    old, parent, _ = authorization(tmp_path)
    old.settle(old.reserve(2000), dict(prompt_tokens=3000, completion_tokens=300))
    with sqlite3.connect(old.path) as db:
        history = db.execute('SELECT * FROM reservations').fetchall()
        original_c = db.execute('SELECT * FROM stage_c_authorization').fetchall()
    child = tmp_path / 'followup'
    receipt = old.authorize_stage_c_followup(child, parent)
    budget = Budget(old.path, stage_c=child, stage_c_followup=True)
    assert old.authorize_stage_c_followup(child, parent) == receipt
    for _ in range(6):
        budget.settle(budget.reserve(32000), dict(prompt_tokens=900000, completion_tokens=32000))
    with pytest.raises(RuntimeError, match='exhausted'):
        Budget(old.path, stage_c=child, stage_c_followup=True).reserve(32000)
    with pytest.raises(ValueError, match='cannot renew'):
        old.authorize_stage_c_followup(tmp_path / 'other', parent)
    with pytest.raises(ValueError, match='original Stage C ledger'):
        old.authorize_stage_c_followup(child, tmp_path / 'wrong-parent')
    with sqlite3.connect(old.path) as db:
        assert db.execute('SELECT * FROM reservations WHERE id<=?', (receipt[1],)).fetchall() == history
        assert db.execute('SELECT * FROM stage_c_authorization').fetchall() == original_c


def test_followup_unknown_cost_cannot_be_reauthorized_or_dispatched(tmp_path):
    old, parent, _ = authorization(tmp_path)
    old.reserve(2000)
    with pytest.raises(ValueError, match='Unknown paid outcome'):
        old.authorize_stage_c_followup(tmp_path / 'followup', parent)


def test_linked_retest_spends_remaining_followup_cap_without_reset(tmp_path):
    old, original, _ = authorization(tmp_path)
    parent, child = tmp_path/'followup', tmp_path/'retest'
    receipt = old.authorize_stage_c_followup(parent, original)
    paid = Budget(old.path, stage_c=parent, stage_c_followup=True)
    for _ in range(3):
        paid.settle(paid.reserve(32000), dict(prompt_tokens=900000, completion_tokens=32000))
    with sqlite3.connect(old.path) as db:
        history = db.execute('SELECT * FROM reservations ORDER BY id').fetchall()
        authorizations = db.execute('SELECT * FROM stage_c_followup_authorization').fetchall()
    linked = old.link_stage_c_followup(child, parent)
    assert linked == (str(child.resolve()), *receipt[1:])
    assert old.link_stage_c_followup(child, parent) == linked
    current = Budget(old.path, stage_c=child, stage_c_followup=True)
    for _ in range(3):
        current.settle(current.reserve(32000), dict(prompt_tokens=900000, completion_tokens=32000))
    for run in (parent, child):
        with pytest.raises(RuntimeError, match='exhausted'):
            Budget(old.path, stage_c=run, stage_c_followup=True).reserve(32000)
    with pytest.raises(ValueError, match='cannot renew'):
        old.link_stage_c_followup(tmp_path/'other', parent)
    with pytest.raises(ValueError, match='authorized followup parent'):
        old.link_stage_c_followup(child, original)
    with sqlite3.connect(old.path) as db:
        assert db.execute('SELECT * FROM reservations ORDER BY id LIMIT ?', (len(history),)).fetchall() == history
        assert db.execute('SELECT * FROM stage_c_followup_authorization').fetchall() == authorizations
        assert db.execute('SELECT count(*) FROM qa_actions').fetchone()[0] == linked[2]


def test_unknown_outcome_blocks_link_and_shared_retest_dispatch(tmp_path):
    old, original, _ = authorization(tmp_path)
    parent, child = tmp_path/'followup', tmp_path/'retest'
    old.authorize_stage_c_followup(parent, original)
    paid = Budget(old.path, stage_c=parent, stage_c_followup=True)
    rid = paid.reserve(2000)
    with pytest.raises(ValueError, match='Unknown paid outcome'):
        old.link_stage_c_followup(child, parent)
    paid.settle(rid, dict(prompt_tokens=1000, completion_tokens=100))
    old.link_stage_c_followup(child, parent)
    current = Budget(old.path, stage_c=child, stage_c_followup=True)
    current.reserve(2000)
    with pytest.raises(RuntimeError, match='Unknown paid outcome'):
        paid.reserve(2000)


def test_unknown_stage_c_outcome_blocks_all_next_dispatches_and_reauthorization(tmp_path):
    budget, directory, _ = authorization(tmp_path)
    def dispatch(_):
        try:
            return Budget(budget.path, stage_c=directory).reserve(2000)
        except RuntimeError:
            return None
    with ThreadPoolExecutor(4) as pool:
        assert sum(r is not None for r in pool.map(dispatch, range(8))) == 1
    with pytest.raises(RuntimeError, match='Unknown paid outcome'):
        budget.reserve(2000)
    with pytest.raises(ValueError, match='mismatched'):
        Budget(budget.path, stage_c=tmp_path / 'copy').reserve(2000)


def test_stage_c_partial_output_is_durable_and_never_refunded(tmp_path):
    budget, directory, _ = authorization(tmp_path)
    def stream(provider, model, max_tokens, on_usage=None):
        yield 'Partial raw LTA\r\n'
        on_usage(dict(prompt_tokens=1, completion_tokens=1))
        raise RuntimeError('Lost final response')
    with pytest.raises(RuntimeError, match='Lost final'):
        list(budget.wrap(stream)(provider='deepseek', model='deepseek-flash', max_tokens=2000))
    chunks = [json.loads(line) for line in next((directory / 'provider-streams').glob('*.jsonl')).read_text().splitlines()]
    assert chunks[1]['text'] == 'Partial raw LTA\r\n'
    assert chunks[-1]['complete'] is False
    with pytest.raises(RuntimeError, match='Unknown paid outcome'):
        budget.reserve(2000)


@pytest.mark.parametrize('state', ['missing', 'held-for-review', 'recorded-without-semantic-review'])
def test_retest_review_cannot_unlock_missing_held_or_unreviewed_group(tmp_path, monkeypatch, state):
    monkeypatch.setattr(stage_c, 'validate', lambda *args: None)
    folder = tmp_path / 'social/000'; folder.mkdir(parents=True)
    if state != 'missing':
        (folder / 'result.json').write_text(json.dumps({'status': 'recorded' if state.startswith('recorded') else state}))
    with pytest.raises((ValueError, FileNotFoundError)):
        stage_c.review(tmp_path, {'seeds': {'social': {}}, 'retest_counts': {'social': 1}}, 'social')
    assert not (tmp_path / 'retest-reviews/social.json').exists()


def test_review_binds_semantic_findings_and_original_failure_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_c, 'validate', lambda *args: None)
    folder = tmp_path / 'social/000';folder.mkdir(parents=True)
    (folder / 'result.json').write_text(json.dumps({'status': 'recorded'}))
    (folder / 'before.json.gz').write_bytes(b'original checkpoint')
    semantic = tmp_path / 'semantic-reviews';semantic.mkdir()
    (semantic / 'social.json').write_text(json.dumps({'case':'social','status':'passed','checks':{'events':True,'agency':True}}))
    stage_c.review(tmp_path, {'seeds':{'social':{}},'retest_counts':{'social':1}}, 'social')
    result = json.loads((tmp_path / 'retest-reviews/social.json').read_text())
    assert set(result['evidence']) == {'social/000/result.json','social/000/before.json.gz','semantic-reviews/social.json'}
    with pytest.raises(ValueError, match='already reviewed'):
        stage_c.review(tmp_path, {'seeds':{'social':{}},'retest_counts':{'social':1}}, 'social')


@pytest.mark.parametrize('stage', ['extraction', 'extraction_repair'])
def test_negative_agency_retest_requires_atomic_state_and_valid_temporal(tmp_path, stage):
    from devtools.live99.evidence import write
    write(tmp_path / 'result.json', {'status':'held-for-review','kind':'retry'})
    for name in ('before', 'after'):
        write(tmp_path / (name+'.json.gz'), {'revision':12,'history':'unchanged'})
    request = {'stage':stage,'status':'complete','response_text':json.dumps({
        'scheduled_event_changes':[{'temporal':{'day_offset':1,'time':'15:00'}}]})}
    job = {'status':'error','repair_diagnostics_json':json.dumps([{'code':'controlled_actor_unsupported'}]),
           'requests':[request]}
    write(tmp_path / 'diagnostics.json.gz',[job])
    audit = {'case':'knowledge','expected_rejection':'controlled_actor_unsupported'}
    assert stage_c.expected_agency_rejection(tmp_path,audit)
    assert not stage_c.expected_agency_rejection(tmp_path,dict(audit,case='social'))
    write(tmp_path / 'after.json.gz', {'revision':13,'history':'changed'})
    assert not stage_c.expected_agency_rejection(tmp_path,audit)
    write(tmp_path / 'after.json.gz', {'revision':12,'history':'unchanged'})
    request['response_text'] = json.dumps({'scheduled_event_changes':[{
        'temporal':{'day_offset':1,'time':'15:00','day_period':'afternoon'}}]})
    write(tmp_path / 'diagnostics.json.gz',[job])
    with pytest.raises(ValueError):
        stage_c.expected_agency_rejection(tmp_path,audit)
    assert json.loads((tmp_path/'result.json').read_text())['status']=='held-for-review'


def test_phone_reload_baseline_waits_for_canonical_read_without_dispatch():
    from types import SimpleNamespace
    from devtools.live99.browser import wait_phone_read
    polls = []
    def get(url):
        polls.append(url)
        events = [{'outgoing':True,'content':'Hello','conversation_id':'direct','unread':False},
                  {'outgoing':False,'content':None,'conversation_id':'direct','unread':len(polls)<3},
                  {'outgoing':False,'content':None,'conversation_id':'other','unread':True}]
        return SimpleNamespace(json=lambda: {'state':{'phone':{'events':events}}})
    waits=[]
    page=SimpleNamespace(request=SimpleNamespace(get=get),wait_for_timeout=waits.append)
    wait_phone_read(page,'http://localhost',6,'Hello')
    assert len(polls)==3 and waits==[250,250]


def test_phone_unsettled_read_is_held_without_retry():
    from types import SimpleNamespace
    from devtools.live99.browser import wait_phone_read
    response=SimpleNamespace(json=lambda: {'state':{'phone':{'events':[]}}})
    page=SimpleNamespace(request=SimpleNamespace(get=lambda _:response),wait_for_timeout=lambda _:None)
    with pytest.raises(ValueError,match='preserve the paid job'):
        wait_phone_read(page,'http://localhost',6,'Missing')


def test_semantic_hold_survives_saved_status_and_binds_evidence(tmp_path, monkeypatch):
    from devtools.live99 import stage_b
    from devtools.live99.evidence import write
    monkeypatch.setattr(stage_b, 'validate', lambda *args: None)
    manifest={'seeds':{'crisis':{},'social':{}}}
    folder=tmp_path/'crisis/010';folder.mkdir(parents=True)
    write(folder/'result.json',dict(status='recorded'))
    notes=tmp_path/'semantic-holds';notes.mkdir()
    write(notes/'crisis.json',dict(case='crisis',status='held',reason='Absent witness accepted in History'))
    stage_c.record_hold(tmp_path,manifest,'crisis',10)
    stage_c.validate(tmp_path,manifest)
    assert stage_c.is_held(tmp_path,'crisis')
    assert not stage_c.is_held(tmp_path,'social')
    with pytest.raises(ValueError,match='already held'):
        stage_c.record_hold(tmp_path,manifest,'crisis',10)
    write(folder/'result.json',dict(status='changed'))
    with pytest.raises(ValueError,match='evidence changed'):
        stage_c.validate(tmp_path,manifest)
