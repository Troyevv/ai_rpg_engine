"""#110: creative guidance is independent of canonical acceptance and lineage."""
from copy import deepcopy
import json
import pytest
from pydantic import ValidationError
from backend.runtime_v3.genre import GenreConfig, THEMES, guidance
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.director import plan
from backend.runtime_v3.resolver import StateResolver
from context_builder import build_context, estimate
from test_runtime_v3_storage import snapshot_fixture
from test_narrative_pacing import raw


def config(primary=None, secondary=(), custom=''):
    return GenreConfig(primary_genre=primary, secondary_genres=list(secondary), custom_genre=custom).model_dump()


def test_distinct_bounded_guidance_and_explicit_emphasis():
    policies = [guidance(config(g)) for g in THEMES]
    assert len({json.dumps(p) for p in policies}) == len(THEMES)
    p = guidance(config('slice_of_life', ['romance', 'drama', 'thriller']))
    assert p['primary']['genre'] == 'slice_of_life'
    assert [g['genre'] for g in p['secondary']] == ['romance', 'drama', 'thriller']
    assert 'main emphasis' in p['instruction'] and 'supporting accents' in p['instruction']
    assert 'off-genre' in p['instruction']
    text = 'Я' * 2000
    assert guidance(config('custom', ['drama', 'romance', 'thriller'], text))['primary']['themes'] == text
    assert len(json.dumps(guidance(config('custom', ['drama', 'romance', 'thriller'], text)), ensure_ascii=False)) < 3500
    assert guidance(config()) is None


@pytest.mark.parametrize('values', [dict(primary_genre='missing'), dict(secondary_genres=['romance']*2),
    dict(primary_genre='romance', secondary_genres=['romance']), dict(primary_genre='custom'),
    dict(secondary_genres=list(THEMES)[:4]), dict(custom_genre='x'*2001)])
def test_invalid_config(values):
    with pytest.raises(ValidationError): GenreConfig(**values)


@pytest.mark.parametrize('legacy', ['', 'romance', 'Сюрреалистическая бытовая комедия'])
def test_legacy_migration_preserves_source_and_explicit_neutral(legacy):
    s = snapshot_fixture()
    s['world_state']['meta'].pop('genre', None)
    s['campaign']['campaign'] = {'genre': legacy}
    original = deepcopy(s)
    migrated = migrate_v2(s).snapshot
    assert s == original
    genre = migrated['world_state']['meta']['genre']
    assert genre == (None if not legacy else config('romance') if legacy == 'romance' else config('custom', custom=legacy))
    migrated['world_state']['meta']['genre'] = config()
    assert migrate_v2(migrated).snapshot['world_state']['meta']['genre'] == config()


def test_creation_schema_roundtrip_and_import():
    from backend.services.world_creation_settings import CreationSettings
    from devtools.narrative_test_world import build_fixture
    original = build_fixture('base')
    original['creation_settings'] = CreationSettings(**config('romance', ['drama','custom'], 'Тихая фантастика')).model_dump()
    migrated = migrate_v2(original).snapshot
    assert migrated['world_state']['meta']['genre'] == config('romance', ['drama','custom'], 'Тихая фантастика')
    assert migrate_v2(json.loads(json.dumps(migrated))).snapshot == migrated


@pytest.mark.parametrize('kind', ['turn', 'start', 'background'])
def test_context_once_diagnostics_extraction_independence_and_budget(kind):
    s = snapshot_fixture(); s['world_state']['meta']['genre'] = config('romance',['drama'])
    s['campaign']['campaign'] = {'genre': 'STALE_GENRE'}
    before = deepcopy(s)
    messages = build_context(s, [], 'Продолжить', kind, 16000, 2000)
    blocks = [m for m in messages if m['content'].startswith('Genre /')]
    assert len(blocks) == 1 and 'STALE_GENRE' not in str(messages)
    assert messages.selection['genre_guidance'] == guidance(s['world_state']['meta']['genre'])
    assert estimate(messages) <= 16000-2000-256 and s == before
    extract = build_context(s, [], '', 'turn', 32768, 4000, extraction_text='Тихий разговор.')
    s['world_state']['meta']['genre'] = config('thriller')
    assert build_context(s, [], '', 'turn', 32768, 4000, extraction_text='Тихий разговор.') == extract


