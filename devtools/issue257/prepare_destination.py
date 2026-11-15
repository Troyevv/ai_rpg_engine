"""Freeze unselected D inputs from a frozen A corpus; never calls a provider."""
import argparse
import json
from pathlib import Path
from context_builder import estimate
from backend.services.structured_extraction import request_schema
from jsonschema import Draft202012Validator
from .prepare import digest
from .destination_prototype import project


def prepare(source,output):
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for path in sorted(source.glob('*.json')):
        if path.name=='manifest.json':continue
        case=json.loads(path.read_text());a=case['messages']['A']
        assert digest(a)==case['hashes']['messages']['A']
        case['messages']={'A':a,'D':project(a)};case['profiles']={'A':'deepseek-flash','D':'deepseek-flash'}
        case['experimental_contract']='issue257-D-destination-prototype';case['status']='NOT_RUN'
        case['hashes']['messages']={v:digest(m) for v,m in case['messages'].items()}
        case['hashes']['wire_schema']={v:digest(request_schema(m)) for v,m in case['messages'].items()}
        for messages in case['messages'].values():
            Draft202012Validator.check_schema(request_schema(messages))
            assert estimate(messages)<case['config']['context_length']-8192-256
        (output/path.name).write_text(json.dumps(case,ensure_ascii=False,indent=2))
        rows.append(dict(case=case['name'],source_sha256=digest(json.loads(path.read_text())),hashes=case['hashes']))
    (output/'manifest.json').write_text(json.dumps(dict(paid_calls=0,cases=rows),indent=2))
    return len(rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(prepare(args.source,args.output))
