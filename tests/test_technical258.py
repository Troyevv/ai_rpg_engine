"""Free controls: provider output is authored unless fixture provenance says otherwise."""
import json
from copy import deepcopy
import pytest
from backend.runtime_v3.structured_payload import object_payload
from backend.runtime_v3.scene_steps import input_schema
from backend.runtime_v3.scene_repair import SceneCandidate, repair_schema
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError
from test_scene_steps255 import fixture

pytestmark=pytest.mark.extraction_v8

@pytest.mark.parametrize('wrapper',['{}','```json\n{}\n```','```\n{}\n```'])
def test_single_object(wrapper):
    p={'text':'literal ``` within a JSON string','nested':{'value':1}}
    result,normalization=object_payload(' \n'+wrapper.format(json.dumps(p))+' \n')
    assert result==p
    assert bool(normalization)==wrapper.startswith('```')

@pytest.mark.parametrize('payload',['[]','null','1','{} {}','text\n```json\n{}\n```','```json\n{}\n```\ntrailer','```python\n{}\n```','```json\n{}\n```\n```json\n{}\n```','```json\n{"a":\n```','{"a":1,"a":2}'])
def test_ambiguous_or_incomplete(payload):
    with pytest.raises(ValueError):object_payload(payload)


def candidate():
    s,_=fixture();text='Иду с b в парк.'
    p={'scene':{'elapsed_minutes':1},'scene_steps':[dict(id='walk',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='park',text='Пришли.',input_source=dict(quote=text,meaning='preserved'))]}
    return s,text,p,SceneCandidate(s,'Пришли.',text,1,version=8)


def test_new_movement_no_addressee_work_legacy_not_reinterpreted():
    s,text,p,c=candidate();bad=deepcopy(p);bad['scene_steps'][0]['input_source']['intended_target_ids']=['b']
    with pytest.raises(StructuralDeltaError) as exc:c.parse(bad)
    feedback=json.loads(c.feedback(exc.value.diagnostics('repair'),json.dumps(bad)))
    assert feedback['diagnostics'][0]['path']=='scene_steps[0].input_source.intended_target_ids'
    assert feedback['diagnostics'][0]['local_id']=='walk'
    assert 'Remove inapplicable' in feedback['diagnostics'][0]['repair_reason']
    # Same repair schema shares v8 step types, rather than accepting/dropping the invalid field.
    from jsonschema import Draft202012Validator
    patch=dict(candidate_hash=feedback['candidate_hash'],replacements=p['scene_steps'],sections={},reason='Remove movement-only mismatch, preserve travellers.')
    assert not list(Draft202012Validator(repair_schema(input_schema(8,'actor'),json.dumps(feedback))).iter_errors(patch))
    raw=c.parse('```json\n'+json.dumps(patch)+'\n```')
    result=StateResolver(s,'Пришли.',text,turn_id=1,**resolver_options(s,text,contract_version=8)).resolve(raw)
    assert result.state['characters']['a']['location_id']==result.state['characters']['b']['location_id']=='park'
    assert not result.history['knowledge_acquisitions']
    assert raw.player_agency['actions'][0]['target_ids']==[]
    assert any(w['code']=='structured_payload_normalized' for w in raw.warnings)
    old=SceneCandidate(s,'Пришли.',text,1,version=7).parse(bad)
    with pytest.raises(StructuralDeltaError) as old_error:StateResolver(s,'Пришли.',text,turn_id=1,**resolver_options(s,text,contract_version=7)).resolve(old)
    assert 'player_action_targets_inconsistent' in str(old_error.value.code)


def test_fenced_patch_keeps_stale_protection():
    s,text,p,c=candidate();c.parse(p)
    c.feedback([dict(section='scene_steps',index=0,code='movement_agency')],json.dumps(p))
    with pytest.raises(StructuralDeltaError) as exc:c.parse('```json\n'+json.dumps(dict(candidate_hash='wrong',replacements=[],sections={},reason='test'))+'\n```')
    assert exc.value.code=='scene_repair_stale'


def test_original_river_pair_and_refusal_diagnostics():
    from pathlib import Path
    from devtools.issue257.destination_prototype import adapt
    from backend.runtime_v3.models import Location
    originals=json.loads((Path(__file__).parent/'fixtures/issue258/original-steps.json').read_text())
    s,_=fixture()
    # Only the before fixture is authored. The provider source step stays verbatim.
    for cid in ('char_alexey','char_galina'):
        s['characters'][cid]=deepcopy(s['characters']['a' if cid=='char_alexey' else 'b'])
        s['characters'][cid]['id']=cid
    s['camera']['controlled_actor_id']='char_alexey'
    s['locations']['loc_berezovsk']=Location(id='loc_berezovsk',name='Берёзовск').model_dump()
    original=originals['river'];first=original['responses'][0]['scene_steps'][0];repaired=original['responses'][1]['replacements'][0]
    assert first==repaired
    payload=adapt(dict(scene={},scene_steps=[first]),s,1)
    c=SceneCandidate(s,original['narrative'],original['player_input'],1,version=8)
    with pytest.raises(StructuralDeltaError) as exc:c.parse(payload)
    feedback=json.loads(c.feedback(exc.value.diagnostics('test'),json.dumps(payload)))
    assert feedback['diagnostics'][0]['path'].endswith('.input_source.intended_target_ids')
    assert feedback['diagnostics'][0]['local_id']=='step_50_01'
    refusal=originals['unrequested_refusal'];p=dict(scene={},scene_steps=refusal['responses'][0]['scene_steps'])
    c=SceneCandidate(s,refusal['narrative'],refusal['player_input'],1,version=8);c.parse(p)
    feedback=json.loads(c.feedback([dict(section='scene_steps',index=2,code='player_action_source_invalid')],json.dumps(p)))
    d=feedback['diagnostics'][0]
    assert d['player_input']==refusal['player_input'] and d['supplied_quote']!=d['player_input']
    assert d['path']=='scene_steps[2].input_source.quote'
    assert 'agency_findings' in d['repair_reason']


def test_movement_feedback_never_requests_internal_authority_fields():
    s,text,p,c=candidate();p['scene_steps'][0].pop('input_source')
    with pytest.raises(StructuralDeltaError) as exc:c.parse(p)
    info=json.loads(c.feedback(exc.value.diagnostics('repair'),json.dumps(p)))
    row=next(d for d in info['diagnostics'] if d['code']=='movement_agency')
    assert row['path']=='scene_steps[0].input_source'
    assert row['player_input']==text
    assert 'involuntary_source_id' in row['repair_reason']
    assert 'explicit_choice' not in row['repair_reason'] and 'player_action_id' not in row['repair_reason']


def test_narrative_recovery_hint_uses_visible_contract():
    s,text,p,c=candidate();c.parse(p)
    info=json.loads(c.feedback([dict(section='scene_steps',index=0,code='event_presence_invalid',repair_reason='Use player_agency.status=violated for an unchosen act.')],json.dumps(p)))
    row=info['diagnostics'][0]
    assert 'player_agency.status' not in row['repair_reason']
    assert 'agency_findings' in row['repair_reason']
    assert 'player_agency.status' in row['compiled_reason']
