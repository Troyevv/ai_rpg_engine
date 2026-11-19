"""Offline C/D preparation and shared evaluation. CLI never dispatches paid calls.

python -m devtools.live99.extraction_compare249 PREPARED_248_REQUESTS NEW_DIRECTORY
C must be prepared by extraction_compare on frozen C_BASELINE, not by a new model.
run_pair accepts the existing Budget.wrap transport after SEPARATE live authorization.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from context_builder import estimate
from backend.runtime_v3 import player_actions, context_contract
from backend.runtime_v3.raw import prompt_schema, repair_feedback, prune_schema_definitions
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.simulation import background_resolver_options
from backend.services.world_delta_errors import StructuralDeltaError
from .extraction_compare import read, digest, baseline_contracts, C_BASELINE, validate_candidates
from .evidence import write

# Stable identities are source path + checkpoint/job/request + input/Narrative hashes.
ALIASES = {'phone_departure':'phone_refusal_001', 'phone_agency':'phone_npc_interpretation_002'}
HOLDOUTS = [
    dict(name='help_gesture_unrequested', source='phone_npc_interpretation_002', player_input='Сортирую снимки по годам.',
         narrative='Кирилл раскладывает снимки. Вера спрашивает, помочь ли с коробкой. Кирилл кивает, соглашаясь.',
         expected=dict(agency='violated', added_choice='consent by gesture', recovery='reauthor')),
    dict(name='help_gesture_authorized', source='phone_npc_interpretation_002', player_input='Киваю Вере, соглашаясь на помощь с коробкой, и сортирую снимки по годам.',
         narrative='Кирилл раскладывает снимки. Вера спрашивает, помочь ли с коробкой. Кирилл кивает, соглашаясь.',
         expected=dict(agency='preserved', consent='authorized', target_mode='interaction')),
    dict(name='involuntary_reaction', source='phone_npc_interpretation_002', player_input='Сортирую снимки по годам.',
         narrative='За окном с грохотом захлопывается ставня. Кирилл вздрагивает; один снимок соскальзывает со стола. Вера поднимает его.',
         expected=dict(agency='preserved', reaction='involuntary', npc_initiative=True)),
    dict(name='group_partial_delivery', source='crisis', player_input='Спрашиваю Марину и Веру, нужна ли им помощь.',
         narrative='Нина обращается к Марине и зовёт Веру. Марина отвечает, что справится сама. Веры здесь нет, и она не слышит вопроса.',
         expected=dict(agency='preserved', outcome='partial', actual_targets=['qa_marina'], vera_contact=False)),
]
EXPECTED_ORIGINAL = {
    'crisis': dict(agency='violated', impossible_contact=False, recovery='reauthor'),
    'phone_refusal_001': dict(agency='violated', unauthorized_refusal=True, recovery='reauthor'),
    'phone_npc_interpretation_002': dict(agency='preserved', npc_interpretation='not a player choice'),
    'knowledge': dict(agency='preserved', acquisitions=4, provenance='both listeners x both facts'),
    'family_birth': dict(agency='preserved', acquisitions=10, birth='one canonical boy',
                        source_actor_id=None, listeners=['qa_kirill','qa_vera']),
    'family_ongoing1': dict(agency='preserved', birth='not completed', temporal_boundary='unresolved'),
    'family_ongoing2': dict(agency='preserved', birth='not completed', temporal_boundary='unresolved'),
    'family_ongoing3': dict(agency='preserved', birth='not completed', temporal_boundary='unresolved'),
    'social': dict(agency='preserved', player_and_npc_actions='separate', decisions='only authorized'),
    'campaign': dict(agency='preserved', commitments='preserve canonical time and participants'),
}
REPEATS = {'phone_refusal_001':2, 'detail_holdout':2,
           'help_gesture_unrequested':2, 'help_gesture_authorized':2}


def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def schema_from(messages):
    return next(json.loads(m['content'].split('\n',1)[1]) for m in messages if m['content'].startswith('JSON Schema\n'))


def candidate(c):
    """Change only contract/schema; never rebuild or truncate canonical context."""
    d=deepcopy(c);old_contract,old_action=baseline_contracts(C_BASELINE)
    system=d[0]['content']
    assert old_contract in system
    if old_action in system:system=system.replace(old_action,player_actions.EXTRACTION_CONTRACT,1)
    d[0]['content']=system.replace(old_contract, context_contract.EXTRACTION_CONTRACT, 1)
    old=schema_from(c);props=old['properties']
    schema=prompt_schema(
        player_agency_required='player_agency' in props,
        elapsed_required='elapsed_minutes' in props['final_scene']['required'],
        relationship_evidence='source_event_ids' in props['relationship_changes']['items']['properties'],
        reproduction='reproductive_events' in props,births='births' in props,
        favorable_paths='favorable_path' in props['thread_changes']['items']['properties'],
        communication='remote_events' in props,groups='group_request_changes' in props,
        voice='call_lifecycle_changes' in props, historical='remote_events' in props and
            'artifact_id' in props['remote_events']['items']['properties'])
    # Match the existing C request's budget-selected optional promotion fields.
    # No prose heuristics and no lost capabilities relative to the paired baseline.
    prior=props['promotions']['items']['properties']['character']['properties']
    current=schema['properties']['promotions']['items']['properties']['character']['properties']
    for field in ('appearance','personality','values'):
        if field not in prior:current.pop(field,None)
    prune_schema_definitions(schema)
    for message in d:
        if message['content'].startswith('JSON Schema\n'):
            message['content']='JSON Schema\n'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
    assert {k for k in props} == {k for k in schema['properties']}
    for left,right in zip(c,d):
        if not left['content'].startswith(('Постоянные правила\n','JSON Schema\n')):assert left==right
    return d


def resolver_kwargs(case, variant):
    if case.get('kind')=='background':
        return background_resolver_options(case['protection_state'], 2 if variant=='D' else 1)
    return player_actions.resolver_options(case['before'],case['player_input'],
        case.get('kind','turn'), 2 if variant=='D' else 1)


def evaluate(case, variant, payload):
    resolver=StateResolver(case['before'],case['narrative'],case['player_input'],**resolver_kwargs(case,variant))
    try:
        result=resolver.resolve(payload)
        return dict(structural_status='accepted',state=result.state,history=result.history,
                    semantic_status='HUMAN_REVIEW_REQUIRED')
    except StructuralDeltaError as exc:
        return dict(structural_status='rejected',repairable=exc.repairable,
                    diagnostics=exc.diagnostics('comparison'),semantic_status='HUMAN_REVIEW_REQUIRED')


def run_pair(case, variant, generate, record=None):
    """At most one repair. Transport must be the existing budget-wrapped provider.

    No semantic PASS inferred from accepted JSON. The optional recorder persists
    request/receipt/partial output even if transport fails; no automatic reroll.
    """
    messages=deepcopy(case['messages'][variant]);attempts=[];start=time.monotonic()
    for attempt in range(2):
        config={key:case['config'][key] for key in
                ('model','provider','thinking','temperature','max_tokens','response_format')}
        assert config['thinking']=='off' and config['provider']=='deepseek' and config['model']=='deepseek-flash'
        usage=[];chunks=[]
        item=dict(attempt=attempt+1,messages=deepcopy(messages),response='',usage=usage,status='dispatching')
        attempts.append(item)
        if record:record(deepcopy(item))
        try:
            for chunk in generate(messages=messages,require_complete=True,on_usage=usage.append,**config):
                chunks.append(chunk)
        except Exception as exc:
            item.update(response=''.join(chunks),status='transport_error',error_type=type(exc).__name__)
            if record:record(deepcopy(item))
            raise
        response=''.join(chunks)
        item.update(response=response,status='received')
        if record:record(deepcopy(item))
        result=evaluate(case,variant,response)
        item.update(result=result,status='evaluated')
        if record:record(deepcopy(item))
        if result['structural_status']=='accepted' or not result.get('repairable'):break
        if attempt==0:
            feedback=repair_feedback(result['diagnostics'],response,case['before'])
            messages=deepcopy(case['messages'][variant])
            messages[0]['content']+='\nПовторно интерпретируй неизменный Narrative по feedback; верни полный JSON:\n'+feedback
            if estimate(messages)>=case['config']['context_length']-case['config']['max_tokens']-256:
                raise ValueError('Repair exceeds the unchanged context budget')
    return dict(attempts=attempts,extraction_plus_repair_seconds=time.monotonic()-start)


def prepare(source,output):
    output.mkdir(parents=True,exist_ok=False)
    cases={ALIASES.get(p.stem,p.stem):read(p) for p in sorted(source.glob('*.json')) if p.name!='summary.json'}
    for row in HOLDOUTS:
        data=deepcopy(cases[row['source']]);data.update(row,origin='authored_holdout_249')
        data.pop('saved_A_responses',None);data.pop('job_id',None)
        for message in data['messages']['C']:
            title,_,body=message['content'].partition('\n')
            if title=='Текущий ввод':
                value=json.loads(body);value['player_input']=row['player_input']
                message['content']=title+'\n'+json.dumps(value,ensure_ascii=False,separators=(',',':'))
            elif title=='completed_narrative':message['content']=title+'\n'+json.dumps(row['narrative'],ensure_ascii=False)
        cases[row['name']]=data
    plan=[];sizes=[]
    for old_name,data in cases.items():
        name=ALIASES.get(old_name,old_name);data['name']=name
        if old_name in EXPECTED_ORIGINAL:data['expected']=EXPECTED_ORIGINAL[old_name]
        if data.get('kind')=='background':
            data['protection_state']=deepcopy(cases['phone_npc_interpretation_002']['before'])
        c=data['messages']['C'];d=candidate(c)
        data['messages']={'C':c,'D':d};validate_candidates(data['messages'],data['config'])
        responses=data.get('saved_A_responses',[])
        data['identity']=dict(source=data['source'],job_id=data.get('job_id'),
            request_ids=[r['id'] for r in responses],before_sha256=sha(data['before']),
            input_sha256=sha(data['player_input']),narrative_sha256=sha(data['narrative']),
            request_sha256={k:sha(v) for k,v in data['messages'].items()})
        data['semantic_CD']='NOT_RUN';data['paid_calls']=0
        # Retain A provenance but never dispatch it or copy the full archived answers again.
        data.pop('saved_A_responses',None);data.pop('offline_current_runtime',None)
        write(output/(name+'.json'),data)
        for repeat in range(REPEATS.get(name,1)):
            order=['C','D'] if len(plan)%2==0 else ['D','C']
            plan.append(dict(case=name,repeat=repeat+1,order=order))
        sizes.append(dict(case=name,bytes={k:sum(len(m['content'].encode()) for m in v) for k,v in data['messages'].items()},
            estimated_tokens={k:estimate(v) for k,v in data['messages'].items()},
            schema_bytes={k:len(json.dumps(schema_from(v),ensure_ascii=False,separators=(',',':')).encode()) for k,v in data['messages'].items()}))
    manifest=dict(baseline=C_BASELINE,cases=len(cases),schedule=plan,first_calls=2*len(plan),
        max_calls_with_one_repair=4*len(plan),thinking='off',paid_calls=0,live_gate='NOT_RUN',
        source_hashes={p.name:digest(p) for p in source.glob('*.json')},sizes=sizes,
        expected_cost_note='Historical B/C mean $0.00623/call, not a current price guarantee; use existing Budget receipts/reservations.',
        historical_rate_estimate_usd=[round(2*len(plan)*.00623,3),round(4*len(plan)*.00623,3)])
    write(output/'manifest.json',manifest)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();result=prepare(args.source,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes','sizes','schedule')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
