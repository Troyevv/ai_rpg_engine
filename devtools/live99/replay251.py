"""Zero-network production replay of the user-provided Berezovsk campaign.

Usage: python -m devtools.live99.replay251 ARCHIVE_ROOT OUTPUT_DIRECTORY
The archive must already be concatenated/verified. Originals are opened read-only;
only provider IO is replaced. Missing historical responses are reported, never
invented. Each case runs on an independent SQLite backup of its checkpoint.
"""
import argparse
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history


def replay(root, output, case):
    folder = root/'turns'/case
    original = folder/'checkpoint.sqlite'
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    target = output/(case+'.sqlite')
    if target.exists():
        raise ValueError(f'Output already exists: {target}')
    with sqlite3.connect(original.resolve().as_uri()+'?mode=ro', uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
    archived = json.loads((folder/'job-record.json').read_text())
    requests = json.loads(gzip.decompress((folder/'requests.json.gz').read_bytes()))
    replies = iter(r for r in requests if r['stage'] in ('extraction', 'extraction_repair'))
    repo = Repository(target)
    sid = archived['save_id']
    # Clear only unapplied jobs on this isolated copy through normal lifecycle.
    with repo.connect() as db:
        pending = [dict(r) for r in db.execute("SELECT * FROM game_jobs WHERE save_id=? AND status IN ('error','stopped')", (sid,))]
    for job in pending:
        repo.abandon_job(sid, job['id'], repo.get_save(sid)['revision'], job['attempt_epoch'])
    before = repo.get_snapshot(sid)
    if before['world_state'] != json.loads(archived['before_json'])['world_state']:
        # Successful original checkpoints are after commit. Restore their parent
        # with the normal branch-aware rollback on the COPY, not a state rewrite.
        repo.rollback_last(sid)
        before = repo.get_snapshot(sid)
    assert before['world_state'] == json.loads(archived['before_json'])['world_state']
    with repo.connect() as db:
        old_history = read_history(db, before['history_head'])[0]
    turns = repo.list_turns(sid)
    config = {k:v for k,v in json.loads(archived['config_json']).items() if not k.startswith('_')
              and k not in ('expected_revision','target_turn_id','rollback_following')}
    config.update(provider='local', model='offline-recorded-251')
    jid = repo.begin_job(sid, archived['user_text'], 'turn', config)
    captured, consumed = [], []
    def stream(**kw):
        captured.append(kw['messages'])
        if kw.get('response_format'):
            record = next(replies, None)
            if record is None:
                raise RuntimeError('Offline replay: no recorded response for this additional dispatch')
            consumed.append(record['id'])
            yield record['response_text']
        elif len(captured) == 1:
            yield archived['narrative']
        else:
            raise RuntimeError('Offline replay: original rejected scene has no recorded background response')
    with patch('engine.find_loaded_model', return_value={'config':{}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    job = repo.get_job(jid)
    fresh = Repository(target)
    after = fresh.get_snapshot(sid)
    with fresh.connect() as db:
        new_history = read_history(db, after['history_head'])[0]
        integrity = db.execute('pragma integrity_check').fetchall()
    if job['status'] == 'saved':
        assert fresh.list_turns(sid)[-1]['assistant_text'] == archived['narrative']
        saved_state = after['world_state']
        fresh.rollback_last(sid)
        assert fresh.get_snapshot(sid) == before
    else:
        saved_state = None
        assert after == before and new_history == old_history and fresh.list_turns(sid) == turns
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    if case in ('016', '017'):
        messages = captured[0]  # Actual engine -> provider boundary, not instructions.
        current = next(json.loads(m['content'].split('\n', 1)[1]) for m in messages
                       if m['content'].startswith('Текущее состояние / GM-only\n'))
        assert current['current_time']['date'] == '2026-04-16'
        assert current['last_time_advance']['start']['date'] == '2026-04-11'
        assert current['past_situations']['observed_no_later_than']['date'] == '2026-04-11'
        assert not current['camera'].get('situation')
        dated = [m for m in messages if m['content'].startswith('Прошлая сцена / canonical time')]
        assert len(dated) == 6 and any('2026-04-11' in m['content'] for m in dated)
    (output/(case+'-messages.json')).write_text(json.dumps(captured, ensure_ascii=False))
    return dict(case=case, status=job['status'], error=job['error'],
        diagnostics=json.loads(job['repair_diagnostics_json']), warnings=json.loads(job['warnings_json']),
        consumed_request_ids=consumed, dispatches=len(captured),
        retry_allowed=repo.public_job(job)['retry_allowed'], integrity=[list(r) for r in integrity],
        original_sha256=digest, original_unchanged=True, atomic_or_rollback=True,
        saved_world_time=saved_state['meta']['world_time'] if saved_state else None,
        saved_event_delta=len(new_history['events'])-len(old_history['events']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.archive_root/'SHA256SUMS.json').read_text())
    for name, expected in manifest.items():
        assert hashlib.sha256((args.archive_root/name).read_bytes()).hexdigest() == expected, name
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in ('001','002','005','006','008','009','016','017','020','024','025r'):
        row = replay(args.archive_root, args.output, case)
        rows.append(row)
        print(case, row['status'], [d['code'] for d in row['diagnostics']], flush=True)
        (args.output/'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
