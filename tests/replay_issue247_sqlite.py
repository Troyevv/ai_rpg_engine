"""Offline replay on copies of the original #245 SQLite; no provider calls.

Run from the repository root. Test-authored repair controls are separate from
archived DeepSeek responses. This verifies persistence, not semantic Live QA.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.repositories.preparation import Repository
from devtools.live99.evidence import snapshot
from devtools.live99.retest import backup
from test_integrated_repair247 import archived, corrected, execute, history


CASES = [('family', '001'), ('knowledge', '002'), ('phone', '001'),
         ('crisis', '001'), ('social', '001'), ('campaign', '000')]


def replay(source, output, case, step, mode):
    data = archived(case)
    with gzip.open(source / case / step / 'before.json.gz', 'rt') as file:
        checkpoint = json.load(file)
    sid = json.loads((source / case / step / 'intent.json').read_text())['save']
    path = output / f'{case}-{mode}.sqlite'
    backup(source / 'game.sqlite', path)
    repo = Repository(path)
    old = repo.get_job(data['job_id'])
    if old['status'] in ('error', 'stopped'):
        repo.abandon_job(sid, old['id'], repo.get_save(sid)['revision'], old['attempt_epoch'])
    if repo.get_snapshot(sid)['world_state'] != data['before']:
        repo.rollback_last(sid, repo.get_save(sid)['revision'])
    before, old_history = snapshot(path, sid), history(repo, sid)
    assert before['snapshot']['world_state'] == data['before'], (case, 'state')
    assert before['snapshot']['history_head'] == checkpoint['snapshot']['history_head'], (case, 'history')

    original = data['responses'][-1 if case == 'campaign' else 0]['payload']
    replies = [original, corrected(data) if mode == 'control' else original]
    with patch('llm.chat_stream', side_effect=AssertionError('No external calls')):
        job, calls = execute(repo, sid, data, replies)
    after = snapshot(path, sid)
    refused = case == 'crisis' or (mode == 'repeat' and case in ('family', 'knowledge', 'phone'))
    assert job['status'] == ('error' if refused else 'saved'), (case, mode, job['error'])
    assert all(after['variants'].get(k) == v for k, v in before['variants'].items()), (case, 'siblings')
    if refused:
        assert before['snapshot'] == after['snapshot']
        assert before['history'] == after['history']
    gains = len(history(repo, sid)['knowledge_acquisitions']) - len(old_history['knowledge_acquisitions'])
    if case == 'knowledge' and mode == 'control':
        assert gains == 4
    assert Repository(path).get_snapshot(sid) == after['snapshot']
    with repo.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    return dict(case=case, mode=mode, status=job['status'], scripted_calls=len(calls),
                knowledge_acquisitions=gains, paid_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Extracted original #245 directory')
    parser.add_argument('output', type=Path, help='New directory for 12 disposable SQLite copies')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original_hash = hashlib.sha256((source / 'game.sqlite').read_bytes()).hexdigest()
    results = []
    for case, step in CASES:
        for mode in ('repeat', 'control'):
            results.append(replay(source, output, case, step, mode))
            print(json.dumps(results[-1]), flush=True)
            (output / 'summary.json').write_text(json.dumps(results, indent=2))
    assert hashlib.sha256((source / 'game.sqlite').read_bytes()).hexdigest() == original_hash


if __name__ == '__main__':
    main()
