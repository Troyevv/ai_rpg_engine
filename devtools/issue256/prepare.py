"""Prepare the original #256 suffix for explicit recovery; no provider calls.

Usage: python devtools/issue256/prepare.py EVIDENCE_DIR OUTPUT_DIR
This is a copy at the last correct state, NOT a repaired campaign or a Live PASS.
"""
import hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.repositories.preparation import Repository

source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
path=out/'recovery-ready.sqlite'
if path.exists():raise SystemExit('Use a new output directory; do not overwrite evidence.')
origin=source/'session-final.sqlite'
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
source_hash=digest(origin)
with sqlite3.connect(f'file:{origin}?mode=ro',uri=True) as src,sqlite3.connect(path) as dst:src.backup(dst)
repo=Repository(path);sid=1
jobs={n:json.loads((source/f'turn{n:02}-summary.json').read_text())['job_id'] for n in range(9,13)}
original_jobs={j:repo.get_job(j) for j in jobs.values()}
with repo.connect() as db:
    variants=[dict(r) for r in db.execute('select * from response_variants')]
    history=[dict(r) for r in db.execute('select * from world_history_v3')]
for _ in range(3):repo.rollback_last(sid,repo.get_save(sid)['revision'])
assert repo.get_snapshot(sid)==json.loads(original_jobs[jobs[9]]['before_json'])
assert all(repo.get_job(j)==old for j,old in original_jobs.items())
with repo.connect() as db:
    assert variants==[dict(r) for r in db.execute('select * from response_variants')]
    assert history==[dict(r) for r in db.execute('select * from world_history_v3')]
    assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
assert source_hash==digest(origin)
manifest=dict(status='READY_NOT_REPAIRED',paid_calls=0,save_id=sid,source=str(origin),
    source_sha256=source_hash,sqlite=str(path),sqlite_sha256=digest(path),
    revision=repo.get_save(sid)['revision'],source_jobs=jobs,
    original_variants_unchanged=len(variants),original_history_rows_unchanged=len(history),
    narrative_sha256={n:hashlib.sha256(original_jobs[j]['narrative'].encode()).hexdigest() for n,j in jobs.items()})
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False,indent=2))