def test_off_genre_event_and_director_remain_identical():
    s = snapshot_fixture()['world_state']
    quote = 'Борис нашёл загадочную записку.'
    payload = raw(s, events=[dict(id='note', text=quote, participants=['b'], evidence=quote)])
    payload['final_scene']['location_id'] = s['camera']['location_id']
    outputs=[]; plans=[]
    for g in [config(), config('romance'), config('slice_of_life'), config('thriller')]:
        state=deepcopy(s); state['meta']['genre']=g
        plans.append(plan(state,'turn'))
        result=StateResolver(state,quote,'').resolve(payload)
        assert result.history['events']
        result.state['meta'].pop('genre')
        outputs.append((result.state,result.history,result.warnings))
    assert all(p == plans[0] for p in plans)
    assert all(out == outputs[0] for out in outputs)


def test_lineage_and_long_run_with_exactly_two_calls_per_turn(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'genre.sqlite'); sid=load_fixture(repo,'pacing')['save']
    initial=repo.get_snapshot(sid)
    ordinary_job(repo,sid,'start')
    def change(g):
        meta=repo.get_snapshot(sid)['world_state']['meta']
        values={k:meta[k] for k in ('narrative_pacing','narrative_risk','outcome_preference')}
        repo.update_narrative_policy(sid,repo.get_save(sid)['revision'],dict(values,genre=g))
    change(config('romance',['drama']))
    changed=repo.get_snapshot(sid)
    ordinary_job(repo,sid)
    original=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    original_context=repo.latest_job(sid)['context_json']
    assert 'Genre / soft creative guidance' in original_context
    change(config('thriller'))
    assert repo.list_turns(sid)[-1] == turn
    ordinary_job(repo,sid,'regenerate')
    assert repo.latest_job(sid)['context_json']==original_context
    assert repo.get_snapshot(sid)['world_state']['meta']['genre']==config('romance',['drama'])
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==original
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==changed
    ordinary_job(repo,sid)  # new branch after rollback
    for _ in range(15): ordinary_job(repo,sid)
    assert Repository(repo.path).get_snapshot(sid)['world_state']['meta']['genre']==config('romance',['drama'])
    # The original snapshot remains immutable.
    assert initial['world_state']['meta']['genre']==config('custom', custom='Повседневная история')


from test_api import api


def test_api_revision_validation_and_old_clients_preserve_genre(api):
    from devtools.narrative_test_world import load_fixture
    client, app = api
    repo=app.state.repository; sid=load_fixture(repo,'pacing')['save']
    url=f'/api/saves/{sid}/narrative-policy'
    before=repo.get_snapshot(sid)
    current=client.get(url).json()['current']
    revision=repo.get_save(sid)['revision']
    invalid=dict(current, genre=config('romance'))
    invalid['genre']['secondary_genres']=['romance']
    assert client.put(url,json=dict(invalid,revision=revision)).status_code==422
    assert repo.get_snapshot(sid)==before
    current['genre']=config('romance',['custom'],'Лирическая научная фантастика')
    assert client.put(url,json=dict(current,revision=revision)).status_code==200
    assert client.put(url,json=dict(current,revision=revision)).status_code==409
    changed=repo.get_snapshot(sid)
    old_client={k:v for k,v in current.items() if k!='genre'}
    assert client.put(url,json=dict(old_client,revision=repo.get_save(sid)['revision'])).status_code==200
    assert repo.get_snapshot(sid)==changed
    assert client.get(url).json()['current']['genre']==current['genre']


