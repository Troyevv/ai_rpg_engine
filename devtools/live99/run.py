"""Linux QA runner. Use python -m devtools.live99.run --help."""
import argparse
from contextlib import contextmanager, closing
import fcntl
import gzip
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
from playwright.sync_api import sync_playwright

from .budget import Budget, MODEL, INPUT, OUTPUT
from .browser import compare_prose, inspect_ui, open_save, plan, play
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
                write(directory / 'preflight.json', results)
    return all(row.get('ok') for row in results)


def step(browser, base, directory, manifest, case, i):
    path, seed = directory / 'game.sqlite', manifest['seeds'][case]
    sid = seed['save']
    folder = directory / case / f'{i:03d}'
    folder.mkdir(parents=True)
    before = snapshot(path, sid)
    kind, action = plan(case, i, before)
    with closing(sqlite3.connect(path)) as db:
        cursor = db.execute('SELECT coalesce(max(rowid),0) FROM game_jobs').fetchone()[0]
    meta = dict(sha=manifest['sha'], case=case, step=i, save=sid, kind=kind, action=action,
                started=now(), job_cursor=cursor, mobile=(list(CASES).index(case)+i)%2==1)
    write(folder / 'intent.json', meta)
    write(folder / 'before.json.gz', before)
    ctx = context_for(browser, meta['mobile'])
    page = None
    errors = []
    choice_index = None
    try:
        page = open_save(ctx, base, seed)
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        if kind == 'turn' and i >= 5 and i % 3:
            choices = page.locator('.choices button')
            if choices.count():
                choice_index = i % choices.count()
                choice = choices.nth(choice_index)
                # A generated player option adapts to the accepted scene.
                action = choice.inner_text()
                meta.update(kind='choice', action=action, choice_index=choice_index)
                write(folder / 'intent.json', meta)
                kind = 'choice'
        play(page, base, sid, kind, action, choice_index)
        after = snapshot(path, sid)
        projected = page.request.get(f'{base}/api/saves/{sid}').json()
        oracle(before, after, projected, 'turn' if kind == 'choice' else kind)
        scenario_checks(case, before, after, projected)
        if kind == 'switch' and after['snapshot']['world_state']['camera']['controlled_actor_id'] != action:
            raise ValueError('Protagonist transition selected the wrong actor')
        if kind in ('variant','rollback'):
            # The immediately preceding regeneration used step 0 as its parent turn.
            filename = 'after.json.gz' if kind == 'variant' else 'before.json.gz'
            with gzip.open(directory / case / '000' / filename, 'rt') as source:
                target = json.load(source)['snapshot']
            if any(after['snapshot'].get(k) != target.get(k) for k in ('world_state','history_head')):
                raise ValueError('Restored variant / rollback differs from its recorded snapshot')
        jobs = diagnostics(path, sid, cursor)
        attempts = [r for j in jobs for r in j['requests']]
        if kind in ('start','turn','choice','regenerate') and not any(
            r['status'] == 'complete' and r['provider'] == 'deepseek' and r['model'] == MODEL for r in attempts
        ):
            raise ValueError('No completed DeepSeek request for this move')
        if kind in ('start','turn','choice','regenerate','variant'):
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
        write(folder / 'diagnostics.json.gz', diagnostics(path, sid, cursor))
        write(folder / 'result.json', dict(meta, finished=now()))
    return meta['status'] == 'recorded'


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
    folder.rename(archive / (folder.name + '-' + str(time.time_ns())))


def read(path):
    return json.loads(path.read_text())


