"""Authored controls only; model qualification is separate."""
import json
from copy import deepcopy
from functools import partial
import pytest
from test_scene_steps255 import fixture
from backend.runtime_v3.scene_steps import input_schema
from backend.services.structured_extraction import request_schema
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.issue259.compound import project, CompoundCandidate


pytestmark = pytest.mark.extraction_v8


def setup():
 s,_=fixture();messages=project([{'role':'system','content':''},{'role':'user','content':'JSON Schema\n'+json.dumps(input_schema(8,'actor'))}]);schema=request_schema(messages)
 c=CompoundCandidate(s,'Они пришли в парк. По дороге b рассказал о встрече.','Иду с b в парк.',1,version=8,schema=schema)
 p={'scene':{'elapsed_minutes':5},'scene_steps':[{'id':'walk','evidence':'Пришли в парк; по дороге b рассказал о встрече.','effects':[
 {'kind':'movement','actor_ids':['a','b'],'assertion':'completed_arrival','destination':{'existing_id':'park'},'input_source':{'quote':'Иду с b в парк.','meaning':'preserved'}},
 {'kind':'information','source_actor_id':'b','target_ids':['a'],'medium':'conversation','channel':'physical','during':0,'claims':[{'fact':{'text':'Вчера состоялась встреча.'},'assertion':'testimony','perceived_by':['a'],'status':'known'}]}]}]}
 return s,c,p


def resolve(s,c,p):
 return StateResolver(s,c.narrative,c.player_input,turn_id=1,**resolver_options(s,c.player_input,contract_version=8)).resolve(c.parse(p,defer_errors=True))


def test_compound_arrival_hearing_and_stable_identity():
 s,c,p=setup();r=resolve(s,c,p)
 assert all(r.state['characters'][a]['location_id']=='park' for a in ['a','b'])
 assert [k['actor_id'] for k in r.history['knowledge_acquisitions']]==['a']
 assert r.history['events'][1]['during_event_id']==r.history['events'][0]['id']
 assert resolve(s,c,p).history==r.history
 assert s['characters']['a']['location_id']=='home'


def test_arrival_bystander_not_hearer():
 s,c,p=setup();p['scene_steps'][0]['effects'][1]['claims'][0]['perceived_by']=['c']
 with pytest.raises(StructuralDeltaError):resolve(s,c,p)


def test_no_change_and_domain_expressiveness():
 s,c,p=setup();p['scene_steps']=[];r=resolve(s,c,p)
 assert not r.history['events'] and r.state['characters']==s['characters']
 old=input_schema(8,'actor')['properties'];new=c.schema['properties']
 assert set(old)==set(new)
 assert new['births']==old['births']
 assert 'situation' not in new['scene']['properties']


def test_scoped_repair_keeps_independent_source_and_hash():
 s,c,p=setup();p['scene_steps'][0]['effects'][0].pop('input_source')
 p['scene_steps'].append({'id':'independent','evidence':'b замечает свет.','effects':[{'kind':'occurrence','actor_ids':['b']}]})
 with pytest.raises(StructuralDeltaError) as exc:resolve(s,c,p)
 feedback=json.loads(c.feedback(exc.value.diagnostics('test'),json.dumps(p)))
 assert feedback['diagnostics'][0]['path']=='scene_steps[0].effects[0].input_source'
 fixed=deepcopy(p['scene_steps'][0]);fixed['effects'][0]['input_source']={'quote':c.player_input,'meaning':'preserved'}
 patch={'candidate_hash':feedback['candidate_hash'],'replacements':[fixed],'sections':{},'reason':'Restore actual input source.'}
 r=resolve(s,c,patch)
 assert c.base['scene_steps'][1]==p['scene_steps'][1]
 assert r.state['characters']['a']['location_id']=='park'
 patch['candidate_hash']='wrong'
 with pytest.raises(StructuralDeltaError):c.parse(patch)


def test_compound_through_production_job_reload_and_rollback(tmp_path):
 from unittest.mock import patch
 import engine
 from backend.repositories.preparation import Repository
 from test_integrated_repair247 import seed, archived, execute
 from backend.runtime_v3.scene_steps import input_schema
 from backend.services.structured_extraction import request_schema
 with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
  data=archived('knowledge');repo=Repository(tmp_path/'compound.sqlite');sid=seed(repo,data)['save']
 data['narrative']='Кирилл дошёл до парка.';data['player_input']='Иду в парк.'
 actor=repo.get_snapshot(sid)['world_state']['camera']['controlled_actor_id']
 p={'scene':{'elapsed_minutes':5},'scene_steps':[{'id':'walk','evidence':data['narrative'],'effects':[{'kind':'movement','actor_ids':[actor],'assertion':'completed_arrival','destination':{'name':'Парк','anchor_id':repo.get_snapshot(sid)['world_state']['characters'][actor]['location_id'],'relation':'вне дома'},'input_source':{'quote':data['player_input'],'meaning':'preserved'}}]}]}
 schema=request_schema(project([{'role':'system','content':''},{'role':'user','content':'JSON Schema\n'+json.dumps(input_schema(8,'actor'))}]))
 # Explicit test seam only: production does not select the unqualified adapter.
 with patch('backend.runtime_v3.scene_repair.SceneCandidate',partial(CompoundCandidate,schema=schema)):
  job,_=execute(repo,sid,data,[p],legacy=False)
 assert job['status']=='saved',job['error']
 fresh=Repository(repo.path);after=fresh.get_snapshot(sid)
 loc=after['world_state']['characters'][actor]['location_id']
 assert after['world_state']['locations'][loc]['name']=='Парк'
 fresh.rollback_last(sid)
 assert fresh.get_snapshot(sid)['world_state']['characters'][actor]['location_id']!=loc


def test_repair_cannot_drop_other_consequences_in_same_source():
 s,c,p=setup();p['scene_steps'][0]['effects'][0].pop('input_source')
 with pytest.raises(StructuralDeltaError) as exc:resolve(s,c,p)
 f=json.loads(c.feedback(exc.value.diagnostics('test'),json.dumps(p)))
 replacement=deepcopy(p['scene_steps'][0]);replacement['effects']=replacement['effects'][:1]
 with pytest.raises(StructuralDeltaError):c.parse({'candidate_hash':f['candidate_hash'],'replacements':[replacement],'sections':{},'reason':'Drop speech to save movement.'})


def test_single_effect_reference_alias_and_external_authority_feedback():
 from devtools.issue259.compound import expand
 p={'scene':{},'scene_steps':[{'id':'source','evidence':'Сообщение.','effects':[{'kind':'occurrence','actor_ids':['a']}]}], 'thread_changes':[{'id':'t','source_event_id':'source/0'}]}
 expanded,_=expand(p)
 assert expanded['scene_steps'][0]['id']=='source'
 assert expanded['thread_changes'][0]['source_event_id']=='source'
 s,c,p=setup();c.parse(p)
 f=json.loads(c.feedback([{'section':'scene_steps','index':1,'code':'player_action_event_mismatch','reason':'missing_player_action_id','repair_reason':'Specify internal player_action_id'}],json.dumps(p)))
 row=f['diagnostics'][0]
 assert row['path']=='scene_steps[0].effects[1].input_source'
 assert 'unrelated genuine input quote' in row['repair_reason'] and 'unauthorized_choice' in row['repair_reason']
 assert 'player_action_id' not in row['repair_reason']
