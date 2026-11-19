"""Offline replay on SQLite backups. Requires both original archives extracted
under the argument directory; original files remain byte-identical. Run with
PYTHONPATH=tests:. python scripts/reproduce_berezovsk_followup248.py /path/to/evidence
Provider transport is patched; no network/model invocation occurs.
"""
from pathlib import Path
import sqlite3,json,gzip,tempfile,hashlib
from unittest.mock import patch
from copy import deepcopy
import engine
from backend.repositories.preparation import Repository
from test_berezovsk_followup248 import DATA,CONFIG,compound_control,grounded_control
from test_integrated_repair247 import execute,history
import sys
root=Path(sys.argv[1])
out={}
with tempfile.TemporaryDirectory() as tmp:
 for case,source in [('002',root/'life248-game-live/off/turns/002/checkpoint.sqlite'),('lta',root/'life248-playability-live/lta/turns/001/checkpoint.sqlite'),('005',root/'life248-game-live/off/turns/005/checkpoint.sqlite')]:
  digest=hashlib.sha256(source.read_bytes()).hexdigest()
  path=Path(tmp)/(case+'.sqlite')
  with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as src,sqlite3.connect(path) as dst:src.backup(dst)
  repo=Repository(path);sid=1
  if case=='002':
   repo.rollback_last(sid);data=deepcopy(DATA['002']);before=repo.get_snapshot(sid)
   assert before['world_state']==data['before']
   old_history=history(repo,sid)
   job,calls=execute(repo,sid,data,[grounded_control(data)],legacy=False,config=CONFIG)
   assert job['status']=='saved',job['error']
   fresh=Repository(path);choices=json.loads(fresh.list_turns(sid)[-1]['choices_json'])
   assert len(choices)==5
   assert all(c['speech']!=json.loads(data['responses']['D'][0])['choices'][3]['speech'] for c in choices)
   assert fresh.get_snapshot(sid)['world_state']['knowledge']==before['world_state']['knowledge']
   fresh.rollback_last(sid);assert fresh.get_snapshot(sid)==before and history(fresh,sid)==old_history
   out[case]=dict(calls=len(calls),safe_choices=len(choices),knowledge_unchanged=True,reload=True,rollback=True)
  elif case=='lta':
   archive=root/'life248-playability-live/lta/turns/001'
   original=json.loads(gzip.decompress((archive/'before.json.gz').read_bytes()))['snapshot']
   answers=iter(json.loads(gzip.decompress((archive/'requests.json.gz').read_bytes())));calls=[]
   assert repo.get_snapshot(sid)['world_state']['characters']['char_pasha']['location_id'] is None
   jid=repo.begin_job(sid,'','regenerate',CONFIG)
   def provider(**kwargs):
    row=next(answers);calls.append(row['stage']);yield row['response_text']
   with patch('engine.chat_stream',side_effect=provider):engine.run_job(path,jid,engine.Worker())
   assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
   saved=Repository(path).get_snapshot(sid)
   assert saved['world_state']['characters']['char_pasha']['location_id']=='loc_home_kovalev'
   assert saved['world_state']['knowledge']==original['world_state']['knowledge']
   repo.rollback_last(sid)
   assert repo.get_snapshot(sid)['world_state']==original['world_state']
   out[case]=dict(calls=len(calls),pasha='loc_home_kovalev',reload=True,rollback=True)
  else:
   data=deepcopy(DATA['005']);before=repo.get_snapshot(sid)
   assert before['world_state']==data['before']
   with repo.connect() as db:jobs=db.execute("select id from game_jobs where status='error'").fetchall()
   for row in jobs:
    job=repo.get_job(row[0]);repo.abandon_job(sid,job['id'],repo.get_save(sid)['revision'],job['attempt_epoch'])
   before=repo.get_snapshot(sid);previous=history(repo,sid)
   job,calls=execute(repo,sid,data,[json.loads(r) for r in data['responses']['D']],legacy=False,config=CONFIG)
   assert job['status']=='error' and repo.get_snapshot(sid)==before
   retry,requests=execute(repo,sid,data,[compound_control(data)],retry=job['id'],legacy=False,config=CONFIG)
   assert retry['status']=='saved',retry['error']
   assert Repository(path).get_snapshot(sid)['world_state']['characters']['char_alexey']['location_id']=='loc_home_viktor'
   repo.rollback_last(sid);assert repo.get_snapshot(sid)==before and history(repo,sid)==previous
   out[case]=dict(initial_calls=len(calls),retry_calls=len(requests),narrative_calls=sum(not c.get('response_format') for c in calls+requests),reload=True,rollback=True)
  with repo.connect() as db:assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
  assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
print(json.dumps(dict(provider_network_calls=0,original_sqlite_unchanged=True,results=out),ensure_ascii=False,indent=2))
