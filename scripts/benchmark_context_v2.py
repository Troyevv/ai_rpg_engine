"""Compare identical synthetic world at a git baseline and in the working tree.

No LLM calls or credentials. Estimates are UTF-8 heuristics, never actual usage.
Run: python scripts/benchmark_context_v2.py --baseline-ref <commit>
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from long_world_fixture import long_world

MEASURE = r'''
import json, sys, time
from context_builder import build_context, estimate
snapshot, turns, history = json.load(open(sys.argv[1], encoding='utf-8'))
output = {}
for mode, narrative in [('Narrative',None),('Extraction','Тимур ответил Илье про конверт.'),('ActiveNarrative',None)]:
    start=time.perf_counter()
    user_text = 'Прочитать сообщение Сони про конверт.' if mode == 'ActiveNarrative' else 'Что с конвертом?'
    messages=build_context(snapshot,turns,user_text,'turn',128000,4000,
                           extraction_text=narrative,world_history=history)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние')))
    output[mode] = dict(estimated_input=estimate(messages), actual_input=None,
        build_ms=round((time.perf_counter()-start)*1000,2),
        sections={key:dict(selected=len(current[key]),total=len(snapshot['world_state'][key]))
                  for key in ('locations','facts','knowledge','relationships','threads','scheduled_events')},
        prompt_parts={m['content'].splitlines()[0] if m['role'] != 'assistant' else 'narrative': estimate([m])-256 for m in messages if m['role'] != 'assistant'},
        narrative_continuity=sum(m['role']=='assistant' for m in messages),
        selection=getattr(messages,'selection',None))
    output[mode]['narrative_continuity_tokens']=sum(estimate([m])-256 for m in messages if m['role']=='assistant')
    if getattr(messages, 'selection', None): output[mode]['sections']=messages.selection['sections']
    if mode == 'Narrative':
        warm = build_context(snapshot,turns,user_text,'turn',128000,4000,world_history=history)
        output[mode]['warm_semantic']=getattr(warm,'selection',{}).get('semantic')
    history_messages=[m for m in messages if m['content'].startswith('Недавняя история')]
    output[mode]['sections'].setdefault('history_events', dict(selected=len(json.loads(history_messages[0]['content'].split('\n',1)[1])) if history_messages else 0,total=len(history['events'])))
print(json.dumps(output,ensure_ascii=False))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-ref',required=True)
    args=parser.parse_args()
    commit=subprocess.check_output(['git','rev-parse',args.baseline_ref+'^{commit}'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp); baseline=folder/'baseline';baseline.mkdir()
        archive=folder/'baseline.tar'
        with archive.open('wb') as out: subprocess.run(['git','archive',commit],cwd=ROOT,stdout=out,check=True)
        with tarfile.open(archive) as tar: tar.extractall(baseline,filter='data')
        fixture=folder/'fixture.json'
        fixture.write_text(json.dumps(long_world(),ensure_ascii=False),encoding='utf-8')
        results={}
        for label,cwd in [('before',baseline),('after',ROOT)]:
            results[label]=json.loads(subprocess.check_output([sys.executable,'-c',MEASURE,str(fixture)],cwd=cwd,text=True))
        snapshot, _, history = long_world()
        world={key:len(snapshot['world_state'][key]) for key in ('characters','locations','facts','knowledge','relationships','threads','scheduled_events')}
        world['history_events']=len(history['events'])
        print(json.dumps(dict(world=world, baseline_commit=commit,method='Conservative UTF-8 estimate, not actual provider usage',results=results),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
