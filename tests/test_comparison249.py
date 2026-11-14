"""The comparison uses production mode boundaries; controlled transport only."""
from copy import deepcopy
import json
import pytest

from backend.runtime_v3.camera import observe
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.simulation import background_resolver_options
from devtools.live99.extraction_compare249 import evaluate, resolver_kwargs, run_pair
from test_extraction_semantics248 import final_live
from test_evidence_first249 import control


def test_background_kwargs_match_hidden_production_and_preserve_knowledge():
    data=final_live('phone');state=data['before'];camera=observe({'world_state':deepcopy(state)},'qa_timur')
    case=dict(before=camera['world_state'],protection_state=state,kind='background',player_input='',
        narrative='Тимур добрался до фотолаборатории.')
    raw=dict(final_scene=dict(location_id='lab',present_character_ids=['qa_timur'],elapsed_minutes=0),
        locations=[dict(id='lab',name='Лаборатория')],
        movements=[dict(actor_id='qa_timur',from_location_id=state['characters']['qa_timur']['location_id'],
            to_location_id='lab',assertion='completed_arrival',source_event_id='arrival',order=1)],
        events=[dict(id='arrival',text=case['narrative'],participants=['qa_timur'],witnesses=['qa_timur'],
            medium='action',location_id='lab',order=1)])
    for variant in ('C','D'):
        assert resolver_kwargs(case,variant)==background_resolver_options(state,2 if variant=='D' else 1)
        out=evaluate(case,variant,raw)
        assert out['structural_status']=='accepted',out
        assert out['state']['knowledge']==state['knowledge']
        assert out['state']['characters']['qa_kirill']==state['characters']['qa_kirill']
        assert not out['history']['events'][0]['player_observed']


def test_ordinary_missing_audit_gets_one_repair_in_current_only():
    data=final_live('phone');good=control(data);bad=deepcopy(good);bad['player_agency'].pop('narrative_audit')
    case=dict(data,messages={'C':[dict(role='system',content='C')],'D':[dict(role='system',content='D')]},
        config=dict(provider='deepseek',model='deepseek-flash',thinking='off',temperature=.1,max_tokens=8192,
                    context_length=65536,response_format={'type':'json_object'}))
    assert resolver_kwargs(case,'D')==resolver_options(data['before'],data['player_input'],'turn',2)
    for variant,expected in [('C',1),('D',2)]:
        replies=iter([bad,good]);calls=[]
        def generate(**kw):
            calls.append(kw);kw['on_usage'](dict(prompt_tokens=100,completion_tokens=20))
            yield json.dumps(next(replies))
        out=run_pair(case,variant,generate)
        assert len(out['attempts'])==len(calls)==expected
        assert out['attempts'][-1]['result']['structural_status']=='accepted'
        assert out['attempts'][-1]['result']['semantic_status']=='HUMAN_REVIEW_REQUIRED'
        assert out['extraction_plus_repair_seconds']>=0
        if variant=='D':
            assert 'player_agency_audit_missing' in calls[1]['messages'][0]['content']
            assert 'context_length' not in calls[1]


def test_comparison_retains_production_elapsed_requirement():
    data=final_live('phone');raw=control(data)
    raw['final_scene'].pop('elapsed_minutes')
    for variant in ('C','D'):
        result=evaluate(data,variant,raw)
        assert result['structural_status']=='rejected' and result['repairable']
    assert resolver_options(data['before'],data['player_input'],time_skip=True)['require_elapsed'] is False


def test_transport_failure_retains_request_partial_response_and_receipt_without_retry():
    data=final_live('phone');records=[];calls=[]
    case=dict(data,messages={'D':[dict(role='system',content='D')]},config=dict(provider='deepseek',
        model='deepseek-flash',thinking='off',temperature=.1,max_tokens=8192,
        context_length=65536,response_format={'type':'json_object'}))
    def generate(**kw):
        calls.append(kw);kw['on_usage'](dict(prompt_tokens=10,completion_tokens=2))
        yield '{"player_agency":'
        raise TimeoutError('interrupted')
    with pytest.raises(TimeoutError):run_pair(case,'D',generate,record=records.append)
    assert len(calls)==1
    assert records[0]['status']=='dispatching'
    assert records[-1]['status']=='transport_error'
    assert records[-1]['response']=='{"player_agency":'
    assert records[-1]['messages']==case['messages']['D']
    assert records[-1]['usage']==[dict(prompt_tokens=10,completion_tokens=2)]