@pytest.mark.parametrize('genre', [config(),config('romance'),config('thriller')])
def test_invalid_location_is_never_authorized_by_genre(genre):
    from backend.services.world_delta_errors import StructuralDeltaError
    s=snapshot_fixture()['world_state'];s['meta']['genre']=genre
    payload=raw(s);payload['final_scene']['location_id']='unknown_location'
    with pytest.raises(StructuralDeltaError): StateResolver(s,'Внезапный поворот.','').resolve(payload)


@pytest.mark.parametrize('neutral', [None, config()])
def test_neutral_migration_preserves_exact_world_and_source(neutral):
    from backend.runtime_v3.genre import initialize
    s=migrate_v2(snapshot_fixture()).snapshot
    s['campaign']={}
    s['world_state']['meta']['genre']=deepcopy(neutral)
    original=deepcopy(s)
    initialize(s)
    assert s==original
    for _ in range(3):
        migrated=migrate_v2(json.loads(json.dumps(s)))
        assert migrated.snapshot==original
        assert not migrated.history['events']
        s=migrated.snapshot
    assert guidance(s['world_state']['meta']['genre']) is None
    messages=build_context(s, [], '', 'turn', 32768, 2000)
    assert not any(m['content'].startswith('Genre /') for m in messages)


def test_missing_genre_uses_model_default_without_initialization():
    from backend.runtime_v3.genre import initialize
    from backend.runtime_v3.models import Meta
    s=migrate_v2(snapshot_fixture()).snapshot
    s['campaign']={};s['world_state']['meta'].pop('genre')
    original=deepcopy(s)
    initialize(s)
    assert s==original  # no genre was authored; no config should be manufactured
    migrated=migrate_v2(s).snapshot
    assert migrated['world_state']['meta']['genre'] is Meta().genre is None
    expected=deepcopy(original);expected['world_state']['meta']['genre']=None
    assert migrated==expected
    assert migrate_v2(migrated).snapshot==migrated
    assert s==original


@pytest.mark.parametrize('neutral', [None, config()])
def test_neutral_save_read_and_rollback_preserve_stored_snapshots(api, neutral):
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    client,app=api;repo=app.state.repository
    sid=load_fixture(repo,'pacing')['save']
    before=repo.get_snapshot(sid)
    before['campaign'].get('campaign',{}).pop('genre',None)
    before['campaign'].pop('genre',None)
    before['world_state']['meta']['genre']=deepcopy(neutral)
    encoded=json.dumps(before,ensure_ascii=False)
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(encoded,sid))
    def stored():
        with repo.connect() as db:
            return db.execute('SELECT state_json FROM saves WHERE id=?',(sid,)).fetchone()[0]
    for _ in range(3):
        assert repo.get_snapshot(sid)==before
        response=client.get(f'/api/saves/{sid}/narrative-policy')
        assert response.status_code==200
        assert response.json()['current']['genre']==config()  # disposable form defaults
        assert stored()==encoded
    ordinary_job(repo,sid,'start');after_start=repo.get_snapshot(sid)
    first_turn=repo.list_turns(sid)[-1]
    with repo.connect() as db:
        stored_before=db.execute('SELECT before_json FROM turns WHERE id=?',(first_turn['id'],)).fetchone()[0]
    assert json.loads(stored_before)==before
    ordinary_job(repo,sid)
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==after_start
    assert repo.list_turns(sid)[-1]==first_turn
    repo.rollback_last(sid)
    assert json.loads(stored())==before
    assert repo.get_snapshot(sid)==before
    assert before['world_state']['meta']['genre']==neutral
    # A neutral form can be submitted (no null/GenreConfig validation mismatch).
    current=client.get(f'/api/saves/{sid}/narrative-policy').json()['current']
    response=client.put(f'/api/saves/{sid}/narrative-policy',json=dict(current,revision=repo.get_save(sid)['revision']))
    assert response.status_code==200,response.text
    assert repo.get_snapshot(sid)['world_state']['meta']['genre']==config()
