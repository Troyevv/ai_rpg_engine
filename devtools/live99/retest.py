"""Explicit post-fix Knowledge/Phone retest; never run B/C or retry a held attempt."""
import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess

from .budget import Budget, action_ledger
from .evidence import now, snapshot, write
from .recovery import completed, digest, qa_only, rows
from .run import ROOT, preflight, read, revision, server, step

FIX = '57c173d8ece34f29cb3af37e6b28beb208e9bf63'
CAP = 'issue99-post204-20261106'
QUESTION = 'У Веры я спрашиваю только о библиотеке. Личное письмо Олега не обсуждаю.'
OPERATIONS = [
    ('knowledge', dict(kind='turn', action=QUESTION)),
    ('knowledge', dict(kind='turn', action='Вера, расскажи подробнее о фонде старых карт в библиотеке.')),
    ('knowledge', dict(kind='regenerate')),
    ('knowledge', dict(kind='variant')),
    ('knowledge', dict(kind='rollback')),
    ('phone', dict(kind='retry')),
]


def backup(source, destination):
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)


def prepare(parent, directory):
    qa_only(revision(), revision())
    subprocess.run(['git', 'merge-base', '--is-ancestor', FIX, 'HEAD'], cwd=ROOT, check=True)
    manifest = read(parent / 'manifest.json')
    ledger = parent / 'budget.sqlite'
    if not ledger.is_file() or ledger.is_symlink():
        raise ValueError('Choose the original run with its original ledger')
    with closing(sqlite3.connect(ledger)) as db:
        if db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
            raise ValueError('Resolve unknown paid outcomes before creating a retest')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    # SQLite backup is consistent, including WAL. No restore over historical saves.
    backup(parent / 'game.sqlite', directory / 'game.sqlite')
    backup(ledger, directory / 'budget-before.sqlite')
    evidence = {str(p.relative_to(parent)): digest(p) for p in parent.rglob('*')
                if p.is_file() and p.name not in ('budget.sqlite', 'run.lock')
                and not p.name.startswith('budget.sqlite-')}
    from backend.repositories.preparation import Repository
    repo = Repository(directory / 'game.sqlite')
    for seed in manifest['seeds'].values():
        sid = seed['save']
        if snapshot(parent / 'game.sqlite', sid) != snapshot(directory / 'game.sqlite', sid):
            raise ValueError('Runtime load changed a checkpoint')
        if repo.get_snapshot(sid) != snapshot(parent / 'game.sqlite', sid)['snapshot']:
            raise ValueError('Runtime snapshot is incompatible')
    baseline = rows(parent)
    actions = action_ledger(parent)
    (directory / 'budget.sqlite').symlink_to(ledger)
    ceiling = Budget(ledger).cap_additional(CAP, 500_000_000)
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        request_ids = [r[0] for r in db.execute('SELECT id FROM llm_requests')]
    write(directory / 'manifest.json', dict(version=2, sha=revision(), created=now(),
        seeds=manifest['seeds'], parent=str(parent), parent_sha=manifest['sha'],
        master_sha=FIX, parent_evidence=evidence, baseline_reservations=baseline,
        baseline_actions=actions, action_limit=actions + len(OPERATIONS),
        baseline_request_ids=request_ids, additional_usd='0.50', ceiling_nusd=ceiling,
        reason='Explicit user-authorized retest after #204; compatible snapshot copy, shared ledger'))


def validate(directory, manifest):
    qa_only(manifest['sha'], revision())
    parent = Path(manifest['parent'])
    if (directory / 'budget.sqlite').resolve() != parent / 'budget.sqlite':
        raise ValueError('Retest lost the shared original spending ledger')
    for name, expected in manifest['parent_evidence'].items():
        if digest(parent / name) != expected:
            raise ValueError('Original evidence changed: ' + name)
    current = rows(parent)
    if current[:len(manifest['baseline_reservations'])] != manifest['baseline_reservations']:
        raise ValueError('Original spending history changed')
    if action_ledger(directory) < manifest['baseline_actions']:
        raise ValueError('Original action history lost')
    with closing(sqlite3.connect(directory / 'budget.sqlite')) as db:
        cap = db.execute('SELECT ceiling FROM spending_caps WHERE name=?', (CAP,)).fetchone()
        if cap != (manifest['ceiling_nusd'],):
            raise ValueError('Additional spending cap changed')


def run(directory, manifest, live):
    from playwright.sync_api import sync_playwright
    validate(directory, manifest)
    if live and not os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('DEEPSEEK_API_KEY unavailable')
    if live and not all(r.get('ok') for r in read(directory / 'preflight.json')):
        raise ValueError('Complete the browser preflight first')
    with server(directory, live) as base:
        os.environ.pop('DEEPSEEK_API_KEY', None)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH') or None)
            try:
                if not live:
                    return preflight(browser, base, directory, manifest)
                held, indices = set(), {}
                for case, operation in OPERATIONS:
                    i = indices.get(case, 0)
                    indices[case] = i + 1
                    if case in held:
                        continue
                    folder = directory / case / f'{i:03d}'
                    if folder.exists():
                        if not completed(folder):
                            held.add(case)
                        continue
                    operation = dict(operation)
                    if case == 'phone':
                        # Explicit single Retry of the original rejected decision. Production
                        # reuses the accepted read frame; no outgoing message is sent twice.
                        parent = Path(manifest['parent'])
                        old = read(parent / 'phone/001/result.json')
                        with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
                            jobs = db.execute('SELECT id,status FROM game_jobs WHERE save_id=? AND rowid>?',
                                              (manifest['seeds'][case]['save'], old['job_cursor'])).fetchall()
                        if len(jobs) != 1 or jobs[0][1] != 'error':
                            raise ValueError('Phone Retry no longer identifies the original failed job')
                        operation.update(job_id=jobs[0][0], job_cursor=old['job_cursor'])
                    if not step(browser, base, directory, manifest, case, i, manifest['action_limit'],
                                operation=operation, lineage_index=1):
                        held.add(case)
                target = directory / 'retest.status.json'
                if target.exists():
                    target = directory / ('retest.status-' + str(__import__('time').time_ns()) + '.json')
                write(target, dict(sha=revision(), finished=now(), held=sorted(held),
                                   cumulative_actions=action_ledger(directory), complete=not held))
                validate(directory, manifest)
                return not held
            finally:
                browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'preflight', 'run', 'audit'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--parent', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT):
        parser.error('Keep evidence outside Git')
    parent = args.parent.resolve() if args.command == 'prepare' else Path(read(directory / 'manifest.json')['parent'])
    os.umask(0o077)
    # Share the original run lock too; old and new runners cannot play concurrently.
    with (parent / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'prepare':
            prepare(parent, directory)
        elif args.command == 'audit':
            validate(directory, read(directory / 'manifest.json'))
        elif not run(directory, read(directory / 'manifest.json'), args.command == 'run'):
            raise SystemExit('Retest held; inspect evidence. No automatic retries.')


if __name__ == '__main__':
    main()