def report(directory, manifest):
    lines = ['# Live Gameplay QA #99', '', 'SHA ' + manifest['sha'], '',
             '| Case | Step | Action | Result | Evidence |', '|---|---:|---|---|---|']
    total = requests_count = unknown_cost = 0
    cost = Decimal(0)
    for case in CASES:
        for folder in sorted((directory / case).glob('[0-9]*')):
            result = folder / 'result.json'
            r = read(result) if result.exists() else {'kind': '?', 'status':'interrupted'}
            relative = folder.relative_to(directory)
            lines.append(f"| {case} | {folder.name} | {r['kind']} | {r['status']} | [{relative}]({relative}/intent.json) |")
            if (folder / 'diagnostics.json.gz').exists():
                with gzip.open(folder / 'diagnostics.json.gz', 'rt') as handle:
                    jobs = json.load(handle)
                    for job in jobs:
                        attempts = job['requests']
                        total += int(job['status'] == 'saved' and any(
                            a['provider'] == 'deepseek' and a['status'] == 'complete' for a in attempts))
                        requests_count += len(attempts)
                        for attempt in attempts:
                            if attempt['cost_usd'] is None:
                                unknown_cost += 1
                            else:
                                cost += Decimal(attempt['cost_usd'])
    with closing(sqlite3.connect((directory / 'budget.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        count, unresolved, inp, out = db.execute('SELECT count(*),count(CASE WHEN settled=0 THEN 1 END),'
            'coalesce(sum(input),0),coalesce(sum(output),0) FROM reservations').fetchone()
    lines.extend(['', f'Dispatches {count}, outstanding worst-case reservations {unresolved}.',
                  f'Conservative cost ceiling including reservations: ${(inp*INPUT+out*OUTPUT)/1e9:.6f}.',
                  f'Provider attempts logged by Runtime: {requests_count}, known estimated USD: {cost}, '
                  f'attempts without a cost receipt: {unknown_cost}.',
                  '', f'Saved jobs with a completed live request: {total}.',
                  'Fixture replay, navigation and deterministic transitions are excluded.',
                  '', 'Held and interrupted attempts require triage. Narrative quality and Knowledge disclosure '
                  'require human comparison of the scene, evidence, observers and History.'])
    (directory / 'report.md').write_text('\n'.join(lines) + '\n')


def run(args, directory, manifest):
    live = args.command == 'run'
    if manifest['sha'] != revision():
        raise SystemExit('Different checkout SHA from prepare; use the original checkout.')
    if live:
        pf = directory / 'preflight.json'
        if not pf.exists() or len(read(pf)) != 2*len(CASES) or not all(r.get('ok') for r in read(pf)):
            raise SystemExit('Run a successful browser preflight first.')
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise SystemExit('DEEPSEEK_API_KEY required in server environment.')
        if args.stage != 'A':
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
                if not live:
                    return preflight(browser, base, directory, manifest)
                caps = dict(zip(CASES, QUOTAS[args.stage]))
                held = set()
                for i in range(max(caps.values())):
                    for case, cap in caps.items():
                        if case in held or i >= cap or args.case and case != args.case:
                            continue
                        folder = directory / case / f'{i:03d}'
                        if folder.exists():
                            result = folder / 'result.json'
                            if not result.exists() or read(result)['status'] != 'recorded':
                                held.add(case)
                        elif not step(browser, base, directory, manifest, case, i):
                            held.add(case)
                        report(directory, manifest)
                if not held and not args.case:
                    write(directory / f'{args.stage}.complete', {'finished':now()})
                return not held
            finally:
                browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare','preflight','run','report','recover-unsubmitted'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stage', choices=list(QUOTAS), default='A')
    parser.add_argument('--case', choices=list(CASES))
    parser.add_argument('--step', type=int)
    parser.add_argument('--reviewed', action='store_true')
    parser.add_argument('--approved-full', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT):
        parser.error('Run directory must be outside the repository.')
    os.umask(0o077)
    if args.command == 'prepare':
        prepare(directory)
        return
    manifest = read(directory / 'manifest.json')
    with (directory / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'report':
            report(directory, manifest)
        elif args.command == 'recover-unsubmitted':
            recover_unsubmitted(directory, manifest, args.case, args.step)
        elif not run(args, directory, manifest):
            raise SystemExit('See preflight.json or report.md; incomplete cases require review.')


if __name__ == '__main__':
    main()
