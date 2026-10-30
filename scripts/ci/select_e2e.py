"""Conservative dependency policy. Only explicitly mapped paths can narrow E2E."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((Path(__file__).with_name('e2e-policy.json')).read_text())


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def select(paths, suites, *, diff_ok=True, force_full=False):
    suites = sorted(suites)
    missing = set(POLICY['smoke']) - set(suites)
    if missing:
        raise ValueError(f'Critical suites missing: {sorted(missing)}')
    chosen = set(POLICY['smoke'])
    reasons = []
    full = force_full or not diff_ok or not paths
    if full:
        reasons.append('full requested / diff unavailable or empty')
    for path in paths:
        domains = [name for name, rule in POLICY['domains'].items() if matches(path, rule['sources'])]
        if domains:
            for name in domains:
                chosen.update(s for s in suites if matches(s, POLICY['domains'][name]['suites']))
            reasons.append(f'{path}: {", ".join(domains)}')
        elif matches(path, POLICY['documentation']):
            reasons.append(f'{path}: documentation + critical smoke')
        else:
            # Includes API/Runtime/state/shared UI, tests (new or changed), config,
            # lockfiles, deletions, renames and all paths not explicitly understood.
            full = True
            reasons.append(f'{path}: unclassified/shared/infrastructure → full')
    return dict(full=full, files=suites if full else sorted(chosen), smoke=POLICY['smoke'], reasons=reasons)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--output', default='e2e-plan.json')
    args = parser.parse_args()
    ok = True
    try:
        if not args.base:
            raise ValueError('No base SHA')
        # No rename detection: both old and new paths participate. NUL handles spaces.
        raw = subprocess.check_output(['git', 'diff', '--no-renames', '--name-only', '-z',
                                       f'{args.base}...{args.head}', '--'], cwd=ROOT)
        paths = [p for p in raw.decode().split('\0') if p]
    except (ValueError, UnicodeError, subprocess.CalledProcessError):
        ok, paths = False, []
    suites = [str(p.relative_to(ROOT / 'frontend/e2e')) for p in (ROOT / 'frontend/e2e').rglob('*.spec.ts')]
    plan = select(paths, suites, diff_ok=ok, force_full=args.full)
    plan.update(changed_files=paths, diff_ok=ok)
    Path(args.output).write_text(json.dumps(plan, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f'full={str(plan["full"]).lower()}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('## E2E selection\n\n' + '\n'.join(f'- `{r}`' for r in plan['reasons']) + '\n\n')
            out.write(f'{len(plan["files"])} suites; critical smoke always included.\n')
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
