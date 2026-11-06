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
from .recovery import completed, digest, qa_only, rows, read as evidence_read, probe_context
from .run import ROOT, preflight, read, revision, server, step

FIX = '57c173d8ece34f29cb3af37e6b28beb208e9bf63'
CAP = 'issue99-post204-20261106'
QUESTION = 'У Веры я спрашиваю только о библиотеке. Личное письмо Олега не обсуждаю.'
OPERATIONS = [
    ('knowledge', dict(kind='retry', action=QUESTION)),
    ('knowledge', dict(kind='turn', action='Вера, расскажи подробнее о фонде старых карт в библиотеке.')),
    ('knowledge', dict(kind='regenerate')),
    ('knowledge', dict(kind='variant')),
    ('knowledge', dict(kind='rollback')),
    ('phone', dict(kind='phone-retry')),
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


def review_unsubmitted(directory, manifest):
    """One explicit review of UI failures, proven to have dispatched no paid work."""
    validate(directory, manifest)
    receipt = directory / 'unsubmitted-review.json'
    if receipt.exists():
        raise ValueError('UI recovery was already reviewed')
    parent = Path(manifest['parent'])
    if rows(parent) != manifest['baseline_reservations']:
        raise ValueError('Paid work exists; UI-only recovery is unsafe')
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        with closing(sqlite3.connect(parent / 'game.sqlite')) as old:
            for table in ('game_jobs', 'llm_requests'):
                if db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() != old.execute(
                        f'SELECT * FROM {table} ORDER BY rowid').fetchall():
                    raise ValueError('A job or request changed')
    evidence = {}
    for case in ('knowledge', 'phone'):
        folder = directory / case / '000'
        result = read(folder / 'result.json')
        before = evidence_read(folder / 'before.json.gz')
        if result['status'] != 'held-for-review' or 'Locator.click: Timeout' not in result.get('error', ''):
            raise ValueError('Only the inspected unsubmitted UI failure can be recovered')
        if before != evidence_read(folder / 'after.json.gz') or before != snapshot(
                directory / 'game.sqlite', manifest['seeds'][case]['save']):
            raise ValueError('Save changed since unsubmitted attempt')
        evidence.update({str(p.relative_to(directory)): digest(p) for p in folder.iterdir() if p.is_file()})
    write(receipt, dict(sha=revision(), reviewed=now(), evidence=evidence,
        action_limit=manifest['action_limit'] + 2, reason='Two proven unsubmitted UI attempts remain charged'))


def review_context(directory, manifest):
    validate(directory, manifest)
    target = directory / 'knowledge-context-review.json'
    if target.exists():
        raise ValueError('Knowledge context recovery already reviewed')
    folder = directory / 'knowledge/000/retries/001'
    result = read(folder / 'result.json')
    if result['status'] != 'held-for-review' or 'Контекст v3 не помещается' not in result.get('error', ''):
        raise ValueError('Only the measured context construction failure can be recovered')
    if evidence_read(folder / 'before.json.gz') != snapshot(directory / 'game.sqlite', result['save']):
        raise ValueError('Save changed after context failure')
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        db.row_factory = sqlite3.Row
        job = dict(db.execute('SELECT * FROM game_jobs WHERE id=?', (result['job_id'],)).fetchone())
        requests = [r[0] for r in db.execute('SELECT id FROM llm_requests WHERE job_id=?', (job['id'],))]
    if any(r not in manifest['baseline_request_ids'] for r in requests) or not job['narrative_complete']:
        raise ValueError('This retest has already dispatched Knowledge work or lost Narrative')
    probe = probe_context(directory, job, 40960)
    if probe['input_estimate'] >= probe['hard_input_limit']:
        raise ValueError('Measured context still does not fit')
    write(target, dict(sha=revision(), reviewed=now(), probe=probe,
        evidence={str(p.relative_to(directory)): digest(p) for p in folder.iterdir() if p.is_file()},
        action_limit=read(directory / 'unsubmitted-review.json')['action_limit'] + 1,
        reason='No new Knowledge dispatch; completed original Narrative retained, measured 40960 context'))


def run(directory, manifest, live):
    from playwright.sync_api import sync_playwright
    validate(directory, manifest)
    if live and not os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('DEEPSEEK_API_KEY unavailable')
    if live:
        checks = read(directory / 'preflight.json')
        if len(checks) != 2 * len(manifest['seeds']) or not all(r.get('ok') for r in checks):
            raise ValueError('Complete the browser preflight first')
    review = directory / 'unsubmitted-review.json'
    receipt = read(review) if review.exists() else None
    if receipt and any(digest(directory / name) != value for name, value in receipt['evidence'].items()):
        raise ValueError('Reviewed UI failure evidence changed')
    context_review = directory / 'knowledge-context-review.json'
    context_receipt = read(context_review) if context_review.exists() else None
    if context_receipt and any(digest(directory / name) != value
                               for name, value in context_receipt['evidence'].items()):
        raise ValueError('Reviewed context failure evidence changed')
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
                    if receipt and i == 0:
                        folder = folder / 'retries/001'
                        if context_receipt and case == 'knowledge':
                            folder = folder.with_name('002')
                    if folder.exists():
                        if not completed(folder):
                            held.add(case)
                        continue
                    operation = dict(operation)
                    if context_receipt and case == 'knowledge':
                        operation['context_length'] = context_receipt['probe']['context_length']
                    if operation['kind'] in ('retry', 'phone-retry'):
                        # Explicit single Retry of the original rejected decision. Production
                        # reuses the accepted read frame; no outgoing message is sent twice.
                        parent = Path(manifest['parent'])
                        old = read(parent / case / '001/result.json')
                        with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
                            jobs = db.execute('SELECT id,status FROM game_jobs WHERE save_id=? AND rowid>?',
                                              (manifest['seeds'][case]['save'], old['job_cursor'])).fetchall()
                        if len(jobs) != 1 or jobs[0][1] != 'error':
                            raise ValueError('Retry no longer identifies the original failed job')
                        operation.update(job_id=jobs[0][0], job_cursor=old['job_cursor'])
                    if not step(browser, base, directory, manifest, case, i,
                                context_receipt['action_limit'] if context_receipt else
                                receipt['action_limit'] if receipt else manifest['action_limit'],
                                operation=operation, lineage_index=1, attempt_folder=folder):
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
    parser.add_argument('command', choices=('prepare', 'preflight', 'run', 'audit', 'review-unsubmitted', 'review-context'))
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
        elif args.command == 'review-unsubmitted':
            review_unsubmitted(directory, read(directory / 'manifest.json'))
        elif args.command == 'review-context':
            review_context(directory, read(directory / 'manifest.json'))
        elif not run(directory, read(directory / 'manifest.json'), args.command == 'run'):
            raise SystemExit('Retest held; inspect evidence. No automatic retries.')


if __name__ == '__main__':
    main()
