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


@pytest.mark.parametrize('observer', [False, True])
def test_canonical_snapshot_import_roundtrip_and_confirm(api, observer):
    client, app = api
    snapshot = normalize(rich_draft()).snapshot
    state = snapshot['world_state']; cid = state['camera']['controlled_actor_id']
    state['meta']['turn_id'] = 9
    state['camera']['subject_id'] = cid
    state['camera']['pov_actor_id'] = cid
    if observer:
        state['camera'].update(mode='observer', controlled_actor_id=None)
    state['threads']['paused'] = dict(id='paused',description='Пауза',status='paused')
    expected = normalize(snapshot).snapshot['world_state']
    original = deepcopy(snapshot)
    draft = draft_world.prepare(snapshot)
    assert not draft_world.validate(draft)['errors']
    assert normalize(draft).snapshot['world_state'] == expected
    assert normalize(parse_summary(draft_world.export_markdown(draft))).snapshot['world_state'] == expected
    assert snapshot == original
    wid = client.post('/api/workspaces', json={'name':'Canonical import'}).json()['id']
    path = f'/api/workspaces/{wid}/draft'
    imported = client.post(path+'/import', json={'revision':0,'format':'json','text':json.dumps(snapshot)})
    assert imported.status_code == 200, imported.text
    ready = client.get(path+'?author=true').json()
    response = client.post(path+'/confirm', json={'revision':ready['revision'],'version_id':ready['version_id']})
    assert response.status_code == 200, response.text
    assert app.state.repository.get_snapshot(response.json()['save'])['world_state'] == expected


def test_canonical_ids_disambiguate_same_named_locations():
    snapshot = normalize(rich_draft()).snapshot
    snapshot['world_state']['locations']['other'] = dict(id='other',name='Кухня')
    expected = normalize(snapshot).snapshot['world_state']
    draft = draft_world.prepare(snapshot)
    assert normalize(draft).snapshot['world_state'] == expected


def test_portable_initial_history_indexes_only_explicit_milestones(api):
    from backend.runtime_v3.milestones import query
    client, app = api
    snapshot = normalize(rich_draft()).snapshot
    cid = snapshot['world_state']['camera']['controlled_actor_id']
    snapshot['initial_history'] = {'state_changes':[dict(id='past-job',kind='roles',entity='old-job',
        before=None,after=dict(id='old-job',actor_id=cid,kind='employment',title='Разработчик',status='active'),
        minute=0,evidence='Начал работать в компании.')], 'events':[]}
    wid = client.post('/api/workspaces',json={'name':'History import'}).json()['id']
    path=f'/api/workspaces/{wid}/draft'
    imported=client.post(path+'/import',json={'revision':0,'format':'json','text':json.dumps(snapshot)})
    assert imported.status_code == 200, imported.text
    draft=client.get(path+'?author=true').json()
    response=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert response.status_code == 200, response.text
    saved=app.state.repository.get_snapshot(response.json()['save'])
    with app.state.repository.connect() as db:
        history,_=read_history(db,saved['history_head'])
        milestones=query(db,saved['history_head'],actor_ids=[cid])
    assert history['state_changes']==snapshot['initial_history']['state_changes']
    assert [row['category'] for row in milestones]==['role_started']


def test_initial_knowledge_correction_does_not_silently_drop_invalid_reference():
    draft=rich_draft();cid=draft['controlled_actor_id']
    draft['world']['knowledge'][cid+':old']['replaced_by']='missing'
    assert 'replaced_by' in readiness(draft)['errors'][0]


def test_empty_observer_snapshot_remains_a_world_without_protagonist():
    from backend.runtime_v3.models import WorldStateV3
    snapshot = dict(schema_version=3, world_state=WorldStateV3(
        camera={'mode':'observer'}, characters={}).model_dump())
    draft = draft_world.prepare(snapshot)
    assert not draft_world.validate(draft)['errors']
    result = normalize(draft).snapshot['world_state']
    assert result['characters'] == {}
    assert result['camera']['controlled_actor_id'] is None
    assert result['meta']['current_protagonist_id'] is None


def test_corporate_parent_claims_preserve_structure_and_knowledge(api):
    client, app = api
    draft = rich_draft()
    draft['world']['organizations'] = {
        key: dict(id=key, name=name) for key, name in
        [('group','Apex Group'), ('bank','Apex Bank'), ('it','Apex IT'),
         ('insurance','Apex Insurance'), ('construction','Apex Construction'), ('legal','Apex Legal')]}
    actor = draft['controlled_actor_id']
    for key in ('bank','it','insurance','construction','legal'):
        fid = 'parent-' + key
        draft['world']['facts'][fid] = dict(id=fid, text=key + ' входит в Apex Group', secret=True,
            character_ids=[], claim=dict(subject_id=key,predicate='organization.parent',value='group'))
        draft['world']['knowledge'][actor+':'+fid] = dict(actor_id=actor,fact_id=fid,status='known')
    canonical = normalize(draft).snapshot
    imported = draft_world.prepare(canonical)
    assert normalize(imported).snapshot['world_state'] == canonical['world_state']
    wid=client.post('/api/workspaces',json={'name':'Corporate group'}).json()['id']
    path=f'/api/workspaces/{wid}/draft'
    response=client.post(path+'/import',json={'revision':0,'format':'json','text':json.dumps(canonical)})
    assert response.status_code == 200, response.text
    author=client.get(path+'?author=true').json()
    response=client.post(path+'/confirm',json={'revision':author['revision'],'version_id':author['version_id']})
    assert response.status_code == 200, response.text
    saved=app.state.repository.get_snapshot(response.json()['save'])['world_state']
    assert saved == canonical['world_state']
    hidden = deepcopy(imported)
    hidden['world']['knowledge'] = {}
    assert 'parent-bank' not in draft_world.player_view(hidden)['world']['facts']
    for child, parent in [('group','bank'), ('bank','missing')]:
        broken = deepcopy(draft)
        broken['world']['facts']['bad-parent'] = dict(id='bad-parent',text='invalid',
            claim=dict(subject_id=child,predicate='organization.parent',value=parent))
        report = readiness(broken)
        assert report['errors'] and 'organization' in report['errors'][0]


def test_game_projection_never_exposes_author_provenance_or_other_npc_knowledge():
    from backend.runtime_v3.selectors import ui_view
    snapshot=normalize(rich_draft()).snapshot
    state=snapshot['world_state'];actor=state['camera']['controlled_actor_id']
    npc=next(cid for cid in state['characters'] if cid!=actor)
    snapshot['campaign']['initial_world']={'brief':'Секретный авторский источник','claims':[{'text':'Скрытая биография'}]}
    state['facts']['private-initial']=dict(id='private-initial',text='Скрытый банковский договор',visibility='secret',character_ids=[npc])
    state['knowledge'][npc+':private-initial']=dict(actor_id=npc,fact_id='private-initial',status='known')
    state['facts']['public-initial']=dict(id='public-initial',text='Станция открыта',visibility='public',character_ids=[])
    state['knowledge'][npc+':public-initial']=dict(actor_id=npc,fact_id='public-initial',status='known')
    visible=ui_view(snapshot)
    text=json.dumps(visible,ensure_ascii=False)
    assert 'Секретный авторский источник' not in text
    assert 'Скрытый банковский договор' not in text
    assert 'Станция открыта' in text
    assert all(row['actor_id']==actor for row in visible['world']['knowledge'].values())
    assert snapshot['campaign']['initial_world']['brief']=='Секретный авторский источник'
    assert npc+':private-initial' in state['knowledge']
