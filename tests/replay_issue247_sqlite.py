"""Offline replay against copies of the original #245 SQLite; no provider calls.

Run from the repository root. Test-authored repair controls are deliberately
separate from archived DeepSeek responses; this is not semantic Live QA.
"""
import argparse
import sys,json,gzip,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'tests')]
from backend.repositories.preparation import Repository
from devtools.live99.retest import backup
from devtools.live99.evidence import snapshot
from test_integrated_repair247 import archived,corrected,execute,history
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Extracted original #245 directory')
parser.add_argument('output', type=Path, help='New disposable directory for 12 SQLite copies')
args = parser.parse_args()
source, out = args.source.resolve(), args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
source_hash=hashlib.sha256((source/'game.sqlite').read_bytes()).hexdigest()
results=[]
for case,step in [('family','001'),('knowledge','002'),('phone','001'),('crisis','001'),('social','001'),('campaign','000')]:
 data=archived(case)
 checkpoint=json.load(gzip.open(source/case/step/'before.json.gz','rt'))
 intent=json.loads((source/case/step/'intent.json').read_text());sid=intent['save']
 for mode in ['repeat','control']:
  path=out/(case+'-'+mode+'.sqlite');backup(source/'game.sqlite',path);repo=Repository(path)
  old=repo.get_job(data['job_id'])
  if old['status'] in ('error','stopped'):
   repo.abandon_job(sid,old['id'],repo.get_save(sid)['revision'],old['attempt_epoch'])
  if repo.get_snapshot(sid)['world_state']!=data['before']:
   repo.rollback_last(sid,repo.get_save(sid)['revision'])
  before=snapshot(path,sid)
  before_history=history(repo,sid)
  assert before['snapshot']['world_state']==data['before'],(case,'state')
  assert before['snapshot']['history_head']==checkpoint['snapshot']['history_head'],(case,'history')
  bad=data['responses'][0]['payload'];last=data['responses'][-1]['payload']
  if case=='campaign':bad=last
  replies=[bad,corrected(data) if mode=='control' else bad]
  with patch('llm.chat_stream',side_effect=AssertionError('No external calls')):
   job,calls=execute(repo,sid,data,replies)
  after=snapshot(path,sid)
  expected='error' if case=='crisis' or mode=='repeat' and case in ('family','knowledge','phone') else 'saved'
  assert job['status']==expected,(case,mode,job['error'])
  assert all(after['variants'].get(k)==v for k,v in before['variants'].items()),(case,'siblings')
  if expected=='error':
   assert before['snapshot']==after['snapshot']
   assert before['history']==after['history']
  gains=len(history(repo,sid)['knowledge_acquisitions'])-len(before_history['knowledge_acquisitions'])
  if case=='knowledge' and mode=='control':assert gains==4
  assert Repository(path).get_snapshot(sid)==after['snapshot']
  with repo.connect() as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  results.append(dict(case=case,mode=mode,status=job['status'],scripted_calls=len(calls),knowledge_acquisitions=gains,paid_calls=0))
  print(json.dumps(results[-1]),flush=True)
  (out/'summary.json').write_text(json.dumps(results,indent=2))
assert hashlib.sha256((source/'game.sqlite').read_bytes()).hexdigest()==source_hash
