"""Keep the full backend gate and budget grounded in recorded run durations."""
from pathlib import Path
import re
import shlex
import subprocess

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/verify.yml'


def job(name):
    # Read only a top-level job in this repository's fixed workflow layout.
    match = re.search(rf'^  {name}:\n(.*?)(?=^  [a-zA-Z][\w-]*:|\Z)',
                      WORKFLOW.read_text(), re.MULTILINE | re.DOTALL)
    assert match, f'Missing required job: {name}'
    return match[1]


@pytest.mark.parametrize('pytest_seconds', [1125.21, 1286.16,
    pytest.param(1435.48, id='ci475-interrupted-at-97pct-lower-bound')])
def test_job_covers_measured_full_suite_setup_and_finalization(pytest_seconds):
    # #382 JUnit + previous complete local run; see live99-ci382.md for evidence.
    # The job deadline includes setup, unlike pytest's reported suite duration.
    # #475 is a LOWER bound, not a fabricated completed-suite duration:
    # pytest ran 20:25:46..20:49:41 before cancellation, with only 97% reported.
    required = 77 + pytest_seconds + 10 + 120  # setup, tests, finalization, reserve
    timeout = int(re.search(r'^    timeout-minutes: (\d+)$', job('backend'), re.MULTILINE)[1])
    assert 20 * 60 < required <= timeout * 60


def test_backend_still_executes_the_entire_suite_and_keeps_failure_status():
    backend = job('backend')
    command, = re.findall(r'^      - run: (python -m pytest[^\n]*)$', backend, re.MULTILINE)
    assert shlex.split(command) == [
        'python', '-m', 'pytest', '-q', '--junitxml=pytest-results.xml', '--durations=20',
    ]  # no selectors, excludes, retries, shell success override or fail-fast
    assert 'continue-on-error' not in backend and 'if:' not in backend.split(command)[0]


@pytest.mark.parametrize('backend', ['success', 'failure', 'cancelled', 'skipped'])
def test_verify_rejects_every_unsuccessful_backend(backend):
    gate = job('verify')
    assert 'if: always()' in gate and 'continue-on-error' not in gate
    command = re.search(r'^        run: (.+)$', gate, re.MULTILINE)[1]
    result = subprocess.run(['bash', '-c', command],
                            env={'BACKEND': backend, 'FRONTEND': 'success', 'PLAN': 'success'})
    assert (result.returncode == 0) == (backend == 'success')
