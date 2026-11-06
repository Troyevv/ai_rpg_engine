"""Opt-in DeepSeek benchmark, scored BEFORE resolver. No production extra call.

python -m devtools.evaluate_extraction136 --live --model MODEL --max-cases 3 --output /tmp/report.json
Uses only DEEPSEEK_API_KEY from the user's server environment. Never logs that key.
Without --live emits NOT RUN; synthetic transport results are never called live QA.
"""
import argparse
from copy import deepcopy
import json
from hashlib import sha256
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'tests/fixtures/extraction136/semantic-corpus.json'


def contains(row, expected):
    if isinstance(expected,dict):
        return isinstance(row,dict) and all(k in row and contains(row[k],v) for k,v in expected.items())
    return row==expected


def score(payload, expected):
    missing=[];false_events=[];identity=[]
    for section, records in expected['required_records'].items():
        for record in records:
            if not any(contains(r,record) for r in payload.get(section,[]) if isinstance(r,dict)):
                missing.append(dict(section=section,expected=record))
    for section, records in expected['forbidden_records'].items():
        for record in records:
            if any(contains(r,record) for r in payload.get(section,[]) if isinstance(r,dict)):
                false_events.append(dict(section=section,forbidden=record))
    scene=payload.get('final_scene',{})
    for key,expected_key in [('present_character_ids','present'),('observed_character_ids','observed')]:
        if sorted(scene.get(key,[]))!=sorted(expected[expected_key]):identity.append(key)
    if 'remote' in expected and sorted(row.get('actor_id') for row in scene.get('remote_interactions',[]))!=sorted(expected['remote']):identity.append('remote_interactions')
    return dict(false_negatives=missing,false_positives=false_events,identity_errors=identity,
                time_error=scene.get('elapsed_minutes')!=expected['elapsed_minutes'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true');parser.add_argument('--model')
    parser.add_argument('--max-cases',type=int,default=3);parser.add_argument('--max-tokens',type=int,default=4096)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=dict(contract='narrative-authority-v1',status='NOT RUN',model=args.model,results=[],calls=0,
                limitation='Only the explicitly labelled benchmark cases; no claim of universal semantic accuracy.',
                reason='Live evaluation was not requested or safe provider configuration is unavailable.')
    if args.live:
        if not args.model or not os.environ.get('DEEPSEEK_API_KEY'):
            parser.error('--live requires an explicit model and user-owned DEEPSEEK_API_KEY')
        if not 1<=args.max_cases<=len(json.loads(CORPUS.read_text())['cases']) or not 256<=args.max_tokens<=8192:parser.error('Invalid bounded budget')
        from backend.runtime_v3.context import build_context
        from backend.runtime_v3.raw import RawTurnResult
        from backend.runtime_v3.models import Condition, ScheduledEvent, NarrativeRole
        from jsonschema import Draft202012Validator, ValidationError
        from llm import chat_stream
        snapshot=json.loads((ROOT/'tests/fixtures/runtime_handoff/legacy_snapshot.json').read_text())
        from backend.runtime_v3.migration import migrate_v2
        snapshot=migrate_v2(snapshot).snapshot
        for case in json.loads(CORPUS.read_text())['cases'][:args.max_cases]:
            current=deepcopy(snapshot)
            for section,rows in case.get('preconditions',{}).items():
                model={'conditions':Condition,'scheduled_events':ScheduledEvent,'roles':NarrativeRole}[section]
                current['world_state'][section].update({key:model.model_validate({k:v for k,v in row.items() if k!='participants'}).model_dump() for key,row in rows.items()})
            messages=build_context(current,[],case['player_input'],'turn',131072,args.max_tokens,extraction_text=case['narrative'])
            schema=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('JSON Schema\n')))
            usage=[];start=time.monotonic()
            output=''.join(chat_stream(model=args.model,provider='deepseek',messages=messages,max_tokens=args.max_tokens,
                temperature=.1,response_format={'type':'json_object'},on_usage=lambda value:usage.append(value)))
            report['calls']+=1
            row=dict(id=case['id'],expected=case['expected'],latency_seconds=time.monotonic()-start,usage=usage,
                prompt_sha256=sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest(),
                schema_sha256=sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest(),
                max_tokens=args.max_tokens,temperature=.1,repair_attempts=0)
            try:
                payload=json.loads(output);Draft202012Validator(schema).validate(payload);RawTurnResult.parse(payload)
                row.update(actual=payload,structure_valid=True,**score(payload,case['expected']))
            except (ValueError,TypeError,ValidationError) as error:
                row.update(actual=output,structure_valid=False,error=type(error).__name__)
            report['results'].append(row)
        report['status']='RUN'
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
