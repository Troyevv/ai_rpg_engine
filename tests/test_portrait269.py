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
        assert p['eye_revision'] == p['cheek_revision'] == p['nose_revision'] == 2
        assert (p['visage'], p['hairstyle'], p['garment'], p['face_revision']) == ('broad','parted','shirt',4)
    assert cast[0] == default_descriptor('0','adult',hints=hints,version=3,world_id='same')
    old = deepcopy(cast[0])
    old['face_revision'] = 3
    del old['nose_revision']
    del old['cheek_revision']
    del old['body_build']
    state = fixture()
    cid = state['characters'][0]['id']
    state['world']['characters'][cid]['procedural_portrait'] = old
    initialize(state, version=3)
    assert state['world']['characters'][cid]['procedural_portrait'] == old
    restored = ProceduralPortraitV3.model_validate(old).model_dump()
    assert 'body_build' not in restored and 'cheek_revision' not in restored and 'nose_revision' not in restored


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
    hints = dict(form='human',face='diamond', hair='crown_braid', clothing='mantle', eye_shape='downturned',
                 body_build='athletic', nose_shape='broad_base', lip_shape='cupid', eyewear='round_wire',
                 face_detail='beauty_mark', hair_color='white', clothing_color='plum', accent_color='bronze')
    packet['changes'][1]['value']['portrait_traits'] = hints
    updated,_ = apply_proposal(state,json.dumps(packet),editing=editing)
    art = updated['world']['characters']['olya']['procedural_portrait']
    assert art['version'] == 3 and art['face_revision'] == 4 and art['visage'] == 'diamond'
    assert (art['hairstyle'], art['garment'], art['hair_color'], art['clothing_color'], art['accent_color']) == ('crown_braid','mantle',6,11,19)
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


def test_explicit_gaze_update_preserves_every_other_trait_and_old_versions(api):
    from test_workshop_portraits import create
    from test_portraits import image
    client, _ = api
    state = fixture()
    ids = [card['id'] for card in state['characters']][:4]
    actors = state['world']['characters']
    for i, cid in enumerate(ids):
        art = default_descriptor(cid, 'adult', version=3, world_id='previous')
        art.pop('eye_revision')
        art['face_revision'] = 3 if i == 0 else 2 if i == 2 else 4
        actors[cid].update(procedural_portrait=art, portrait_mode='procedural')
    url, draft = create(client, state)
    photo = client.post(url+f'/characters/{ids[3]}/portraits',params={'revision':draft['revision']},
                        content=image(),headers={'content-type':'image/png'})
    assert photo.status_code == 200
    before = client.get(url+'?author=true').json()
    def art(d, cid):
        return d['state']['world']['characters'][cid]['procedural_portrait']
    assert [c for c in ids if before['portraits'][c].get('can_update_eyes')] == ids[:2]
    def update(revision):
        return client.post(url+'/portraits/update-eyes',params={'revision':revision})
    assert update(before['revision']).json() == {'updated':2}
    assert update(before['revision']).status_code == 409
    after=client.get(url+'?author=true').json()
    for i,cid in enumerate(ids):
        assert art(after,cid)==({**art(before,cid),'eye_revision':2} if i<2 else art(before,cid))
        assert after['state']['world']['characters'][cid]['portrait_mode']==before['state']['world']['characters'][cid]['portrait_mode']
    assert update(after['revision']).json() == {'updated':0}
    restored=client.patch(url,json=dict(revision=after['revision'],operation='restore',source_id=before['version_id']))
    assert restored.status_code==200
    assert all(art(restored.json(),cid)==art(before,cid) for cid in ids)


def test_full_classic_catalog_is_reachable_without_hints_and_survives_reload():
    from collections import Counter
    outfits = set()
    for profile, wardrobe in CATALOG['wardrobes'].items():
        adults = [default_descriptor(str(i), 'adult', {'biological_sex':'male'}, version=3,
                                     world_id='sample-'+profile, profile=profile) for i in range(768)]
        assert {p['garment'] for p in adults} == set(wardrobe)
        outfits.update(wardrobe)
        for key, layer in [('hair','hairstyle'), ('face','visage'), ('facial_hair','facial_hair')]:
            counts = Counter(p[layer] for p in adults)
            assert set(counts) == set(CATALOG['styles'][key]) and min(counts.values()) >= 3
        assert len({(p['hairstyle'], p['visage'], p['garment']) for p in adults}) > 600
        assert {p['clothing_color'] for p in adults} == {p['accent_color'] for p in adults} == set(range(20))
        if profile == 'modern':
            assert {p['hair_color'] for p in adults} == set(range(16))
        for p in adults[:8]:
            assert ProceduralPortraitV3.model_validate_json(json.dumps(p)).model_dump() == p
    infants = [default_descriptor(str(i),'infant',version=3,profile='modern') for i in range(64)]
    assert all(p['eyewear']=='none' and p['facial_hair']=='clean_shaven' for p in infants)
    assert outfits.union(p['garment'] for p in infants) == set(CATALOG['styles']['clothing'])


@pytest.mark.parametrize('revision', [3, 4])
def test_a_nose_proposal_preserves_saved_eyes_and_other_layers(revision):
    from backend.services.portrait_proposals import proposed
    old = default_descriptor('dossier','adult',version=3,world_id='original')
    old['face_revision'] = revision
    for key in ('nose_revision','eye_revision','cheek_revision'):
        old.pop(key)
    ref = dict(existing=old, art_style='legacy', approved={}, actor={}, world_id='imported',
               stage='adult', age='young_adult', profile='modern')
    for shape in CATALOG['features']['nose_shape']:
        art = proposed('dossier', {'nose_shape':shape}, ref)['descriptor']
        assert art == {**old, 'nose_shape':shape, 'nose_revision':2}
