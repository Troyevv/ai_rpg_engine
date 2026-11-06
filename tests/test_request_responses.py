"""Raw provider text belongs to the usage row for each individual attempt (#212)."""
import gzip
import json
from threading import Event
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from backend.services.usage import tracked_stream
from devtools.live99.evidence import diagnostics, write
from devtools.narrative_test_world import load_fixture
from llm import OutputLimitReached, ProviderHTTPError
from test_engine import CONFIG, db


USAGE = {'prompt_tokens': 1000, 'completion_tokens': 100, 'prompt_cache_hit_tokens': 800}
CHUNKS = ('  Начало\r', '\n', '  конец\t🙂 ')
SECRET = 'test-credential-never-persist'


@pytest.mark.parametrize('stage', [
    'long_term_narrative', 'long_term_extraction', 'narrative', 'extraction',
    'remote_initiative', 'draft_world',
])
def test_tracker_preserves_exact_chunks_and_usage(db, stage):
    repo, _, sid = db
    job = repo.begin_job(sid, '', 'start', CONFIG)
    messages = [{'role': 'user', 'content': 'Replay'}]
    calls = []

    def stream(**kwargs):
        calls.append(kwargs['messages'])
        assert kwargs['api_key'] == SECRET
        yield from CHUNKS
        kwargs['on_usage'](USAGE)
        kwargs['on_finish']('stop')

    config = dict(CONFIG, headers={'Authorization': f'Bearer {SECRET}'}, api_key=SECRET)
    assert tuple(tracked_stream(repo, stream, job, stage, config, messages, api_key=SECRET)) == CHUNKS
    row, = repo.request_log(job_id=job)
    assert (row['job_id'], row['stage'], row['messages']) == (job, stage, messages)
    assert (row['status'], row['finish_reason'], row['response_text']) == ('complete', 'stop', ''.join(CHUNKS))
    assert json.loads(row['usage_json']) == USAGE
    assert (row['input_tokens'], row['output_tokens'], row['cached_input_tokens'], row['cost_usd']) == (1000, 100, 800, '0')
    assert calls == [messages]
    with repo.connect() as conn:
        stored = conn.execute('SELECT * FROM llm_requests WHERE id=?', (row['id'],)).fetchone()
        assert SECRET not in repr(tuple(stored))
        assert 'Authorization' not in stored['config_json']


@pytest.mark.parametrize(('outcome', 'status', 'finish'), [
    ('error', 'error', None), ('length', 'length', 'length'),
    ('cancel', 'stopped', None), ('close', 'stopped', None),
])
def test_interrupted_request_keeps_only_received_prefix(db, outcome, status, finish):
    repo, _, sid = db
    job = repo.begin_job(sid, '', 'start', CONFIG)
    cancel = Event()

    def stream(**kwargs):
        yield CHUNKS[0]
        if outcome == 'length':
            kwargs['on_usage'](USAGE)
            kwargs['on_finish']('length')
        elif outcome == 'cancel':
            cancel.set()
            raise RuntimeError('provider stream cancelled')
        else:
            raise ProviderHTTPError('unsafe provider error ' + SECRET, 503)

    iterator = tracked_stream(repo, stream, job, 'long_term_extraction', CONFIG, [], cancel_event=cancel)
    assert next(iterator) == CHUNKS[0]
    if outcome == 'close':
        iterator.close()
    else:
        with pytest.raises({'length': OutputLimitReached, 'error': ProviderHTTPError, 'cancel': RuntimeError}[outcome]):
            next(iterator)
    row, = repo.request_log(job_id=job)
    assert row['id'] and row['job_id'] == job and row['stage'] == 'long_term_extraction'
    assert (row['response_text'], row['status'], row['finish_reason']) == (CHUNKS[0], status, finish)
    assert row['usage_json'] == (json.dumps(USAGE) if finish else None)
    assert SECRET not in str(row)
    if outcome == 'error':
        assert row['diagnostics']['provider_error'] == {'http_status': 503}


