"""Initial authoring/runtime boundary regressions; no provider calls."""
from copy import deepcopy
import json

import pytest

from backend.services import draft_world
from backend.services.initial_world_v2 import normalize, readiness
from backend.runtime_v3.models import Motivation, PersonalityProfile, PersonalityItem
from backend.runtime_v3.repository import migrate_snapshot, committed_snapshot, read_history
from backend.runtime_v3.resolver import StateResolver
from test_draft_world import fixture
from test_runtime_v3_storage import connection
from test_api import api
from world_parser import parse_summary


def rich_draft():
    draft = fixture()
    cid = draft['controlled_actor_id']
    actor = draft['world']['characters'][cid]
    actor['personality'] = PersonalityProfile(items={
        'voice': PersonalityItem(field='communication', text='Говорит тихо.', revision=2)
    }).model_dump()
    actor['values'] = {'honesty': {'id':'honesty', 'text':'Честность', 'revision':3}}
    actor['physical_state'] = 'Устал после дороги.'
    actor['goals'] = [Motivation(id='goal', text='Забрать сумку', status='completed', revision=2).model_dump()]
    draft['world']['narrative_pacing'] = {'preset':'calm'}
    draft['world']['narrative_risk'] = {'preset':'safe'}
    draft['world']['organizations'] = {}
    draft['locations'] = [{'id':'kitchen', 'name':'Кухня', 'text':''}]
    for actor in draft['world']['characters'].values():
        actor['location'] = 'Кухня'
    draft['world']['facts']['old'] = {'id':'old','text':'Старое убеждение','secret':True,
                                    'character_ids':[cid], 'claim':{'subject_id':cid,'predicate':'belief','value':'old'}}
    draft['world']['knowledge'][cid+':old'] = {'actor_id':cid,'fact_id':'old','status':'refuted',
                                            'revision':2,'evidence':'Письмо','source_turn':0}
    draft['world']['scheduled_events']['later'] = {'id':'later','description':'Когда-нибудь встретиться',
        'participants':[cid], 'status':'pending','due_minute':None,'condition':'После возвращения'}
    return draft_world.prepare(draft)


def test_generated_json_text_share_canonical_semantics_without_creative_calls():
    draft = rich_draft()
    original = deepcopy(draft)
    generated = normalize(draft, operation='creative_generate').snapshot
    imported = normalize(json.loads(json.dumps(draft))).snapshot
    text = normalize(parse_summary(draft_world.export_markdown(draft))).snapshot
    assert generated == imported == text
    assert draft == original
    state = generated['world_state']; cid = draft['controlled_actor_id']
    actor = state['characters'][cid]
    assert actor['personality'] == draft['world']['characters'][cid]['personality']
    assert actor['values']['honesty']['revision'] == 3
    assert actor['goals'][0]['status'] == 'completed'
    assert actor['physical_state'] == 'Устал после дороги.'
    assert state['knowledge'][cid+':old']['status'] == 'refuted'
    assert state['knowledge'][cid+':old']['evidence'] == 'Письмо'
    assert state['facts']['old']['claim']['value'] == 'old'
    assert state['meta']['narrative_pacing']['preset'] == 'calm'
    assert state['meta']['narrative_risk']['preset'] == 'safe'
    assert state['scheduled_events']['later']['due_minute'] is None
    assert 'kitchen' in state['locations']
    assert not state['residences'] and not state['pregnancies']
    assert actor['birth_date'] is None
    assert normalize(generated).snapshot == generated


def test_new_draft_rejects_invalid_optional_canonical_data_with_safe_path():
    draft = rich_draft(); cid = draft['controlled_actor_id']
    draft['world']['characters'][cid]['personality']['items']['voice']['revision'] = -1
    report = readiness(draft)
    assert report['errors']
    assert f'world/characters/{cid}/personality/items/voice/revision' in report['errors'][0]
    assert 'Говорит тихо' not in report['errors'][0]


def test_historical_load_keeps_conservative_optional_salvage():
    from backend.runtime_v3.migration import migrate_v2
    draft = rich_draft(); cid = draft['controlled_actor_id']
    draft['world']['characters'][cid]['personality'] = {'items': 'damaged'}
    result = migrate_v2(draft)
    assert result.history['legacy'][0]['world']['characters'][cid]['personality'] == {'items':'damaged'}
    assert result.snapshot['world_state']['characters'][cid]['personality'] is not None
    assert readiness(draft)['errors']


