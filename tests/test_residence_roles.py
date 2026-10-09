"""#39 integration contracts: identity, evidence, chronology, agency and lineage."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, settings, strategies as st
from backend.runtime_v3.models import WorldStateV3, Residence, NarrativeRole, Organization, Fact, Knowledge, assert_world_state_v3_invariants
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.residence import visible_social_state
from backend.runtime_v3.migration import migrate_v2
from backend.services.world_delta_errors import StructuralDeltaError

TEXT='Установлен новый факт. Я подтверждаю свой выбор.'


def state():
    return WorldStateV3(camera=dict(location_id='home',present_character_ids=['a'],controlled_actor_id='a'),
        characters={c:dict(id=c,location_id='home' if c=='a' else 'south',life_status='alive') for c in 'abc'},
        locations={k:dict(id=k,name=k,kind=kind,parent_id=p) for k,kind,p in (
            ('realm','realm',None),('north','city','realm'),('south','city','realm'),('home','building','north'),
            ('room','room','home'),('office','building','north'),('second','building','south'))},
        organizations={'guild':Organization(id='guild',name='Guild',kind='guild',status='active',location_ids=['office']).model_dump()}).model_dump()


def run(s, section=None, rows=(), *, player=TEXT, scene=None, **kwargs):
    payload=dict(final_scene=scene or dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=5))
    if section:
        payload[section]=[dict({'evidence':TEXT,'assertion':'established'},**r) for r in rows]
        if player:
            for r in payload[section]:r.update(player_assertion='explicit_choice',player_evidence=player)
        if section in ('locations','location_changes','organization_changes'):
            for r in payload[section]:
                r.pop('player_assertion',None);r.pop('player_evidence',None)
                if section=='locations':r.pop('assertion',None)
    return StateResolver(s,TEXT,player,**kwargs).resolve(payload)


def residence(rid='r1',actor='a',location='home',**kwargs):
    return dict(id=rid,actor_id=actor,location_id=location,**kwargs)


def role(rid='job',actor='a',**kwargs):
    return dict(dict(id=rid,actor_id=actor,kind='employment',title='Restorer',organization_id='guild'),**kwargs)


def proof(s,fid,actor='a',observers=('a',)):
    s['facts'][fid]=Fact(id=fid,text=fid,character_ids=[actor]).model_dump()
    for cid in observers:s['knowledge'][cid+':'+fid]=Knowledge(actor_id=cid,fact_id=fid).model_dump()


def test_travel_sublocations_and_role_never_mutate_residence_or_presence():
    s=run(state(),'residence_changes',[residence()]).state
    s=run(s,'role_changes',[role()]).state
    for destination in ('room','south','second','home'):
        before=deepcopy(s)
        s=run(s,scene=dict(location_id=destination,present_character_ids=['a'])).state
        assert s['residences']==before['residences'] and s['roles']==before['roles']
        assert s['characters']['a']['location_id']==destination
        assert s['characters']['b']['location_id']=='south'
    assert s['characters']['a']['location_id']!='office'


def test_relocation_replacement_is_explicit_atomic_and_history_is_immutable():
    s=run(state(),'residence_changes',[residence(),residence('holiday',location='room')]).state
    r=run(s,'residence_changes',[residence('new',location='second',replaces=['r1'])]);after=r.state
    assert after['residences']['r1']['status']=='closed'
    assert after['residences']['r1']['until']==10
    assert after['residences']['new']['since']==10
    assert after['residences']['holiday']['status']=='active'
    assert after['characters']==s['characters']
    assert any(h.get('entity')=='r1' and h['before']['status']=='active' for h in r.history['state_changes'])
    assert run(after,'residence_changes',[dict(id='r1',status='active')]).state['residences']==after['residences']
    bad=run(s,'residence_changes',[residence('bad',location='absent',replaces=['r1'])])
    assert bad.state['residences']==s['residences']
    assert not any(h.get('kind')=='residences' for h in bad.history['state_changes'])


def test_two_jobs_school_training_work_and_specific_termination():
    s=state();s['characters']['b']['developmental_stage']='child'
    for rid,kind,title in [('school','education','Pupil'),('academy','training','Apprentice'),('work','employment','Worker')]:
        previous={'academy':'school','work':'academy'}.get(rid)
        s=run(s,'role_changes',[dict(id=rid,actor_id='b',kind=kind,title=title,organization_id='guild',
            **({'replaces':[previous]} if previous else {}))]).state
    assert s['roles']['school']['status']=='closed' and s['roles']['academy']['status']=='closed'
    s=run(s,'role_changes',[role(),dict(id='student',actor_id='a',kind='education',title='Student',field='Maps')]).state
    r=run(s,'role_changes',[dict(id='job',status='closed',outcome='resigned')])
    assert r.state['roles']['student']['status']=='active' and r.state['roles']['work']['status']=='active'
    assert r.state['roles']['job']['outcome']=='resigned'
    assert r.state['characters']==s['characters']


@pytest.mark.parametrize('outcome',['graduated','completed','left','expelled','retired','fired','resigned'])
def test_role_endings_keep_opening_evidence(outcome):
    s=run(state(),'role_changes',[role()]).state
    r=run(s,'role_changes',[dict(id='job',status='closed',outcome=outcome)])
    assert r.state['roles']['job']['status']=='closed' and r.state['roles']['job']['evidence']==TEXT
    assert r.state['roles']['job']['since']==5 and r.state['roles']['job']['until']==10


def test_employer_program_change_new_phase_not_arbitrary_rewrite():
    s=run(state(),'role_changes',[role()]).state
    for field,value in [('organization_id',None),('field','New program'),('title','New job'),('actor_id','b')]:
        r=run(s,'role_changes',[dict(id='job',status='closed',**{field:value})])
        assert r.state['roles']==s['roles'] and r.warnings
    s=run(s,'organization_changes',[dict(id='academy',name='Academy',kind='academy',status='active')]).state
    s=run(s,'role_changes',[dict(id='training',actor_id='a',kind='education',title='Scholar',field='Maps',organization_id='academy',replaces=['job'])]).state
    assert s['roles']['job']['organization_id']=='guild' and s['roles']['job']['status']=='closed'
    assert s['roles']['training']['field']=='Maps'


def test_organization_rename_alias_closure_no_jobs_knowledge_or_residence_invented():
    s=run(state(),'role_changes',[role(),role('other','b')]).state
    s=run(s,'residence_changes',[residence()]).state
    knowledge=deepcopy(s['knowledge']);actors=deepcopy(s['characters']);homes=deepcopy(s['residences'])
    s=run(s,'organization_changes',[dict(id='guild',name='New Guild')]).state
    assert s['organizations']['guild']['name_history'][0]['previous']=='Guild'
    duplicate=run(s,'organization_changes',[dict(id='duplicate',name='Guild')])
    assert 'duplicate' not in duplicate.state['organizations'] and duplicate.warnings
    s=run(s,'organization_changes',[dict(id='guild',status='closed')]).state
    assert all(r['status']=='closed' and r['outcome']=='organization_closed' for r in s['roles'].values())
    assert s['knowledge']==knowledge and s['characters']==actors and s['residences']==homes
    assert 'new' not in run(s,'role_changes',[role('new')]).state['roles']
    assert run(s,'organization_changes',[dict(id='guild',status='active')]).state['organizations']==s['organizations']


def test_hierarchy_forward_parents_cycles_broken_refs_dynamic_aliases():
    s=state()
    r=run(s,'locations',[dict(id='new_room',name='New Room',parent_id='new_building'),
        dict(id='new_building',name='New Building',parent_id='north'),
        dict(id='cycle_a',name='Cycle A',parent_id='cycle_b'),dict(id='cycle_b',name='Cycle B',parent_id='cycle_a'),
        dict(id='orphan',name='Orphan',parent_id='absent')])
    assert set(r.state['locations'])-set(s['locations'])=={'new_room','new_building'}
    assert len(r.warnings)==3
    r=run(r.state,'location_changes',[dict(id='realm',parent_id='room'),dict(id='north',parent_id='absent'),dict(id='home',aliases=['House'])])
    assert r.state['locations']['realm']['parent_id'] is None and len(r.warnings)==2
    r=run(r.state,'locations',[dict(id='duplicate',name='House')],scene=dict(location_id='duplicate',present_character_ids=['a']))
    assert 'duplicate' not in r.state['locations'] and r.state['camera']['location_id']=='home'
    assert r.warnings[0]['code']=='location_identity_reused'


def test_new_scene_arrival_requires_movement_evidence_not_residence_or_job():
    s=run(state(),'residence_changes',[residence('remote','b','home')]).state
    s=run(s,'role_changes',[role('remote_job','b')]).state
    with pytest.raises(StructuralDeltaError,match='основания'):
        run(s,scene=dict(location_id='home',present_character_ids=['a','b']))
    r=run(s,scene=dict(location_id='home',present_character_ids=['a','b'],situation_evidence=TEXT))
    assert r.state['characters']['b']['location_id']=='home'
    assert r.state['residences']==s['residences']


@pytest.mark.parametrize('section,row',[
    ('residence_changes',residence(actor='absent')),('residence_changes',residence(location='absent')),
    ('residence_changes',dict(id=[],actor_id='a')),('role_changes',role(organization_id='absent')),
    ('role_changes',dict(id='x',actor_id='a',kind='education',title='Student',since=999)),
    ('organization_changes',dict(id='x',name='X',location_ids=['absent'])),
])
def test_malformed_optional_record_does_not_discard_ordinary_turn(section,row):
    s=state();r=run(s,section,[row])
    assert r.warnings and r.state['meta']['turn_id']==1
    assert r.state['roles']==s['roles'] and r.state['residences']==s['residences'] and r.state['organizations']==s['organizations']


def test_unsupported_future_and_player_background_agency():
    s=state()
    for section,row in [('residence_changes',residence()),('role_changes',role())]:
        assert run(s,section,[row],player='').warnings
        assert run(s,section,[dict(row,assertion='proposal')]).warnings
        assert run(s,section,[row],mode='background').warnings
        assert run(s,section,[dict(row,transition='external',decision_actor_id='a')],player='').warnings
        result=run(s,section,[dict(row,transition='external',decision_actor_id='b')],player='')
        assert not result.warnings
    s=run(s,'role_changes',[role()]).state
    r=run(s,'organization_changes',[dict(id='guild',status='closed')],mode='background')
    assert r.state['roles']==s['roles'] and r.state['organizations']==s['organizations'] and r.warnings


def test_known_opening_does_not_disclose_closure_or_rename_to_other_observer():
    s=state();proof(s,'opening',observers=('a','b'));proof(s,'closure');proof(s,'rename')
    s=run(s,'role_changes',[role(fact_id='opening')]).state
    s=run(s,'organization_changes',[dict(id='guild',name='Hidden new name',fact_id='rename')]).state
    s=run(s,'role_changes',[dict(id='job',status='closed',closure_fact_id='closure')]).state
    a=visible_social_state(s,'a')['roles'][0];b=visible_social_state(s,'b')['roles'][0]
    assert a['status']=='closed' and a['organization']=='Hidden new name'
    assert b['status']=='active' and b['organization']=='Guild' and b['until'] is None
    assert visible_social_state(s,'c')=={'residences':[],'roles':[]}
    assert 'evidence' not in json.dumps(b) and 'closure' not in json.dumps(b)


def test_legacy_unknown_defaults_idempotence_import_references_and_ordinary_turn():
    from devtools.narrative_test_world import build_fixture
    legacy=build_fixture();original=deepcopy(legacy)
    first=migrate_v2(legacy).snapshot;second=migrate_v2(first).snapshot
    assert first==second and legacy==original
    s=first['world_state']
    assert not s['residences'] and not s['roles'] and not s['organizations']
    assert all(loc['parent_id'] is None and loc['kind']=='unknown' for loc in s['locations'].values())
    assert run(s).state['characters']==s['characters']
    fixture=build_fixture('residence-roles')
    structured=migrate_v2(fixture).snapshot['world_state']
    assert structured['locations']['qa_room']['parent_id']=='qa_home'
    assert structured['characters']['qa_elena']['location_id']=='qa_garden'
    assert structured['residences']['qa_elena_residence']['location_id']=='qa_garden'
    from backend.services.draft_world import validate
    fixture['locations'][0]['parent_id']='qa_room'
    assert validate(fixture)['errors']


def test_context_contains_current_hierarchy_organization_and_knowledge_without_presence():
    from backend.runtime_v3.context import build_context
    from devtools.narrative_test_world import build_fixture
    snap=migrate_v2(build_fixture('residence-roles')).snapshot
    msgs=build_context(snap,[],'Ася думает о школе.','turn',32768,2000)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in msgs if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert any(r['id']=='qa_job' for r in current['roles'])
    assert current['locations']['qa_realm']['kind']=='realm'
    assert any(o['id']=='qa_restorers' for o in current['organizations'])
    assert 'qa_elena' not in current['camera']['present_character_ids']
    assert not any(r['id']=='qa_elena_residence' for r in current['residence_role_knowledge']['qa_kirill']['residences'])


@settings(deadline=None,max_examples=20)
@given(st.lists(st.integers(min_value=0,max_value=4),min_size=1,max_size=20))
def test_property_concurrent_phases_reload_never_changes_unrelated_state(actions):
    s=state();s=run(s,'residence_changes',[residence()]).state
    for n in actions:
        old=deepcopy(s);rid='role'+str(n)
        r=run(s,'role_changes',[dict(id=rid,actor_id='b',kind='other',title=rid)])
        s=assert_world_state_v3_invariants(json.loads(json.dumps(r.state)))
        assert s['residences']==old['residences'] and s['characters']==old['characters']
        assert set(old['roles'])<=set(s['roles'])


def test_real_start_turn_reload_regenerate_variants_rollback_and_sibling_history(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import ordinary_job,CONFIG
    from runtime_v3_fixture import execute
    from test_runtime_v3_storage import connection
    from backend.runtime_v3.repository import committed_snapshot,read_history
    repo=Repository(tmp_path/'residence.sqlite');sid=load_fixture(repo,'residence-roles')['save']
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    before=repo.get_snapshot(sid)
    camera=before['world_state']['camera']
    raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
        residence_changes=[dict(id='new_home',actor_id=ACTOR_ID,location_id='qa_garden',replaces=['qa_home_residence'],
            evidence=TEXT,assertion='established',player_assertion='explicit_choice',player_evidence=TEXT)],
        role_changes=[dict(id='new_role',actor_id=ACTOR_ID,kind='education',title='Ученик',organization_id='qa_academy',
            evidence=TEXT,assertion='established',player_assertion='explicit_choice',player_evidence=TEXT)])
    jid=repo.begin_job(sid,TEXT,'turn',CONFIG);execute(repo,jid,raw,TEXT)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert after['world_state']['residences']['qa_home_residence']['status']=='closed'
    assert 'new_role' in after['world_state']['roles']
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==after
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    execute(repo,jid,dict(final_scene=raw['final_scene']),'Разговор продолжается.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    alternate=repo.get_snapshot(sid)
    assert alternate['world_state']['residences']==before['world_state']['residences']
    assert alternate['world_state']['roles']==before['world_state']['roles']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==before
    # Independent sibling history batches over the same canonical base.
    db=connection(tmp_path/'branches.sqlite')
    a=run(before['world_state'],'role_changes',[dict(id='qa_job',status='closed')])
    b=run(before['world_state'],'residence_changes',[dict(id='qa_home_residence',status='closed')])
    with db:
        sa=committed_snapshot(db,before,a);sb=committed_snapshot(db,before,b)
    assert sa['history_head']!=sb['history_head']
    assert sa['world_state']['residences']['qa_home_residence']['status']=='active'
    assert sb['world_state']['roles']['qa_job']['status']=='active'
    assert read_history(db,sa['history_head'])!=read_history(db,sb['history_head'])


def test_closed_last_role_is_authoritative_over_static_card_and_history_is_lower_priority():
    from backend.runtime_v3.context import build_context
    from devtools.narrative_test_world import build_fixture
    snap=migrate_v2(build_fixture('residence-roles')).snapshot
    snap['world_state']=run(snap['world_state'],'role_changes',[dict(id='qa_job',status='closed')]).state
    msgs=build_context(snap,[],'Продолжаем разговор.','turn',32768,2000)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in msgs if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert current['social_status']['qa_kirill']['roles']==[]
    assert 'social_history' not in current
    assert current['social_status']['qa_kirill']['residences']==['qa_home_residence']


def test_real_time_skip_does_not_create_or_close_roles_residences(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job,CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'skip.sqlite');sid=load_fixture(repo,'residence-roles')['save']
    ordinary_job(repo,sid,'start');before=repo.get_snapshot(sid)['world_state'];camera=before['camera']
    jid=repo.begin_job(sid,'Жду минуту.','turn',dict(CONFIG,time_skip=dict(duration=1)))
    execute(repo,jid,dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'])),'Проходит минута.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=Repository(repo.path).get_snapshot(sid)['world_state']
    assert after['meta']['world_time']==before['meta']['world_time']+1
    for section in ('roles','residences','organizations'):assert after[section]==before[section]


def test_bad_organization_closure_rolls_back_cascade_and_history():
    s=run(state(),'role_changes',[role()]).state
    r=run(s,'organization_changes',[dict(id='guild',status='closed',closure_fact_id='absent')])
    assert r.state['roles']==s['roles'] and r.state['organizations']==s['organizations']
    assert not any(h.get('kind') in ('roles','organizations') for h in r.history['state_changes'])
    assert r.warnings


def test_import_duplicate_organization_alias_and_broken_role_reference_rejected():
    from devtools.narrative_test_world import build_fixture
    from backend.services.draft_world import validate
    f=build_fixture('residence-roles')
    f['world']['organizations']['duplicate']=Organization(id='duplicate',name='Мастерская карт').model_dump()
    assert validate(f)['errors']
    f=build_fixture('residence-roles');f['world']['roles']['qa_job']['organization_id']='missing'
    assert validate(f)['errors']


def test_pre39_v3_snapshot_defaults_do_not_rewrite_old_snapshot():
    s=state();s.pop('residences');s.pop('roles');s.pop('organizations')
    for loc in s['locations'].values():
        for key in ('parent_id','kind','aliases'):loc.pop(key)
    original=deepcopy(s)
    snapshot=dict(schema_version=3,world_state=s,character_cards=[],campaign={})
    migrated=migrate_v2(snapshot).snapshot
    assert s==original and snapshot['world_state']==original
    for section in ('residences','roles','organizations'):assert migrated['world_state'][section]=={}
    assert migrate_v2(migrated).snapshot==migrated
    assert run(migrated['world_state']).state['characters']==s['characters']


def test_import_distinct_same_named_places_resolve_by_explicit_ids():
    from devtools.narrative_test_world import build_fixture
    f=build_fixture('residence-roles')
    f['locations'] += [dict(id='room_a',name='Комната',text='',kind='room',parent_id='qa_home'),
                       dict(id='room_b',name='Комната',text='',kind='room',parent_id='qa_garden')]
    f['world']['characters']['qa_elena']['location']='room_b'
    s=migrate_v2(f).snapshot['world_state']
    assert s['characters']['qa_elena']['location_id']=='room_b'
    assert s['locations']['room_a']['parent_id']=='qa_home'


@pytest.mark.parametrize('section',['residences','roles','organizations'])
@pytest.mark.parametrize('bad',[None,[],42])
def test_malformed_optional_import_map_reports_error(section,bad):
    from devtools.narrative_test_world import build_fixture
    from backend.services.draft_world import validate
    f=build_fixture('residence-roles');f['world'][section]=bad
    assert validate(f)['errors']


def test_token_pressure_drops_known_closed_history_before_current_roles():
    from backend.runtime_v3.context import build_context
    from devtools.narrative_test_world import build_fixture,ACTOR_ID
    snap=migrate_v2(build_fixture('residence-roles')).snapshot;s=snap['world_state']
    proof(s,'archive',ACTOR_ID,(ACTOR_ID,))
    for i in range(20):
        rid='archive_'+str(i)
        s['roles'][rid]=NarrativeRole(id=rid,actor_id=ACTOR_ID,kind='employment',title='Архив',status='closed',
            since=0,until=1,outcome='ended',fact_id='archive',closure_fact_id='archive').model_dump()
    msgs=build_context(snap,[],'Архив','turn',128000,2000,target_context_budget=1000)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in msgs if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert any(r['id']=='qa_job' for r in current['roles'])
    assert 'social_history' not in current
    assert all(r['status']=='active' for r in current['residence_role_knowledge'][ACTOR_ID]['roles'])
    assert len(s['roles'])==22


def test_legacy_empty_place_name_remains_loadable_but_new_empty_place_is_local_error():
    s=state();s['locations']['home']['name']=''
    assert assert_world_state_v3_invariants(s)['locations']['home']['name']==''
    r=run(s,'locations',[dict(id='new',name='')])
    assert 'new' not in r.state['locations'] and r.warnings
