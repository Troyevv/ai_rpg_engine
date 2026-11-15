"""Offline smoke replay through production FastAPI; no provider/network calls.

Original first Extraction and original failed repair are preserved verbatim.
The successful repair and next-turn IO are explicitly authored test controls.
Neither the source save nor the paid ledger is modified.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import engine
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from .evidence import snapshot, write


def backup(source, target):
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)


def wait(client, jid):
    for _ in range(300):
        response = client.get('/api/jobs/' + jid); response.raise_for_status()
        job = response.json()
        if job['status'] not in ('generating', 'extracting', 'validating'):
            return job
        time.sleep(.05)
    raise TimeoutError('Offline job did not terminate')


def run(source, output, mode):
    output.mkdir(parents=True, exist_ok=False)
    db = output / 'game.sqlite'; backup(source / 'smoke-final.sqlite', db)
    repo = Repository(db); before = snapshot(db, 1); write(output / 'before.json.gz', before)
    inputs = json.loads((source / 'input.json').read_text())
    original = (source / 'request-4-extraction.txt').read_text()
    old_repair = (source / 'request-5-extraction_repair.txt').read_text()
    narrative = (source / 'narrative.txt').read_text()
    jid = json.loads((source / 'submitted.json').read_text())['id']
    calls = []; phase = 'retry'; foreground_calls = 0; background = False

    def stream(**kwargs):
        nonlocal foreground_calls, background
        messages = kwargs['messages']; calls.append(deepcopy(messages))
        write(output / f'call-{len(calls)}.json', messages)
        if messages[0]['content'].startswith('Select at most ONE optional grounded autonomous remote action.'):
            yield '{"action":null}'; return
        if messages[0]['content'].startswith('Постоянные правила\nТы рассказчик сцены наблюдения.'):
            background = True
            yield 'Вечер проходит спокойно; новых событий не происходит.'; return
        if background:
            assert kwargs.get('response_format')
            background = False
            yield '{"scene":{},"scene_steps":[]}'; return
        if phase == 'next':
            if not kwargs.get('response_format'):
                current = [json.loads(m['content'].split('\n', 1)[1]) for m in messages
                           if m['content'].startswith('Текущее состояние')]
                assert current and current[0]['camera']['location_id'] == 'loc_home_galina'
                yield 'Алексей стучит в дверь квартиры матери и ждёт.'; return
            yield json.dumps(dict(scene=dict(elapsed_minutes=1), scene_steps=[dict(
                id='knock', kind='interaction', actor_id='char_alexey', target_ids=[],
                outcome='completed', text='Алексей стучит в дверь и ждёт.',
                input_source=dict(quote='Стучу в дверь и жду.', meaning='preserved'))]), ensure_ascii=False)
            return
        assert kwargs.get('response_format'), 'Recovery must never regenerate Narrative'
        foreground_calls += 1
        if foreground_calls == 1:
            yield original; return
        assert foreground_calls == 2, 'Only one automatic repair allowed'
        feedback = next(json.loads(line) for m in messages for line in m['content'].splitlines()
                        if line.startswith('{"repair_mode"'))
        assert {d['code'] for d in feedback['diagnostics']} == {
            'movement_endpoint_invalid', 'camera_invalid', 'movement_agency'}
        write(output / 'full-feedback.json', feedback)
        if mode == 'original':
            assert json.loads(old_repair)['candidate_hash'] == feedback['candidate_hash']
            yield old_repair; return
        steps = json.loads(old_repair)['replacements']
        arrival = deepcopy(steps[5])
        arrival['input_source'] = dict(quote='иду домой к маме на Лесную.', meaning='preserved')
        control = dict(candidate_hash=feedback['candidate_hash'], replacements=[steps[3], arrival],
            sections={'scene': {'observer_location_id': None}},
            reason='AUTHORED OFFLINE CONTROL: departure endpoint, actor camera, selected arrival source.')
        write(output / 'authored-repair-control.json', control)
        yield json.dumps(control, ensure_ascii=False)

    # Even an accidental new transport call must fail rather than spend money.
    with patch('engine.chat_stream', side_effect=stream), patch('llm.chat_stream', side_effect=stream), \
         patch('llm.OpenAI', side_effect=AssertionError('Offline replay forbids provider IO')), \
         TestClient(create_app(db)) as client:
        job = client.get('/api/jobs/' + jid).json()
        response = client.post('/api/jobs/' + jid + '/retry', json=dict(
            config=inputs['config'], api_key='offline-test-only', revision=before['revision'],
            attempt_epoch=job['attempt_epoch']))
        response.raise_for_status(); job = wait(client, jid); write(output / 'result.json', job)
        after = snapshot(db, 1); write(output / 'after.json.gz', after)
        assert job['narrative'] == narrative and foreground_calls == 2
        if mode == 'original':
            assert job['status'] == 'error' and before == after
        else:
            assert job['status'] == 'saved', job['error']
            world = after['snapshot']['world_state']
            assert world['characters']['char_alexey']['location_id'] == 'loc_home_galina'
            assert world['camera']['location_id'] == 'loc_home_galina'
            assert world['camera']['present_character_ids'] == ['char_alexey']
            assert world['knowledge'] == before['snapshot']['world_state']['knowledge']
            for cid in ('char_viktor', 'char_tamara', 'char_galina'):
                assert world['characters'][cid]['location_id'] == before['snapshot']['world_state']['characters'][cid]['location_id']
            assert all(after['variants'][k] == v for k,v in before['variants'].items())
            saved = json.loads(after['last_turn']['changes_json'])['raw_turn_result']['semantic_candidate']
            expected = json.loads(original); expected['scene']['observer_location_id'] = None
            expected['scene_steps'][3]['endpoint'] = None
            expected['scene_steps'][5]['input_source'] = dict(quote='иду домой к маме на Лесную.', meaning='preserved')
            assert saved == expected
    # A fresh production app, with ordinary startup recovery, reloads the commit.
    with patch('engine.chat_stream', side_effect=stream), patch('llm.chat_stream', side_effect=stream), \
         patch('llm.OpenAI', side_effect=AssertionError('Offline replay forbids provider IO')), \
         TestClient(create_app(db)) as client:
        projected = client.get('/api/saves/1'); projected.raise_for_status()
        assert snapshot(db, 1) == after
        if mode != 'original':
            phase = 'next'
            response = client.post('/api/saves/1/turns', json=dict(kind='turn',text='Стучу в дверь и жду.',
                config=inputs['config'],api_key='offline-test-only',revision=after['revision']))
            response.raise_for_status(); following = wait(client, response.json()['id'])
            write(output / 'next-result.json', following)
            assert following['status'] == 'saved', following['error']
            assert snapshot(db,1)['snapshot']['world_state']['camera']['location_id']=='loc_home_galina'
    requests = repo.request_log(job_id=jid)
    write(output / 'request-log.json.gz', requests)
    write(output / 'summary.json', dict(mode=mode,provider_calls=0,mocked_dispatches=len(calls),
        original_narrative_unchanged=True,reload=True,job_status=job['status'],
        next_turn='saved at loc_home_galina' if mode!='original' else 'not run',
        note='Authored successful control is not a real DeepSeek result.'))
    print(mode, job['status'], 'mocked dispatches', len(calls))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for mode in ('original','corrected_control'):
        run(args.source.resolve(),args.output.resolve()/mode,mode)


if __name__=='__main__':main()
