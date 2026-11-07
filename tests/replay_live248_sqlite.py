"""Offline #248 archive replay on disposable SQLite copies; never calls providers.

Usage: python tests/replay_live248_sqlite.py EXTRACTED/live248 NEW_OUTPUT_DIRECTORY
Original Family is a characterization of false speaker attribution, NOT a pass.
The explicitly test-authored controls are persistence tests, NOT Live QA.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.repositories.preparation import Repository
from devtools.live99.evidence import snapshot
from devtools.live99.retest import backup
from test_live248_recovery import live, control
from test_integrated_repair247 import execute, history

CASES = [('crisis','002'),('family','001'),('knowledge','001'),('phone','002'),('social','001')]


def replay(source,output,case,step,mode):
    data=live(case)
    with gzip.open(source/case/step/'before.json.gz','rt') as f:checkpoint=json.load(f)
    with gzip.open(source/case/step/'diagnostics.json.gz','rt') as f:original=json.load(f)[0]
    assert original['id']==data['job_id'] and original['narrative']==data['narrative']
    assert checkpoint['snapshot']['world_state']==data['before']
    responses=[json.loads(r['response_text']) for r in original['requests'] if r['stage']!='narrative' and r.get('response_text')]
    assert responses==[r['payload'] for r in data['responses']]
    sid=json.loads((source/case/step/'intent.json').read_text())['save']
    path=output/f'{case}-{mode}.sqlite';backup(source/'game.sqlite',path)
    repo=Repository(path);job=repo.get_job(data['job_id'])
    if job['status'] in ('error','stopped'):
        repo.abandon_job(sid,job['id'],repo.get_save(sid)['revision'],job['attempt_epoch'])
    if repo.get_snapshot(sid)!=checkpoint['snapshot']:
        repo.rollback_last(sid,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==checkpoint['snapshot'],(case,'exact checkpoint')
    before=snapshot(path,sid);hist=history(repo,sid)
    if mode=='control':
        replies=[control(data)] if case=='family' else [responses[0],control(data)]
    else:
        replies=[responses[0]] if case=='family' else [responses[0],responses[-1]]
    with patch('llm.chat_stream',side_effect=AssertionError('External calls forbidden')):
        job,calls=execute(repo,sid,data,replies)
    after=snapshot(path,sid)
    refused=case=='crisis' or mode=='original' and case!='family'
    assert job['status']==('error' if refused else 'saved'),(case,mode,job['error'])
    assert all(after['variants'].get(k)==v for k,v in before['variants'].items()),(case,'siblings')
    if refused:
        assert before['snapshot']==after['snapshot'] and before['history']==after['history']
    fresh=Repository(path)
    assert fresh.get_snapshot(sid)==after['snapshot']
    gains=len(history(fresh,sid)['knowledge_acquisitions'])-len(hist['knowledge_acquisitions'])
    if case=='knowledge' and mode=='control':assert gains==4
    if case=='family':assert gains==10
    with repo.connect() as db:assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    return dict(case=case,mode=mode,status=job['status'],scripted_calls=len(calls),knowledge_acquisitions=gains,
                semantic_acceptance=False,paid_calls=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    original_hash=hashlib.sha256((args.source/'game.sqlite').read_bytes()).hexdigest();results=[]
    for case,step in CASES:
        for mode in ('original','control'):
            results.append(replay(args.source,args.output,case,step,mode))
            print(json.dumps(results[-1]),flush=True)
            (args.output/'summary.json').write_text(json.dumps(results,indent=2))
    assert hashlib.sha256((args.source/'game.sqlite').read_bytes()).hexdigest()==original_hash

if __name__=='__main__':main()
