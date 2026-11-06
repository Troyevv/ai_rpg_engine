"""Resume must retain paid evidence, reject unknown outcomes and count retries."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from devtools.live99.budget import Budget, action_ledger, reserve_action
from devtools.live99.evidence import snapshot, write
from devtools.live99.recovery import (adopt, validate_revision, retry_candidate, probe_context,
                                     completed, digest)
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG, NARRATIVE


@pytest.mark.parametrize('product_path', [None, 'backend/runtime_v3/continuity.py', 'frontend/src/Phone.tsx'])
def test_ci_budget_adoption_keeps_product_change_guard(monkeypatch, product_path):
    from devtools.live99 import recovery
    paths = ['.github/workflows/verify.yml', 'tests/test_ci_backend_budget.py']
    if product_path:
        paths.append(product_path)
    monkeypatch.setattr(recovery.subprocess, 'check_output',
                        lambda command, **_: '\n'.join(paths) if command[1] == 'diff' else '')
    if product_path:
        with pytest.raises(ValueError, match='Product changed'):
            recovery.qa_only('before', 'after')
    else:
        recovery.qa_only('before', 'after')
        monkeypatch.setattr(recovery.subprocess, 'check_output',
                            lambda command, **_: '\n'.join(paths) if command[1] == 'diff' else ' M dirty')
        with pytest.raises(ValueError, match='Commit the reviewed'):
            recovery.qa_only('before', 'after')


def test_action_import_reservations_survive_missing_files_and_concurrency(tmp_path):
    Budget(tmp_path / 'budget.sqlite')
    for n in range(11):
        folder = tmp_path / 'case' / str(n)
        folder.mkdir(parents=True)
        write(folder / 'intent.json', {'step': n})
    assert action_ledger(tmp_path) == 11
    (tmp_path / 'case/0/intent.json').unlink()
    assert action_ledger(tmp_path) == 11

    def reserve(n):
        try:
            reserve_action(tmp_path, tmp_path / 'retries' / str(n), {}, 20)
            return True
        except RuntimeError:
            return False
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(reserve, range(15))) == 9
    assert action_ledger(tmp_path) == 20
    with pytest.raises(RuntimeError, match='exhausted'):
        reserve_action(tmp_path, tmp_path / 'new', {}, 20)


@pytest.fixture
def failed_family(tmp_path):
    Budget(tmp_path / 'budget.sqlite')
    repo = Repository(tmp_path / 'game.sqlite')
    seed = load_fixture(repo, 'newborn-family')
    sid = seed['save']
    config = dict(CONFIG, provider='deepseek', model='deepseek-flash')
    before = snapshot(repo.path, sid)
    with repo.connect() as db:
        cursor = db.execute('SELECT max(rowid) FROM game_jobs').fetchone()[0]
    action = 'Спрашиваю Веру, как она себя чувствует после родов и чем я могу помочь.'
    jid = repo.begin_job(sid, action, 'turn', config)
    # A completed paid Narrative followed by a context construction failure.
    rid = repo.begin_request(jid, 'narrative', config, [], {})
    repo.finish_request(rid, 'complete', dict(prompt_tokens=100, completion_tokens=20,
                        prompt_cache_hit_tokens=0), .1, 'stop')
    with repo.connect() as db:
        db.execute("UPDATE game_jobs SET status='error',narrative=?,narrative_complete=1,error=?,context_json='[]' WHERE id=?",
                   (NARRATIVE, 'Контекст v3 не помещается в выбранную модель (29566 / 28416).', jid))
    folder = tmp_path / 'family/000'
    folder.mkdir(parents=True)
    write(folder / 'intent.json', dict(save=sid, kind='turn', action=action, job_cursor=cursor))
    write(folder / 'before.json.gz', before)
    write(folder / 'result.json', dict(status='held-for-review'))
    return tmp_path, repo, dict(sha='old', seeds={'family': seed}), jid, rid


def test_retry_only_unpaid_extraction_and_production_reuses_narrative(failed_family):
    directory, repo, manifest, jid, rid = failed_family
    _, _, job, request_ids = retry_candidate(directory, manifest, 'family', 0)
    assert request_ids == [rid]
    probe = probe_context(directory, job)
    assert probe['input_estimate'] < probe['hard_input_limit'] < 1048576
    assert probe['conservative_usd_after_one_reservation'] < 2
    camera = repo.get_snapshot(job['save_id'])['world_state']['camera']
    raw = dict(final_scene=dict(location_id=camera['location_id'],
                               present_character_ids=camera['present_character_ids'], elapsed_minutes=1))
    repo.retry_job(jid, dict(json.loads(job['config_json']), context_length=65536))
    with patch('engine.chat_stream', return_value=iter([json.dumps(raw)])) as calls:
        engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert repo.get_job(jid)['narrative'] == NARRATIVE
    assert calls.call_count == 1
    assert calls.call_args.kwargs['response_format'] == {'type': 'json_object'}
    with pytest.raises(ValueError, match='Save changed'):
        retry_candidate(directory, manifest, 'family', 0)


@pytest.mark.parametrize('change', ['paid_extraction', 'unknown_narrative', 'changed_save', 'retry_exists'])
def test_unsafe_retry_rejected(failed_family, change):
    directory, repo, manifest, jid, rid = failed_family
    with repo.connect() as db:
        if change == 'paid_extraction':
            db.execute("UPDATE llm_requests SET stage='extraction' WHERE id=?", (rid,))
        elif change == 'unknown_narrative':
            db.execute("UPDATE llm_requests SET status='running' WHERE id=?", (rid,))
        elif change == 'changed_save':
            db.execute('UPDATE saves SET revision=revision+1')
        else:
            (directory / 'family/000/retries/001').mkdir(parents=True)
    with pytest.raises(ValueError):
        retry_candidate(directory, manifest, 'family', 0)


def test_adoption_preserves_manifest_and_detects_evidence_or_budget_loss(tmp_path, monkeypatch):
    from devtools.live99 import recovery
    monkeypatch.setattr(recovery, 'qa_only', lambda *_: None)
    ledger = Budget(tmp_path / 'budget.sqlite')
    ledger.settle(ledger.reserve(1000), dict(prompt_tokens=100, completion_tokens=20))
    manifest = dict(sha='original')
    write(tmp_path / 'manifest.json', manifest)
    old = (tmp_path / 'manifest.json').read_bytes()
    adopt(tmp_path, manifest, 'new')
    validate_revision(tmp_path, manifest, 'new')
    assert (tmp_path / 'manifest.json').read_bytes() == old
    with sqlite3.connect(tmp_path / 'budget.sqlite') as db:
        db.execute('DELETE FROM reservations')
    with pytest.raises(ValueError, match='reservation'):
        validate_revision(tmp_path, manifest, 'new')
    with pytest.raises(ValueError, match='reservation'):
        adopt(tmp_path, manifest, 'next')


@pytest.mark.parametrize('linked', [False, True])
def test_unsubmitted_recovery_keeps_action_charge(tmp_path, monkeypatch, linked):
    from devtools.live99 import run
    monkeypatch.setattr(run, 'revision', lambda: 'same')
    if linked:
        ledger = tmp_path / 'historical.sqlite'
        Budget(ledger)
        (tmp_path / 'budget.sqlite').symlink_to(ledger)
    else:
        Budget(tmp_path / 'budget.sqlite')
    repo = Repository(tmp_path / 'game.sqlite')
    seed = load_fixture(repo)
    folder = tmp_path / 'social/000'
    folder.mkdir(parents=True)
    intent = dict(sha='same', save=seed['save'], job_cursor=0)
    write(folder / 'intent.json', intent)
    write(folder / 'before.json.gz', snapshot(repo.path, seed['save']))
    if linked:
        # Paid stages import the ledger before creating their absolute-path intent.
        with sqlite3.connect(tmp_path / 'budget.sqlite') as db:
            db.execute('CREATE TABLE qa_actions(path TEXT PRIMARY KEY, intent TEXT NOT NULL)')
        reserve_action(tmp_path, folder, intent, 20)
    assert action_ledger(tmp_path) == 1
    run.recover_unsubmitted(tmp_path, dict(seeds={'social': seed}), 'social', 0)
    assert action_ledger(tmp_path) == 1
    assert len(list((tmp_path / 'attempts').rglob('intent.json'))) == 1
    reserve_action(tmp_path, folder, intent, 20)
    assert action_ledger(tmp_path) == 2


def test_recheck_receipt_does_not_erase_original_failure_or_accept_changed_evidence(tmp_path):
    write(tmp_path / 'result.json', dict(status='held-for-review'))
    original = (tmp_path / 'result.json').read_bytes()
    write(tmp_path / 'verified.json', dict(status='recorded', evidence={'result.json': digest(tmp_path / 'result.json')}))
    assert completed(tmp_path)
    assert (tmp_path / 'result.json').read_bytes() == original
    write(tmp_path / 'result.json', dict(status='interrupted'))
    assert not completed(tmp_path)
