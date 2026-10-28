"""#69: deterministic Director eligibility, agency claims and real job lineage."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.initiative import scene_plan, recorded_plan
from backend.runtime_v3.scope import RelevanceResolver
from backend.runtime_v3.director import plan
from backend.runtime_v3.context import build_context
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.protagonist import transition
from backend.runtime_v3.models import Condition, Knowledge
from backend.services.world_delta_errors import StructuralDeltaError
from test_protagonist import snapshot

TEXT = 'Борис предлагает поговорить и ждёт ответа.'


def permit(snap):
    scope = RelevanceResolver().resolve(snap, '')
    return scene_plan(snap['world_state'], scope)


def payload(snap, text=TEXT, **changes):
    state = snap['world_state']
    claim = dict(actor_id='b', target_ids=['a'], source_event_id='initiative', phase='start',
                 modality='speech', interruptible=True, response='open', evidence=text)
    claim.update(changes)
    return dict(final_scene=dict(location_id='home', present_character_ids=state['camera']['present_character_ids']),
        events=[dict(id='initiative', text=text, participants=list(state['characters']),
                     witnesses=['a','b'], medium='conversation', evidence=text)], scene_actions=[claim])


def resolve(snap, raw=None, text=TEXT, player=''):
    return StateResolver(snap['world_state'], text, player, initiative_decision=permit(snap)).resolve(raw or payload(snap, text))


@pytest.mark.parametrize('phase',['start','continue','redirect','end','refuse','offer'])
def test_meaningful_action_without_external_input(phase):
    snap = snapshot(); before = deepcopy(snap)
    result = resolve(snap, payload(snap, phase=phase))
    action = result.history['events'][0]['scene_action']
    assert action['phase'] == phase and action['response'] == 'open'
    assert result.state['characters'] == snap['world_state']['characters']
    assert result.state['relationships'] == snap['world_state']['relationships']
    assert not result.state['scheduled_events']
    assert snap == before


def test_accepted_speech_before_same_turn_death_is_not_erased():
    snap=snapshot();raw=payload(snap)
    raw['life_changes']=[dict(id='b',life_status='dead')]
    out=resolve(snap,raw,text='Борис успел заговорить, затем его дыхание оборвалось.')
    assert out.state['characters']['b']['life_status']=='dead'
    assert out.history['events'][0]['scene_action']['modality']=='speech'
    assert 'b' not in out.state['camera']['present_character_ids']


@pytest.mark.parametrize('text,modality',[
    ('Борис протягивает ладонь, предлагая взять его за руку.', 'physical'),
    ('Борис раскрывает объятия и ждёт.', 'physical'),
    ('Борис наклоняется для поцелуя, оставляя возможность отстраниться.', 'physical'),
    ('Борис предлагает провести ночь вместе.', 'speech'),
    ('Борис предлагает пожениться.', 'speech'),
])
def test_adult_proposals_do_not_create_consent_or_reciprocity(text, modality):
    snap = snapshot()
    result = resolve(snap, payload(snap,text,adult=True,modality=modality),text)
    assert result.history['events'][0]['scene_action']['response'] == 'open'
    for key in ('relationships','objective_relations','scheduled_events','knowledge'):
        assert result.state[key] == snap['world_state'][key]


@pytest.mark.parametrize('changes',[
    dict(actor_id='a'), dict(actor_id='baby'), dict(target_ids=['missing']),
    dict(response='none'), dict(response='involuntary'),
    dict(response='player_supplied',player_evidence='Да, я согласен.'),
    dict(adult=True,target_ids=['child']), dict(source_event_id='missing'),
    dict(knowledge_ids=['a:secret']), dict(evidence='Выдуманная цитата'),
])
def test_unsupported_agency_is_atomic(changes):
    snap=snapshot();before=deepcopy(snap)
    if changes.get('response')=='player_supplied' or 'knowledge_ids' in changes or changes.get('adult') or changes.get('actor_id')=='baby':
        with pytest.raises(StructuralDeltaError): resolve(snap,payload(snap,**changes))
    else:
        out=resolve(snap,payload(snap,**changes))
        assert len(out.history['events'])==1
        assert out.state['knowledge']==snap['world_state']['knowledge']
        assert out.state['characters']['a']['intentions']==[]
    assert snap==before



def test_refusal_is_a_supplied_response_not_forced_reconciliation():
    snap = snapshot(); text='Борис отступает после отказа.'; player='Нет, я не хочу.'
    result = resolve(snap,payload(snap,text,phase='end',response='player_supplied',player_evidence=player),text,player)
    assert result.history['events'][0]['scene_action']['phase']=='end'
    assert result.state['relationships']==snap['world_state']['relationships']
    assert result.state['characters']['a']['intentions']==[]


def test_temporary_control_and_observation_follow_camera_not_protagonist():
    snap = snapshot(); temp,_=transition(snap,'temporary','b','temp')
    assert 'b' not in {a['actor_id'] for a in permit(temp)['actors']}
    assert 'a' in {a['actor_id'] for a in permit(temp)['actors']}
    raw=payload(temp,actor_id='a',target_ids=['b'])
    assert resolve(temp,raw).history['events'][0]['scene_action']['actor_id']=='a'
    observer,_=transition(temp,'observe','b','watch')
    assert permit(observer)['external_actor_id'] is None
    assert {'a','b'} <= {a['actor_id'] for a in permit(observer)['actors']}
    result=resolve(observer,payload(observer,response='none',interruptible=False))
    assert result.choices==[]
    assert result.state['meta']['current_protagonist_id']=='a'


@pytest.mark.parametrize('effect,modality',[('can_speak','speech'),('can_move','departure'),('can_act','other')])
def test_capabilities_constrain_actions_without_personality_gates(effect,modality):
    snap=snapshot();s=snap['world_state']
    s['conditions']['blocked']=Condition(id='blocked',actor_id='b',description='Ограничение',effects={effect:False}).model_dump()
    with pytest.raises(StructuralDeltaError):resolve(snap,payload(snap,modality=modality))


def test_reference_does_not_open_remote_channel():
    snap=snapshot();s=snap['world_state'];s['camera']['present_character_ids'].remove('b')
    scope=RelevanceResolver().resolve(snap,'Вспоминаю b.')
    assert 'b' not in {a['actor_id'] for a in scene_plan(s,scope)['actors']}
    s['camera']['remote_interactions']=[dict(actor_id='b',channel='phone',last_active_turn=0,evidence='Говорим по телефону')]
    assert next(a for a in permit(snap)['actors'] if a['actor_id']=='b')['channel']=='established_remote'
    with pytest.raises(StructuralDeltaError):resolve(snap,payload(snap,modality='physical'))


@pytest.mark.parametrize('status,usage,allowed',[
    ('known','assertion',True),('suspected','inquiry',True),('suspected','assertion',False),
    ('unknown','inquiry',False),('outdated','assertion',False),('refuted','assertion',False)])
def test_actor_knowledge_is_not_world_truth(status,usage,allowed):
    snap=snapshot();snap['world_state']['facts']['secret']['character_ids']=['a','b'];snap['world_state']['knowledge']['b:secret']=Knowledge(actor_id='b',fact_id='secret',status=status).model_dump()
    raw=payload(snap,knowledge_ids=['b:secret'],knowledge_use=usage)
    if allowed: assert resolve(snap,raw).history['events']
    else:
        with pytest.raises(StructuralDeltaError):resolve(snap,raw)


@given(st.sampled_from(['calm','moderate','dynamic','intense']),st.booleans())
def test_pacing_and_silence_never_require_or_forbid_ordinary_initiative(preset,quiet):
    from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile
    snap=snapshot();s=snap['world_state'];s['meta']['narrative_pacing']=NarrativePacingProfile(preset=preset).model_dump()
    if quiet:s['meta']['pacing_recent']=[dict(source_id='previous',family='life_opportunity',minute=0,weight=1.)]
    scope=RelevanceResolver().resolve(snap,'');before=deepcopy(s)
    result=plan(s,'turn',scope=scope)
    assert result['scene_agency']==permit(snap) and s==before
    assert result['scene_agency']['extra_llm_calls']==0
    assert resolve(snap).history['events']
    raw=payload(snap);raw['scene_actions']=[];raw['events']=[]
    assert not resolve(snap,raw).history['events']


def test_budget_and_legacy_context_do_not_invent_permission():
    snap=snapshot();raw=payload(snap);raw['scene_actions']*=4
    out=resolve(snap,raw)
    assert len(out.history['events'])==1 and len(out.warnings)==3
    assert recorded_plan([])=={}
    out=StateResolver(snap['world_state'],TEXT,'',initiative_decision={}).resolve(payload(snap))
    assert out.history['events'][0]['scene_action']['actor_id']=='b'
    raw=payload(snap);raw.pop('scene_actions')
    assert len(StateResolver(snap['world_state'],TEXT,'').resolve(raw).history['events'])==1



def test_context_personality_emotion_intentions_relationships_and_permit_replay(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    repo=Repository(tmp_path/'context.sqlite');sid=load_fixture(repo,'initiative')['save'];snap=repo.get_snapshot(sid)
    messages=build_context(snap,[],'','start',32768,2000)
    wire='\n'.join(m['content'] for m in messages)
    for phrase in ('Сдержанная','импульсивный','Спокойное любопытство','провести вечер вдвоём','Вера тепло относится'):
        assert phrase in wire
    permit_before=recorded_plan(messages)
    assert messages.selection['initiative']==permit_before
    snap['world_state']['camera']['controlled_actor_id']='qa_vera'
    extraction=build_context(snap,[],'','turn',32768,4096,extraction_text=TEXT,initiative_decision=permit_before)
    assert extraction.selection['initiative']==permit_before
    assert 'qa_vera' not in {r['actor_id'] for r in permit(snap)['actors']}


def test_real_job_start_save_reload_next_turn_regenerate_rollback_branch(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'lineage.sqlite');sid=load_fixture(repo,'initiative')['save']
    def run(kind,text,phase,player=''):
        before=repo.get_snapshot(sid);camera=before['world_state']['camera']
        action=dict(actor_id='qa_vera',target_ids=[ACTOR_ID],source_event_id='invitation',phase=phase,
                    modality='speech',adult=True,interruptible=True,response='open',evidence=text)
        # These open invitations deliberately do not acknowledge a prior
        # response ID; later dialogue must retain its temporal boundary.
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1 if kind=='start' else 0),
            events=[dict(id='invitation',text=text,evidence=text,participants=['qa_vera',ACTOR_ID],witnesses=list(camera['present_character_ids']),medium='conversation')],scene_actions=[action])
        job=repo.begin_job(sid,player,kind,CONFIG);calls=execute(repo,job,raw,text)
        assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
        assert len(calls)==2
        from backend.runtime_v3.repository import read_history
        current=repo.get_snapshot(sid)
        with repo.connect() as db:
            history,warnings=read_history(db,current['history_head'])
        assert not warnings
        assert history['events'][-1]['scene_action']['phase']==phase
        return current,repo.get_job(job)
    initial=repo.get_snapshot(sid)
    first,_=run('start','Вера предлагает вечером побыть вдвоём.','offer')
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==first
    second,job=run('turn','Вера меняет тему и спрашивает о фотографиях.','redirect','Пока не хочу.')
    assert second['world_state']['meta']['world_time']==first['world_state']['meta']['world_time']
    turn=repo.list_turns(sid)[-1]
    original_plan=recorded_plan(json.loads(job['context_json']))
    variant,newjob=run('regenerate','Вера заканчивает разговор, оставляя ответ открытым.','end')
    assert recorded_plan(json.loads(newjob['context_json']))==original_plan
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==second
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==first
    branch,_=run('turn','Вера предлагает посмотреть альбом.','start','Рассматриваю стол.')
    assert branch['world_state']['characters'][ACTOR_ID]['intentions']==[]
    assert branch['world_state']['relationships']==initial['world_state']['relationships']
    assert branch['world_state']['knowledge']==initial['world_state']['knowledge']


def test_involuntary_outcome_uses_existing_risk_and_canonical_condition():
    from test_narrative_pacing import setup
    from backend.runtime_v3.pacing import evaluate
    snap=snapshot();s,scope=setup('intense','unrestricted');snap['world_state']=s
    text='Борис толкает Александра, тот повреждает руку.'
    raw=payload(snap,text,modality='physical',interruptible=False,response='involuntary')
    raw['consequences']=[dict(kind='injury',actor_id='a',source_event_id='initiative',basis_ids=['work'],evidence=text)]
    raw['condition_changes']=[dict(id='injury',actor_id='a',description='Повреждена рука.',effects={'can_act':False},duration='temporary',source_event_id='initiative',assertion='established',evidence=text)]
    out=StateResolver(s,text,'',initiative_decision=permit(snap),pacing_decision=evaluate(s,scope)).resolve(raw)
    assert out.state['conditions']['injury']['actor_id']=='a'
    assert out.state['characters']['a']['intentions']==[]
    assert out.history['events'][0]['scene_action']['response']=='involuntary'
    raw.pop('condition_changes')
    with pytest.raises(StructuralDeltaError):
        StateResolver(s,text,'',initiative_decision=permit(snap),pacing_decision=evaluate(s,scope)).resolve(raw)


def test_completed_npc_departure_changes_scene_without_moving_external():
    snap=snapshot();text='Борис прощается и уходит из комнаты.'
    raw=payload(snap,text,phase='end',modality='departure',interruptible=False,response='none')
    raw['final_scene']['present_character_ids']=['a','child','baby']
    result=resolve(snap,raw,text)
    assert 'b' not in result.state['camera']['present_character_ids']
    assert result.state['characters']['a']['location_id']=='home'


def test_initiative_cannot_supply_external_desires_or_agreement():
    snap=snapshot();raw=payload(snap)
    raw['character_changes']=[dict(id='a',intentions=['Поцеловать Бориса.'],emotion='Влюблён.',evidence=TEXT)]
    raw['scheduled_event_changes']=[dict(id='date',description='Свидание',character_ids=['a','b'],
        temporal=dict(day_offset=1,time='19:00'),assertion='agreed',evidence=TEXT)]
    before=deepcopy(snap)
    with pytest.raises(StructuralDeltaError) as exc: resolve(snap,raw)
    assert exc.value.code=='controlled_actor_unsupported' and snap==before
    raw['scheduled_event_changes']=[]
    out=resolve(snap,raw)
    assert not out.state['characters']['a']['intentions'] and not out.state['characters']['a']['emotion']
    assert not out.state['scheduled_events']
    assert out.warnings


def test_initiative_news_and_completed_intention_use_normal_provenance():
    from backend.runtime_v3.lifecycle import Motivation
    snap=snapshot();s=snap['world_state']
    s['facts']['secret']['character_ids']=['a','b']
    s['knowledge'].pop('a:secret')
    s['knowledge']['b:secret']=Knowledge(actor_id='b',fact_id='secret',status='known').model_dump()
    s['characters']['b']['intentions']=[Motivation(id='tell',text='Рассказать о письме.').model_dump()]
    text='Борис рассказывает Александру о приватном письме.'
    raw=payload(snap,text,knowledge_ids=['b:secret'],interruptible=False,response='none')
    raw['events'][0]['fact_ids']=['secret']
    raw['knowledge_gained']=[dict(actor_id='a',fact_id='secret',source_event_id='initiative',evidence=text)]
    raw['character_changes']=[dict(id='b',intentions_updates=[dict(id='tell',status='completed',expected_revision=0,source_event_id='initiative',evidence=text)])]
    out=resolve(snap,raw,text)
    event=out.history['events'][0]
    assert out.state['characters']['b']['intentions'][0]['status']=='completed'
    assert out.state['knowledge']['a:secret']['source_event_id']==event['id']
    assert event['scene_action']['actor_id']=='b'
    assert 'child:secret' not in out.state['knowledge']
    assert out.state['characters']['a']['intentions']==[]


def test_invalid_claim_fails_real_job_without_extra_repair_or_saved_state(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG,ordinary_job
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'invalid.sqlite');sid=load_fixture(repo,'initiative')['save']
    ordinary_job(repo,sid,'start');before=repo.get_snapshot(sid);camera=before['world_state']['camera']
    text='Вера обнимает Кирилла; тот добровольно отвечает объятием.'
    raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
        events=[dict(id='bad',text=text,evidence=text,participants=['qa_vera',ACTOR_ID])],
        scene_actions=[dict(actor_id='qa_vera',target_ids=[ACTOR_ID],source_event_id='bad',phase='start',modality='physical',adult=True,interruptible=True,response='player_supplied',player_evidence='Обнимаю в ответ.',evidence=text)])
    job=repo.begin_job(sid,'Слушаю.','turn',CONFIG);calls=execute(repo,job,raw,text)
    assert repo.get_job(job)['status']=='error'
    assert len(calls)==3 and repo.get_snapshot(sid)==before


def test_shared_event_cannot_overwrite_another_initiator():
    snap=snapshot();observer,_=transition(snap,'observe','b','watch')
    raw=payload(observer,response='none',interruptible=False)
    raw['scene_actions'].append(dict(raw['scene_actions'][0],actor_id='a',target_ids=['b']))
    out=resolve(observer,raw)
    assert out.history['events'][0]['scene_action']['actor_id']=='b'
    assert any(w['code']=='initiative_duplicate' for w in out.warnings)
