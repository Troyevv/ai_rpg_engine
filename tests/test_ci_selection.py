"""Selection/gate regression tests; no application behavior is mocked or weakened."""
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
from select_e2e import POLICY, select
from check_e2e import validate

SUITES = [p.name for p in (ROOT / 'frontend/e2e').glob('*.spec.ts')]

@pytest.mark.parametrize('source,expected', [
    ('frontend/src/Phone.tsx', ['phone.spec.ts', 'current-game.spec.ts', 'reachability129.spec.ts', 'portrait-polish.spec.ts', 'call-continuity.spec.ts']),
    ('frontend/src/PhoneContent.tsx', ['phone.spec.ts', 'portrait-polish.spec.ts']),
    ('frontend/src/GameCalendar.tsx', ['calendar155.spec.ts', 'current-game.spec.ts', 'mobile-menu126.spec.ts']),
    ('frontend/src/lib/genealogyLayout.ts', ['genealogy156.spec.ts', 'dossier.spec.ts', 'personal-relationships.spec.ts']),
    ('frontend/src/RelationshipCard.tsx', ['relationships157.spec.ts', 'personal-relationships.spec.ts', 'inspector86.spec.ts']),
])
def test_cross_domain_regressions(source, expected):
    plan = select([source], SUITES)
    assert not plan['full']
    assert set(expected + POLICY['smoke']) <= set(plan['files'])

@pytest.mark.parametrize('path', ['backend/runtime_v3/state.py', 'backend/api/app.py', 'unknown.txt',
    'frontend/src/App.tsx', 'frontend/src/components/Button.tsx', 'frontend/playwright.config.ts',
    'tests/e2e_server.py', '.github/workflows/verify.yml', 'frontend/e2e/new-regression.spec.ts'])
def test_risk_fallback(path):
    plan = select([path], SUITES)
    assert plan['full'] and plan['files'] == sorted(SUITES)


def test_failed_or_empty_diff_and_mixed_unknown():
    for paths, ok in [([], False), ([], True), (['README.md'], False), (['README.md', 'unknown'], True)]:
        assert select(paths, SUITES, diff_ok=ok)['full']


def test_new_phone_suite_automatically_included():
    for name in ['phone163.spec.ts', 'narrative-phone999.spec.ts', 'call-new.spec.ts']:
        assert name in select(['frontend/src/Phone.tsx'], SUITES + [name])['files']


def test_smoke_cannot_disappear():
    assert set(POLICY['smoke']) <= set(select(['README.md'], SUITES)['files'])
    with pytest.raises(ValueError, match='Critical suites missing'):
        select(['README.md'], [])


def reports():
    rows = [dict(file=f, project=p, status='passed', retry=0, title=POLICY['critical_tests'][f]) for p in ['desktop', 'mobile'] for f in POLICY['smoke']]
    return [dict(status='passed', rows=rows[i::4]) for i in range(4)]


def test_gate_accepts_complete_reports():
    assert validate(reports()) == len(POLICY['smoke']) * 2

@pytest.mark.parametrize('status', ['failed', 'timedOut', 'interrupted'])
def test_gate_rejects_failure_timeout_cancel(status):
    data = reports()
    data[0]['status'] = status
    with pytest.raises(ValueError):
        validate(data)


def test_gate_rejects_missing_empty_skipped_smoke_and_retry():
    with pytest.raises(ValueError): validate(reports()[:-1])
    for mutation in ('skip', 'empty', 'retry'):
        data = reports()
        if mutation == 'skip': data[0]['rows'][0]['status'] = 'skipped'
        elif mutation == 'empty': data[0]['rows'] = []
        else: data[0]['rows'][0]['retry'] = 1
        with pytest.raises(ValueError): validate(data)


def test_other_passes_cannot_mask_skipped_critical_scenario():
    data = reports()
    data[0]['rows'][0]['title'] = 'some other test in the same file'
    with pytest.raises(ValueError, match='critical scenario missing'):
        validate(data)
