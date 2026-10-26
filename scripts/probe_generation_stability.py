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


def generation_input(client, wid, scenario):
    """Both creation inputs; scenario text is authored, not another paid LLM call."""
    use_idea=scenario.get('flow')=='scenario'
    if use_idea:
        document=f'/api/documents/idea/{wid}'
        head=client.get(document).json()['active_id']
        reply=client.post(document,json={'content':scenario['idea'],'expected_head':head})
        reply.raise_for_status()
    revision=client.get(f'/api/workspaces/{wid}').json()['revision']
    return dict(revision=revision,text='' if use_idea else scenario['idea'],use_idea=use_idea,
                creation_settings=dict(scenario.get('settings',{}),calendar_start=scenario['start']))


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
    scenarios=json.loads((ROOT/'tests/fixtures/generation_scenarios/inputs_final.json').read_text())
    cap=args.budget_usd/(len(scenarios)*args.runs)
    config=dict(provider='deepseek',model=args.model,temperature=0.7,max_tokens=16000,context_length=131072)
    metrics=[];app=create_app(args.output/'probe.sqlite3')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (args.output/'inputs.json').write_text(json.dumps(dict(commit=commit,config=config,budget_usd=str(args.budget_usd),runs=args.runs,scenarios=scenarios),ensure_ascii=False,indent=2)+'\n')
    with TestClient(app) as client:
        for scenario in scenarios:
            for run in range(args.runs):
                started=time.monotonic()
                wid=client.post('/api/workspaces',json={'name':scenario['id']+' '+str(run+1)}).json()['id']
                url=f'/api/workspaces/{wid}/draft'
                request=client.post(url+'/generate',json=dict(generation_input(client,wid,scenario),config=config,api_key=key,budget={'max_cost_usd':str(cap)}))
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
                    gameplay=dict(mode='controlled',outcome='not_started')
                    if job['status']=='saved':
                        draft=client.get(url+'?author=true').json()
                        confirmed=client.post(url+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
                        if confirmed.status_code==200:
                            # This verifies integration only, and is never counted as live gameplay.
                            sys.path.insert(0,str(ROOT/'tests'))
                            from test_runtime_v3_engine import run as play,raw_for
                            from test_engine import CONFIG
                            from backend.repositories.preparation import Repository
                            repo=app.state.repository;sid=confirmed.json()['save'];steps=[]
                            for kind in ('start','turn','turn'):
                                before=repo.get_snapshot(sid)
                                turn=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,context_length=262144))
                                play(repo,turn,raw_for(before))
                                result=repo.get_job(turn);steps.append(dict(kind=kind,status=result['status']))
                                persisted=repo.get_snapshot(sid);repo=Repository(repo.path)
                                if repo.get_snapshot(sid)!=persisted:raise RuntimeError('Reload changed canonical snapshot')
                                if result['status']!='saved':break
                            gameplay.update(outcome='saved' if len(steps)==3 and all(s['status']=='saved' for s in steps) else 'failed',steps=steps)
                        else:gameplay.update(outcome='confirm_failed',http_status=confirmed.status_code)
                    rows=exported.get('requests',[])
                    costs=[r.get('cost_usd') for r in rows]
                    metrics.append(dict(commit=commit,scenario=scenario['id'],run=run+1,config=config,creation_flow=scenario['flow'],creation_settings=dict(scenario['settings'],calendar_start=scenario['start']),review_contract=CONTRACT_VERSION,outcome=job['status'],duration_seconds=round(time.monotonic()-started,3),requests=rows,cost_usd=str(sum(Decimal(str(c)) for c in costs)) if costs and all(c is not None for c in costs) else None,diagnostics=exported.get('current_diagnostics'),generation_contract=exported.get('generation_contract'),scope='live generation; controlled editor/confirm/start/turn/reload/next-turn',gameplay=gameplay,review_resolutions=exported.get('review_resolutions',[]),repair_failures=exported.get('repair_failures',[]),quality=exported.get('quality'),ready_to_start=job['status']=='saved'))
                (args.output/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2,default=str)+'\n')
                print(scenario['id'],run+1,metrics[-1]['outcome'],flush=True)


if __name__=='__main__':main()
