"""Freeze technical/speech/review variants; no provider access or oracle input."""
import argparse,json,hashlib
from pathlib import Path
from copy import deepcopy
from backend.runtime_v3.scene_steps import input_schema
from backend.services.structured_extraction import request_schema
from context_builder import estimate
from devtools.issue257.prepare import digest
from devtools.issue257.destination_prototype import project as destination
from .candidates import project


def prepare(source,output):
    output.mkdir(parents=True,exist_ok=False);manifest=[]
    for path in sorted(source.glob('*.json')):
        if path.name=='manifest.json':continue
        case=json.loads(path.read_text());messages=deepcopy(case['messages']['A'])
        for m in messages:
            if m['content'].startswith('JSON Schema\n'):m['content']='JSON Schema\n'+json.dumps(input_schema(8,case['snapshot']['world_state']['camera']['mode']),ensure_ascii=False,separators=(',',':'))
        messages[0]['content']=messages[0]['content'].replace('Extraction/7','Extraction/8')+'\nMovement input_source contains quote and meaning only, never intended_target_ids. Travellers are not speech addressees. Preserve separate questions and perceived replies using during_step_id along a route.\n'
        case['messages']={'D7':case['messages']['D'],'T':destination(messages),'S':project(messages,speech=True),'R':project(messages,review=True)}
        case['profiles']={v:'deepseek-flash' for v in case['messages']}
        case['contract_versions']={'D7':7,'T':8,'S':8,'R':8};case['contract_version']=8
        case['status']='NOT_RUN';case['experimental_contract']='issue258-frozen-unselected'
        case['hashes']['messages']={v:digest(m) for v,m in case['messages'].items()}
        case['hashes']['wire_schema']={v:digest(request_schema(m)) for v,m in case['messages'].items()}
        for m in case['messages'].values():assert estimate(m)<case['config']['context_length']-8192-256
        (output/path.name).write_text(json.dumps(case,ensure_ascii=False,indent=2))
        manifest.append(dict(case=case['name'],source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),hashes=case['hashes']))
    (output/'manifest.json').write_text(json.dumps(dict(paid_calls=0,cases=manifest),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);args=p.parse_args();prepare(args.source,args.output)
