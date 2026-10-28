"""#41 deterministic domain and repository/POV regressions, no live model calls."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import WorldStateV3, Character, Calendar, Knowledge
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.reproduction import appearance_adapter, context_projection
from backend.runtime_v3.milestones import derive
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.repository import committed_snapshot
from backend.runtime_v3.kinship import genealogy
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.context import build_context
from test_milestones import db

TEXT='Оба взрослых участника подтвердили согласие; событие произошло.'
BIRTH='Роды завершились в доме; присутствующие увидели детей.'
NAME='Мы договорились об имени.'


def state(count=1):
    actors={c:Character(id=c,display_name=c,location_id='home',life_status='alive',
        developmental_stage='adult',birth_date='1990-01-01',
        reproductive_capability='can_become_pregnant' if c=='a' else 'can_impregnate',
        personality={},values={},identity_components={'family_name':'Общее'}).model_dump() for c in 'abc'}
    return WorldStateV3(characters=actors,camera=dict(location_id='home',present_character_ids=['a','b'],controlled_actor_id='a'),
        locations={'home':dict(id='home',name='Дом')},
        meta=dict(calendar=Calendar(start_minute=0,start_weekday=0,start_date='2026-01-01')),
        reproduction_policy=dict(unprotected=1.,protected=0.,unknown=0.,child_weights=[0.]*(count-1)+[1.],gestation_days=1)).model_dump()


def snap(s):
    return dict(schema_version=3,world_state=s,character_cards=[dict(id=c,name=c,fields={}) for c in s['characters']],campaign={},memory={},history_head=None)


def service(**changes):
    return dict(dict(id='encounter',kind='sexual_intercourse',source_event_id='event',gestational_actor_id='a',
        impregnating_actor_id='b',protection='unprotected',consent_actor_ids=['a','b'],parent_ids=['a','b'],
        assertion='completed_consensual_adult_event',evidence=TEXT,player_evidence=TEXT,player_assertion='explicit_choice'),**changes)


def run(s, section=None, rows=(), text=TEXT, player=TEXT, elapsed=0, witnesses=None, **kwargs):
    raw=dict(final_scene=dict(location_id='home',present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=elapsed),
        events=[dict(id='event',text=text,evidence=text,participants=['a','b'],witnesses=witnesses or ['a','b'],fact_ids=[],medium='observation')])
    if section: raw[section]=list(rows)
    return StateResolver(s,text,player,**kwargs).resolve(raw)


def conceive(s=None,**kw): return run(s or state(),'reproductive_events',[service(**kw)])


def deliver(s,**kw):
    p=next(iter(s['pregnancies'].values()))
    return run(s,'births',[dict(pregnancy_id=p['id'],source_event_id='event',assertion='birth_completed',
        location_id='home',evidence=BIRTH,disclosed_parent_ids=p['parent_ids'],**kw)],text=BIRTH+' '+ ' '.join(kw.get('appearance',{}).values()),elapsed=max(0,p['due_minute']-s['meta']['world_time']))


@pytest.mark.parametrize('count',[1,2,3])
def test_conception_birth_multiples_retry_rollback_and_cards(count):
    original=state(count);r=conceive(original)
    assert r.state['relationships']==original['relationships']
    assert not r.state['knowledge']
    p=next(iter(r.state['pregnancies'].values()));assert len(p['children'])==count
    assert p['conception_minute'] is None
    retry=conceive(r.state);assert retry.state['pregnancies']==r.state['pregnancies']
    assert retry.state['reproductive_events']==r.state['reproductive_events']
    result=deliver(r.state)
    assert len(result.cards)==count and len(result.state['characters'])==3+count
    assert len(result.state['objective_relations'])==2*count
    assert len([m for m in derive(result.history) if m['category']=='birth'])==count
    assert not deliver(result.state).cards
    assert deliver(result.state).state['objective_relations']==result.state['objective_relations']
    snapshot=snap(r.state);con=db();committed=committed_snapshot(con,snapshot,result)
    assert len(genealogy(committed)['nodes'])==2+count
    for child in p['children']:
        actor=result.state['characters'][child['id']]
        assert actor['biological_sex']==child['sex']
        assert actor['birth_date']=='2026-01-02'
        assert not capabilities(result.state,child['id'])['can_act']
        assert actor['display_name'] is None and actor['identity_components']=={'family_name':'Общее'}
        assert actor['goals']==actor['intentions']==actor['obligations']==[]
        assert actor['values']=={} and set(actor['personality']['items'])=={'early_temperament'}
        assert not any(k['actor_id']==child['id'] for k in result.state['knowledge'].values())
    assert migrate_v2(json.loads(json.dumps(committed))).snapshot['world_state']==committed['world_state']
    assert snapshot['world_state']==r.state  # immutable before/rollback boundary
    assert original==state(count)


@pytest.mark.parametrize('change',[
    {'gestational_actor_id':'missing'}, {'impregnating_actor_id':'a'}, {'consent_actor_ids':['a']},
    {'assertion':'intention'}, {'player_evidence':''}, {'source_event_id':'missing'}])
def test_invalid_optional_events_are_local(change):
    r=conceive(**change);assert not r.state['pregnancies'] and r.warnings


@pytest.mark.parametrize('condition',['unknown','impossible','minor','unconscious','dead','background'])
def test_eligibility(condition):
    s=state();kw={}
    if condition=='unknown':s['characters']['a']['reproductive_capability']='unknown'
    if condition=='impossible':s['characters']['a']['reproductive_capability']='neither'
    if condition=='minor':s['characters']['a']['birth_date']='2020-01-01'
    if condition=='unconscious':s['characters']['a']['capabilities']['conscious']=False
    if condition=='dead':
        s['characters']['b']['life_status']='dead';s['camera']['present_character_ids']=['a']
    if condition=='background':kw['mode']='background'
    r=run(s,'reproductive_events',[service()],**kw)
    assert not r.state['pregnancies'] and r.warnings


def test_no_event_no_pregnancy_protection_and_continuous_scene():
    s=state()
    assert not run(s,elapsed=1000).state['pregnancies']
    for protection in ('protected','unknown'):
        r=conceive(s,protection=protection)
        assert not r.state['pregnancies'] and len(r.state['reproductive_events'])==1
        repeated=run(r.state,'reproductive_events',[service(id='changed',protection=protection)])
        assert len(repeated.state['reproductive_events'])==1
    first=conceive(s)
    assert not conceive(first.state,id='other').state['pregnancies'].keys()-first.state['pregnancies'].keys()


def naming(s,status='agreed',**changes):
    p=next(iter(s['pregnancies'].values()))
    row=dict(id='n1',pregnancy_id=p['id'],child_id=p['children'][0]['id'],components={'given_name':'Мира'},
        status=status,source_event_id='event',decision_actor_ids=['a','b'],evidence=NAME,
        player_evidence=NAME,player_assertion='explicit_choice')
    row.update(changes)
    return run(s,'naming_decisions',[row],text=NAME,player=NAME)


def test_names_agency_proposals_agreement_and_family_rules():
    base=conceive().state
    proposed=naming(base,'proposed'); born=deliver(proposed.state)
    cid=next(iter(base['pregnancies'].values()))['children'][0]['id']
    assert born.state['characters'][cid]['display_name'] is None
    nid=next(iter(proposed.state['naming_decisions']))
    agreed=naming(proposed.state,id='n2',replaces=nid)
    assert agreed.state['naming_decisions'][nid]['status']=='replaced'
    assert deliver(agreed.state).state['characters'][cid]['display_name']=='Мира'
    rejected=naming(base,player_evidence='')
    assert rejected.warnings and not rejected.state['naming_decisions']
    delegated=naming(base,'proposed',delegated_to='b')
    chosen=naming(delegated.state,id='npc',player_evidence='')
    assert any(n['status']=='agreed' for n in chosen.state['naming_decisions'].values())
    invalid=naming(base,child_id='unknown');assert invalid.warnings and not invalid.state['naming_decisions']
    base['characters']['b']['identity_components']['family_name']='Другое'
    assert deliver(base).state['characters'][cid]['identity_components']=={}


def test_knowledge_is_granular_and_narrative_never_gets_hidden_outcomes():
    s=conceive(state(3)).state;p=next(iter(s['pregnancies'].values()))
    assert not context_projection(s,{'a','b'},'a')
    s['knowledge']['a:'+p['fact_id']]=Knowledge(actor_id='a',fact_id=p['fact_id']).model_dump()
    visible=context_projection(s,{'a','b'},'a')['pregnancies'][0]
    assert 'child_count' not in visible and 'known_children' not in visible
    s['knowledge']['a:'+p['count_fact_id']]=Knowledge(actor_id='a',fact_id=p['count_fact_id']).model_dump()
    visible=context_projection(s,{'a','b'},'a')['pregnancies'][0]
    assert visible['child_count']==3 and 'known_children' not in visible
    cid=p['children'][0]['id'];fid=p['sex_fact_ids'][cid]
    s['knowledge']['a:'+fid]=Knowledge(actor_id='a',fact_id=fid).model_dump()
    assert len(context_projection(s,{'a'},'a')['pregnancies'][0]['known_children'])==1
    messages=build_context(snap(s),[],'Продолжить','turn',65536,2000)
    assert p['sex_fact_ids'][p['children'][1]['id']] not in str(messages)
    assert p['sex_fact_ids'][p['children'][2]['id']] not in str(messages)


@given(st.integers(min_value=1,max_value=3))
def test_retry_is_deterministic(count):
    s=state(count);a=conceive(s);b=conceive(json.loads(json.dumps(s)))
    assert a.state==b.state


def test_appearance_adapter_aging_keeps_identity_no_genetics():
    s=conceive().state;cid=next(iter(s['pregnancies'].values()))['children'][0]['id']
    result=deliver(s,appearance={cid:'На левой щеке маленькое родимое пятно.'})
    snapshot=committed_snapshot(db(),snap(s),result)
    expected=appearance_adapter(snapshot,cid)
    loaded=migrate_v2(json.loads(json.dumps(snapshot))).snapshot
    assert appearance_adapter(loaded,cid)==expected
    loaded['world_state']['meta']['world_time']+=20*366*1440
    assert appearance_adapter(loaded,cid)==expected
    assert loaded['world_state']['characters'][cid]['id']==cid
    assert loaded['world_state']['characters'][cid]['personality']==result.state['characters'][cid]['personality']


@pytest.mark.parametrize('checkpoint,count',[('pregnancy',1),('pregnancy-twins',2),('pregnancy-triplets',3),('newborn',1),('newborn-twins',2),('newborn-triplets',3)])
def test_existing_qa_world_extended_and_ordinary_game_cycle(tmp_path,checkpoint,count):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'qa.sqlite');sid=load_fixture(repo,checkpoint)['save']
    before=repo.get_snapshot(sid);p=next(iter(before['world_state']['pregnancies'].values()))
    assert len(p['children'])==count
    ordinary_job(repo,sid)
    saved=repo.get_snapshot(sid);repo=Repository(repo.path)
    assert repo.get_snapshot(sid)==saved
    ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['pregnancies']==saved['world_state']['pregnancies']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==saved


def test_canonical_encounter_id_closes_and_replays_without_reroll():
    s=state();s['reproduction_policy']['unprotected']=0.0
    first=conceive(s);eid=next(iter(first.state['reproductive_events']))
    repeated=conceive(first.state,id=eid)
    assert repeated.state['reproductive_events']==first.state['reproductive_events']
    ended=run(first.state,'reproductive_events',[service(id=eid,kind='encounter_ended')])
    assert ended.state['reproductive_events'][eid]['closed']
    second=conceive(ended.state,id='genuinely-new-encounter')
    assert len(second.state['reproductive_events'])==2
    assert not second.warnings


def test_delegation_without_a_name_and_post_birth_naming_replacement():
    s=conceive().state
    delegated=naming(s,'proposed',components={},delegated_to='b')
    assert not delegated.warnings
    chosen=naming(delegated.state,id='chosen',player_evidence='')
    born=deliver(chosen.state);cid=next(iter(s['pregnancies'].values()))['children'][0]['id']
    nid=next(n['id'] for n in chosen.state['naming_decisions'].values() if n['status']=='agreed')
    renamed=naming(born.state,id='renamed',replaces=nid,components={'given_name':'Лея'})
    assert not renamed.warnings
    assert renamed.state['characters'][cid]['display_name']=='Лея'
    assert renamed.state['characters'][cid]['name_history'][-1]['previous']=='Мира'
    assert len(renamed.state['naming_decisions'])==3
    repeated=naming(renamed.state,id='renamed',replaces=nid,components={'given_name':'Лея'})
    assert repeated.state['naming_decisions']==renamed.state['naming_decisions']
    assert repeated.state['characters'][cid]==renamed.state['characters'][cid]


def test_hidden_birth_does_not_reveal_children_or_names_to_other_observers():
    from backend.runtime_v3.selectors import ui_view
    s=conceive(state(2)).state;r=deliver(naming(s).state)
    snapshot=committed_snapshot(db(),snap(s),r)
    # The third actor was not a witness; switching POV must not broadcast.
    snapshot['world_state']['camera'].update(controlled_actor_id='c',present_character_ids=['c'])
    view=ui_view(snapshot)
    assert len(view['characters'])==3
    assert not any(cid.startswith('character_') for cid in view['world']['characters'])
    assert not view.get('reproduction')
    messages=build_context(snapshot,[],'Осмотреть комнату.','turn',65536,2000)
    pregnancy=next(iter(r.state['pregnancies'].values()))
    assert all(ch['id'] not in str(messages) for ch in pregnancy['children'])
    assert pregnancy['id'] not in view['world']['scheduled_events']
    assert all(ch['id'] not in str(view['world']['scenes']) for ch in pregnancy['children'])


def test_known_child_does_not_reveal_unknown_agreed_name():
    from backend.runtime_v3.selectors import ui_view
    from backend.runtime_v3.context import canonical_slice
    from backend.runtime_v3.scope import RelevanceResolver
    s=conceive().state;r=deliver(naming(s).state)
    snapshot=committed_snapshot(db(),snap(s),r);s=snapshot['world_state']
    cid=next(iter(s['pregnancies'].values()))['children'][0]['id']
    fid=s['characters'][cid]['life_fact_id']
    s['knowledge']['c:'+fid]=Knowledge(actor_id='c',fact_id=fid).model_dump()
    s['camera'].update(controlled_actor_id='c',present_character_ids=['c',cid])
    scope=RelevanceResolver().resolve(snapshot,'')
    assert 'Мира' not in str(canonical_slice(s,scope))
    assert ui_view(snapshot)['world']['characters'][cid]['display_name']=='Без имени'


def test_birth_witness_does_not_learn_private_planned_name():
    s=naming(conceive().state).state;p=next(iter(s['pregnancies'].values()))
    result=run(s,'births',[dict(pregnancy_id=p['id'],source_event_id='event',assertion='birth_completed',
        location_id='home',evidence=BIRTH)],text=BIRTH,elapsed=1440,witnesses=['a','b','c'])
    name=next(iter(s['naming_decisions'].values()))
    assert 'c:'+p['count_fact_id'] in result.state['knowledge']
    assert 'c:'+name['fact_id'] not in result.state['knowledge']
    father=next(r for r in result.state['objective_relations'].values() if r['source_id']=='b')
    assert 'c:'+father['fact_id'] not in result.state['knowledge']


def test_npc_cannot_forge_external_delegation_but_authorized_background_choice_works():
    s=conceive().state
    forged=naming(s,'proposed',decision_actor_ids=['b'],delegated_to='b',player_evidence='')
    assert not any(n['status']=='agreed' for n in naming(forged.state,id='forged',player_evidence='').state['naming_decisions'].values())
    delegated=naming(s,'proposed',delegated_to='b').state
    p=next(iter(delegated['pregnancies'].values()))
    delegated['camera'].update(controlled_actor_id='b',present_character_ids=['b'])
    payload=dict(final_scene=dict(location_id='home',present_character_ids=['b'],elapsed_minutes=0),
        events=[dict(id='event',text=NAME,evidence=NAME,participants=['b'],witnesses=['b'],fact_ids=[],medium='observation')],
        naming_decisions=[dict(id='chosen',pregnancy_id=p['id'],child_id=p['children'][0]['id'],
            components={'given_name':'Мира'},status='agreed',decision_actor_ids=['a','b'],source_event_id='event',evidence=NAME)])
    result=StateResolver(delegated,NAME,'',mode='background',observed=False,protected_actor_id='a',protected_knowledge_actor_ids=['a']).resolve(payload)
    assert not result.warnings
    assert any(n['status']=='agreed' for n in result.state['naming_decisions'].values())
    chosen=next(n for n in result.state['naming_decisions'].values() if n['status']=='agreed')
    assert 'a:'+chosen['fact_id'] not in result.state['knowledge']


def test_no_birth_from_due_alone_wrong_count_or_sex_cannot_override():
    s=conceive(state(2)).state
    due=run(s,elapsed=1440)
    assert next(iter(due.state['pregnancies'].values()))['status']=='due'
    assert len(due.state['characters'])==3
    p=next(iter(s['pregnancies'].values()))
    premature=run(s,'births',[dict(pregnancy_id=p['id'],source_event_id='event',assertion='birth_completed',evidence=BIRTH)],text=BIRTH)
    assert not premature.cards and premature.warnings
    forged=run(s,'births',[dict(pregnancy_id=p['id'],source_event_id='event',assertion='birth_completed',evidence=BIRTH,
        child_count=3,sex='male')],text=BIRTH,elapsed=1440)
    assert not forged.cards and forged.warnings
    assert next(iter(forged.state['pregnancies'].values()))['children']==p['children']


def test_background_birth_has_no_external_knowledge_and_no_extra_call():
    s=conceive().state;s['meta']['world_time']=1440
    p=next(iter(s['pregnancies'].values()))
    s['camera'].update(controlled_actor_id='c',present_character_ids=['c'])
    r=run(s,'births',[dict(pregnancy_id=p['id'],source_event_id='event',assertion='birth_completed',
        evidence=BIRTH,location_id='home')],text=BIRTH,player='',mode='background',observed=False,protected_actor_id='c')
    assert r.cards and not r.warnings
    assert all(k['actor_id']!='c' for k in r.state['knowledge'].values())
    assert r.state['meta']['world_time']==1440


def test_legacy_defaults_do_not_infer_capabilities_or_modify_original():
    original=snap(state())
    for key in ('reproduction_policy','reproductive_events','pregnancies','naming_decisions'):
        original['world_state'].pop(key)
    for actor in original['world_state']['characters'].values():
        for key in ('biological_sex','identity_components','birth_provenance','reproductive_capability'): actor.pop(key)
    saved=deepcopy(original);migrated=migrate_v2(original).snapshot
    assert original==saved
    assert all(c['reproductive_capability']=='unknown' for c in migrated['world_state']['characters'].values())
    assert not conceive(migrated['world_state']).state['pregnancies']
    assert not run(migrated['world_state']).warnings


def test_newborn_cannot_be_aged_into_adult_by_extraction():
    s=deliver(conceive().state).state
    cid=next(c for c in s['characters'] if c.startswith('character_'))
    from backend.services.world_delta_errors import StructuralDeltaError
    with pytest.raises(StructuralDeltaError): run(s,'life_changes',[dict(id=cid,assertion='established',developmental_stage='adult',evidence=TEXT)])
    assert s['characters'][cid]['developmental_stage']=='infant'
    adult=deepcopy(s);adult['meta']['world_time']+=20*366*1440
    changed=run(adult,'life_changes',[dict(id=cid,assertion='established',developmental_stage='adult',evidence=TEXT)])
    assert not changed.warnings and capabilities(changed.state,cid)['adult_eligible']
    assert changed.state['characters'][cid]['personality']==s['characters'][cid]['personality']
    assert changed.state['characters'][cid]['birth_provenance']==s['characters'][cid]['birth_provenance']


def test_birth_real_engine_regenerate_variants_and_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute as execute_turn
    from unittest.mock import patch
    def execute(*args):
        # This provider fixture supplies only the observed birth. Background
        # agency is exercised separately, not with a replay of the birth payload.
        with patch('backend.runtime_v3.simulation.background_candidate', return_value=None):
            return execute_turn(*args)
    repo=Repository(tmp_path/'variants.sqlite');sid=load_fixture(repo,'pregnancy-triplets')['save']
    before=repo.get_snapshot(sid);s=before['world_state'];p=next(iter(s['pregnancies'].values()))
    camera=s['camera'];text='Роды Веры завершились. Кирилл присутствовал.'
    payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1440),
        events=[dict(id='birth_event',text=text,evidence=text,participants=[ACTOR_ID,'qa_vera'],witnesses=[ACTOR_ID,'qa_vera'],fact_ids=[],medium='observation')],
        births=[dict(pregnancy_id=p['id'],source_event_id='birth_event',assertion='birth_completed',evidence=text,location_id=camera['location_id'])])
    jid=repo.begin_job(sid,'Остаюсь рядом.','turn',CONFIG);execute(repo,jid,payload,text)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert len(after['character_cards'])==len(before['character_cards'])+3
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==after
    jid=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,jid,payload,text)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    regenerated=repo.get_snapshot(sid)
    assert regenerated['world_state']==after['world_state']
    assert regenerated['character_cards']==after['character_cards']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==before
    assert not any(ch['id'] in repo.get_snapshot(sid)['world_state']['characters'] for ch in p['children'])
    # Immutable historical branch still has its three original child records.
    assert all(ch['id'] in after['world_state']['characters'] for ch in p['children'])


def test_same_character_later_develops_through_67_and_branch_appearance_boundary():
    from backend.runtime_v3.milestones import query
    s=conceive().state;p=next(iter(s['pregnancies'].values()));cid=p['children'][0]['id']
    born=deliver(s,appearance={cid:'На щеке родимое пятно.'});con=db()
    before=snap(s);branch=committed_snapshot(con,before,born)
    no_birth=committed_snapshot(con,before,run(s))
    assert len(query(con,branch['history_head'],category='birth'))==1
    assert not query(con,no_birth['history_head'],category='birth')
    assert cid not in no_birth['world_state']['characters']
    # #74 consumer boundary: round-trip the complete accepted input without
    # implementing the future AppearanceProfile or mutating historical snapshots.
    boundary=json.loads(json.dumps(appearance_adapter(branch,cid)))
    assert boundary['character_id']==cid and boundary['appearance_text']=='На щеке родимое пятно.'
    grown=deepcopy(branch['world_state']);grown['meta']['world_time']+=20*366*1440
    grown=run(grown,'life_changes',[dict(id=cid,assertion='established',developmental_stage='adult',evidence=TEXT)]).state
    raw=dict(final_scene=dict(location_id='home',present_character_ids=grown['camera']['present_character_ids']),
        events=[dict(id='experience',text=TEXT,evidence=TEXT,participants=[cid],witnesses=[cid],fact_ids=[])],
        development_evidence=[dict(id='proof',actor_id=cid,source_event_id='experience',meaning='Значимый личный опыт.',
            kind='turning_point',assertion='completed',evidence=TEXT)],
        personality_deltas=[dict(actor_id=cid,evidence_ids=['proof'],rationale='Опыт взрослого персонажа.',
            developmental_fit='established_capability',evidence=TEXT,operations=[dict(item_id='traits',field='traits',
                operation='establish',text='Спокойно обсуждает трудности.',expected_text=None,expected_revision=0)])])
    evolved=StateResolver(grown,TEXT,'').resolve(raw)
    assert not evolved.warnings
    assert evolved.state['characters'][cid]['personality']['items']['traits']['text']=='Спокойно обсуждает трудности.'
    assert evolved.state['characters'][cid]['birth_provenance']==born.state['characters'][cid]['birth_provenance']
    later=deepcopy(branch);later['world_state']=evolved.state
    assert appearance_adapter(later,cid)==boundary
