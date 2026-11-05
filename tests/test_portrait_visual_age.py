from copy import deepcopy
import pytest
from backend.runtime_v3 import portraits
from backend.services.draft_portraits import default_descriptor, initialize, portrait_state
from test_draft_world import fixture

@pytest.mark.parametrize('age,stage,expected',[(0,'infant','infant'),(1,'infant','infant'),(2,'child','child'),(12,'child','child'),(13,'adolescent','adolescent'),(17,'adolescent','adolescent'),(18,'adult','young_adult'),(34,'adult','young_adult'),(35,'adult','mature_adult'),(59,'adult','mature_adult'),(60,'adult','elderly'),(90,'adult','elderly')])
def test_visual_age_uses_canonical_period(monkeypatch,age,stage,expected):
    monkeypatch.setattr(portraits,'life_period',lambda state,cid:(age,stage))
    assert portraits.visual_age({},'a')==expected
    p=default_descriptor('a',stage,age_style=expected)
    assert p['visual_age']==expected and p['form']=='human'


def test_initialize_preserves_saved_art_and_runtime_age():
    state=fixture();cid=state['characters'][0]['id']
    runtime=portrait_state(state)
    initialize(state)
    assert state['world']['characters'][cid]['procedural_portrait'].get('visual_age')==portraits.visual_age(runtime,cid)
    saved=deepcopy(state['world']['characters'][cid]['procedural_portrait'])
    state['world_clock']['minute']+=365*1440*10
    initialize(state)
    assert state['world']['characters'][cid]['procedural_portrait']==saved


def test_old_descriptor_keeps_sparse_shape():
    from backend.runtime_v3.models import ProceduralPortrait
    old=default_descriptor('old','adult')
    assert 'visual_age' not in old
    assert ProceduralPortrait.model_validate(old).model_dump()==old


def test_real_calendar_boundaries_and_saved_descriptor():
    from backend.runtime_v3.portraits import projection
    from backend.services.draft_portraits import initialize, portrait_state
    state=fixture();cid=state['characters'][0]['id'];actor=state['world']['characters'][cid]
    state['world_clock']['calendar']={'start_minute':0,'start_date':'2026-01-01','start_weekday':3,'profile':{'id':'gregorian','system':'gregorian'}}
    state['world_clock']['minute']=0
    actor.update(birth_date='1991-01-02',developmental_stage='adult')
    actor.pop('procedural_portrait',None)
    initialize(state);saved=deepcopy(actor['procedural_portrait'])
    assert saved['visual_age']=='young_adult'
    state['world_clock']['minute']=1440
    runtime=portrait_state(state)
    assert portraits.visual_age(runtime,cid)=='mature_adult'
    assert projection(runtime,cid)['procedural_portrait']==saved
    assert actor['developmental_stage']=='adult'
