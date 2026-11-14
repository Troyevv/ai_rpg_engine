"""Free fixed-prose contract comparison. No model IO or semantic PASS inference.
Run: python tests/measure_policy252.py /tmp/policy252-measurements.json
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from context_builder import estimate
from test_integrated_repair247 import archived, seed, corrected


def size(value):
    return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())


def measure():
    rows=[]
    with TemporaryDirectory() as folder:
        for case in ('crisis','knowledge','phone','family','social','campaign'):
            data=archived(case);repo=Repository(Path(folder)/(case+'.sqlite'))
            sid=seed(repo,data)['save'];snapshot=repo.get_snapshot(sid)
            payload=data['responses'][0]['payload']
            for version in (4,5):
                messages=build_context(snapshot,[],data['player_input'],'turn',65536,8192,
                    extraction_text=data['narrative'],extraction_contract=version)
                schema=next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('JSON Schema\n'))
                try:
                    result=StateResolver(data['before'],data['narrative'],data['player_input'],
                        **resolver_options(data['before'],data['player_input'],contract_version=version)).resolve(payload)
                    status='accepted';codes=[];warnings=[w.get('code') for w in result.warnings]
                    gains=len(result.history['knowledge_acquisitions'])
                except StructuralDeltaError as error:
                    status='rejected';codes=[d['code'] for d in error.diagnostics('offline')];warnings=[];gains=0
                rows.append(dict(case=case,version=version,prompt_utf8=sum(len(m['content'].encode()) for m in messages),
                    prompt_estimate=estimate(messages),schema_utf8=len(schema.encode()),original_output_utf8=size(payload),
                    structural_status=status,error_codes=codes,warning_codes=warnings,knowledge_acquisitions=gains,
                    semantic_acceptance=False,provider_calls=0))
    old=corrected(archived('knowledge'));new=json.loads(json.dumps(old))
    facts=new.pop('facts');acquisitions=new.pop('knowledge_gained');event=new['events'][0];event['fact_ids']=[]
    new['information_events']=[dict(id='vera-reply',text='Вера сообщила день рождения и расположение каталога.',evidence='\n'.join(f['evidence'] for f in facts),
        source_actor_id='qa_vera',medium='conversation',location_id='qa_home',order=2,
        claims=[dict(fact={k:v for k,v in f.items() if k!='evidence'},assertion='testimony',status='known',perceived_by=[k['actor_id'] for k in acquisitions if k['fact_id']==f['id']]) for f in facts])]
    return dict(cases=rows,authored_knowledge_output=dict(legacy_utf8=size(old),semantic_utf8=size(new),
        note='Representation control on unchanged recorded prose; not a model result.'),
        note='UTF8/estimate are not actual provider token usage. Fixed old raw is never new Extraction. No paid calls.')


if __name__=='__main__':
    Path(sys.argv[1]).write_text(json.dumps(measure(),ensure_ascii=False,indent=2))
