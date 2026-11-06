"""Linux QA runner. Use python -m devtools.live99.run --help."""
import argparse
from contextlib import contextmanager, closing
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from decimal import Decimal

import requests

from .budget import Budget, MODEL, INPUT, OUTPUT, action_ledger, reserve_action
from .browser import compare_prose, inspect_ui, open_save, plan, play, configure_context
from .recovery import (adopt, validate_revision, completed, retry_candidate,
                       probe_context, FAMILY_CONTEXT, digest)
from .evidence import delta, diagnostics, now, oracle, scenario_checks, snapshot, write
from .scenarios import CASES, QUOTAS

ROOT = Path(__file__).resolve().parents[2]


def revision():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def prepare(directory):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    # mkdir is exclusive: a normal save, partial init or existing run cannot be reset.
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    Budget(directory / 'budget.sqlite')
    repo = Repository(directory / 'game.sqlite')
    seeds = {case: load_fixture(repo, checkpoint) for case, (checkpoint, _) in CASES.items()}
    repo.save_settings('live99', {'game': {'provider': 'deepseek', 'model': MODEL, 'thinking': 'off'}})
    write(directory / 'manifest.json', dict(version=1, sha=revision(), created=now(), seeds=seeds))


@contextmanager
def server(directory, live):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        env = os.environ.copy()
        if not live:
            env.pop('DEEPSEEK_API_KEY', None)
        env.pop('OPENAI_LOG', None)
        proc = subprocess.Popen([sys.executable, '-m', 'devtools.live99.server', str(directory),
                                 str(listener.fileno()), 'live' if live else 'preflight'],
                                cwd=ROOT, env=env, pass_fds=(listener.fileno(),))
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(140):
            if proc.poll() is not None:
                raise RuntimeError('QA server failed preflight (check model/authentication)')
            try:
                if requests.get(url + '/api/health', timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(.25)
        else:
            raise TimeoutError('QA server startup timed out')
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def context_for(browser, mobile):
    return browser.new_context(viewport={'width': 393 if mobile else 1440, 'height': 852 if mobile else 940},
                               is_mobile=mobile, has_touch=mobile, service_workers='block')


def preflight(browser, base, directory, manifest):
    results = []
    destination = directory / 'preflight.json'
    if destination.exists():
        destination = directory / 'preflights' / (revision() + '.json')
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            archive = destination.with_name(revision() + '-' + digest(destination) + '.json')
            if not archive.exists():
                archive.write_bytes(destination.read_bytes())
    for case, seed in manifest['seeds'].items():
        for mobile in (False, True):
            ctx = context_for(browser, mobile)
            try:
                path = directory / 'game.sqlite'
                sid = seed['save']
                before = snapshot(path, sid)
                page = open_save(ctx, base, seed)
                failures = []
                page.on('pageerror', lambda err: failures.append(str(err)))
                inspect_ui(page, case)
                page.reload()
                page.locator('.current-game-entry button').wait_for()
                projected = page.request.get(f'{base}/api/saves/{sid}').json()
                after = snapshot(path, sid)
                oracle(before, after, projected, 'reload')
                scenario_checks(case, before, after, projected)
                if failures:
                    raise ValueError(failures)
                results.append({'case': case, 'mobile': mobile, 'ok': True})
            except Exception as error:
                results.append({'case': case, 'mobile': mobile, 'error': str(error)})
            finally:
                ctx.close()
                write(destination, results)
    return all(row.get('ok') for row in results)


def step(browser, base, directory, manifest, case, i, limit, retry=None, operation=None, lineage_index=0,
         attempt_folder=None):
    path, seed = directory / 'game.sqlite', manifest['seeds'][case]
    sid = seed['save']
    folder = directory / case / f'{i:03d}'
    if attempt_folder:
        folder = attempt_folder
    if retry:
        folder = folder / 'retries' / '001'
    before = snapshot(path, sid)
    if operation and operation.get('recovery_before_path'):
        with gzip.open(operation['recovery_before_path'], 'rt') as source:
            if before != json.load(source):
                raise ValueError('Save changed after reviewed unpaid recovery')
    kind, action = plan(case, i, before)
    if operation:
        kind, action = operation['kind'], operation.get('action', '')
    if retry:
        kind, action = retry[1]['kind'], retry[1]['action']
    with closing(sqlite3.connect(path)) as db:
        cursor = db.execute('SELECT coalesce(max(rowid),0) FROM game_jobs').fetchone()[0]
    if operation and 'job_cursor' in operation:
        cursor = operation['job_cursor']
    meta = dict(sha=revision(), source_sha=manifest['sha'], case=case, step=i, save=sid, kind=kind, action=action,
                started=now(), job_cursor=cursor, mobile=(list(CASES).index(case)+i)%2==1)
    meta['context_length'] = FAMILY_CONTEXT if case == 'family' else 32768
    if operation:
        meta['context_length'] = operation.get('context_length', meta['context_length'])
    if operation and operation.get('job_id'):
        meta['job_id'] = operation['job_id']
    if retry:
        meta.update(operation='retry-extraction', job_id=retry[2]['id'],
                    original_request_ids=retry[3], original_narrative_sha256=hashlib.sha256(
                        retry[2]['narrative'].encode()).hexdigest())
    reserve_action(directory, folder, meta, limit)
    folder.mkdir(parents=True)
    write(folder / 'intent.json', meta)
    write(folder / 'before.json.gz', before)
    ctx = context_for(browser, meta['mobile'])
    page = None
    errors = []
    choice_index = None
    try:
        page = open_save(ctx, base, seed)
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        configure_context(page, meta['context_length'])
        if kind == 'observed-choice' or kind == 'turn' and not operation and i >= 5 and i % 3:
            choices = page.locator('.choices button')
            if kind == 'observed-choice' and not choices.count():
                raise ValueError('No observed player choice; do not invent filler actions')
            if choices.count():
                choice_index = i % choices.count()
                choice = choices.nth(choice_index)
                # A generated player option adapts to the accepted scene.
                action = choice.inner_text()
                meta.update(kind='choice', action=action, choice_index=choice_index)
                write(folder / 'intent.json', meta)
                kind = 'choice'
        if retry:
            # Revalidate immediately before clicking the production Retry control.
            retry_candidate(directory, manifest, case, i, allow_pending=folder)
            play(page, base, sid, 'retry', action, job_id=retry[2]['id'])
        else:
            play(page, base, sid, kind, action, choice_index,
                 job_id=operation.get('job_id') if operation else None,
                 options=operation)
        after = snapshot(path, sid)
        projected = page.request.get(f'{base}/api/saves/{sid}').json()
        oracle(before, after, projected, 'turn' if kind == 'choice' or operation and operation.get('reuse_narrative') else kind)
        scenario_checks(case, before, after, projected)
        if kind == 'switch' and after['snapshot']['world_state']['camera']['controlled_actor_id'] != action:
            raise ValueError('Protagonist transition selected the wrong actor')
        if kind in ('variant','rollback'):
            # The immediately preceding regeneration used step 0 as its parent turn.
            filename = 'after.json.gz' if kind == 'variant' else 'before.json.gz'
            with gzip.open(directory / case / f'{lineage_index:03d}' / filename, 'rt') as source:
                target = json.load(source)['snapshot']
            if any(after['snapshot'].get(k) != target.get(k) for k in ('world_state','history_head')):
                raise ValueError('Restored variant / rollback differs from its recorded snapshot')
        jobs = diagnostics(path, sid, retry[1]['job_cursor'] if retry else cursor)
        attempts = [r for j in jobs for r in j['requests']]
        if operation and operation.get('reuse_narrative'):
            new = [r for r in attempts if r['id'] not in operation['original_request_ids']]
            if len(jobs) != 1 or jobs[0]['narrative'] != operation['reuse_narrative'] or not new or any(
                    r['stage'] not in ('extraction', 'extraction_repair') for r in new):
                raise ValueError('Recovery repeated paid Narrative or changed job identity')
        if retry:
            if len(jobs) != 1 or jobs[0]['id'] != retry[2]['id'] or jobs[0]['narrative'] != retry[2]['narrative']:
                raise ValueError('Retry changed job identity or completed Narrative')
            new = [r for r in attempts if r['id'] not in retry[3]]
            if not new or any(r['stage'] not in ('extraction', 'extraction_repair') for r in new):
                raise ValueError('Retry repeated a completed provider stage')
        if kind in ('start','turn','choice','regenerate') and not any(
            r['status'] == 'complete' and r['provider'] == 'deepseek' and r['model'] == MODEL for r in attempts
        ):
            raise ValueError('No completed DeepSeek request for this move')
        if kind in ('start','turn','choice','regenerate','variant') or operation and operation.get('reuse_narrative'):
            compare_prose(page, base, sid, seed['world'], after['last_turn']['assistant_text'])
        write(folder / 'ui.json.gz', dict(text=page.locator('body').inner_text(), projection=projected))
        page.reload()
        page.locator('.current-game-entry button').wait_for()
        oracle(after, snapshot(path, sid), page.request.get(f'{base}/api/saves/{sid}').json(), 'reload')
        if errors:
            raise ValueError(errors)
        meta['status'] = 'recorded'
    except Exception as error:
        meta.update(status='held-for-review', error=str(error))
        if page and not page.is_closed():
            page.screenshot(path=str(folder / 'failure.png'), timeout=5000)
            write(folder / 'failure-ui.json.gz', page.locator('body').inner_text())
    finally:
        ctx.close()
        final = snapshot(path, sid)
        write(folder / 'after.json.gz', final)
        write(folder / 'delta.json', delta(before, final))
        write(folder / 'diagnostics.json.gz', diagnostics(path, sid, retry[1]['job_cursor'] if retry else cursor))
        write(folder / 'result.json', dict(meta, finished=now()))
    return meta['status'] == 'recorded'


def recheck_saved(browser, base, directory, manifest, case, index):
    folder = directory / case / f'{index:03d}'
    result = read(folder / 'result.json')
    if result.get('error') != 'Wrong sequence or empty committed scene' or result['kind'] != 'start':
        raise ValueError('Only the diagnosed zero-based start false positive can be rechecked')
    seed = manifest['seeds'][case]
    with gzip.open(folder / 'before.json.gz', 'rt') as f:
        before = json.load(f)
    with gzip.open(folder / 'after.json.gz', 'rt') as f:
        after = json.load(f)
    if snapshot(directory / 'game.sqlite', seed['save']) != after:
        raise ValueError('Save changed since the held action')
    jobs = diagnostics(directory / 'game.sqlite', seed['save'], result['job_cursor'])
    if len(jobs) != 1 or jobs[0]['status'] != 'saved' or not any(
            r['status'] == 'complete' and r['model'] == MODEL for r in jobs[0]['requests']):
        raise ValueError('No unique saved live job to recheck')
    ctx = context_for(browser, result['mobile'])
    errors = []
    try:
        page = open_save(ctx, base, seed)
        page.on('pageerror', lambda e: errors.append(str(e)))
        projection = page.request.get(f'{base}/api/saves/{seed["save"]}').json()
        oracle(before, after, projection, 'start')
        scenario_checks(case, before, after, projection)
        compare_prose(page, base, seed['save'], seed['world'], after['last_turn']['assistant_text'])
        inspect_ui(page, case)
        page.reload()
        page.locator('.current-game-entry button').wait_for()
        oracle(after, snapshot(directory / 'game.sqlite', seed['save']),
               page.request.get(f'{base}/api/saves/{seed["save"]}').json(), 'reload')
        if errors:
            raise ValueError(errors)
        receipt = folder / 'verified.json'
        if not receipt.exists():
            write(receipt, dict(status='recorded', sha=revision(), at=now(), paid_calls=0,
                evidence={name: digest(folder / name) for name in
                          ('intent.json', 'result.json', 'before.json.gz', 'after.json.gz', 'diagnostics.json.gz')}))
    finally:
        ctx.close()


def recover_unsubmitted(directory, manifest, case, index):
    """Permit a new attempt only if storage proves no action or job was applied."""
    if case not in CASES or index is None or index < 0:
        raise ValueError('Choose --case and --step for recovery')
    folder = directory / case / f'{index:03d}'
    intent = read(folder / 'intent.json')
    sid = manifest['seeds'][case]['save']
    if intent['sha'] != revision() or intent['save'] != sid:
        raise ValueError('Checkpoint identity mismatch')
    result = folder / 'result.json'
    if result.exists() and read(result)['status'] == 'recorded':
        raise ValueError('Already completed')
    path = directory / 'game.sqlite'
    with gzip.open(folder / 'before.json.gz', 'rt') as source:
        original = json.load(source)
    if diagnostics(path, sid, intent['job_cursor']) or snapshot(path, sid) != original:
        raise ValueError('A job or a mutation exists. Preserve this attempt for manual review.')
    archive = directory / 'attempts' / case
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / (folder.name + '-' + str(time.time_ns()))
    action_ledger(directory)
    with sqlite3.connect(directory / 'budget.sqlite') as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE qa_actions SET path=? WHERE path=?',
                   (str(target.relative_to(directory)), str(folder.relative_to(directory))))
        folder.rename(target)


