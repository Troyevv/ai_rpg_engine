"""#193: stable catalog contract and preservation across the existing Runtime."""
from copy import deepcopy
from typing import get_args
import json
import pytest
from pydantic import ValidationError
from backend.runtime_v3.genre import CATALOG, Genre, GenreConfig, THEMES, guidance, initialize
from backend.services.world_creation_settings import CreationSettings
from backend.runtime_v3.migration import migrate_v2
from context_builder import build_context, estimate
from test_genre_policy import config
from test_runtime_v3_storage import snapshot_fixture
from test_api import api

OLD_IDS = 'slice_of_life family_saga romance drama detective thriller science_fiction fantasy horror adventure post_apocalyptic historical'.split()
# The issue's table lists 25 names, despite its 24/36 totals. None is omitted.
NEW_IDS = 'psychological_drama political_drama crime_drama space_opera dystopia alternate_history cyberpunk dark_fantasy urban_fantasy epic_fantasy mysticism gothic supernatural_thriller dynastic_saga court_intrigue war_drama music_drama sports_drama business_drama comedy satire black_comedy survival exploration nautical_adventure'.split()
ALL_IDS = OLD_IDS + NEW_IDS


def test_catalog_is_the_single_complete_schema_and_guidance_source():
    assert len(NEW_IDS) == 25
    assert set(get_args(Genre)) == set(ALL_IDS + ['custom'])
    assert len(CATALOG['genres']) == len(set(get_args(Genre)))
    assert set(THEMES) == set(ALL_IDS)
    groups = {g['id'] for g in CATALOG['groups']}
    for row in CATALOG['genres']:
        assert row['group'] in groups
        for language in ('ru', 'en'):
            assert row[language]['name'].strip() and row[language]['description'].strip()
        if row['id'] != 'custom':
            assert row['themes'] and len(row['themes']) <= 165
    schema = GenreConfig.model_json_schema()
    assert set(schema['properties']['secondary_genres']['items']['enum']) == set(ALL_IDS + ['custom'])


@pytest.mark.parametrize('genre', ALL_IDS)
def test_every_genre_creation_import_serialization_secondary_and_legacy(genre):
    from devtools.narrative_test_world import build_fixture
    expected = config(genre, ['custom'], 'Авторские оттенки')
    creation = CreationSettings(**expected)
    assert CreationSettings.model_validate_json(creation.model_dump_json()) == creation
    original = build_fixture('base')
    original['creation_settings'] = creation.model_dump()
    before = deepcopy(original)
    snapshot = migrate_v2(original).snapshot
    assert original == before
    assert snapshot['world_state']['meta']['genre'] == expected
    assert migrate_v2(json.loads(json.dumps(snapshot))).snapshot == snapshot
    assert guidance(config(None, [genre]))['secondary'][0] == dict(genre=genre, themes=THEMES[genre])
    legacy = snapshot_fixture()
    legacy['world_state']['meta']['genre'] = None
    legacy['campaign']['campaign'] = {'genre':genre}
    initialize(legacy)
    assert legacy['world_state']['meta']['genre'] == config(genre)


@pytest.mark.parametrize('genre', ALL_IDS)
def test_every_genre_context_is_bounded_and_cannot_change_extraction_director_or_canon(genre):
    from backend.runtime_v3.director import plan
    s = snapshot_fixture()
    original = deepcopy(s)
    extraction = build_context(s, [], '', 'turn', 32768, 4000, extraction_text='Тихий разговор.')
    director = plan(s['world_state'], 'turn')
    s['world_state']['meta']['genre'] = config(genre)
    messages = build_context(s, [], 'Продолжить', 'turn', 16000, 2000)
    assert messages.selection['genre_guidance']['primary'] == dict(genre=genre, themes=THEMES[genre])
    assert estimate(messages) <= 16000 - 2000 - 256
    assert build_context(s, [], '', 'turn', 32768, 4000, extraction_text='Тихий разговор.') == extraction
    assert plan(s['world_state'], 'turn') == director
    s['world_state']['meta']['genre'] = original['world_state']['meta'].get('genre')
    original['world_state']['meta'].setdefault('genre', None)
    assert s == original


@pytest.mark.parametrize('values', [dict(primary_genre=''), dict(primary_genre='not_a_genre'),
    dict(secondary_genres=['']), dict(secondary_genres=['cyberpunk'] * 2),
    dict(primary_genre='cyberpunk', secondary_genres=['cyberpunk']),
    dict(secondary_genres=NEW_IDS[:4]), dict(primary_genre='custom', custom_genre='  ')])
