"""Offline A/B/C request preparation from original final #248 evidence. NO dispatch.

python -m devtools.live99.extraction_compare ARCHIVE_ROOT NEW_OUTPUT_DIRECTORY
A is immutable recorded messages/answers. B removes only the exact historical default.
C replaces the contract/agency instructions on the SAME context, schema and Narrative.
Holdouts are labelled human-authored variations, never replacements for original evidence.
Use existing live99 budget/transport instrumentation for any separately authorized dispatch.
"""
import argparse
import ast
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from context_builder import estimate
from backend.runtime_v3 import context_contract, player_actions
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from .evidence import write

C_BASELINE = '4dc593e798892f0cfb3d1764468dd5516ce3bb85'
BASELINE = '87abdb8dbe67fbe191cadd30fe2aa785672bde01'
CASES = {
    'crisis': 'live248-finish/crisis/crisis/000',
    'phone_refusal_001': 'live248-finish/phone/phone/001',
    'phone_npc_interpretation_002': 'live248-finish/phone/phone/002',
    'family_ongoing1': 'live248-finish/family/family/001',
    'family_ongoing2': 'live248-finish/family/family/002',
    'family_ongoing3': 'live248-finish/family/family/003',
    'family_birth': 'live248-finish/family/family/004',
    'campaign': 'live248-finish/campaign/campaign/000',
    'knowledge': 'live248-retest/knowledge/000',
    'social': 'live248-retest/social/000',
}


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def baseline_contracts(ref=BASELINE):
    # Fixed trusted repository source; no import/execution of archived QA scripts.
    source = subprocess.check_output(['git', 'show', ref + ':backend/runtime_v3/context_contract.py'], text=True)
    values = {}
    def constant(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
        if isinstance(node, ast.Name): return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return constant(node.left) + constant(node.right)
        raise ValueError('Baseline contract is not a string constant expression')
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            value = constant(node.value)
            for name in node.targets:
                values[name.id] = value
        elif isinstance(node, ast.AugAssign):
            values[node.target.id] += constant(node.value)
    source = subprocess.check_output(['git', 'show', ref + ':backend/runtime_v3/player_actions.py'], text=True)
    action = next(ast.literal_eval(node.value) for node in ast.parse(source).body
                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'EXTRACTION_CONTRACT' for t in node.targets))
    return values['EXTRACTION_CONTRACT'], action


def variants(messages, legacy, old_contract, old_action):
    b = deepcopy(messages)
    assert b[0]['content'].startswith('Постоянные правила\n' + legacy + '\n')
    b[0]['content'] = b[0]['content'].replace(legacy + '\n', '', 1)
    assert b[0]['content'].count(old_contract) == 1
    c_contract, c_action = baseline_contracts(C_BASELINE)
    c = deepcopy(b)
    c[0]['content'] = c[0]['content'].replace(old_contract, c_contract, 1)
    assert c[0]['content'].count(old_action) == 1
    c[0]['content'] = c[0]['content'].replace(old_action, c_action, 1)
    assert b[1:] == c[1:] == messages[1:]
    return dict(A=messages, B=b, C=c)


def resolve_outcome(before, narrative, player_input, payload):
    try:
        out = StateResolver(before, narrative, player_input, require_player_agency=True).resolve(payload)
        return dict(structural_status='accepted', knowledge_acquisitions=len(out.history['knowledge_acquisitions']),
                    movements=len(out.history['movements']))
    except StructuralDeltaError as error:
        return dict(structural_status='rejected', diagnostics=error.diagnostics('offline'))


def validate_candidates(candidates, config):
    """Free structural checks, deliberately no semantic score for unrun models."""
    from jsonschema import Draft202012Validator
    for messages in candidates.values():
        schema = next(json.loads(m['content'].split('\n',1)[1]) for m in messages
                      if m['content'].startswith('JSON Schema\n'))
        Draft202012Validator.check_schema(schema)
        assert estimate(messages) < config['context_length'] - config['max_tokens'] - 256