def read(path):
    return json.loads(path.read_text())


def report(directory, manifest):
    previous_report = directory / 'report.md'
    if previous_report.exists():
        archive = directory / 'reports' / (digest(previous_report) + '.md')
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            archive.write_bytes(previous_report.read_bytes())
    lines = ['# Live Gameplay QA #99', '', 'Original SHA ' + manifest['sha'],
             'Report checkout SHA ' + revision(), '',
             '| Case | Step | Action | Result | Evidence |', '|---|---:|---|---|---|']
    total = requests_count = unknown_cost = 0
    cost = Decimal(0)
    logged_jobs = {}
    for case in CASES:
        folders = sorted((directory / case).glob('[0-9]*'))
        for folder in [attempt for f in folders for attempt in [f, *sorted((f / 'retries').glob('[0-9]*'))]]:
            result = folder / 'result.json'
            r = read(result) if result.exists() else {'kind': '?', 'status':'interrupted'}
            relative = folder.relative_to(directory)
            status = r['status'] + (' (browser recheck passed)' if (folder / 'verified.json').exists() else '')
            lines.append(f"| {case} | {folder.name} | {r.get('operation', r['kind'])} | {status} | [{relative}]({relative}/intent.json) |")
            if (folder / 'diagnostics.json.gz').exists():
                with gzip.open(folder / 'diagnostics.json.gz', 'rt') as handle:
                    jobs = json.load(handle)
                    for job in jobs:
                        logged_jobs[job['id']] = job
    # Retry keeps the same job and old receipts; count each request exactly once.
    receipts = {r['id']: r for j in logged_jobs.values() for r in j['requests']}
    if manifest.get('stage') == 'B':
        receipts = {key: value for key, value in receipts.items() if key not in manifest['baseline_request_ids']}
    total = sum(j['status'] == 'saved' and any(r['status'] == 'complete' and r['provider'] == 'deepseek'
                for r in j['requests']) for j in logged_jobs.values())
    requests_count = len(receipts)
    unknown_cost = sum(r['cost_usd'] is None for r in receipts.values())
    cost = sum((Decimal(r['cost_usd']) for r in receipts.values() if r['cost_usd'] is not None), Decimal(0))
    with closing(sqlite3.connect((directory / 'budget.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        count, unresolved, inp, out = db.execute('SELECT count(*),count(CASE WHEN settled=0 THEN 1 END),'
            'coalesce(sum(input),0),coalesce(sum(output),0) FROM reservations').fetchone()
    lines.extend(['', f'Cumulative action reservations: {action_ledger(directory)}.',
                  f'Dispatches {count}, outstanding worst-case reservations {unresolved}.',
                  f'Conservative cost ceiling including reservations: ${(inp*INPUT+out*OUTPUT)/1e9:.6f}.',
                  f'Provider attempts logged by Runtime: {requests_count}, known estimated USD: {cost}, '
                  f'attempts without a cost receipt: {unknown_cost}.',
                  '', f'Saved jobs with a completed live request: {total}.',
                  'Fixture replay, navigation and deterministic transitions are excluded.',
                  '', 'Held and interrupted attempts require triage. Narrative quality and Knowledge disclosure '
                  'require human comparison of the scene, evidence, observers and History.'])
    (directory / 'report.md').write_text('\n'.join(lines) + '\n')


def run(args, directory, manifest):
    from playwright.sync_api import sync_playwright
    live = args.command in ('run', 'retry-extraction')
    validate_revision(directory, manifest, revision())
    stage_b = manifest.get('stage') == 'B'
    if stage_b:
        from .stage_b import validate
        validate(directory, manifest)
        if live and (args.stage != 'B' or not args.reviewed):
            raise ValueError('This authorization is only for reviewed Stage B, never Stage C')
    if live:
        pf = directory / 'preflights' / (revision() + '.json') if manifest['sha'] != revision() else directory / 'preflight.json'
        if not pf.exists() or len(read(pf)) != 2*len(CASES) or not all(r.get('ok') for r in read(pf)):
            raise SystemExit('Run a successful browser preflight first.')
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise SystemExit('DEEPSEEK_API_KEY required in server environment.')
        if args.stage != 'A' and not stage_b:
            previous = 'A' if args.stage == 'B' else 'B'
            if not (directory / f'{previous}.complete').exists() or not args.reviewed:
                raise SystemExit('Previous stage must complete and be reviewed first.')
            if args.stage == 'C' and not args.approved_full:
                raise SystemExit('Full stage requires separate explicit budget approval.')
    with server(directory, live) as base:
        # Server inherited its key. Remove it before spawning the Playwright driver/browser.
        os.environ.pop('DEEPSEEK_API_KEY', None)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH') or None)
            try:
                if args.command == 'recheck-saved':
                    recheck_saved(browser, base, directory, manifest, args.case, args.step)
                    report(directory, manifest)
                    return True
                if not live:
                    return preflight(browser, base, directory, manifest)
                if args.command == 'retry-extraction':
                    retry = retry_candidate(directory, manifest, args.case, args.step)
                    probe = probe_context(directory, retry[2])
                    destination = retry[0] / 'context-probe.json'
                    if not destination.exists():
                        write(destination, dict(probe, at=now(), sha=revision()))
                    result = step(browser, base, directory, manifest, args.case, args.step,
                                  sum(QUOTAS[args.stage]), retry=retry)
                    report(directory, manifest)
                    return result
                plans = read(directory / 'plan.json') if stage_b else None
                extension_manifest = manifest
                if stage_b:
                    from .stage_b import extend_crisis
                    extension_manifest = extend_crisis(directory, manifest, plans)
                caps = {case: len(plan) for case, plan in plans.items()} if plans else dict(zip(CASES, QUOTAS[args.stage]))
                limit = manifest['action_limit'] if stage_b else sum(QUOTAS[args.stage])
                held = set()
                for i in range(max(caps.values())):
                    for case, cap in caps.items():
                        if case in held or i >= cap or args.case and case != args.case:
                            continue
                        folder = directory / case / f'{i:03d}'
                        operation = plans[case][i] if plans else None
                        if stage_b:
                            from .stage_b import recovery_operation
                            operation, folder = recovery_operation(directory, case, i, operation)
                            with closing(sqlite3.connect(directory / 'budget.sqlite')) as db:
                                if db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
                                    report(directory, manifest)
                                    raise RuntimeError('Unknown paid outcome; Stage B stopped globally')
                        if folder.exists():
                            if not completed(folder):
                                held.add(case)
                        elif action_ledger(directory) >= limit:
                            held.add(case)
                        elif not step(browser, base, directory,
                                      extension_manifest if case == 'crisis' and i >= 15 else manifest, case, i, limit,
                                      operation=operation, attempt_folder=folder if stage_b else None):
                            held.add(case)
                        print(json.dumps(dict(case=case, step=i, held=case in held,
                                              cumulative_actions=action_ledger(directory))), flush=True)
                        report(directory, manifest)
                if not held and not args.case:
                    write(directory / f'{args.stage}.complete', {'finished':now()})
                status_file = directory / f'{args.stage}.status.json'
                if status_file.exists():
                    archive = directory / 'reports' / (digest(status_file) + '.json')
                    archive.parent.mkdir(exist_ok=True)
                    if not archive.exists():
                        archive.write_bytes(status_file.read_bytes())
                write(status_file, dict(finished=now(), sha=revision(),
                    held=sorted(held), actions=action_ledger(directory), complete=not held and not args.case))
                return not held
            finally:
                browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare','prepare-stage-b','prepare-crisis-extension','review-stage-b','preflight','run','report','recover-unsubmitted',
                                          'adopt', 'recheck-saved', 'retry-extraction'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stage', choices=list(QUOTAS), default='A')
    parser.add_argument('--case', choices=list(CASES))
    parser.add_argument('--step', type=int)
    parser.add_argument('--reviewed', action='store_true')
    parser.add_argument('--approved-full', action='store_true')
    parser.add_argument('--parent', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT):
        parser.error('Run directory must be outside the repository.')
    os.umask(0o077)
    if args.command == 'prepare':
        prepare(directory)
        return
    if args.command == 'prepare-stage-b':
        if not args.reviewed or not args.parent:
            parser.error('Stage B requires the reviewed historical parent')
        from .stage_b import prepare as prepare_b
        parent = args.parent.resolve()
        with ((parent / 'budget.sqlite').resolve().parent / 'run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            master = subprocess.check_output(['git', 'rev-parse', 'origin/master'], cwd=ROOT, text=True).strip()
            subprocess.run(['git', 'merge-base', '--is-ancestor', master, 'HEAD'], cwd=ROOT, check=True)
            prepare_b(parent, directory, revision(), master)
        return
    manifest = read(directory / 'manifest.json')
    lock_path = (directory / 'budget.sqlite').resolve().parent / 'run.lock' if manifest.get('stage') == 'B' else directory / 'run.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'adopt':
            if not args.reviewed:
                parser.error('QA-only adoption requires --reviewed')
            adopt(directory, manifest, revision())
        elif args.command == 'report':
            report(directory, manifest)
        elif args.command == 'prepare-crisis-extension':
            if manifest.get('stage') != 'B' or not args.reviewed:
                parser.error('Choose reviewed Stage B')
            validate_revision(directory, manifest, revision())
            from .stage_b import prepare_crisis
            prepare_crisis(directory, manifest)
        elif args.command == 'review-stage-b':
            if manifest.get('stage') != 'B' or not args.reviewed or args.case is None or args.step is None:
                parser.error('Choose reviewed Stage B --case and --step')
            validate_revision(directory, manifest, revision())
            from .stage_b import review_recovery
            review_recovery(directory, manifest, args.case, args.step)
        elif args.command == 'recover-unsubmitted':
            recover_unsubmitted(directory, manifest, args.case, args.step)
        elif args.command in ('recheck-saved', 'retry-extraction') and (args.case is None or args.step is None):
            parser.error('Choose --case and --step')
        elif not run(args, directory, manifest):
            raise SystemExit('See preflight.json or report.md; incomplete cases require review.')


if __name__ == '__main__':
    main()
