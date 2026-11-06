"""Terminal job recovery through the production repository, resolver and HTTP API."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from threading import Barrier
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import engine
from backend.api.app import create_app
from devtools.narrative_test_world import load_fixture
from rejected_meeting_fixture import CONSENT, QUESTION, meeting_reply
from test_narrative_test_world import CONFIG, ordinary_job


@pytest.fixture
def game(tmp_path):
    app = create_app(tmp_path / 'game.sqlite')
    with TestClient(app) as client:
        repo = app.state.repository
        sid = load_fixture(repo)['save']
        ordinary_job(repo, sid, 'start')
        yield client, repo, sid


def canonical(repo, sid):
    with repo.connect() as db:
        # Include inactive siblings and immutable History, not just the chosen tip.
        return (repo.get_snapshot(sid), repo.list_turns(sid), [
            [tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
            for table in ('response_variants', 'world_history_v3', 'archived_turns')
        ])


def test_stage_c_knowledge_recovery(game):
    client, repo, sid = game
    path = f'/api/saves/{sid}'
    ordinary_job(repo, sid, 'regenerate')
    before = canonical(repo, sid)
    revision = repo.get_save(sid)['revision']
    camera = repo.get_snapshot(sid)['world_state']['camera']
    config = dict(CONFIG, provider='deepseek', model='deepseek-flash')

    def play(action):
        def stream(**kw):
            kw['on_usage'](dict(prompt_tokens=1000, completion_tokens=60, prompt_cache_hit_tokens=200))
            yield (json.dumps(meeting_reply(action, camera), ensure_ascii=False)
                   if kw.get('response_format') else meeting_reply(action))
        jid = repo.begin_job(sid, action, 'turn', config)
        with patch('engine.chat_stream', side_effect=stream) as provider:
            engine.run_job(repo.path, jid, engine.Worker())
        return repo.get_job(jid), provider.call_count

    failed, calls = play(QUESTION)
    jid = failed['id']
    assert calls == 3 and failed['status'] == 'error' and failed['narrative_complete']
    assert failed['revision'] == revision and canonical(repo, sid) == before
    assert [r['code'] for r in json.loads(failed['repair_diagnostics_json'])] == ['controlled_actor_unsupported'] * 2
    requests = repo.request_log(save_id=sid)
    rejected = [r for r in requests if r['job_id'] == jid]
    assert len(rejected) == 3
    assert all(r['response_text'] and Decimal(r['cost_usd']) > 0 and r['input_tokens'] for r in rejected)
    url = f'{path}/jobs/{jid}/abandon'
    body = dict(revision=revision, attempt_epoch=0)
    with patch('engine.launch') as launch, patch('engine.chat_stream') as provider:
        for _ in range(2):
            assert client.post(url, json=body).json()['status'] == 'abandoned'
        launch.assert_not_called()
        provider.assert_not_called()
    assert client.get(path).json()['job']['status'] == 'abandoned'
    assert repo.get_job(jid) == dict(failed, status='abandoned')
    assert repo.request_log(save_id=sid) == requests
    assert canonical(repo, sid) == before
    with pytest.raises(ValueError):
        repo.retry_job(jid)
    saved, calls = play(CONSENT)
    assert calls == 2 and saved['status'] == 'saved', saved['error']
    assert 'sched_vera_meeting' in repo.get_snapshot(sid)['world_state']['scheduled_events']
    # A delayed duplicate for the abandoned job cannot touch a newer result.
    accepted = canonical(repo, sid)
    assert client.post(url, json=body).status_code == 200
    assert canonical(repo, sid) == accepted
    repo.rollback_last(sid, revision + 1)
    assert repo.get_snapshot(sid) == before[0]
    assert repo.list_turns(sid) == before[1]
    ordinary_job(repo, sid)  # new branch after rollback
    assert repo.get_job(jid) == dict(failed, status='abandoned')


def test_stopped_attempt_owner_revision_and_inflight_guards(game):
    client, repo, sid = game
    jid = repo.begin_job(sid, QUESTION, 'turn', CONFIG)
    url = f'/api/saves/{sid}/jobs/{jid}/abandon'
    revision = repo.get_save(sid)['revision']
    body = dict(revision=revision, attempt_epoch=0)
    assert client.post(url, json=body).status_code == 409
    repo.job_progress(jid, 'extracting', 'Сцена', complete=True)
    repo.job_progress(jid, 'stopped')
    with patch('engine.live', return_value=True):
        assert client.post(url, json=body).status_code == 409
    other = load_fixture(repo)['save']
    assert client.post(f'/api/saves/{other}/jobs/{jid}/abandon', json=body).status_code == 409
    assert client.post(url, json=dict(body, revision=revision-1)).status_code == 409
    repo.retry_job(jid)
    repo.job_progress(jid, 'stopped')
    assert client.post(url, json=body).status_code == 409  # same revision, newer attempt
    assert client.post(url, json=dict(body, attempt_epoch=1)).status_code == 200


def test_reload_finds_remaining_recovery_and_active_retry(game):
    client, repo, sid = game
    first = repo.begin_job(sid, QUESTION, 'turn', CONFIG)
    repo.job_progress(first, 'error', 'Сцена', complete=True)
    second = repo.begin_job(sid, '', 'regenerate', CONFIG)
    repo.job_progress(second, 'stopped', 'Вариант', complete=True)
    revision = repo.get_save(sid)['revision']
    view = lambda: client.get(f'/api/saves/{sid}').json()['job']
    assert view()['id'] == second
    repo.abandon_job(sid, second, revision, 0)
    assert view()['id'] == first
    repo.retry_job(first)
    assert view()['id'] == first and view()['status'] == 'extracting'
    repo.job_progress(first, 'stopped')
    # Explicit rollback of the accepted turn makes this recovery stale.
    repo.rollback_last(sid, revision)
    with pytest.raises(ValueError, match='устарел'):
        repo.abandon_job(sid, first, revision, 1)


@pytest.mark.parametrize('competing', ['retry', 'abandon'])
def test_racing_recovery_commands(game, competing):
    _, repo, sid = game
    jid = repo.begin_job(sid, QUESTION, 'turn', CONFIG)
    repo.job_progress(jid, 'error', 'Сцена', complete=True)
    revision = repo.get_save(sid)['revision']
    gate = Barrier(2)

    def command(name):
        gate.wait(timeout=5)
        try:
            if name == 'retry':
                repo.retry_job(jid)
            else:
                repo.abandon_job(sid, jid, revision, 0)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(command, ['abandon', competing]))
    assert sum(results) == (2 if competing == 'abandon' else 1)
    assert repo.get_job(jid)['status'] == ('abandoned' if results[0] else 'extracting')
