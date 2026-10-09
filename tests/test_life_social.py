"""#38 canonical transitions, secrecy and real storage lineage regressions."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, settings, strategies as st
from backend.runtime_v3.models import Character, WorldStateV3, Fact, Knowledge, ObjectiveRelation, Condition, assert_world_state_v3_invariants
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.kinship import genealogy, visible_relations

TEXT='Установлен новый факт. Подтверждаю свой выбор.'


def state():
    return WorldStateV3(camera=dict(location_id='home',present_character_ids=['a','b'],controlled_actor_id='a'),
        characters={c:Character(id=c,location_id='home' if c in 'ab' else None,display_name=c.upper(),life_status='alive').model_dump() for c in 'abcdef'},
        locations={'home':dict(id='home',name='Дом')}).model_dump()


def snapshot(s):
    return dict(world_state=s,character_cards=[dict(id=c,name=c.upper(),fields={}) for c in s['characters']])


def run(s,section=None,records=(),text=TEXT,player=TEXT,**kwargs):
    rows=[]
    for r in records:
        r=deepcopy(r);r.setdefault('evidence',text);r.setdefault('assertion','established')
        if player:r.setdefault('player_assertion','explicit_choice');r.setdefault('player_evidence',player)
        rows.append(r)
    payload=dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=1))
    if section:payload[section]=rows
    return StateResolver(s,text,player,**kwargs).resolve(payload)


def tie(rid='marriage',kind='spouse',a='a',b='b',**kw):
    return dict(id=rid,kind=kind,source_id=a,target_id=b,**kw)


def inform(s,fid,actors,observers):
    s['facts'][fid]=Fact(id=fid,text=fid,character_ids=actors).model_dump()
    for c,status in observers.items():s['knowledge'][c+':'+fid]=Knowledge(actor_id=c,fact_id=fid,status=status).model_dump()


def test_partner_engagement_marriage_divorce_reconnection_keep_all_phases_and_names():
    s=state();baseline=deepcopy(s['relationships'])
    for kind in ('partner','engaged','spouse'):
        s=run(s,'social_relation_changes',[tie(kind,kind)]).state
    before=deepcopy(s)
    s=run(s,'social_relation_changes',[dict(id='engaged',status='closed',outcome='superseded'),
        dict(id='partner',status='closed'),dict(id='spouse',status='closed',outcome='divorced'),
        tie('remarriage','spouse','a','c')]).state
    assert len(s['objective_relations'])==4
    assert s['objective_relations']['spouse']['outcome']=='divorced'
    assert s['objective_relations']['engaged']['outcome']=='superseded'
    assert s['objective_relations']['remarriage']['status']=='active'
    assert s['relationships']==baseline
    assert s['characters']==before['characters']
    rejected=run(s,'social_relation_changes',[dict(id='spouse',status='active')])
    assert rejected.state['objective_relations']==s['objective_relations'] and rejected.warnings


def test_concurrent_marriages_and_contacts_no_monogamy_or_emotion_coupling():
    s=run(state(),'social_relation_changes',[tie(),tie('second','spouse','a','c'),tie('friend','friend')]).state
    s=run(s,'social_relation_changes',[dict(id='marriage',status='closed',outcome='divorced')]).state
    assert s['objective_relations']['second']['status']=='active'
    assert s['objective_relations']['friend']['status']=='active'
    assert not s['relationships']
    s=run(s,'social_relation_changes',[dict(id='friend',status='closed')]).state
    s=run(s,'social_relation_changes',[tie('friend-again','close_friend')]).state
    assert s['objective_relations']['friend']['status']=='closed'


@pytest.mark.parametrize('bad',[
    tie(evidence='not in narrative'),tie(assertion='proposal'),tie(assertion='wish'),
    tie(a='missing'),tie(a='a',b='a'),tie(kind='emotional_parent'),dict(id=[],kind='spouse'),
])
def test_optional_bad_records_are_local(bad):
    s=state()
    r=run(s,'social_relation_changes',[bad,tie('good','friend','c','d')])
    assert set(r.state['objective_relations'])=={'good'}
    assert r.warnings and r.state['meta']['turn_id']==1
    assert s==state()


def test_no_player_choice_no_voluntary_relation_but_npc_closure_is_allowed():
    r=run(state(),'social_relation_changes',[tie()],player='')
    assert not r.state['objective_relations']
    s=run(state(),'social_relation_changes',[tie()]).state
    r=run(s,'social_relation_changes',[dict(id='marriage',status='closed',decision_actor_id='b')],player='')
    assert r.state['objective_relations']['marriage']['status']=='closed'
    r=run(s,'social_relation_changes',[dict(id='marriage',status='closed')],player='',mode='background',protected_actor_id='a')
    assert r.state['objective_relations']==s['objective_relations']


def test_inverse_symmetry_duplicate_and_cycle_never_rewrite_existing_relations():
    s=run(state(),'social_relation_changes',[tie('child','child','b','a'),tie('bc','parent','b','c')]).state
    assert s['objective_relations']['child']['source_id']=='a'
    r=run(s,'social_relation_changes',[tie('duplicate','parent','a','b'),tie('cycle','parent','c','a'),tie('ok','guardian','d','b')])
    assert set(r.state['objective_relations'])=={'child','bc','ok'} and len(r.warnings)==2
    r=run(r.state,'social_relation_changes',[dict(id='child',target_id='d')])
    assert r.state['objective_relations']['child']['target_id']=='b'


def test_adoption_guardian_foster_step_and_revocation_preserve_biology_and_personality():
    s=run(state(),'social_relation_changes',[tie('bio','parent','c','d'),tie('guardian','guardian','e','d'),
        tie('foster','foster_parent','f','d'),tie('step','step_parent','b','d')],player='').state
    actors=deepcopy(s['characters']);knowledge=deepcopy(s['knowledge'])
    s=run(s,'social_relation_changes',[dict(id='guardian',status='closed'),tie('adoption','adoptive_parent','e','d'),
                                     tie('adoption2','adoptive_parent','f','d')],player='').state
    assert s['characters']==actors and s['knowledge']==knowledge
    assert s['objective_relations']['bio']['status']=='active'
    assert s['objective_relations']['guardian']['status']=='closed'
    s=run(s,'social_relation_changes',[dict(id='adoption',status='closed',outcome='revoked')],player='').state
    assert s['objective_relations']['adoption2']['status']=='active'
    assert s['objective_relations']['step']['kind']=='step_parent'


def test_name_change_history_and_no_marriage_surname_inference():
    s=run(state(),'social_relation_changes',[tie()]).state
    assert s['characters']['a']['display_name']=='A'
    r=run(s,'life_changes',[dict(id='a',display_name='Новое имя')],player='')
    assert r.state['characters']['a']['display_name']=='A'
    s=run(s,'life_changes',[dict(id='a',display_name='Новое имя')]).state
    s=run(s,'life_changes',[dict(id='a',display_name='Третье имя')]).state
    assert [r['previous'] for r in s['characters']['a']['name_history']]==['A','Новое имя']
    assert s['characters']['a']['display_name']=='Третье имя'
    assert assert_world_state_v3_invariants(json.loads(json.dumps(s)))==s


def test_death_is_not_missing_and_death_blocks_scene_emotions_movement_and_background():
    from backend.runtime_v3.director import background_candidate,interval_candidates
    s=run(state(),'social_relation_changes',[tie()]).state
    s=run(s,'life_changes',[dict(id='b',life_status='missing')]).state
    assert capabilities(s,'b')['can_act']
    s['characters']['b']['goals']=[dict(id='goal',text='Работать',status='active',source_sequence=0,evidence='',due_minute=None)]
    r=run(s,'life_changes',[dict(id='b',life_status='dead')]);s=r.state
    assert s['characters']['b']['life_status']=='dead' and 'b' not in s['camera']['present_character_ids']
    assert s['characters']['b']['goals'][0]['status']=='cancelled'
    assert s['objective_relations']['marriage']['outcome']=='widowed'
    assert not capabilities(s,'b')['can_act']
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['a','b']),character_changes=[dict(id='b',emotion='Радость',evidence=TEXT)],
        relationship_changes=[dict(source_id='b',target_id='a',dimensions={'trust':80},evidence=TEXT)])
    result=StateResolver(s,TEXT,'').resolve(raw)
    assert result.state['characters']['b']==s['characters']['b']
    assert not result.state['relationships'] and 'b' not in result.state['camera']['present_character_ids']
    after=deepcopy(s);after['meta']['world_time']+=100
    assert background_candidate(s,after) is None and not interval_candidates(s,after)[0]
    assert run(s,'life_changes',[dict(id='b',life_status='alive')]).state['characters']['b']['life_status']=='dead'


def test_dead_controlled_identity_retained_without_ordinary_choices():
    r=run(state(),'life_changes',[dict(id='a',life_status='dead')])
    assert r.state['camera']['controlled_actor_id']=='a'
    assert r.state['camera']['mode']=='actor' and 'a' in r.state['characters']
    assert r.choices==[]
    assert run(r.state).state['characters']['a']['life_status']=='dead'


def test_conditions_overlap_unknown_outcome_and_explicit_recovery():
    s=run(state(),'condition_changes',[dict(id='coma',actor_id='a',description='Без сознания',effects={'conscious':False}),
        dict(id='leg',actor_id='a',description='Травма ноги',effects={'can_move':False},duration='persistent')]).state
    assert not capabilities(s,'a')['can_act']
    s=run(s,'condition_changes',[dict(id='coma',status='unknown_outcome')]).state
    assert not capabilities(s,'a')['can_act']
    s=run(s,'condition_changes',[dict(id='coma',status='resolved')]).state
    assert capabilities(s,'a')['can_act'] and not capabilities(s,'a')['can_move']
    assert s['conditions']['leg']['status']=='active'
    r=run(s,'condition_changes',[dict(id='leg',effects={'can_move':True})])
    assert r.state['conditions']==s['conditions'] and r.warnings
    assert run(s,'condition_changes',[dict(id='coma',status='active')]).state['conditions']['coma']['status']=='resolved'


@pytest.mark.parametrize('stage,act,speak,adult',[('infant',False,False,False),('child',True,True,False),('adolescent',True,True,False),('adult',True,True,True),('unknown',True,True,False)])
def test_coarse_developmental_eligibility_without_biography(stage,act,speak,adult):
    s=run(state(),'life_changes',[dict(id='c',developmental_stage=stage)]).state
    c=capabilities(s,'c')
    assert (c['can_act'],c['can_speak'],c['adult_eligible'])==(act,speak,adult)
    assert not s['characters']['c']['goals'] and not s['objective_relations']


def family():
    s=state()
    records=[]
    for rid,a,b in [('ab','a','b'),('bc','b','c'),('bd','b','d'),('ec','e','c'),('fd','f','d')]:
        inform(s,rid,[a,b],{'a':'known','b':'known'})
        records.append(tie(rid,'parent',a,b,fact_id=rid))
    s=run(s,'social_relation_changes',records).state
    return s


def test_genealogy_inverse_ancestors_siblings_unknown_parentage_and_boundaries():
    s=family();g=genealogy(snapshot(s))
    assert any(r['kind']=='ancestor' and r['source_id']=='a' and r['target_id']=='c' for r in g['kinship'])
    assert any(r['kind']=='descendant' and r['source_id']=='c' and r['target_id']=='a' for r in g['kinship'])
    assert any(r['kind']=='sibling' and r['source_id']=='c' and r['target_id']=='d' for r in g['kinship'])
    assert not any(r['kind']=='half_sibling' for r in g['kinship'])
    for c in 'cd':
        inform(s,'complete_'+c,[c],{'a':'known'})
        s['characters'][c]['parentage_complete_fact_id']='complete_'+c
    assert any(r['kind']=='half_sibling' for r in genealogy(snapshot(s))['kinship'])
    assert len(genealogy(snapshot(s),limit=2)['nodes'])==2
    assert len(genealogy(snapshot(s),depth=0)['nodes'])==1
    with pytest.raises(ValueError):genealogy(snapshot(s),depth=9)


def test_unknown_and_suspected_links_no_hidden_counts_names_or_closure_metadata():
    s=family();baseline=genealogy(snapshot(s))
    inform(s,'secret',['e','f'],{'e':'known'})
    s=run(s,'social_relation_changes',[tie('secret','spouse','e','f',fact_id='secret')]).state
    assert genealogy(snapshot(s))==baseline
    assert genealogy(snapshot(s),'missing')==genealogy(snapshot(s),'not_known')
    s['camera']['controlled_actor_id']='b'
    inform(s,'suspect',['e','f'],{'b':'suspected'})
    s=run(s,'social_relation_changes',[tie('care','guardian','e','f',fact_id='suspect')]).state
    assert next(r for r in genealogy(snapshot(s))['edges'] if r['id']=='care')['certainty']=='suspected'
    assert 'secret' not in json.dumps(genealogy(snapshot(s)))
    s=run(s,'social_relation_changes',[dict(id='care',status='closed',outcome='revoked')]).state
    assert next(r for r in visible_relations(s,'b') if r['id']=='care')['status']=='active'
    assert 'revoked' not in json.dumps(genealogy(snapshot(s)))


def test_known_dead_ancestor_and_name_disclosure_do_not_broadcast():
    s=family();inform(s,'death',['b'],{'a':'known'})
    s=run(s,'life_changes',[dict(id='b',life_status='dead',fact_id='death')]).state
    assert next(n for n in genealogy(snapshot(s))['nodes'] if n['id']=='b')['life_status']=='dead'
    inform(s,'rename',['c'],{'b':'known'})
    s=run(s,'life_changes',[dict(id='c',display_name='Secret new name',fact_id='rename')]).state
    assert 'Secret new name' not in json.dumps(genealogy(snapshot(s)))
    s['knowledge']['a:rename']=Knowledge(actor_id='a',fact_id='rename').model_dump()
    assert 'Secret new name' in json.dumps(genealogy(snapshot(s)))


@settings(deadline=None,max_examples=10)
@given(st.integers(min_value=100,max_value=125))
def test_long_turns_pruning_and_reload_do_not_erase_relations(turns):
    s=run(state(),'social_relation_changes',[tie()]).state
    canonical=deepcopy(s['objective_relations'])
    for _ in range(turns):s=run(s).state
    # No history is provided at all, equivalent to bounded/pruned History reads.
    s=assert_world_state_v3_invariants(json.loads(json.dumps(s)))
    assert s['objective_relations']==canonical


def test_event_without_relation_delta_and_asymmetric_feelings_are_independent():
    s=state();raw=dict(final_scene=dict(location_id='home',present_character_ids=['a','b']),
        events=[dict(id='shared',text=TEXT,evidence=TEXT,participants=['a','b'])])
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert not r.state['relationships'] and not r.state['objective_relations']
    raw['relationship_changes']=[dict(source_id='b',target_id='a',dimensions={'affection':20},evidence=TEXT)]
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert r.state['relationships']['b:a']['dimensions']['affection']==20
    assert 'a:b' not in r.state['relationships'] and not r.state['knowledge']


def test_qa_real_start_reload_regenerate_rollback_branch_and_read_api(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import ordinary_job,CONFIG
    from runtime_v3_fixture import execute
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    repo=Repository(tmp_path/'life.sqlite');sid=load_fixture(repo,'family')['save']
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    before=repo.get_snapshot(sid)
    def job(records,text,kind='turn',section='social_relation_changes'):
        camera=repo.get_snapshot(sid)['world_state']['camera']
        payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
            **{section:[dict(r,assertion='established',evidence=text,player_assertion='explicit_choice',player_evidence=text) for r in records]})
        jid=repo.begin_job(sid,text if kind=='turn' else '',kind,CONFIG)
        execute(repo,jid,payload,text)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        return repo.get_snapshot(sid)
    after=job([dict(id='qa_marriage',status='closed',outcome='divorced')],'Я подтверждаю развод.')
    turn=repo.list_turns(sid)[-1]
    alternate=job([], 'Развод не состоялся.','regenerate')
    assert alternate['world_state']['objective_relations']['qa_marriage']['status']=='active'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before
    client=TestClient(create_app(repo.path));revision=repo.get_save(sid)['revision']
    g=client.get(f'/api/saves/{sid}/genealogy').json()
    assert 'qa_secret_parent' not in json.dumps(g) and 'qa_zoya' not in json.dumps(g)
    assert client.get(f'/api/saves/{sid}/genealogy?root_id=qa_zoya').json()==client.get(f'/api/saves/{sid}/genealogy?root_id=absent').json()
    assert client.get(f'/api/saves/{sid}/genealogy?depth=99').status_code==409
    assert repo.get_save(sid)['revision']==revision
    job([dict(id=ACTOR_ID,capabilities={'can_act':False})],'Кирилл временно не может действовать.',section='life_changes')
    with pytest.raises(ValueError,match='не может действовать'):repo.begin_job(sid,'Бегу.', 'turn',CONFIG)
    jid=repo.begin_job(sid,'','turn',CONFIG)
    camera=repo.get_snapshot(sid)['world_state']['camera']
    execute(repo,jid,dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1)),'Проходит минута.')
    assert repo.get_job(jid)['status']=='saved'
    assert repo.list_turns(sid)[-1]['choices_json']=='[]'


def test_read_defaults_and_malformed_optional_fields_do_not_rewrite_original(caplog):
    s=state();s['characters']['a'].update(life_status='typo',capabilities={'can_act':'bad'})
    s['objective_relations']['bad']={'id':'bad','kind':'not_supported'}
    original=deepcopy(s)
    result=assert_world_state_v3_invariants(s)
    assert s==original and result['characters']['a']['life_status']=='unknown'
    assert not capabilities(result,'a')['can_act'] and not result['objective_relations']
    assert 'malformed optional' in caplog.text


def test_partial_condition_effect_update_cannot_silently_heal():
    s=run(state(),'condition_changes',[dict(id='coma',actor_id='c',description='Кома',effects={'conscious':False})]).state
    s=run(s,'condition_changes',[dict(id='coma',effects={'can_move':False})]).state
    assert not capabilities(s,'c')['conscious'] and not capabilities(s,'c')['can_move']
    s=run(s,'condition_changes',[dict(id='coma',effects={'conscious':None})]).state
    assert not capabilities(s,'c')['conscious']


@pytest.mark.parametrize('malformed',[None,[], 'corrupt'])
def test_corrupt_condition_section_cannot_silently_restore_capabilities(malformed):
    s=state();s['conditions']=malformed
    with pytest.raises(ValueError,match='capability safety'):
        assert_world_state_v3_invariants(s)


def test_known_revoked_adoption_keeps_history_without_current_derived_kinship():
    s=state()
    inform(s,'adoption',['b','c'],{'a':'known','b':'known'})
    inform(s,'revocation',['b','c'],{'a':'known'})
    s=run(s,'social_relation_changes',[tie('adopt','adoptive_parent','b','c',fact_id='adoption')]).state
    s=run(s,'social_relation_changes',[dict(id='adopt',status='closed',outcome='revoked',closure_fact_id='revocation')]).state
    g=genealogy(snapshot(s),'b')
    assert g['edges'][0]['status']=='closed' and not g['kinship']
    s['camera']['controlled_actor_id']='b'
    g=genealogy(snapshot(s),'b')
    assert g['edges'][0]['status']=='active' and g['kinship']


def test_death_invalidates_commitments_without_success_and_no_new_unrelated_changes():
    from test_commitments import plans,change
    s=plans()
    s=run(s,'life_changes',[dict(id='sonya',life_status='dead')]).state
    assert s['scheduled_events']['trip']['status']=='cancelled'
    assert s['scheduled_events']['return']['status']=='cancelled'
    assert not any(e['outcome']=='fulfilled' for e in s['scheduled_events'].values())
    s2=change(s,[dict(id='trip',assertion='occurred')],player='').state
    assert s2['scheduled_events']==s['scheduled_events']


def test_invalid_transition_does_not_leave_phantom_history():
    s=run(state(),'social_relation_changes',[tie()]).state
    # Fact does not cover B, so the entire optional death transition is rejected.
    inform(s,'bad',['a'],{'a':'known'})
    r=run(s,'life_changes',[dict(id='b',life_status='dead',fact_id='bad')])
    assert r.state['objective_relations']==s['objective_relations']
    assert not any(h.get('kind')=='objective_relations' for h in r.history['state_changes'])


def test_real_history_sibling_branches_keep_independent_genealogy(tmp_path):
    from test_runtime_v3_storage import connection
    from backend.runtime_v3.repository import committed_snapshot,read_history
    s=family();base=dict(snapshot(s),schema_version=3,campaign={},memory={},history_head=None)
    a=run(s,'social_relation_changes',[dict(id='bc',status='closed',outcome='revoked')])
    b=run(s,'life_changes',[dict(id='c',display_name='Ветка Б')])
    db=connection(tmp_path/'siblings.sqlite')
    with db:
        sa=committed_snapshot(db,base,a);sb=committed_snapshot(db,base,b)
    assert sa['history_head']!=sb['history_head']
    assert sa['world_state']['characters']['c']['display_name']=='C'
    assert sb['world_state']['objective_relations']['bc']['status']=='active'
    assert read_history(db,sa['history_head'])!=read_history(db,sb['history_head'])
    assert genealogy(json.loads(json.dumps(sa)))==genealogy(sa)
    assert genealogy(json.loads(json.dumps(sb)))==genealogy(sb)


def test_import_cycles_and_wrong_references_rejected_before_confirmation():
    from devtools.narrative_test_world import build_fixture
    from backend.services.draft_world import validate
    f=build_fixture('family')
    f['world']['objective_relations']['bad']=ObjectiveRelation(id='bad',kind='parent',source_id='qa_asya',target_id='qa_kirill').model_dump()
    assert validate(f)['errors']


@pytest.mark.parametrize('checkpoint',['family','family-care','family-incapacitated'])
def test_family_checkpoints_use_normal_import_and_incapacitated_start_is_playable(tmp_path,checkpoint):
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from backend.repositories.preparation import Repository
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'checkpoints.sqlite')
    sid=load_fixture(repo,checkpoint)['save']
    snap=ordinary_job(repo,sid,'start')
    assert bool(capabilities(snap['world_state'],ACTOR_ID)['can_act'])==(checkpoint!='family-incapacitated')
    assert repo.get_save(sid)['state']['life_state']['life_status']=='alive'
    if checkpoint=='family-care':
        from backend.runtime_v3.camera import transition
        assert 'qa_guardianship' not in json.dumps(genealogy(snap))
        assert 'qa_guardianship' in json.dumps(genealogy(transition(snap,'qa_vera')))


def test_impossible_known_biological_birth_order_rejected_locally():
    s=state();s['characters']['a']['birth_date']='2020-01-01';s['characters']['b']['birth_date']='2000-01-01'
    r=run(s,'social_relation_changes',[tie('bad','parent')])
    assert not r.state['objective_relations'] and r.warnings
