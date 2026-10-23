from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from backend.runtime_v3.models import AppearanceFeature, AppearanceProfile
from backend.services.generated_appearance import normalize_batch, character_schema
from backend.services.initial_world_stages import CharactersPart
from test_api import api
from test_world_blueprint import short_provider, submit
from test_world_generation import wait


def batch(items):
    return {'characters': {'actor': {'appearance': {'items': items, 'legacy_text': 'Исходное описание'}}}}


def test_category_mismatch_is_reproduced_and_normalized_without_runtime_changes():
    items = {'hair': dict(category='presentation', kind='natural_hair_color', text='От природы каштановые волосы'),
             'style': dict(category='intrinsic', kind='hairstyle', text='Короткая стрижка')}
    for item in items.values():
        with pytest.raises(ValueError, match='category/kind mismatch'):
            AppearanceFeature.model_validate(item)
    raw = batch(items); before = deepcopy(raw)
    result = normalize_batch(raw)
    profile = AppearanceProfile.model_validate(result['characters']['actor']['appearance'])
    assert profile.items['hair'].category == 'intrinsic'
    assert profile.items['style'].category == 'presentation'
    assert [i.text for i in profile.items.values()] == [i['text'] for i in items.values()]
    assert raw == before and normalize_batch(result) == result


@pytest.mark.parametrize('kind,text', [('hair_color','Розовые волосы'), ('clothing','Синий пиджак и джинсы'),
    ('style','Короткие волосы, очки и клетчатая рубашка'), ('appearance','Рыжие кудри, веснушки, чёрное пальто')])
def test_unclassified_prose_is_preserved_without_inventing_traits(kind, text):
    result = normalize_batch(batch({'visual':dict(category='presentation',kind=kind,text=text)}))
    profile = AppearanceProfile.model_validate(result['characters']['actor']['appearance'])
    assert not profile.items
    assert profile.legacy_text == 'Исходное описание\n' + text
    assert normalize_batch(result) == result


@pytest.mark.parametrize('extra', [{'condition_id':'injury'}, {'source_event_id':'event'}, {'revision':2}, {'unknown':'data'}])
def test_invalid_or_evidence_bearing_prose_is_not_silently_discarded(extra):
    raw = batch({'outfit': dict(category='presentation',kind='clothing',text='Пальто',**extra)})
    assert normalize_batch(raw) == raw
    with pytest.raises(ValueError):
        AppearanceProfile.model_validate(raw['characters']['actor']['appearance'])


def test_condition_invariants_and_other_invalid_fields_still_block():
    for item in [dict(category='condition',kind='condition',text='Хромота'),
                 dict(category='intrinsic',kind='hairstyle',text=''),
                 dict(category='intrinsic',kind='hairstyle',text='x'*601)]:
        normalized = normalize_batch(batch({'bad':item}))
        with pytest.raises(ValueError):
            AppearanceProfile.model_validate(normalized['characters']['actor']['appearance'])


def test_provider_schema_expresses_pairs():
    pairs = character_schema(CharactersPart)['$defs']['AppearanceFeature']['allOf'][0]['anyOf']
    from backend.runtime_v3.appearance import KINDS
    assert {p['properties']['category']['const']:set(p['properties']['kind']['enum']) for p in pairs} == KINDS


def test_failed_character_batch_resumes_without_repeating_accepted_stages(api, captured_generation_v6):
    client, app = api; repo = app.state.repository; calls = []; base = short_provider(calls)
    broken = True
    requested = []
    def provider(**kw):
        nonlocal broken
        system = kw['messages'][0]['content']
        raw = json.loads(''.join(base(**kw)))
        if system.split('\nStage: ')[1].split('\n')[0] == 'characters':
            ids = tuple(sorted(raw['characters'])); requested.append(ids)
            data = json.loads(kw['messages'][-1]['content'])
            secondary = any(r['id'] in ids and r['tier']=='secondary' for r in data['registry'])
            for actor in raw['characters'].values():
                actor['appearance'] = {'items': {
                    'appearance_hair':dict(category='presentation',kind='natural_hair_color',text='От природы тёмные волосы'),
                    'appearance_style':dict(category='intrinsic',kind='hairstyle',text='Короткая стрижка'),
                    'outfit':dict(category='presentation',kind='clothing',text='Серый пиджак, рубашка без галстука')},
                    'legacy_text':'Веснушки и внимательный взгляд'}
                if secondary and broken:
                    actor['appearance']['items']['appearance_style']['text'] = ''
        yield json.dumps(raw,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        wid,jid = submit(client,'Илья переезжает в Москву и работает в НИИ.')
        assert wait(client,jid)['status']=='failed'
        saved = {u['unit_id']:repo.inspect_generation_checkpoint(jid,u['unit_id'],True)['artifact_version']
                 for u in repo.generation_status(jid)['units'] if u['status']=='completed'}
        assert 'core_0' in saved and 'places' in saved and 'setting' in saved
        broken = False
        response = client.post(f'/api/jobs/{jid}/generation/resume',json={
            'revision':repo.generation_status(jid)['revision'],'api_key':'fixture'})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert all(repo.inspect_generation_checkpoint(jid,k,True)['artifact_version']==v for k,v in saved.items())
    assert requested.count(requested[0])==1
    artifact=repo.inspect_generation_checkpoint(jid,'secondary_0',True)['artifact']
    for actor in artifact['characters'].values():
        profile=AppearanceProfile.model_validate(actor['appearance'])
        assert profile.items['appearance_hair'].category=='intrinsic'
        assert profile.items['appearance_style'].category=='presentation'
        assert profile.legacy_text=='Веснушки и внимательный взгляд\nСерый пиджак, рубашка без галстука'

    draft=repo.draft(wid,True)
    save=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    from backend.repositories.preparation import Repository
    reloaded=Repository(repo.path).get_snapshot(save)
    for actor in reloaded['world_state']['characters'].values():
        assert 'Серый пиджак, рубашка без галстука' in actor['appearance']['legacy_text']
        assert actor['appearance']['items']['appearance_hair']['category']=='intrinsic'