def test_schema_valid_draft_cannot_bypass_runtime_cross_references():
    draft = rich_draft()
    draft['world']['scheduled_events']['later']['location_id'] = 'missing'
    errors = draft_world.validate(draft)['errors']
    assert errors and 'scheduled_events/later' in errors[-1]


@pytest.mark.parametrize('value', [[], {'broken': 'not a process'}])
def test_malformed_process_map_is_an_actionable_validation_error(value):
    draft = rich_draft(); draft['world']['pregnancies'] = value
    errors = draft_world.validate(draft)['errors']
    assert errors and errors[-1].startswith('world/pregnancies')


def test_normalized_world_ordinary_turn_save_reload_branch(tmp_path):
    draft = rich_draft(); db = connection(tmp_path/'initial.sqlite')
    with db: snapshot, _ = migrate_snapshot(db, draft)
    assert snapshot['world_state'] == normalize(draft).snapshot['world_state']
    original = deepcopy(snapshot)
    for _ in range(2):
        camera = snapshot['world_state']['camera']
        delta = {'final_scene': {'location_id':camera['location_id'],
            'present_character_ids':camera['present_character_ids'], 'elapsed_minutes':1}}
        resolved = StateResolver(snapshot['world_state'], 'Пауза.', '').resolve(delta)
        with db: snapshot = committed_snapshot(db, snapshot, resolved)
        snapshot = json.loads(json.dumps(snapshot))
    assert snapshot['world_state']['meta']['turn_id'] == 2
    assert original['world_state']['meta']['turn_id'] == 0
    # Sibling branch starts from the same immutable initial state.
    camera = original['world_state']['camera']
    result = StateResolver(original['world_state'], 'Пауза.', '').resolve({'final_scene':{
        'location_id':camera['location_id'], 'present_character_ids':camera['present_character_ids'],
        'elapsed_minutes':2}})
    with db: branch = committed_snapshot(db, original, result)
    assert branch['history_head'] != snapshot['history_head']
    assert len(read_history(db, branch['history_head'])[0]['turns']) == 1
    assert len(read_history(db, snapshot['history_head'])[0]['turns']) == 2


def test_initial_review_does_not_require_secrets():
    draft = fixture(); draft['world']['facts'] = {}; draft['world']['knowledge'] = {}
    assert not any('тайна' in warning for warning in draft_world.review_initial(draft))


@pytest.mark.parametrize('format', ['json','text'])
def test_import_author_confirm_retains_canonical_extensions(api, format):
    client, app = api
    draft = rich_draft()
    workspace = client.post('/api/workspaces', json={'name':'Initial world'}).json()
    path = f"/api/workspaces/{workspace['id']}/draft"
    text = json.dumps(draft) if format == 'json' else draft_world.export_markdown(draft)
    imported = client.post(path+'/import', json={'revision':0,'format':format,'text':text})
    assert imported.status_code == 200, imported.text
    authored = client.get(path+'?author=true').json()
    assert not authored['validation']['errors']
    request = {'revision':authored['revision'],'version_id':authored['version_id']}
    response = client.post(path+'/confirm', json=request)
    assert response.status_code == 200, response.text
    assert client.post(path+'/confirm', json=request).json() == response.json()
    saved = app.state.repository.get_snapshot(response.json()['save'])
    assert saved['world_state'] == normalize(draft).snapshot['world_state']
    public = client.get(path).json()
    assert 'Старое убеждение' not in json.dumps(public, ensure_ascii=False)


def test_explicit_reproductive_processes_survive_authoring_boundary():
    from test_reproduction import conceive
    canonical = conceive().state
    draft = rich_draft()
    draft['characters'] = [dict(id=cid,name=cid,fields={}) for cid in canonical['characters']]
    draft['world'] = {**deepcopy(canonical),'version':2,
        'scenes':{'opening':dict(id='opening',location='Дом',participants=['a','b'],text='Утро.',
                               start_minute=0,end_minute=0,status='active',event_ids=[])},
        'events':{},'scene_records':{}}
    draft['world'].pop('meta'); draft['world'].pop('camera'); draft['world'].pop('locations')
    for actor in draft['world']['characters'].values():
        actor.pop('location_id'); actor['location'] = 'Дом'
    draft.update(protagonist_id='a',controlled_actor_id='a',camera={'scene_id':'opening','mode':'actor'},
                 locations=[{'id':'home','name':'Дом','text':''}],
                 world_clock={'minute':0,'calendar':canonical['meta']['calendar']})
    result = normalize(draft).snapshot['world_state']
    for section in ('reproductive_events','pregnancies','naming_decisions','reproduction_policy'):
        assert result[section] == canonical[section]
