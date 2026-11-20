import json
from copy import deepcopy

import pytest

from backend.runtime_v3.models import ProceduralPortraitV3
from backend.runtime_v3.portrait_catalog import CATALOG
from backend.services.draft_portraits import default_descriptor, initialize
from backend.services.portrait_traits import input_schema
from test_workshop_portraits import fixture


def test_new_classic_faces_have_independent_persisted_features():
    hints = dict(form='human', face='broad', hair='parted', clothing='shirt')
    cast = [default_descriptor(str(i), 'adult', hints=hints, version=3, world_id='same')
            for i in range(72)]
    for field, options in CATALOG['features'].items():
        assert {p[field] for p in cast} == set(options)
        assert set(input_schema()['properties'][field]['enum']) == set(options)
    for p in cast:
        assert (p['visage'], p['hairstyle'], p['garment'], p['face_revision']) == ('broad','parted','shirt',4)
    assert cast[0] == default_descriptor('0','adult',hints=hints,version=3,world_id='same')
    old = deepcopy(cast[0])
    old['face_revision'] = 3
    del old['body_build']
    state = fixture()
    cid = state['characters'][0]['id']
    state['world']['characters'][cid]['procedural_portrait'] = old
    initialize(state, version=3)
    assert state['world']['characters'][cid]['procedural_portrait'] == old
    assert 'body_build' not in ProceduralPortraitV3.model_validate(old).model_dump()


@pytest.mark.parametrize('editing',[True,False])
def test_creative_and_editor_honor_classic_traits_in_existing_worlds(editing):
    from test_draft_editor_paths import recorded
    from backend.repositories.drafts import candidate_hash
    from backend.services.draft_changes import apply_proposal
    sample = recorded()
    state = sample['base']['state']
    state['creation_settings'] = {**state.get('creation_settings',{}), 'portrait_style':'semi_realistic'}
    packet = json.loads(sample['reply'])
    packet['candidate_hash'] = candidate_hash(state)
    hints = dict(form='human',face='angular',eye_shape='hooded',body_build='full',nose_shape='arched',lip_shape='fine')
    packet['changes'][1]['value']['portrait_traits'] = hints
    updated,_ = apply_proposal(state,json.dumps(packet),editing=editing)
    art = updated['world']['characters']['olya']['procedural_portrait']
    assert art['version'] == 3 and art['face_revision'] == 4 and art['visage'] == 'angular'
    assert all(art[k] == hints[k] for k in CATALOG['features'])


def test_open_body_description_and_explicit_infant_choices():
    actor = {'appearance': {'items': {'body': {'kind':'build','text':'Широкоплечее'}}}}
    art = default_descriptor('a', 'adult', actor, {'body_build':'slender'}, version=3)
    assert art['body_build'] == 'broad'
    baby = default_descriptor('b','infant',hints={'hair':'braid','clothing':'dress','hair_color':'white'},version=3)
    assert baby['hairstyle'] == 'braid' and baby['garment'] == 'dress' and baby['hair_color'] == 6
