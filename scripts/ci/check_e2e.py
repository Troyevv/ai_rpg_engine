"""Required aggregate gate: missing reports, skipped jobs and empty smoke fail closed."""
import argparse
import json
from pathlib import Path
from select_e2e import POLICY


def validate(reports, expected_reports=4):
    if len(reports) != expected_reports:
        raise ValueError(f'Expected {expected_reports} shard reports, got {len(reports)}')
    if any(r['status'] != 'passed' or not r['rows'] for r in reports):
        raise ValueError('A shard failed/interrupted or ran no tests')
    rows = [row for report in reports for row in report['rows']]
    for project in ('desktop', 'mobile'):
        passed = {r['file'] for r in rows if r['project'] == project and r['status'] == 'passed'}
        missing = set(POLICY['smoke']) - passed
        if missing:
            raise ValueError(f'{project}: critical suites did not execute successfully: {sorted(missing)}')
    for project in ('desktop', 'mobile'):
        for file, title in POLICY['critical_tests'].items():
            if not any(r['project'] == project and r['file'] == file and
                       r['status'] == 'passed' and r.get('title', '').endswith(title) for r in rows):
                raise ValueError(f'{project}: critical scenario missing/skipped: {file} / {title}')
    if any(r['status'] not in ('passed', 'skipped') or r['retry'] for r in rows):
        raise ValueError('Unexpected failures or retries')
    return len(rows)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('directory')
    args = p.parse_args()
    reports = [json.loads(f.read_text()) for f in Path(args.directory).rglob('ci-summary.json')]
    print(f'Validated {validate(reports)} test results across isolated shards')