def prepare(source, output):
    source = source.resolve(); output.mkdir(parents=True, exist_ok=False)
    manifest = read(source/'live248-final-87abdb8-sha256.json')
    assert all(digest(source/name) == value for name, value in manifest.items()), 'Original evidence hash mismatch'
    requests, legacy = {}, None
    for path in sorted(source.rglob('game.sqlite')):
        with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            db.row_factory = sqlite3.Row
            assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
            for row in db.execute('select * from llm_requests'):
                requests[row['id']] = dict(row)
            value = db.execute("select content from document_versions where owner='state_update_prompt.md' order by id limit 1").fetchone()[0]
            if legacy is not None: assert legacy == value
            legacy = value
    old_contract, old_action = baseline_contracts()
    summary, source_cases = [], {}
    stream_messages = [read_request(p) for p in source.rglob('provider-streams/*.jsonl')]
    for name, relative in CASES.items():
        folder = source/relative; job = read(folder/'diagnostics.json.gz')[0]
        before = read(folder/'before.json.gz')['snapshot']['world_state']
        player_input = read(folder/'intent.json')['action']
        initial = [r for r in job['requests'] if r['stage'] == 'extraction' and r['status'] == 'complete'][-1]
        request = requests[initial['id']]
        messages = json.loads(request['context_json']); config = json.loads(request['config_json'])
        assert config['thinking'] == 'off' and config['model'] == 'deepseek-flash'
        assert config['response_format'] == {'type': 'json_object'}
        candidates = variants(messages, legacy, old_contract, old_action)
        validate_candidates(candidates, config)
        payloads = [r for r in job['requests'] if r['stage'] in ('extraction','extraction_repair') and r['status']=='complete']
        payloads = payloads[payloads.index(initial):]
        replay = [dict(request_id=r['id'], stage=r['stage'], **resolve_outcome(before, job['narrative'], player_input, json.loads(r['response_text']))) for r in payloads]
        data = dict(name=name, origin='original', source=relative, job_id=job['id'], before=before,
                    player_input=player_input, narrative=job['narrative'], config=config,
                    messages=candidates, saved_A_responses=payloads, offline_current_runtime=replay,
                    B_C_semantic_status='NOT_RUN', paid_calls=0)
        write(output/(name+'.json'), data); source_cases[name] = data
        row = dict(name=name, request_id=initial['id'], origin='original', A_input_tokens=request['input_tokens'],
                   A_output_tokens=request['output_tokens'], A_seconds=request['duration'],
                   stream_matches=any(m == messages for m in stream_messages),
                   conservative_input_estimates={k:estimate(v) for k,v in candidates.items()},
                   system_bytes={k:len(v[0]['content'].encode()) for k,v in candidates.items()},
                   offline_current_runtime=replay)
        summary.append(row)
    holdouts = read(Path(__file__).resolve().parents[2]/'tests/fixtures/issue247/semantic_holdouts.json')
    for case in holdouts:
        data = deepcopy(source_cases[case['source']]); data.update(name=case['id'],origin='human_authored_holdout',expected=case['expected'])
        data.pop('saved_A_responses'); data.pop('offline_current_runtime'); data.pop('job_id')
        data['player_input'],data['narrative'] = case['player_input'],case['narrative']
        if case.get('kind') == 'background':
            from backend.runtime_v3.camera import observe
            from backend.runtime_v3.context import build_context
            snap = read(source/CASES[case['source']]/'before.json.gz')['snapshot']
            snap = observe(snap, 'qa_timur')
            c = build_context(snap, [], '', 'background', data['config']['context_length'], data['config']['max_tokens'],
                              extraction_text=case['narrative'], extraction_contract=1)
            c_contract,_ = baseline_contracts(C_BASELINE)
            assert context_contract.EXTRACTION_CONTRACT in c[0]['content']
            c[0]['content']=c[0]['content'].replace(context_contract.EXTRACTION_CONTRACT,c_contract,1)
            b = deepcopy(c); b[0]['content'] = b[0]['content'].replace(c_contract,old_contract,1)
            a = deepcopy(b); a[0]['content'] = a[0]['content'].replace('Постоянные правила\n','Постоянные правила\n'+legacy+'\n',1)
            data.update(before=snap['world_state'],kind='background',messages=dict(A=a,B=b,C=c))
        for messages in data['messages'].values():
            for message in messages:
                title, _, body = message['content'].partition('\n')
                if title == 'Текущий ввод':
                    value=json.loads(body);value['player_input']=case['player_input']
                    message['content']=title+'\n'+json.dumps(value,ensure_ascii=False,separators=(',',':'))
                elif title == 'completed_narrative':
                    message['content']=title+'\n'+json.dumps(case['narrative'],ensure_ascii=False)
        assert data['messages']['A'][1:] == data['messages']['B'][1:] == data['messages']['C'][1:]
        # Same production hard budget and schema; no paid dispatch or fake usage.
        validate_candidates(data['messages'], data['config'])
        write(output/(case['id']+'.json'),data)
    assert all(digest(source/name) == value for name,value in manifest.items()), 'Original evidence modified'
    result=dict(baseline=BASELINE,manifest_files_verified=len(manifest),original_cases=summary,
                holdouts=len(holdouts),paid_calls=0,semantic_B_C='NOT_RUN',
                note='UTF-8 estimates are not provider tokenization; A usage is real. Holdouts have no A model response.')
    write(output/'summary.json',result)
    return result


def read_request(path):
    with path.open() as stream:
        value=json.loads(stream.readline())
    return value['messages'] if value.get('event')=='request' else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=prepare(args.source,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
