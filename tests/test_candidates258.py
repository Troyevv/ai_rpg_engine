"""Authored semantic prototype controls, not evidence of model accuracy."""
import json
from copy import deepcopy
import pytest
from test_scene_steps255 import fixture
from devtools.issue258.candidates import SemanticCandidate
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError


def test_speech_perceivers_not_addressees_and_partial_secret():
    s,_=fixture();p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='news',kind='speech',source_actor_id='b',target_ids=['a'],outcome='completed',medium='conversation',channel='physical',text='Сообщил о встрече.',claims=[dict(fact=dict(text='Вчера состоялся разговор.'),assertion='testimony',perceived_by=['a'],status='known')])])
    c=SemanticCandidate(s,'Сообщил о встрече.','Слушаю.',1,version=8,speech=True)
    raw=c.parse(p);result=StateResolver(s,'Сообщил о встрече.','Слушаю.',turn_id=1,**resolver_options(s,'Слушаю.',contract_version=8)).resolve(raw)
    assert len(result.history['knowledge_acquisitions'])==1
    assert result.history['knowledge_acquisitions'][0]['actor_id']=='a'
    assert len(result.history['events'])==1
    assert result.history['events'][0]['id']==result.history['knowledge_acquisitions'][0]['source_event_id']
    p['scene_steps'][0]['claims'][0]['perceived_by']=[]
    with pytest.raises(StructuralDeltaError):c.parse(p)  # no inferred recipients from target_ids


def test_empty_question_and_explicit_assessment_no_permission():
    s,_=fixture();p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='question',kind='speech',source_actor_id='b',target_ids=['a'],outcome='completed',medium='conversation',channel='physical',text='Как дела?',claims=[])],semantic_reviews=[dict(domain='agency',assessment='unassessed',findings=[]),dict(domain='time',assessment='not_applicable',claims=[])])
    c=SemanticCandidate(s,'Как дела?','Слушаю.',1,version=8,speech=True,review=True)
    raw=c.parse(p)
    assert raw.player_agency['status']=='uncertain'
    result=StateResolver(s,'Как дела?','Слушаю.',turn_id=1,**resolver_options(s,'Слушаю.',contract_version=8)).resolve(raw)
    assert not result.history['knowledge_acquisitions']
    assert len(result.history['events'])==1
    p['semantic_reviews'][0]['findings']=[dict(narrative_evidence='Игрок отказался без выбора.',classification='unauthorized_choice')]
    p['semantic_reviews'][0]['assessment']='no_significant_conflict'
    # Status cannot override an actual finding.
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Как дела?','Слушаю.',turn_id=1,**resolver_options(s,'Слушаю.',contract_version=8)).resolve(c.parse(p))


def test_route_speech_does_not_grant_arrival_bystander_earlier_knowledge():
    s,_=fixture();text='Иду с b в парк.'
    p=dict(scene=dict(elapsed_minutes=5),scene_steps=[dict(id='walk',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',destination={'existing_id':'park'},text='Дошли.',input_source=dict(quote=text,meaning='preserved')),dict(id='news',kind='speech',source_actor_id='b',target_ids=['a'],outcome='completed',medium='conversation',channel='physical',during_step_id='walk',text='По дороге сообщил о встрече.',claims=[dict(fact=dict(text='Вчера состоялась встреча.'),assertion='testimony',perceived_by=['a'],status='known')])])
    def run(p):
        c=SemanticCandidate(s,'По дороге сообщил.',text,1,version=8,speech=True)
        return StateResolver(s,'По дороге сообщил.',text,turn_id=1,**resolver_options(s,text,contract_version=8)).resolve(c.parse(p))
    good=run(p);assert [k['actor_id'] for k in good.history['knowledge_acquisitions']]==['a']
    p['scene_steps'][1]['claims'][0]['perceived_by']=['c']
    with pytest.raises(StructuralDeltaError):run(p)


def test_review_repair_keeps_same_source_and_independent_step():
    s,_=fixture();text='Слушаю.'
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='hello',kind='interaction',actor_id='b',target_ids=['a'],outcome='completed',text='Поздоровался.')],semantic_reviews=[dict(domain='agency',assessment='unassessed',findings=[]),dict(domain='time',assessment='unassessed',claims=[])])
    c=SemanticCandidate(s,'Поздоровался.',text,1,version=8,review=True)
    c.parse(p);info=json.loads(c.feedback([dict(section='scene_steps',index=0,code='player_action_source_invalid')],json.dumps(p)))
    patch=dict(candidate_hash=info['candidate_hash'],replacements=[],sections={'semantic_reviews':[dict(domain='agency',assessment='no_significant_conflict',findings=[]),dict(domain='time',assessment='not_applicable',claims=[])]},reason='Authored explicit assessment.')
    raw=c.parse(patch)
    assert c.base['scene_steps']==p['scene_steps']
    assert c.narrative=='Поздоровался.'
    assert not raw.records['knowledge_gained']


def test_duplicate_source_ids_use_full_repair_not_an_ambiguous_patch():
    s,_=fixture();step=dict(id='same',kind='interaction',actor_id='b',target_ids=['a'],outcome='completed',text='Поздоровался.')
    p=dict(scene={},scene_steps=[step,deepcopy(step)])
    c=SemanticCandidate(s,'Приветствие.','Слушаю.',1,version=8)
    with pytest.raises(StructuralDeltaError) as exc:c.parse(p)
    assert json.loads(c.feedback(exc.value.diagnostics('test'),json.dumps(p)))['repair_mode']=='full'
