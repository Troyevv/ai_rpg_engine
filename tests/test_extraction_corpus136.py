"""Synthetic transport replay measures plumbing, never live model accuracy."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from jsonschema import Draft202012Validator
from test_api import api, wait_job
from test_runtime_handoff import imported, submit, source
from devtools.evaluate_extraction136 import score

CASES=json.loads((Path(__file__).parent/'fixtures/extraction136/semantic-corpus.json').read_text())['cases']


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_semantic_fixture_before_resolver_and_real_job(api,case):
    client,app=api;world_source=source()
    for section,rows in case.get('preconditions',{}).items():world_source['world'].setdefault(section,{}).update(rows)
    sid=imported(client,world_source);seen=[]
    def provider(**kw):
        if kw.get('response_format'):
            seen.append(kw['messages'])
            assert case['narrative'] in '\n'.join(m['content'] for m in kw['messages'])
            yield json.dumps(case['synthetic_provider_reply'])
        else:yield case['narrative']
    # Score the raw provider answer separately; a saved job is not semantic proof.
    metrics=score(case['synthetic_provider_reply'],case['expected'])
    assert metrics==dict(false_negatives=[],false_positives=[],identity_errors=[],time_error=False)
    with patch('engine.chat_stream',side_effect=provider):
        job=wait_job(client,submit(client,sid,text=case['player_input']))
    assert job['status']=='saved',job.get('error')
    assert len(seen)==1
    schema=json.loads(next(m['content'].split('\n',1)[1] for m in seen[0] if m['content'].startswith('JSON Schema\n')))
    Draft202012Validator(schema).validate(case['synthetic_provider_reply'])
    world=app.state.repository.get_snapshot(sid)['world_state']
    assert world['camera']['present_character_ids']==case['expected']['present']
    if case['id']=='death_ellipsis':assert world['characters']['viktoria_solovyova']['life_status']=='dead'
    if case['id'] in ('rumor','hypothesis','negation'):assert world['characters']['viktoria_solovyova']['life_status']!='dead'
