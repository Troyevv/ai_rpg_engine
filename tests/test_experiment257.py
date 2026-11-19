"""Experimental context projection only; no provider calls or product defaults."""
import json
from copy import deepcopy
from devtools.issue257.prepare import compact


def test_projection_preserves_private_boundary_and_schema():
    state={'facts':{'secret':{'text':'Private'}},'characters':{'a':{'goals':[{'text':'A long meaningful goal repeated in both contexts, with all original content retained.'}]}}}
    choice={'enabled':True,'actor_id':'a','goals':deepcopy(state['characters']['a']['goals']),'knowledge':[]}
    messages=[{'role':'system','content':'Rules'},*({'role':'user','content':title+'\n'+json.dumps(value)} for title,value in [('Текущее состояние / GM-only',state),('Choice context / controlled actor',choice),('JSON Schema',{'type':'object','properties':{}}),('completed_narrative','Unchanged prose')])]
    before=deepcopy(messages);out=compact(messages)
    projected=json.loads(out[2]['content'].split('\n',1)[1])
    def expand(v):
        if isinstance(v,dict) and set(v)=={'state_ref'}:
            value=state
            for part in v['state_ref'].split('/')[1:]:value=value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
            return value
        if isinstance(v,dict):return {k:expand(x) for k,x in v.items()}
        if isinstance(v,list):return [expand(x) for x in v]
        return v
    assert expand(projected)==choice
    assert projected['knowledge']==[]
    assert messages==before and out[1]==before[1] and out[3:]==before[3:]


def test_destination_prototype_shared_arrival_and_idempotence():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.player_actions import resolver_options
    from devtools.issue257.destination_prototype import DestinationCandidate
    state,_=fixture();before=deepcopy(state);text='Выхожу вместе с b к входу в дом.'
    payload={'scene':{'elapsed_minutes':1},'scene_steps':[{'id':'walk','kind':'movement','actor_ids':['a','b'],'assertion':'completed_arrival','destination':{'name':'Вход снаружи','anchor_id':'home','relation':'Снаружи у входа'},'text':'Дошли до входа.','input_source':{'quote':text,'meaning':'preserved'}}]}
    candidate=DestinationCandidate(state,'Дошли до входа.',text,1,version=7)
    raw=candidate.parse(payload);again=candidate.parse(payload)
    assert raw.records['locations']==again.records['locations']
    result=StateResolver(state,'Дошли до входа.',text,turn_id=1,**resolver_options(state,text,contract_version=7)).resolve(raw)
    lid=result.state['characters']['a']['location_id']
    assert result.state['characters']['b']['location_id']==lid!='home'
    assert result.state['locations'][lid]['parent_id'] is None
    assert not result.history['knowledge_acquisitions'] and state==before
    assert candidate.base==payload


def test_destination_prototype_existing_and_local_exit():
    from test_scene_steps255 import fixture
    from devtools.issue257.destination_prototype import adapt
    s,_=fixture()
    for assertion,destination,expected in [('completed_arrival',{'existing_id':'park'},'park'),('local_exit',None,None),('departure',None,None),('intent',{'existing_id':'park'},'park')]:
        p={'scene':{},'scene_steps':[{'id':'move','kind':'movement','assertion':assertion,'actor_ids':['b'],'destination':destination}]}
        out=adapt(p,s,1)
        assert out['scene_steps'][0]['endpoint']==expected and not out.get('locations')


def test_destination_prototype_one_scoped_repair_retains_neighbors():
    import pytest
    from test_scene_steps255 import fixture
    from backend.services.world_delta_errors import StructuralDeltaError
    from devtools.issue257.destination_prototype import DestinationCandidate
    s,_=fixture();candidate=DestinationCandidate(s,'Проза.','Жду.',1,version=7)
    p={'scene':{'elapsed_minutes':1},'scene_steps':[{'id':'move','kind':'movement','actor_ids':['b'],'assertion':'completed_arrival','destination':{'name':'Вход','anchor_id':'missing','relation':'Снаружи'},'text':'Вышел.'},{'id':'independent','kind':'occurrence','actor_ids':['a'],'text':'Ждёт.'}]}
    with pytest.raises(StructuralDeltaError) as error:candidate.parse(p)
    feedback=json.loads(candidate.feedback(error.value.diagnostics('comparison'),json.dumps(p)))
    fixed=deepcopy(p['scene_steps'][0]);fixed['destination']['anchor_id']='home'
    raw=candidate.parse({'candidate_hash':feedback['candidate_hash'],'replacements':[fixed],'reason':'Исправлен ориентир.'})
    assert candidate.base['scene_steps'][1]==p['scene_steps'][1]
    assert len(raw.records['movements'])==1


def test_destination_schema_replaces_endpoint_and_preserves_other_domains():
    from backend.runtime_v3.scene_steps import input_schema
    from backend.services.structured_extraction import request_schema
    from devtools.issue257.destination_prototype import project
    from jsonschema import Draft202012Validator
    original=input_schema(7,'actor')
    messages=[{'role':'system','content':'Rules'}, {'role':'user','content':'JSON Schema\n'+json.dumps(original)}]
    changed=project(messages);schema=request_schema(changed)
    Draft202012Validator.check_schema(schema)
    for k in original['properties']:
        if k!='scene_steps':assert schema['properties'][k]==request_schema(messages)['properties'][k]
    p={'scene':{'elapsed_minutes':1},'scene_steps':[{'id':'m','text':'Arrived','kind':'movement','assertion':'completed_arrival','actor_ids':['a'],'destination':{'existing_id':'park'}}]}
    assert not list(Draft202012Validator(schema).iter_errors(p))
    p['scene_steps'][0]['endpoint']='park'
    assert list(Draft202012Validator(schema).iter_errors(p))
