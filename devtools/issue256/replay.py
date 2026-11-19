"""Free production recovery on an isolated SQLite backup. AUTHORED controls, no Live PASS.

Usage: python devtools/issue256/replay.py EVIDENCE_DIR OUTPUT_DIR
Original provider records are only read; all changes use rollback/begin_job/commit.
"""
import sys,json,gzip,sqlite3,hashlib
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history

source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
path=out/'authored-control.sqlite'
if path.exists():raise SystemExit('Use a new output directory; do not overwrite evidence.')
with sqlite3.connect(f'file:{source / "session-final.sqlite"}?mode=ro',uri=True) as src,sqlite3.connect(path) as dst:src.backup(dst)
repo=Repository(path);sid=1
jobs={n:json.loads((source/f'turn{n:02}-summary.json').read_text())['job_id'] for n in range(9,13)}
def records(n):return json.load(gzip.open(source/(jobs[n]+'-requests.json.gz'),'rt'))
def extraction(n):return deepcopy(next(r['diagnostics']['extraction_candidate']['candidate'] for r in reversed(records(n)) if r['stage']=='extraction'))
def group(id,endpoint,text,quote):return dict(id=id,kind='movement',actor_ids=['char_alexey','char_galina'],assertion='completed_arrival',endpoint=endpoint,text=text,input_source=dict(quote=quote,meaning='preserved'))
controls={}
for n in range(9,13):
 p=extraction(n);p['scene'].pop('observer_location_id',None);controls[n]=p
p=controls[9];ss=p['scene_steps'];ss[0]['input_source']['quote']=repo.get_job(jobs[9])['user_text']
ss[3]=dict(id=ss[3]['id'],kind='occurrence',actor_ids=['char_galina'],text=ss[3]['text'])
ss[5]=group(ss[5]['id'],'authored_porch','Вместе вышли на крыльцо.','Давай немного пройдёмся, если ты не слишком устала?')
p['locations']=[dict(id='authored_porch',name='Крыльцо дома Галины',parent_id='loc_berezovsk',evidence='Authored control from original prose')]
p=controls[10];trip=group('authored_shared_walk','authored_shore','Вместе дошли до берега.','Иду рядом с мамой к Березянке, подстраиваясь под её шаг.')
for s in p['scene_steps'][:3]:s['during_step_id']=trip['id']
p['scene_steps'].insert(0,trip)
p['locations']=[dict(id='authored_shore',name='Берег Березянки',parent_id='loc_berezovsk',evidence='Authored control from original prose')]
p=controls[12];ss=p['scene_steps'];old=ss[2];ss[2]=group(old['id'],'loc_cafe','Вместе дошли к дверям кафе.',repo.get_job(jobs[12])['user_text'])
for s in ss[3:5]:s['during_step_id']=old['id']
del ss[5]  # Its arrival outcome is represented once by the shared trip.
bg=deepcopy(next(r['diagnostics']['extraction_candidate']['candidate'] for r in records(11) if r['stage']=='world_simulation_delta'))
bg['scene_steps'][0]['actor_ids']=[bg['scene_steps'][0].pop('actor_id')];bg['scene_steps'][0]['assertion']='local_exit'
for n,p in controls.items():(out/f'authored-{n}.json').write_text(json.dumps(p,ensure_ascii=False,indent=2))
(out/'authored-background.json').write_text(json.dumps(bg,ensure_ascii=False,indent=2))
# Archive the incorrect suffix; no direct state/snapshot UPDATE.
original_jobs={j:repo.get_job(j) for j in jobs.values()}
for _ in range(3):repo.rollback_last(sid,repo.get_save(sid)['revision'])
before=repo.get_snapshot(sid);report=[]
config=dict(provider='local',model='authored-control',context_length=131072,max_tokens=2400,update_tokens=8192,thinking='off')
for n in range(9,13):
 sourcejob=original_jobs[jobs[n]];calls=[]
 def provider(**kw):
  calls.append(kw)
  narrative=next((json.loads(m['content'].split('\n',1)[1]) for m in kw['messages'] if m['content'].startswith('completed_narrative\n')),None)
  if narrative==sourcejob['narrative']:answer=controls[n]
  elif n==11 and narrative==next(r['response_text'] for r in records(11) if r['stage']=='world_simulation'):answer=bg
  else:raise AssertionError('Unexpected generation: no new Narrative is allowed in this free replay.')
  yield json.dumps(answer,ensure_ascii=False)
 jid=repo.begin_job(sid,'','turn',dict(config,_recovery_source_job_id=jobs[n],expected_revision=repo.get_save(sid)['revision']))
 with patch('engine.find_loaded_model',return_value={'config':{'context_length':131072}}),patch('engine.chat_stream',side_effect=provider):engine.run_job(path,jid,engine.Worker())
 j=repo.get_job(jid);snap=repo.get_snapshot(sid)
 report.append(dict(turn=n,job_id=jid,status=j['status'],error=j['error'],calls=len(calls),same_narrative=j['narrative']==sourcejob['narrative'],locations={a:snap['world_state']['characters'][a]['location_id'] for a in ['char_alexey','char_galina','char_olga']}))
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report[-1],ensure_ascii=False),flush=True)
 assert j['status']=='saved',j['error']
 assert repo.get_job(jobs[n])==original_jobs[jobs[n]]
 assert Repository(path).get_snapshot(sid)==snap
 with gzip.open(out/f'after-{n}.json.gz','wt') as f:json.dump(snap,f,ensure_ascii=False)
assert report[-1]['locations']['char_alexey']==report[-1]['locations']['char_galina']=='loc_cafe'
assert report[-1]['locations']['char_olga']=='loc_home_sokolov'
with repo.connect() as db:
 history,warnings=read_history(db,snap['history_head'])
 assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
(out/'history.json').write_text(json.dumps(history,ensure_ascii=False))
(out/'checks.json').write_text(json.dumps(dict(authored_control_only=True,reload=True,original_jobs_unchanged=True,paid_calls=0,source_sha256=hashlib.file_digest((source/'session-final.sqlite').open('rb'),'sha256').hexdigest()),indent=2))
