"""Identify the Python code loaded by this server, including installations without Git."""
import hashlib
from functools import lru_cache
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def server_build():
    digest = hashlib.sha256()
    files = [*ROOT.glob('*.py'), *(ROOT / 'backend').rglob('*.py'),
             *(ROOT / 'prompts').glob('*.md'), ROOT / 'requirements.txt']
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
        digest.update(path.read_bytes())
    try:
        revision = subprocess.check_output(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=ROOT,
                                           stderr=subprocess.DEVNULL, timeout=2, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    return {'id': digest.hexdigest()[:16], 'revision': revision}
