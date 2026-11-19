"""Offline frozen v7 comparison inputs. Never dispatches a provider request.

python -m devtools.issue257.prepare WORK_DIRECTORY NEW_OUTPUT_DIRECTORY
Authored predecessor setup is copied from issue256's production recovery controls;
it is not a model success. Original jobs/responses remain separate evidence.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import compact_choice_context, build_context
from backend.services.structured_extraction import request_schema


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def compact(messages):
    """Use the existing lossless projection, before hard-limit pressure only in B."""
    out=deepcopy(messages)
    current=next(json.loads(m['content'].split('\n',1)[1]) for m in out if m['content'].startswith('Текущее состояние / GM-only\n'))
    for m in out:
        if m['content'].startswith('Choice context / controlled actor\n'):
            title,body=m['content'].split('\n',1)
            value=compact_choice_context(current,json.loads(body))
            candidate=title+'\n'+json.dumps(value,ensure_ascii=False,separators=(',',':'))
            instruction='\nChoice state_ref references Текущее состояние / GM-only; grants no extra knowledge.'
            if len(candidate.encode())+len(instruction.encode())<len(m['content'].encode()):
                m['content']=candidate;out[0]['content']+=instruction
    assert request_schema(out)==request_schema(messages)
    return out


EXPECTATIONS={
 'porch':dict(required='Both outside at the entrance to Galina home on Lesnaya; river is only a proposal.',forbidden='Lenin Street, reached river, inside apartment; inferred assent to the next trip.'),
 'river':dict(required='Both reach the riverbank; retain conversation and only actually heard information.',forbidden='Old apartment address, missing companion, completed travel reduced to intent.'),
 'river_talk':dict(required='Conversation continues by the water; retain independent consequences.',forbidden='Return home from stale memory, new unchosen journey.'),
 'cafe':dict(required='Both reach the cafe doors; whether to enter remains open.',forbidden='Entering or answering for player; visibility used as transport.'),
 'olga':dict(required='Olga leaves kitchen for another room, same home address; no automatic hearing.',forbidden='Unknown canonical address, hero changes, new player Knowledge from common address.')}


def prepare(work,out):
    out.mkdir(parents=True,exist_ok=False)
    control=work/'issue256-free/control-stable'
    repo=Repository(control/'authored-control.sqlite')
    report=json.loads((control/'report.json').read_text());cases=[]
    for row,name in zip(report,('porch','river','river_talk','cafe')):
        job=repo.get_job(row['job_id']);requests=repo.request_log(job_id=job['id'])
        request=next(r for r in requests if r['stage']=='extraction')
        case=dict(name=name,origin='original_narrative_with_explicit_authored_predecessor_setup',
            source_job_id=json.loads(job['config_json'])['_narrative_recovery']['source_job_id'],
            snapshot=json.loads(job['before_json']),memory_before=json.loads(job['memory_before_json']),
            player_input=job['user_text'],narrative=job['narrative'],kind='turn',
            messages=request['messages'],expected=EXPECTATIONS[name])
        cases.append(case)
        if name=='river_talk':
            bg=next(r for r in requests if r['stage']=='world_simulation_delta')
            fixture=json.loads((Path(__file__).resolve().parents[2]/'tests/fixtures/issue256/room.json').read_text())
            background=deepcopy(case['snapshot']);background['world_state']['camera']=deepcopy(fixture['snapshot']['world_state']['camera'])
            cases.append(dict(name='olga',origin='original_background_isolated_fixture',
                source_job_id=case['source_job_id'],snapshot=background,
                player_input=fixture['player_input'],narrative=fixture['narrative'],kind='background',
                resolver_options=fixture['resolver_options'],messages=list(build_context(background, [], fixture['player_input'], 'background',131072,8192,extraction_text=fixture['narrative'],extraction_contract=7)),expected=EXPECTATIONS['olga']))
    specs=json.loads((Path(__file__).parent/'cases.json').read_text())
    for spec in specs:
        snapshot=deepcopy(cases[0]['snapshot'])
        if spec.get('base')=='authored_fantasy':
            from backend.runtime_v3.models import WorldStateV3, Character
            state=WorldStateV3(characters={c:Character(id=c,display_name=name,location_id='castle').model_dump() for c,name in [('a','Арден'),('b','Брин')]},locations={'castle':dict(id='castle',name='Замок',description='Зал и спальня внутри одного замка.')},camera=dict(location_id='castle',present_character_ids=['a','b'],controlled_actor_id='a')).model_dump()
            snapshot=dict(schema_version=3,world_state=state,character_cards=[dict(id=c,name=state['characters'][c]['display_name'],fields={}) for c in state['characters']],campaign=dict(genre='Средневековое фэнтези'),memory={},history_head=None)
        messages=list(build_context(snapshot,[],spec['input'],'turn',131072,8192,extraction_text=spec['narrative'],extraction_contract=7))
        cases.append(dict(name=spec['name'],origin='authored_'+spec['suite'],snapshot=snapshot,player_input=spec['input'],narrative=spec['narrative'],kind='turn',messages=messages,expected={k:spec[k] for k in ('required','forbidden')},source=spec.get('source')))
    manifest=[]
    for case in cases:
        a=case.pop('messages');case['messages']={'A':a,'B':compact(a),'C':deepcopy(a)}
        case['config']=dict(provider='deepseek',model='deepseek-flash',thinking='off',temperature=.1,
            context_length=131072,max_tokens=8192,extraction_transport='responses_json_schema')
        case['profiles']={'A':'deepseek-flash','B':'deepseek-flash','C':'deepseek-v4-pro'}
        case['hashes']={k:digest(case[k]) for k in ('snapshot','player_input','narrative')}
        case['hashes']['messages']={k:digest(v) for k,v in case['messages'].items()}
        case['hashes']['wire_schema']=digest(request_schema(a))
        case['hashes']['narrative_utf8']=hashlib.sha256(case['narrative'].encode()).hexdigest()
        case['status']='NOT_RUN'
        (out/(case['name']+'.json')).write_text(json.dumps(case,ensure_ascii=False,indent=2))
        manifest.append(dict(name=case['name'],hashes=case['hashes'],bytes={k:sum(len(m['content'].encode()) for m in v) for k,v in case['messages'].items()}))
    (out/'manifest.json').write_text(json.dumps(dict(paid_calls=0,cases=manifest),indent=2))
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.work,a.output),indent=2))
