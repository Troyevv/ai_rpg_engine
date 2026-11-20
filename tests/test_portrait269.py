import json
from copy import deepcopy

import pytest

from backend.runtime_v3.models import ProceduralPortraitV3
from backend.runtime_v3.portrait_catalog import CATALOG
from backend.services.draft_portraits import default_descriptor, initialize
from backend.services.portrait_traits import input_schema
from test_api import api
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


@pytest.mark.parametrize('version',[1,2,3])
def test_partial_description_preserves_an_imported_portrait(version):
    from backend.services.portrait_proposals import proposed
    actor = {'biological_sex':'female'}
    old = default_descriptor('original','adult',actor,version=version,world_id='original')
    if version == 3:
        old.update(face_revision=3, skin_swatch=False, eye_swatch=False)
        old.pop('body_build')
    reference = dict(existing=old, art_style='legacy', approved={}, actor=actor,
                     world_id='imported', stage='adult', age='young_adult', profile='neutral')
    art = proposed('local-id', {'hair':'bun'}, reference)['descriptor']
    allowed = {'hair','hairstyle','version'}
    assert {k:art[k] for k in old if k not in allowed} == {k:v for k,v in old.items() if k not in allowed}
    assert art['hairstyle'] == 'bun' and 'body_build' not in art
    if version < 3:
        assert art['base_version'] == version and 'face_revision' not in art
        assert art['garment'] is None and art['visage'] is None
        assert not art['eye_swatch'] and not art['skin_swatch']


def test_manual_new_dossier_draws_without_inventing_a_canonical_age(api):
    from test_workshop_portraits import create
    client, _ = api
    url, draft = create(client)
    response = client.patch(url, json=dict(revision=draft['revision'], operation='add', kind='character',
                                           value={'name':'Ирина'}, warnings_ack=True))
    assert response.status_code == 200, response.text
    result = response.json()
    cid = result['entity_id']
    art = result['portraits'][cid]['procedural_portrait']
    assert (art['version'], art['face_revision'], art['form'], art['stage']) == (3, 4, 'human', 'unknown')
    assert not result['state']['world']['characters'][cid].get('birth_date')
    assert all(result['portraits'][k] == p for k,p in draft['portraits'].items())
