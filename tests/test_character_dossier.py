"""Dossier is a projection: conditions cannot become a second health model."""
from copy import deepcopy
import pytest
from test_life_social import state, snapshot, inform
from backend.runtime_v3.models import Condition
from backend.runtime_v3.dossier import details
from backend.runtime_v3.selectors import ui_view

@pytest.mark.parametrize('transient,condition', [('',False),('Устал',False),('',True),('Промок',True)])
def test_transient_and_condition_stay_independent(transient, condition):
    s=state();s['characters']['a']['physical_state']=transient
    if condition:s['conditions']['injury']=Condition(id='injury',actor_id='a',description='Повреждение ноги',effects={'can_move':False},evidence='Упал').model_dump()
    before=deepcopy(s);view=ui_view(snapshot(s));card=next(c for c in view['characters'] if c['id']=='a')
    assert view['world']['characters']['a']['physical_state']==transient
    assert len(card['dossier']['conditions'])==int(condition)
    if condition:assert card['dossier']['conditions'][0]['restrictions']==['can_move']
    assert s==before


def test_hidden_condition_cannot_leak_through_capability_or_provenance():
    s=state();inform(s,'secret',['b'],{'b':'known'})
    s['conditions']['hidden']=Condition(id='hidden',actor_id='b',description='SECRET CONDITION',fact_id='secret',effects={'conscious':False},evidence='SECRET EVIDENCE').model_dump()
    assert details(s,'b')['conditions']==[]
    assert details(s,'b')['restrictions']==[]
    inform(s,'secret',['b'],{'a':'known','b':'known'})
    assert details(s,'b')['conditions'][0]['restrictions']==['conscious']
    s['camera']['controlled_actor_id']='c'
    assert details(s,'b')['conditions']==[]


def test_resolved_condition_is_history_not_active_restriction_and_legacy_has_no_invented_health():
    s=state();s['conditions']['old']=Condition(id='old',actor_id='a',description='Устал',status='resolved',effects={'can_act':False}).model_dump()
    assert details(s,'a')['conditions'][0]['status']=='resolved'
    assert details(s,'a')['restrictions']==[]
    s.pop('conditions')
    assert details(s,'a')['conditions']==[]
    assert details(s,'b')['sex']=='neutral'


def test_explicit_incapacitation_and_sex_not_inferred_from_names():
    s=state();s['characters']['a']['capabilities']['can_act']=False
    s['characters']['a']['biological_sex']='female'
    assert details(s,'a')['restrictions']==['can_act']
    assert details(s,'a')['sex']=='female'
    s['characters']['a']['biological_sex']='unknown'
    assert details(s,'a')['sex']=='neutral'


def test_api_projection_survives_storage_reload_without_mutating_save(tmp_path):
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    app=create_app(tmp_path/'game.sqlite',recover=False)
    repo=app.state.repository;sid=load_fixture(repo,'ui-dossier')['save']
    original=deepcopy(repo.get_snapshot(sid))
    client=TestClient(app)
    first=client.get(f'/api/saves/{sid}').json()
    rows={c['id']:c['dossier'] for c in first['state']['characters']}
    assert rows[ACTOR_ID]['conditions'][0]['description']=='Повреждение ноги'
    assert not rows['qa_vera']['conditions']
    assert 'dossier-hidden' not in first['state']['world']['facts']
    assert not any(k['fact_id']=='dossier-hidden' for k in first['state']['world']['knowledge'].values())
    # A new application/connection reconstructs the projection from the same save.
    second=TestClient(create_app(tmp_path/'game.sqlite',recover=False)).get(f'/api/saves/{sid}').json()
    assert [c['dossier'] for c in second['state']['characters']]==[c['dossier'] for c in first['state']['characters']]
    assert repo.get_snapshot(sid)==original
