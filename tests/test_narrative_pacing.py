"""#68 policy: deterministic selection, consequence limits and immutable lineage."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile as Pacing, NarrativeRiskProfile as Risk, RISK_FIELDS
from backend.runtime_v3.pacing import evaluate, development_sources, NarrativeDeathPolicy
from backend.runtime_v3.scope import ContextScope
from backend.runtime_v3.models import Thread, Condition
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_protagonist import snapshot


def setup(pacing='moderate', risk='realistic'):
    s=snapshot()['world_state'];s['meta']['world_time']=1000
    s['meta']['narrative_pacing']=Pacing(preset=pacing).model_dump()
    s['meta']['narrative_risk']=Risk(preset=risk).model_dump()
    s['threads']['work']=Thread(id='work',description='Помочь с выставкой',character_ids=['a','b'],relevance=.8).model_dump()
    s['threads']['other']=Thread(id='other',description='Дела другой семьи',character_ids=['child']).model_dump()
    scope=ContextScope('a',pov_actor_id='a',present_actor_ids={'a','b'},relevant_actor_ids={'a','b'},thread_ids=['work','other'])
    return s,scope


def raw(s, **sections):
    return dict(final_scene=dict(location_id='home',present_character_ids=['a','b'],elapsed_minutes=1),**sections)


@pytest.mark.parametrize('preset',['calm','moderate','dynamic','intense','custom'])
@pytest.mark.parametrize('risk',['safe','realistic','harsh','unrestricted','custom'])
def test_profiles_do_not_force_events_or_mutate_state(preset,risk):
    s,scope=setup(preset,risk);before=deepcopy(s)
    decision=evaluate(s,scope)
    assert decision==evaluate(s,scope) and s==before
    assert decision['ordinary_scene_valid'] and decision['budget']['extra_llm_calls']==0
    assert len(decision['selected_ids'])<=s['meta']['narrative_pacing']['candidate_budget']
    out=StateResolver(s,'Тихий разговор.','',pacing_decision=decision).resolve(raw(s))
    assert not out.history['events'] and out.state['characters']==s['characters']
    assert out.state['meta']['pacing_recent']==[]


def test_intensity_relevance_quiet_pressure_cap_and_decay():
    s,scope=setup('calm');scope.thread_ids=[]
    scope.development_sources=[dict(id='move',category='relocation',actor_ids=['a'],minute=900,summary='Переезд',freshness=1.)]
    assert not evaluate(s,scope)['selected_ids']
    s['meta']['narrative_pacing']=Pacing(preset='dynamic').model_dump()
    decision=evaluate(s,scope);assert decision['selected_ids']
    assert all(c['family']=='life_opportunity' for c in decision['candidates'])
    s['meta']['pacing_recent']=[dict(source_id=decision['selected_ids'][0],family='life_opportunity',minute=999,weight=1.)]
    assert evaluate(s,scope)['quiet'] and not evaluate(s,scope)['selected_ids']
    s['meta']['world_time']+=1000
    assert evaluate(s,scope)['selected_ids']
    s['meta']['narrative_pacing']=Pacing(preset='custom',thread_cap=1).model_dump()
    assert all('thread_cap' in c['reasons'] for c in evaluate(s,scope)['candidates'])


def test_recent_milestone_projection_is_bounded_known_and_decays():
    s,scope=setup();s['knowledge']['a:secret']['status']='known'
    def read(**kwargs):
        assert kwargs['limit']==24 and len(kwargs['actor_ids'])<=8
        return [dict(id=str(i),category='relocation',actor_ids=['a'],minute=999-i,summary='Переезд',fact_id='secret') for i in range(24)] + [dict(id='private',category='birth',actor_ids=['b'],minute=1000,summary='SECRET',fact_id='hidden')]
    before=deepcopy(s);sources=development_sources(s,scope,read)
    assert len(sources)==6 and all(r['id']!='private' for r in sources)
    scope.development_sources=sources
    assert evaluate(s,scope)['candidates'] and s==before
    s['meta']['world_time']+=43201
    assert not development_sources(s,scope,read)


@pytest.mark.parametrize('preset',['safe','realistic','harsh','unrestricted'])
@pytest.mark.parametrize('kind',RISK_FIELDS)
def test_all_risk_permissions_are_independent_and_enforced(preset,kind):
    s,scope=setup('intense',preset);quote='Произошло событие с последствиями.'
    actor='a' if kind=='protagonist_death' else 'b'
    decision=evaluate(s,scope)
    claim=dict(kind=kind,actor_id=actor,source_event_id='event',basis_ids=['work'],evidence=quote,candidate_id=decision['selected_ids'][0])
    payload=raw(s,events=[dict(id='event',text=quote,participants=[actor],evidence=quote)],consequences=[claim])
    from backend.runtime_v3.pacing import validate_risk
    from backend.runtime_v3.raw import RawTurnResult
    resolver=StateResolver(s,quote,'',pacing_decision=decision);before=deepcopy(resolver.state)
    if s['meta']['narrative_risk'][kind]:
        validate_risk(resolver,RawTurnResult.parse(payload))
        assert resolver.state==before  # permission alone is never an outcome
    else:
        with pytest.raises(StructuralDeltaError):validate_risk(resolver,RawTurnResult.parse(payload))


@given(st.dictionaries(st.sampled_from(RISK_FIELDS),st.booleans(),min_size=1,max_size=10))
def test_custom_risk_has_no_coupled_controls(values):
    risk=Risk(preset='custom',**values).model_dump()
    assert all(risk[k]==v for k,v in values.items())


@pytest.mark.parametrize('field,value',[('intensity',float('nan')),('thread_cap',13),('candidate_budget',7),('quiet_minutes',-1),('extra_llm_calls',1)])
def test_invalid_custom_values_rejected(field,value):
    with pytest.raises(ValidationError):Pacing(preset='custom',**{field:value})


def test_risk_death_uses_current_protagonist_not_temporary_control_and_continues():
    s,scope=setup('intense','unrestricted');quote='Персонаж погиб.'
    decision=evaluate(s,scope)
    out=StateResolver(s,quote,'',pacing_decision=decision).resolve(raw(s,events=[dict(id='fatal',text=quote,participants=['a'],evidence=quote)],consequences=[dict(kind='protagonist_death',actor_id='a',source_event_id='fatal',basis_ids=['work'],candidate_id=decision['selected_ids'][0],evidence=quote)],life_changes=[dict(id='a',source_event_id='fatal',life_status='dead',assertion='established',evidence=quote)]))
    assert out.state['meta']['protagonist_required'] and out.state['camera']['controlled_actor_id'] is None
    assert 'a' in out.state['characters']
    s['meta']['narrative_risk']=Risk(preset='custom',npc_death=True,protagonist_death=False).model_dump()
    s['camera']['controlled_actor_id']='b'
    assert NarrativeDeathPolicy().permits_autonomous_death(s,'b')
    assert not NarrativeDeathPolicy().permits_autonomous_death(s,'a')
    with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'').resolve(raw(s,life_changes=[dict(id='a',life_status='dead',assertion='established',evidence=quote)]))


def test_safe_rejects_unclassified_incapacity_and_loss_before_any_mutation():
    s,_=setup(risk='safe');quote='Произошло событие.';before=deepcopy(s)
    for section,item in [('condition_changes',dict(id='injury',actor_id='b',description='Травма',effects={'can_act':False})),
                         ('social_relation_changes',dict(id='partnership',status='closed')),
                         ('life_changes',dict(id='b',life_status='dead'))]:
        with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'').resolve(raw(s,**{section:[dict(item,assertion='established',evidence=quote)]}))
    assert s==before


def test_candidate_acceptance_has_provenance_and_does_not_choose_external_response():
    s,scope=setup('dynamic');decision=evaluate(s,scope);candidate=decision['selected_ids'][0]
    quote='Борис предлагает обсудить выставку.'
    payload=raw(s,events=[dict(id='offer',text=quote,participants=['a','b'],evidence=quote)],
        narrative_developments=[dict(candidate_id=candidate,source_event_id='offer',assertion='established',evidence=quote)],
        character_changes=[dict(id='a',goals=['Бросить работу'],evidence=quote)])
    out=StateResolver(s,quote,'',pacing_decision=decision).resolve(payload)
    assert out.state['characters']['a']['goals']==s['characters']['a']['goals']
    assert out.state['meta']['pacing_recent'][0]['source_id']==candidate
    assert len(out.state['threads'])==len(s['threads'])
    payload['narrative_developments']*=7
    with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'',pacing_decision=decision).resolve(payload)


@pytest.mark.parametrize('preference',['natural','prefer_happy','guaranteed_happy_path'])
def test_outcome_scope_and_concrete_path(preference):
    s,scope=setup();s['meta']['outcome_preference']=preference;decision=evaluate(s,scope)
    assert decision['outcome']['linked_thread_ids']==['work']
    quote='Есть возможность подготовить выставку вместе.'
    change=dict(id='work',state=quote,evidence=quote)
    if preference=='guaranteed_happy_path':
        with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'').resolve(raw(s,thread_changes=[change]))
        change['favorable_path']=dict(opportunity='Можно договориться о помощи',next_step='Обсудить условия',basis_ids=['work'])
    out=StateResolver(s,quote,'').resolve(raw(s,thread_changes=[change]))
    assert out.state['characters']==s['characters']
    # No policy is imposed on an unrelated NPC thread.
    StateResolver(s,quote,'').resolve(raw(s,thread_changes=[dict(id='other',state=quote,evidence=quote)]))
    s['meta']['current_protagonist_id']='child'
    assert evaluate(s,scope)['outcome']['linked_thread_ids']==['other']


def test_negative_explicit_choice_does_not_force_romantic_reconciliation():
    s,_=setup();s['meta']['outcome_preference']='guaranteed_happy_path';quote='Я окончательно отказываюсь.'
    out=StateResolver(s,quote,quote).resolve(raw(s,thread_changes=[dict(id='work',status='resolved',state=quote,evidence=quote,player_assertion='explicit_choice',player_evidence=quote)]))
    assert out.state['threads']['work']['status']=='resolved'
    assert out.state['relationships']==s['relationships']


def test_settings_save_reload_rollback_and_ordinary_smoke(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job,CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'pacing.sqlite');sid=load_fixture(repo,'pacing')['save']
    initial=repo.get_snapshot(sid)
    ordinary_job(repo,sid,'start');before=repo.get_snapshot(sid)
    values=dict(narrative_pacing=Pacing(preset='intense').model_dump(),narrative_risk=Risk(preset='safe').model_dump(),outcome_preference='prefer_happy')
    revision=repo.get_save(sid)['revision'];repo.update_narrative_policy(sid,revision,values)
    changed=repo.get_snapshot(sid)
    assert {k:v for k,v in changed['world_state'].items() if k!='meta'}=={k:v for k,v in before['world_state'].items() if k!='meta'}
    with pytest.raises(ValueError):repo.update_narrative_policy(sid,revision,values)
    assert Repository(repo.path).get_snapshot(sid)==changed
    ordinary_job(repo,sid)
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==changed
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==initial


def test_legacy_read_defaults_do_not_rewrite_history():
    from backend.runtime_v3.migration import migrate_v2
    s=snapshot();prior=deepcopy(s)
    for key in ('narrative_pacing','narrative_risk','outcome_preference','pacing_recent'):s['world_state']['meta'].pop(key,None)
    original=deepcopy(s);migrated=migrate_v2(s)
    assert s==original and migrated.snapshot['world_state']['meta']['outcome_preference']=='natural'
    assert not migrated.history['events']
    result=StateResolver(migrated.snapshot['world_state'],'Обычный разговор.','').resolve(raw(s))
    assert result.state['characters']==migrated.snapshot['world_state']['characters']


def test_policy_regeneration_and_branch_restore_original_planning(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'branches.sqlite');sid=load_fixture(repo,'pacing')['save']
    ordinary_job(repo,sid,'start')
    def settings(pacing,risk,outcome):
        repo.update_narrative_policy(sid,repo.get_save(sid)['revision'],dict(
            narrative_pacing=Pacing(preset=pacing).model_dump(),narrative_risk=Risk(preset=risk).model_dump(),outcome_preference=outcome))
    settings('calm','safe','guaranteed_happy_path')
    ordinary_job(repo,sid);original=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    settings('intense','unrestricted','natural')
    ordinary_job(repo,sid,'regenerate')
    meta=repo.get_snapshot(sid)['world_state']['meta']
    assert meta['narrative_pacing']['preset']=='calm' and meta['narrative_risk']['preset']=='safe'
    assert meta['outcome_preference']=='guaranteed_happy_path'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==original
    repo.rollback_last(sid);ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['meta']['narrative_risk']['preset']=='safe'


@pytest.mark.parametrize('kind',['serious_illness','injury','permanent_injury'])
def test_allowed_harm_requires_accepted_condition_and_incapacitation_is_not_death(kind):
    s,scope=setup('intense','unrestricted');quote='Борис временно не может действовать.'
    decision=evaluate(s,scope)
    claim=dict(kind=kind,actor_id='b',source_event_id='harm',basis_ids=['work'],evidence=quote,candidate_id=decision['selected_ids'][0])
    payload=raw(s,events=[dict(id='harm',text=quote,participants=['b'],evidence=quote)],consequences=[claim])
    with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'',pacing_decision=decision).resolve(payload)
    payload['condition_changes']=[dict(id='condition',actor_id='b',description=quote,effects={'can_act':False},
        duration='persistent' if kind=='permanent_injury' else 'temporary',source_event_id='harm',assertion='established',evidence=quote)]
    out=StateResolver(s,quote,'',pacing_decision=decision).resolve(payload)
    from backend.runtime_v3.life import capabilities
    assert out.state['meta']['pacing_recent'][0]['source_event_id']==out.history['events'][0]['id']
    assert not capabilities(out.state,'b')['can_act'] and out.state['characters']['b']['life_status']=='alive'
    assert out.state['camera']['controlled_actor_id']=='a'


def test_constructive_closure_is_not_automatic_career_loss():
    from backend.runtime_v3.models import NarrativeRole
    s,_=setup(risk='safe');quote='Борис закончил обучение.'
    s['roles']['study']=NarrativeRole(id='study',actor_id='b',kind='education',title='Обучение').model_dump()
    out=StateResolver(s,quote,'').resolve(raw(s,role_changes=[dict(id='study',status='closed',
        consequence_outcome='constructive',assertion='established',evidence=quote)]))
    assert out.state['roles']['study']['status']=='closed'


def test_calm_long_interval_bounded_opportunity_and_no_mandatory_disaster():
    s,scope=setup('calm','unrestricted');scope.thread_ids=[];s['threads']={}
    scope.development_sources=[dict(id='move',category='relocation',actor_ids=['a'],minute=0,summary='Переезд',freshness=0)]
    s['meta']['world_time']=15*365*1440
    s['characters']['a']['goals']=[dict(id='goal',text='Найти друзей',status='active')]
    d=evaluate(s,scope)
    assert len(d['selected_ids'])==1 and d['ordinary_scene_valid']
    assert all(c['family']=='life_opportunity' for c in d['candidates'])


def test_guaranteed_path_does_not_grant_secret_knowledge():
    s,_=setup();s['meta']['outcome_preference']='guaranteed_happy_path';s['knowledge']['a:secret']['status']='unknown';quote='Есть возможность помочь.'
    with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'').resolve(raw(s,thread_changes=[dict(
        id='work',state=quote,evidence=quote,favorable_path=dict(opportunity=quote,next_step='Обсудить',basis_ids=['work','secret']))]))


def test_legacy_recorded_prompt_never_grants_new_candidate_permissions():
    from backend.runtime_v3.pacing import recorded_policy
    s,_=setup('intense','unrestricted');d=recorded_policy([],s)
    assert d['selected_ids']==[] and d['budget']['candidates']==0 and d['legacy_unplanned']


def test_denied_risk_is_atomic_without_extra_repair_calls(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import CONFIG,ordinary_job
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'atomic.sqlite');sid=load_fixture(repo,'pacing')['save']
    ordinary_job(repo,sid,'start')
    before=repo.get_snapshot(sid);turns=repo.list_turns(sid);camera=before['world_state']['camera']
    payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
        life_changes=[dict(id=ACTOR_ID,life_status='dead',assertion='established',evidence='Герой погиб.')])
    job=repo.begin_job(sid,'Осмотреть дом.','turn',CONFIG)
    calls=execute(repo,job,payload,'Герой погиб.')
    assert len(calls)==2 and repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before and repo.list_turns(sid)==turns


def test_existing_temporary_injury_cannot_become_permanent_without_permission():
    s,scope=setup('intense','realistic');quote='Травма остаётся навсегда.'
    s['conditions']['injury']=Condition(id='injury',actor_id='b',description='Травма',duration='temporary',effects={'can_act':False}).model_dump()
    payload=raw(s,events=[dict(id='worse',participants=['b'],text=quote,evidence=quote)],
        consequences=[dict(kind='injury',actor_id='b',source_event_id='worse',basis_ids=['injury'],evidence=quote)],
        condition_changes=[dict(id='injury',duration='persistent',source_event_id='worse',assertion='established',evidence=quote)])
    with pytest.raises(StructuralDeltaError):StateResolver(s,quote,'',pacing_decision=evaluate(s,scope)).resolve(payload)
