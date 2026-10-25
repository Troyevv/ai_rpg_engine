"""Opt-in bounded live generation probe. Never run by pytest or ordinary CI.

The six-scenario editor/start/turn/reload integration is separately exercised by
 tests/test_generation_scenarios.py with controlled providers. This probe records
 actual fresh-world provider outcomes, including every failed attempt.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget-usd',type=Decimal,required=True,help='Total reservation cap, divided across all runs')
    parser.add_argument('--runs',type=int,default=2,help='Independent runs per scenario')
    parser.add_argument('--model',default='deepseek-flash')
    parser.add_argument('--output',type=Path,required=True,help='New directory for SQLite and JSON metrics')
    args=parser.parse_args()
    if args.runs<1 or args.budget_usd<=0:parser.error('runs and budget must be positive')
    key=os.environ.get('DEEPSEEK_API_KEY')
    if not key:parser.error('DEEPSEEK_API_KEY is not configured; no requests sent')
    args.output.mkdir(parents=True,exist_ok=False)
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.services.draft_completeness import CONTRACT_VERSION
    scenarios=json.loads((ROOT/'tests/fixtures/generation_scenarios/inputs.json').read_text())
    cap=args.budget_usd/(len(scenarios)*args.runs)
    config=dict(provider='deepseek',model=args.model,temperature=0.7,max_tokens=16000,context_length=131072)
    metrics=[];app=create_app(args.output/'probe.sqlite3')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with TestClient(app) as client:
        for scenario in scenarios:
            for run in range(args.runs):
                started=time.monotonic()
                wid=client.post('/api/workspaces',json={'name':scenario['id']+' '+str(run+1)}).json()['id']
                url=f'/api/workspaces/{wid}/draft'
                request=client.post(url+'/generate',json=dict(revision=0,text=scenario['idea'],config=config,api_key=key,creation_settings={'calendar_start':scenario['start']},budget={'max_cost_usd':str(cap)}))
                if request.status_code!=200:
                    metrics.append(dict(commit=commit,scenario=scenario['id'],run=run+1,outcome='preflight_rejected',http_status=request.status_code,requests=[],cost_usd=None))
                else:
                    jid=request.json()['id']
                    # No timeout retry: a pending provider request has unknown outcome.
                    while True:
                        job=app.state.repository.preparation_job(jid)
                        if job['status'] not in ('queued','generating'):break
                        time.sleep(0.5)
                    exported=client.get(url+'/raw').json()
                    rows=exported.get('requests',[])
                    costs=[r.get('cost_usd') for r in rows]
                    metrics.append(dict(commit=commit,scenario=scenario['id'],run=run+1,config=config,calendar_start=scenario['start'],review_contract=CONTRACT_VERSION,outcome=job['status'],duration_seconds=round(time.monotonic()-started,3),requests=rows,cost_usd=str(sum(Decimal(str(c)) for c in costs)) if costs and all(c is not None for c in costs) else None,diagnostics=exported.get('current_diagnostics'),generation_contract=exported.get('generation_contract'),scope='generation only; no live gameplay'))
                (args.output/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2,default=str)+'\n')
                print(scenario['id'],run+1,metrics[-1]['outcome'],flush=True)


if __name__=='__main__':main()
