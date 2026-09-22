import json
import threading
from copy import deepcopy
from unittest.mock import patch

import pytest
import engine
from context_builder import build_context, estimate
from state_updates import apply_updates, choice_input
from storage import Storage
from test_worlds import summary

CONFIG = {'model': 'test', 'context_length': 32768, 'max_tokens': 2000, 'update_tokens': 4096, 'temperature': 0.8}
NARRATIVE = 'Персонаж 1 подвигает свободный стул. «Садись, поговорим».'


def result():
    return {'scene': {'text': 'Разговор на кухне.', 'time': '18:20', 'location': 'Кухня', 'present_ids': ['character_1', 'character_2']},
            'events': [{'text': 'Собеседник предложил поговорить.', 'character_ids': ['character_1', 'character_2'], 'evidence': 'Садись, поговорим'}],
            'choices': [{'action': 'Действие ' + str(i), 'speech': 'Реплика ' + str(i)} for i in range(6)]}


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / 'game.sqlite3')
    wid = storage.save_world('Мир', summary())
    sid = storage.create_save(wid, 'Игра')
    return storage, wid, sid


def run(storage, job_id, extraction=None):
    calls = []
    def stream(**kwargs):
        calls.append(kwargs)
        yield json.dumps(result() if extraction is None else extraction, ensure_ascii=False) if kwargs.get('response_format') else NARRATIVE
    with patch('engine.find_loaded_model', return_value={'config': {'context_length': 32768}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(storage.path, job_id, engine.Worker())
    return calls


def test_start_then_free_input_and_atomic_rollback(db):
    storage, wid, sid = db
    initial = storage.get_save(sid)['state']
    job = storage.begin_job(sid, '', 'start', CONFIG)
    with pytest.raises(ValueError):
        storage.begin_job(sid, '', 'start', CONFIG)
    calls = run(storage, job)
    assert len(calls) == 2
    assert storage.get_job(job)['status'] == 'saved'
    first = storage.list_turns(sid)[0]
    assert first['kind'] == 'start' and first['user_text'] == ''
    assert len(json.loads(first['choices_json'])) == 6
    with pytest.raises(ValueError):
        storage.begin_job(sid, '', 'start', CONFIG)
    assert storage.get_world(wid)['state'] == initial
    after_start = storage.get_save(sid)['state']
    action = 'Илья молча садится на стул.'
    job2 = storage.begin_job(sid, action, 'turn', CONFIG)
    run(storage, job2)
    assert storage.list_turns(sid)[-1]['user_text'] == action
    storage.rollback_last(sid)
    assert storage.get_save(sid)['state'] == after_start
    storage.rollback_last(sid)
    assert storage.get_save(sid)['state'] == initial
    assert storage.list_turns(sid) == []
    assert storage.begin_job(sid, '', 'start', CONFIG)


def test_extraction_retry_does_not_regenerate_narrative(db):
    storage, wid, sid = db
    job = storage.begin_job(sid, '', 'start', CONFIG)
    bad = result(); bad['choices'] = bad['choices'][:5]
    run(storage, job, bad)
    assert storage.get_job(job)['status'] == 'error'
    assert storage.get_job(job)['narrative_complete']
    assert storage.list_turns(sid) == []
    storage.retry_job(job, CONFIG)
    calls = run(storage, job)
    assert len(calls) == 1 and calls[0]['response_format'] == {'type': 'json_object'}
    assert storage.list_turns(sid)[0]['assistant_text'] == NARRATIVE


def test_cancel_late_result_and_revision_checks(db):
    storage, wid, sid = db
    job = storage.begin_job(sid, '', 'start', CONFIG)
    storage.job_progress(job, 'validating', narrative=NARRATIVE, complete=True)
    storage.job_progress(job, 'stopped')
    state, choices, changes = apply_updates(storage.get_save(sid)['state'], result(), NARRATIVE, '', 0)
    with pytest.raises(ValueError):
        storage.commit_job(job, state, choices, changes)
    assert storage.list_turns(sid) == []
    storage.update_scene_meta(sid, {'time': '19:00', 'location': 'Двор', 'present_ids': []})
    with pytest.raises(ValueError):
        storage.retry_job(job)
    with pytest.raises(ValueError):
        storage.begin_job(sid, '', 'start', {**CONFIG, 'expected_revision': 0})


def test_failed_regeneration_preserves_previous_turn(db):
    storage, wid, sid = db
    job = storage.begin_job(sid, '', 'start', CONFIG); run(storage, job)
    original = storage.list_turns(sid)
    state = storage.get_save(sid)['state']
    replacement = storage.begin_job(sid, '', 'regenerate', CONFIG)
    run(storage, replacement, {'choices': []})
    assert storage.list_turns(sid) == original
    assert storage.get_save(sid)['state'] == state
    storage.retry_job(replacement); run(storage, replacement)
    assert len(storage.list_turns(sid)) == 1
    with storage.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM archived_turns').fetchone()[0] == 1


def test_invalid_patch_and_relationship_arrow_lifetime(db):
    storage, wid, sid = db
    before = storage.get_save(sid)['state']
    payload = result()
    payload['relationships'] = [{'source_id': 'character_2', 'target_id': 'character_1', 'text': 'Стало больше доверия.',
                                 'direction': 'up', 'aspect': 'доверие', 'reason': 'Пригласил поговорить', 'evidence': 'Садись, поговорим'}]
    state, choices, changes = apply_updates(before, payload, NARRATIVE, '', 0)
    assert state['relationships'][-1]['change']['direction'] == 'up'
    next_state, _, _ = apply_updates(state, result(), NARRATIVE, 'Ответ', 1)
    assert all('change' not in r for r in next_state['relationships'])
    assert choice_input(choices[0]) == 'Действие 0: «Реплика 0»'
    for broken in [dict(payload, characters=[{'id': 'missing', 'now': 'Там', 'evidence': NARRATIVE}]),
                   dict(payload, characters=[{'id': 'character_1', 'goal': 'Влюбиться', 'evidence': NARRATIVE}]),
                   dict(payload, facts=[{'text': 'Выдумка', 'known_by': ['character_1'], 'evidence': 'нет в тексте'}]),
                   dict(payload, choices=[payload['choices'][0]] * 6)]:
        with pytest.raises(ValueError):
            apply_updates(before, broken, NARRATIVE, '', 0)
    assert storage.get_save(sid)['state'] == before


def test_context_budget_rejects_core_overflow(db):
    storage, wid, sid = db
    state = storage.get_save(sid)['state']
    messages = build_context(state, [], '', 'start', 32768, 2000)
    assert estimate(messages) <= 32768 - 2000 - 256
    with pytest.raises(ValueError):
        build_context(state, [], '', 'start', 1000, 500)


def test_stop_during_stream_preserves_draft(db):
    storage, wid, sid = db
    job = storage.begin_job(sid, '', 'start', CONFIG)
    worker = engine.Worker()
    def stream(**kwargs):
        yield 'Начало сцены.'
        storage.job_progress(job, 'stopped')
        worker.cancelled.set()
        yield ' Не фиксировать мир.'
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(storage.path, job, worker)
    assert storage.get_job(job)['status'] == 'stopped'
    assert storage.get_job(job)['narrative'] == 'Начало сцены.'
    assert storage.list_turns(sid) == []






def test_commit_is_atomic_if_save_update_fails(db):
    storage, wid, sid = db
    initial = storage.get_save(sid)['state']
    job = storage.begin_job(sid, '', 'start', CONFIG)
    storage.job_progress(job, 'validating', narrative=NARRATIVE, complete=True)
    state, choices, changes = apply_updates(initial, result(), NARRATIVE, '', 0)
    with storage.connect() as conn:
        conn.execute("CREATE TRIGGER fail_commit BEFORE UPDATE ON saves BEGIN SELECT RAISE(ABORT, 'test'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        storage.commit_job(job, state, choices, changes)
    assert storage.list_turns(sid) == []
    assert storage.get_save(sid)['state'] == initial


def test_migration_of_old_database_preserves_existing_save(tmp_path):
    import sqlite3
    path = tmp_path / 'legacy.sqlite3'
    connection = sqlite3.connect(path)
    connection.executescript('''
        CREATE TABLE saves(id INTEGER PRIMARY KEY, world_id INTEGER NOT NULL, name TEXT NOT NULL,
          state_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT 'old', updated_at TEXT NOT NULL DEFAULT 'old');
        CREATE TABLE turns(id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, sequence INTEGER NOT NULL,
          user_text TEXT NOT NULL, assistant_text TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
          UNIQUE(save_id,sequence));
        INSERT INTO saves(id,world_id,name,state_json) VALUES(1,1,'Старый сейв','{"scene":"Старая сцена"}');
    ''')
    connection.close()
    storage = Storage(path)
    assert storage.get_save(1)['state'] == {'scene': 'Старая сцена'}
    assert storage.get_save(1)['revision'] == 0
    Storage(path)  # Idempotent initialization.
    with storage.connect() as conn:
        assert {'kind', 'choices_json', 'changes_json'} <= {r['name'] for r in conn.execute('PRAGMA table_info(turns)')}


@pytest.mark.parametrize('quote,narrative,player,valid', [
    ('«Садись, поговорим»', '“Садись,\n  поговорим”', '', True),
    ('Садись, поговорим', 'Садись,\u00a0поговорим', '', True),
    ('Я сяду здесь.', NARRATIVE, 'Я сяду здесь.', True),
    ('Садись, поговорим', 'Не садись. Поговорим потом.', '', False),
    ('Садись поговорим', 'Садись', 'поговорим', False),
    ('Садись… поговорим', NARRATIVE, '', False),
    ('', NARRATIVE, '', False),
])
def test_evidence_formatting_without_accepting_invented_quotes(db, quote, narrative, player, valid):
    from state_updates import EvidenceError
    storage, _, sid = db
    before = storage.get_save(sid)['state']
    payload = result()
    payload['events'][0]['evidence'] = quote
    if valid:
        apply_updates(before, payload, narrative, player, 0)
    else:
        with pytest.raises(EvidenceError, match=r'events\[0\].evidence'):
            apply_updates(before, payload, narrative, player, 0)
    assert storage.get_save(sid)['state'] == before


@pytest.mark.parametrize('outcome', ['fixed', 'invalid', 'stopped'])
def test_evidence_repair_is_bounded_atomic_and_keeps_narrative(db, outcome):
    storage, _, sid = db
    before = storage.get_save(sid)['state']
    job = storage.begin_job(sid, '', 'start', {**CONFIG, 'provider': 'deepseek'})
    worker = engine.Worker()
    calls = []
    def stream(**kwargs):
        calls.append(kwargs)
        if not kwargs.get('response_format'):
            yield NARRATIVE
            return
        payload = result()
        if len(calls) == 2 or outcome == 'invalid':
            payload['events'][0]['evidence'] = 'Пересказ вместо цитаты'
        if len(calls) == 3:
            assert any('events[0].evidence' in m['content'] for m in kwargs['messages'])
            assert estimate(kwargs['messages']) <= CONFIG['context_length'] - CONFIG['update_tokens'] - 256
            if outcome == 'stopped':
                engine.stop(storage, job)
                worker.cancelled.set()
        yield json.dumps(payload, ensure_ascii=False)
    with patch('engine.chat_stream', side_effect=stream):
        engine.run_job(storage.path, job, worker)
    assert len(calls) == 3
    assert storage.get_job(job)['narrative'] == NARRATIVE
    assert storage.get_job(job)['narrative_complete']
    if outcome in ('fixed','invalid'):
        if outcome == 'invalid':
            assert json.loads(storage.get_job(job)['warnings_json'])[0]['section'] == 'events'
            assert storage.get_save(sid)['state'].get('events',[]) == before.get('events',[])
        assert storage.get_job(job)['status'] == 'saved'
        assert len(storage.list_turns(sid)) == 1
        assert len(json.loads(storage.list_turns(sid)[0]['choices_json'])) == 6
    else:
        assert storage.get_job(job)['status'] == ('stopped' if outcome == 'stopped' else 'error')
        assert storage.list_turns(sid) == []
        assert storage.get_save(sid)['state'] == before
        storage.retry_job(job, CONFIG)
        assert len(run(storage, job)) == 1
        assert storage.get_job(job)['status'] == 'saved'