def test_catalog_does_not_relax_validation(values):
    with pytest.raises(ValidationError): GenreConfig(**values)


def test_all_new_ids_api_revision_and_reopen_without_history_changes(api):
    from devtools.narrative_test_world import load_fixture
    client, app = api
    repo=app.state.repository; sid=load_fixture(repo,'pacing')['save']
    url=f'/api/saves/{sid}/narrative-policy'
    before_turns=repo.list_turns(sid)
    baseline=deepcopy(repo.get_snapshot(sid)['world_state'])
    for i, genre in enumerate(NEW_IDS):
        current=client.get(url).json()['current']
        revision=repo.get_save(sid)['revision']
        expected=config(genre,[g for g in NEW_IDS if g != genre][:3])
        current['genre']=expected
        assert client.put(url,json=dict(current, revision=revision)).status_code == 200
        assert client.put(url,json=dict(current, revision=revision)).status_code == 409
        assert client.get(url).json()['current']['genre'] == expected
        from backend.repositories.preparation import Repository
        reopened=Repository(repo.path).get_snapshot(sid)['world_state']
        assert reopened['meta']['genre'] == expected
        reopened['meta']['genre']=baseline['meta']['genre']
        assert reopened == baseline
    assert repo.list_turns(sid) == before_turns
    for invalid in ['', 'missing']:
        current['genre']=dict(primary_genre=invalid,secondary_genres=[],custom_genre='')
        assert client.put(url,json=dict(current,revision=repo.get_save(sid)['revision'])).status_code == 422


@pytest.mark.parametrize('genre', ['cyberpunk','nautical_adventure','supernatural_thriller'])
def test_new_genre_handoff_turn_reload_regenerate_rollback_and_branch(api, genre):
    from test_runtime_handoff import source, imported
    from test_runtime_handoff import submit, provider_payload, NARRATIVE
    from test_api import wait_job
    from unittest.mock import patch
    from backend.repositories.preparation import Repository
    value=source();expected=config(genre,['music_drama','court_intrigue','black_comedy'])
    value['creation_settings'].update(expected)
    client,app=api;sid=imported(client,value);repo=app.state.repository
    initial=repo.get_snapshot(sid)
    def ordinary_job(repo,sid,kind='turn'):
        def provider(**kw):
            yield json.dumps(provider_payload(kw),ensure_ascii=False) if kw.get('response_format') else NARRATIVE
        with patch('engine.chat_stream',side_effect=provider) as calls:
            job=wait_job(client,submit(client,sid,kind,'Я жду.' if kind=='turn' else ''))
        assert job['status']=='saved',job.get('error')
        assert calls.call_count==2
        state=repo.get_snapshot(sid)['world_state']
        assert state['camera']['controlled_actor_id']==initial['world_state']['camera']['controlled_actor_id']
        assert state['knowledge']==initial['world_state']['knowledge']
    assert initial['world_state']['meta']['genre'] == expected
    ordinary_job(repo,sid,'start')
    before=repo.get_snapshot(sid)
    ordinary_job(repo,sid)
    recorded=repo.latest_job(sid)['context_json']
    assert genre in recorded
    assert Repository(repo.path).get_snapshot(sid)['world_state']['meta']['genre'] == expected
    current=client.get(f'/api/saves/{sid}/narrative-policy').json()['current']
    current['genre']=config('comedy')
    assert client.put(f'/api/saves/{sid}/narrative-policy',json=dict(current,revision=repo.get_save(sid)['revision'])).status_code == 200
    ordinary_job(repo,sid,'regenerate')
    assert repo.latest_job(sid)['context_json'] == recorded
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['meta']['genre'] == expected
    assert initial['world_state']['meta']['genre'] == expected


def test_maximum_policy_context_includes_only_selected_themes():
    # Four selected entries, never the entire catalog; custom text remains intact.
    s=snapshot_fixture()
    selected=['supernatural_thriller','nautical_adventure','court_intrigue']
    s['world_state']['meta']['genre']=config('custom',selected,'Я'*2000)
    original=deepcopy(s)
    messages=build_context(s,[],'Продолжить','turn',32768,4000)
    block=messages.selection['genre_guidance']
    assert block['primary']['themes']=='Я'*2000
    assert [g['genre'] for g in block['secondary']]==selected
    assert 'music_drama' not in json.dumps(block)
    assert estimate(messages)<=32768-4000-256
    assert s==original