def test_rejected_lta_groups_reload_export_and_regeneration(tmp_path):
    repo = Repository(tmp_path / 'game.sqlite')
    sid = load_fixture(repo, 'long-term')['save']
    config = dict(CONFIG, long_term_advance=dict(amount=15, unit='years', max_llm_calls=4))
    attempts = {}
    for kind in ('long_term', 'regenerate'):
        job = repo.begin_job(sid, '', kind, config)
        calls = []

        def stream(**kwargs):
            is_extraction = bool(kwargs.get('response_format'))
            stage = 'long_term_extraction' if is_extraction else 'long_term_narrative'
            # Valid JSON with no supporting Event: the provider completes, the Runtime rejects.
            if is_extraction:
                state = next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n'))
                camera = json.loads(state.split('\n', 1)[1])['camera']
                scene = {k: camera[k] for k in ('location_id', 'present_character_ids')}
                text = ' ' + json.dumps({'final_scene': dict(scene, elapsed_minutes=0)}) + '\r\n'
            else:
                text = f' {kind} {len(calls)}.\n'
            calls.append((stage, text, kwargs['messages']))
            yield text[:3]
            yield text[3:]
            kwargs['on_usage'](USAGE)
            kwargs['on_finish']('stop')

        with patch('engine.chat_stream', side_effect=stream):
            engine.run_job(repo.path, job, engine.Worker(api_key=SECRET))
        repo = Repository(repo.path)
        saved = repo.get_job(job)
        assert saved['status'] == 'saved', saved['error']
        report = repo.get_snapshot(sid)['last_long_term_advance']
        assert not report['accepted'] and any(d['code'] == 'invalid_outcome' for d in report['diagnostics'])
        assert len(calls) == report['llm_calls'] == 4
        rows = list(reversed(repo.request_log(job_id=job)))
        frames = json.loads(saved['context_json'])
        assert len({r['id'] for r in rows}) == len(frames) == 4
        # Regeneration retains the original input frames; request rows hold its actual new inputs.
        for r, frame, (stage, text, messages) in zip(rows, frames, calls, strict=True):
            assert (r['job_id'], r['stage'], r['messages']) == (job, stage, messages)
            assert r['diagnostics']['context_key'] == frame['context_key']
            assert (r['response_text'], r['status'], r['finish_reason']) == (text, 'complete', 'stop')
            assert json.loads(r['usage_json']) == USAGE
            assert 'response_text' not in frame and 'response' not in frame
        attempts[job] = {r['id']: r['response_text'] for r in rows}

    exported = tmp_path / 'diagnostics.json.gz'
    write(exported, diagnostics(repo.path, sid, 0))
    data = gzip.decompress(exported.read_bytes()).decode()
    assert SECRET not in data
    by_job = {j['id']: {r['id']: r['response_text'] for r in j['requests']} for j in json.loads(data)}
    for job, expected in attempts.items():
        assert by_job[job] == expected
    assert len(set.union(*(set(rows) for rows in attempts.values()))) == 8


def test_retry_keeps_prior_attempts_and_does_not_repeat_narrative(db):
    from test_runtime_v3_engine import raw_for

    repo, _, sid = db
    config = dict(CONFIG, provider='deepseek', model='deepseek-flash')
    job = repo.begin_job(sid, '', 'start', config)
    final = json.dumps(raw_for(repo.get_snapshot(sid)))
    text = ' Окно открыто.\n'
    prefix = '{"final'
    replies = iter([text, prefix, final])

    def stream(**kwargs):
        reply = next(replies)
        yield reply
        if reply == prefix:
            raise RuntimeError('disconnected')
        kwargs['on_usage'](USAGE)
        kwargs['on_finish']('stop')

    with patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, job, engine.Worker())
        assert repo.get_job(job)['status'] == 'error'
        original = repo.request_log(job_id=job)
        repo.retry_job(job)
        engine.run_job(repo.path, job, engine.Worker())
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    rows = repo.request_log(job_id=job)
    assert rows[1:] == original
    assert len({r['id'] for r in rows}) == 3 and all(r['job_id'] == job for r in rows)
    assert [(r['stage'], r['status'], r['finish_reason'], r['response_text']) for r in reversed(rows)] == [
        ('narrative', 'complete', 'stop', text),
        ('extraction', 'error', None, prefix),
        ('extraction', 'complete', 'stop', final),
    ]


def test_historical_response_stays_unknown_on_reload(db):
    repo, _, sid = db
    job = repo.begin_job(sid, '', 'start', CONFIG)
    request = repo.begin_request(job, 'long_term_extraction', CONFIG, [], {})
    repo.finish_request(request, 'complete', USAGE, finish_reason='stop')
    historical, = Repository(repo.path).request_log(job_id=job)
    assert (historical['id'], historical['job_id'], historical['status'], historical['response_text']) == (
        request, job, 'complete', None,
    )
