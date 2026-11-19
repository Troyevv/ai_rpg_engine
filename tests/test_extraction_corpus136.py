"""Synthetic transport replay measures plumbing, never live model accuracy."""
import json
from copy import deepcopy
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
    from runtime_v3_fixture import reviewed
    reply=reviewed(case['synthetic_provider_reply']) if case['player_input'].strip() else case['synthetic_provider_reply']
    reply=deepcopy(reply)
    if case['id']=='rumor_knowledge':
        # Authored v5 representation of the same fixed semantic oracle; no LLM inference.
        fact=reply.pop('facts')[0]
        reply.pop('knowledge_gained')
        reply['events']=[e for e in reply['events'] if e['id']!='report']
        reply['information_events']=[dict(id='report',text='Виктория передала слух.',
            source_actor_id='viktoria_solovyova',medium='conversation',order=2,
            claims=[dict(fact=fact,assertion='rumor',perceived_by=['ilya'],status='suspected')])]
    def provider(**kw):
        if kw.get('response_format'):
            seen.append(kw['messages'])
            assert case['narrative'] in '\n'.join(m['content'] for m in kw['messages'])
            yield json.dumps(reply)
        else:yield case['narrative']
    # Score the raw provider answer separately; a saved job is not semantic proof.
    metrics=score(case['synthetic_provider_reply'],case['expected'])
    assert metrics==dict(false_negatives=[],false_positives=[],identity_errors=[],time_error=False)
    with patch('engine.chat_stream',side_effect=provider):
        job=wait_job(client,submit(client,sid,text=case['player_input']))
    assert job['status']=='saved',job.get('error')
    assert len(seen)==1
    schema=json.loads(next(m['content'].split('\n',1)[1] for m in seen[0] if m['content'].startswith('JSON Schema\n')))
    Draft202012Validator(schema).validate(reply)
    world=app.state.repository.get_snapshot(sid)['world_state']
    assert world['camera']['present_character_ids']==case['expected']['present']
    if case['id']=='rumor_knowledge':
        gains=[k for k in world['knowledge'].values() if world['facts'][k['fact_id']]['text']=='Юра покинул город']
        assert len(gains)==1 and gains[0]['actor_id']=='ilya' and gains[0]['status']=='suspected'
    if case['id']=='death_ellipsis':assert world['characters']['viktoria_solovyova']['life_status']=='dead'
    if case['id'] in ('rumor','hypothesis','negation'):assert world['characters']['viktoria_solovyova']['life_status']!='dead'

    if case['id']=='new_npc':
        assert world['characters']['arsen']['biological_sex']=='male'
        snapshot=app.state.repository.get_snapshot(sid)
        assert snapshot['pending_reviews']['arsen']['status']=='pending_review'
        assert not any(next(c for c in snapshot['character_cards'] if c['id']=='arsen')['fields'].values())
