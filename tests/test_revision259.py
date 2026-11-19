"""Authored controls for the single-revision experiment; no provider requests."""
from copy import deepcopy
import json

import pytest
from backend.services.structured_extraction import request_schema
from devtools.issue259.revision import run
from test_compound259 import setup

pytestmark = pytest.mark.extraction_v8


def case_and_payload():
    state, candidate, payload = setup()
    case = dict(snapshot={'world_state':state}, narrative=candidate.narrative,
                player_input=candidate.player_input, profiles={'compound259':'deepseek-flash'},
                config={'context_length':1048576}, messages={'compound259':[
                    {'role':'system','content':'Extract actual effects.'},
                    {'role':'user','content':'JSON Schema\n'+json.dumps(candidate.schema)}]})
    return case, payload


def execute(case, original, patcher):
    events = []
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        feedback = json.loads(kwargs['messages'][0]['content'].split('Candidate revision protocol:\n',1)[1])
        assert kwargs['thinking']=='off' and kwargs['max_tokens']==8192
        assert kwargs['structured_schema']==request_schema(kwargs['messages'])
        yield patcher(feedback)
    run(case, json.dumps(original), generate, events.append)
    assert len(calls)==1
    return events


def noop(feedback):
    return json.dumps(dict(candidate_hash=feedback['candidate_hash'], replacements=[], sections={}, reason='No change.'))


def test_valid_first_still_gets_exactly_one_revision_and_noop_preserves_everything():
    case, payload = case_and_payload()
    before = deepcopy(case)
    events = execute(case, payload, noop)
    first = next(e for e in events if e['event']=='before_revision')
    final = next(e for e in events if e['event']=='resolved')
    assert (first['state'],first['history'])==(final['state'],final['history'])
    assert case==before


def test_revision_can_add_an_omitted_actual_claim_without_regenerating_first_response():
    case, complete = case_and_payload()
    incomplete = deepcopy(complete)
    incomplete['scene_steps'][0]['effects'].pop()
    def patch(feedback):
        assert feedback['diagnostics']==[]  # No invented Runtime/oracle error.
        assert feedback['revision_scope']=='whole_candidate_semantic_review'
        return json.dumps(dict(candidate_hash=feedback['candidate_hash'],replacements=complete['scene_steps'],sections={},reason='The stated message was also heard during travel.'))
    events = execute(case, incomplete, patch)
    first = next(e for e in events if e['event']=='before_revision')
    final = next(e for e in events if e['event']=='resolved')
    assert not first['history']['knowledge_acquisitions']
    assert [k['actor_id'] for k in final['history']['knowledge_acquisitions']]==['a']
    assert final['state']['characters']['a']['location_id']=='park'


@pytest.mark.parametrize('mode',['malformed','stale','delete_effect'])
def test_invalid_revision_is_final_without_another_repair(mode):
    case, payload = case_and_payload()
    def patch(feedback):
        if mode=='malformed':return '{'
        replacements = deepcopy(payload['scene_steps']) if mode=='delete_effect' else []
        if replacements:replacements[0]['effects'].pop()
        return json.dumps(dict(candidate_hash='other' if mode=='stale' else feedback['candidate_hash'],replacements=replacements,sections={},reason='Invalid test control.'))
    events = execute(case, payload, patch)
    assert any(e['event']=='diagnostics' for e in events)
    assert not any(e['event']=='resolved' for e in events)
    assert events[-1]['calls']==1


def test_structural_diagnostics_are_real_and_repaired_in_same_revision():
    case, complete = case_and_payload()
    incomplete = deepcopy(complete)
    incomplete['scene_steps'][0]['effects'][0].pop('input_source')
    def patch(feedback):
        assert any(d['code']=='movement_agency' for d in feedback['diagnostics'])
        return json.dumps(dict(candidate_hash=feedback['candidate_hash'],replacements=complete['scene_steps'],sections={},reason='Bind the actual chosen walk to its original input.'))
    assert any(e['event']=='resolved' for e in execute(case,incomplete,patch))
