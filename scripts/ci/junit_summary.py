"""Small report adapter, not a test runner: never replaces the test exit code."""
import html
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

path = Path(sys.argv[1])
lines = [f'## {path.name}', '']
if not path.exists():
    lines.append('No JUnit report: tests did not finish or setup failed. See job log.')
else:
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    failed = [c for c in cases if c.find('failure') is not None or c.find('error') is not None]
    skipped = sum(c.find('skipped') is not None for c in cases)
    lines.append(f'{len(cases)-len(failed)-skipped} passed / {len(failed)} failed / {skipped} skipped; '
                 f'{sum(float(c.get("time", 0)) for c in cases):.1f}s summed test time.')
    for case in failed:
        lines.append(f'- {html.escape(case.get("classname", ""))}::{html.escape(case.get("name", ""))}')
text = '\n'.join(lines) + '\n'
print(text)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write(text)
