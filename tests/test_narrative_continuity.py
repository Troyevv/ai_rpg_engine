"""#71: bounded policy, evidence ownership and real persisted turn regression."""
from copy import deepcopy
import json
import time
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.continuity import project, scene_signature, recorded, compression_limit
from backend.runtime_v3.scope import RelevanceResolver, ContextScope
from backend.runtime_v3.context import build_context
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.models import Thread, ScheduledEvent, Character
from backend.services.world_delta_errors import StructuralDeltaError
from test_protagonist import snapshot


def setup():
    snap=snapshot();s=snap['world_state']
    s['threads']['meeting']=Thread(id='meeting',description='Отношения',state='Ждёт встречи',character_ids=['a','b'],status='developing').model_dump()
    return snap


def payload(s, text='Разговор завершён.', **extra):
    return dict(final_scene=dict(location_id='home',present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=1),
        events=[dict(id='event',text=text,evidence=text,participants=['a','b'],witnesses=['a','b'],medium='conversation')],**extra)


def permit(snap, history=None):
    return project(snap['world_state'],RelevanceResolver().resolve(snap,''),history)


def beat(status='open',kind='proposal'):
    return dict(source_event_id='event',actor_id='b',target_ids=['a'],basis_ids=['meeting'],kind=kind,status=status,evidence='Разговор завершён.')


def test_stagnation_optional_pressure_and_reset():
    from backend.runtime_v3.pacing import evaluate
    from backend.runtime_v3.initiative import scene_plan
    snap=setup();s=snap['world_state'];scope=RelevanceResolver().resolve(snap,'')
    h={'turns':[dict(player_observed=True,camera=s['camera'],continuity=dict(scene=scene_signature(s),progress=[])) for _ in range(6)]}
    prior=deepcopy(s);scope.continuity_decision=project(s,scope,h)
    assert scope.continuity_decision['pressure']>0
    elevated=evaluate(s,scope)
    assert scene_plan(s,scope)['optional'] and scene_plan(s,scope)['grounded_development_priority']>0
    scope.continuity_decision={};baseline=evaluate(s,scope)
    assert elevated['candidates'][0]['relevance']>baseline['candidates'][0]['relevance']
    out=StateResolver(s,'Тихо.','').resolve(dict(final_scene=dict(location_id='home',present_character_ids=s['camera']['present_character_ids'])))
    assert out.state['characters']==s['characters'] and not out.history['events'] and s==prior
    for r in h['turns']:r['continuity']['progress']=['knowledge']
    assert project(s,scope,h)['pressure']==0


@pytest.mark.parametrize('kind',['question','proposal','information','opportunity'])
def test_answered_beats_cannot_reopen_without_changed_basis(kind):
    snap=setup();s=snap['world_state'];raw=payload(s,continuity_beats=[beat('rejected',kind)])
    out=StateResolver(s,'Разговор завершён.','',continuity_decision=permit(snap)).resolve(raw)
    snap['world_state']=out.state;p=permit(snap,out.history)
    assert p['recent_beats'][0]['status']=='rejected'
    raw=payload(out.state,continuity_beats=[beat('open',kind)])
    with pytest.raises(StructuralDeltaError):StateResolver(out.state,'Разговор завершён.','',continuity_decision=p).resolve(raw)
    snap['world_state']['threads']['meeting']['state']='Новые обстоятельства.'
    assert not permit(snap,out.history)['recent_beats']


def test_choices_semantic_identity_and_terminal_lifecycle():
    snap=setup();s=snap['world_state']
    choices=[dict(action='Спросить об этом',speech='',basis_ids=['meeting'],kind='question'),
             dict(action='Уточнить тот же вопрос',speech='',basis_ids=['meeting'],kind='question'),
             dict(action='Помолчать',speech='')]
    out=StateResolver(s,'Разговор завершён.','').resolve(payload(s,choices=choices))
    assert len(out.choices)==2
    raw=payload(s,choices=choices,continuity_beats=[beat('resolved','question')])
    out=StateResolver(s,'Разговор завершён.','').resolve(raw)
    assert out.choices==[dict(action='Помолчать',speech='')]
    s['threads']['meeting']['status']='resolved'
    assert len(StateResolver(s,'Разговор завершён.','').resolve(payload(s,choices=choices)).choices)==1


def test_scene_transition_invalidates_only_linked_summaries_no_invented_travel():
    snap=setup();s=snap['world_state']
    s['characters']['b']['situation']='Идёт на встречу.'
    before=deepcopy(s)
    raw=payload(s,scene_transitions=[dict(source_event_id='event',phase='ended',actor_ids=['a','b'],thread_ids=['meeting'],evidence='Разговор завершён.')])
    out=StateResolver(s,'Разговор завершён.','').resolve(raw)
    assert out.state['threads']['meeting']['state']=='' and out.state['threads']['meeting']['status']=='developing'
    assert out.state['characters']['b']['situation']==''
    assert out.state['characters']['b']['location_id']==before['characters']['b']['location_id']
    assert s==before
    raw['scene_transitions'][0]['source_event_id']='missing'
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','').resolve(raw)


def test_closed_thread_requires_new_accepted_event():
    s=setup()['world_state'];s['threads']['meeting']['status']='resolved'
    changes=[dict(id='meeting',status='developing',evidence='Разговор завершён.')]
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','').resolve(payload(s,thread_changes=changes))
    changes[0]['source_event_id']='event'
    assert StateResolver(s,'Разговор завершён.','').resolve(payload(s,thread_changes=changes)).state['threads']['meeting']['status']=='developing'


@given(st.integers(min_value=1,max_value=60))
def test_compression_bounded_and_canonical(minutes):
    snap=setup();s=snap['world_state'];p=permit(snap)
    raw=payload(s);raw['final_scene'].update(elapsed_minutes=minutes,compression=dict(kind='waiting',evidence='Разговор завершён.'))
    if minutes>30:
        with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','',continuity_decision=p).resolve(raw)
    else:
        out=StateResolver(s,'Разговор завершён.','',continuity_decision=p).resolve(raw)
        assert out.state['meta']['world_time']==s['meta']['world_time']+minutes
        assert out.history['state_changes'][0]['kind']=='natural_compression'


@pytest.mark.parametrize('offset',[0,5,30,60])
def test_compression_stops_at_relevant_commitment_or_interruption(offset):
    snap=setup();s=snap['world_state'];s['meta']['world_time']=1000;now=s['meta']['world_time']
    s['scheduled_events']['due']=ScheduledEvent(id='due',description='Прерывание',character_ids=['b'],due_minute=now+offset,interrupts=True).model_dump()
    assert compression_limit(s,{'a'})['max_minutes']==min(30,offset)
    p=permit(snap);raw=payload(s);raw['final_scene'].update(elapsed_minutes=min(30,offset)+1,compression=dict(kind='work',evidence='Разговор завершён.'))
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','',continuity_decision=p).resolve(raw)


def test_compression_does_not_consume_external_response():
    snap=setup();s=snap['world_state'];p=permit(snap);p['pending_response_ids']=['question']
    raw=payload(s);raw['final_scene']['compression']=dict(kind='routine',evidence='Разговор завершён.')
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','',continuity_decision=p).resolve(raw)
    raw['final_scene']['compression'].update(response_event_id='question',player_evidence='Нет.')
    out=StateResolver(s,'Разговор завершён.','Нет.',continuity_decision=p).resolve(raw)
    assert out.history['turns'][0]['continuity']['answered_response_ids']==['question']
    assert out.history['state_changes'][0]['response_event_id']=='question'
    p['pending_response_ids'].append('other')
    with pytest.raises(StructuralDeltaError):
        StateResolver(s,'Разговор завершён.','Нет.',continuity_decision=p).resolve(raw)


def test_shared_history_is_relevant_but_not_disclosed_to_other_actors():
    from backend.runtime_v3.history_selector import HistorySelector
    snap=setup();s=snap['world_state'];s['meta']['turn_id']=10
    event=dict(id='shared',text='Общий опыт',participants=['a','b'],witnesses=['a','b'],turn_id=1)
    scope=ContextScope('a',present_actor_ids={'a','b'})
    before=deepcopy(s)
    assert HistorySelector(s,{'events':[event]}).select_scope(scope,2400)==[event]
    scope=ContextScope('child',present_actor_ids={'child','b'})
    assert not HistorySelector(s,{'events':[event]}).select_scope(scope,2400)
    assert s==before


def test_100_actors_long_history_projection_bounded():
    snap=setup();s=snap['world_state']
    for n in range(120):s['characters'][f'n{n}']=Character(id=f'n{n}').model_dump()
    history={'events':[dict(id=str(n),text='Тихо',participants=['a','b'],witnesses=['a','b']) for n in range(20000)]}
    start=time.monotonic();p=permit(snap,history)
    assert len(p['recent_beats'])<=16 and time.monotonic()-start<2


def test_ilya_sonya_real_jobs_reload_regenerate_rollback_branch(tmp_path):
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.repository import read_history
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'continuity.sqlite');sid=load_fixture(repo,'continuity')['save']
    a,b=ACTOR_ID,'qa_vera'
    def run(text,phase=None,kind='turn',depart=False,finish=False):
        before=repo.get_snapshot(sid);s=before['world_state'];camera=s['camera']
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=[a] if depart else camera['present_character_ids'],elapsed_minutes=1),
            events=[dict(id='meeting',text=text,evidence=text,participants=[a,b],witnesses=[a,b],medium='conversation')])
        if phase:raw['scene_transitions']=[dict(source_event_id='meeting',phase=phase,actor_ids=[a,b],thread_ids=['qa_meeting'],evidence=text)]
        if finish:
            intention=s['characters'][a]['intentions'][0]
            raw['character_changes']=[dict(id=a,intentions_updates=[dict(id=intention['id'],status='completed',expected_revision=intention['revision'],source_event_id='meeting',evidence=text)])]
            raw['scheduled_event_changes']=[dict(id='date',assertion='occurred',source_event_id='meeting',evidence=text)]
        raw['choices']=[dict(action='Встретиться с Соней',speech='',kind='proposal',basis_ids=['date']),dict(action='Организовать эту встречу',speech='',kind='proposal',basis_ids=['date']),dict(action='Осмотреться',speech='')]
        job=repo.begin_job(sid,'Слушаю.' if kind!='start' else '',kind,CONFIG)
        calls=execute(repo,job,raw,text)
        assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
        assert len(calls)==2
        return repo.get_snapshot(sid),repo.get_job(job)
    initial=repo.get_snapshot(sid);s=initial['world_state']
    s['scheduled_events']['date']=ScheduledEvent(id='date',description='Встреча Ильи и Сони в «Гвозде»',character_ids=[a,b],due_minute=s['meta']['world_time'],commitment=True).model_dump()
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(initial),sid))
    agreed,_=run('Илья и Соня договорились встретиться в «Гвозде».',kind='start')
    met,_=run('Соня пришла, Илья и Соня встретились в «Гвозде».','started',finish=True)
    assert met['world_state']['characters'][a]['intentions'][0]['status']=='completed'
    assert met['world_state']['scheduled_events']['date']['status']=='resolved'
    talked,_=run('Илья и Соня поговорили о прошедшем дне.','advanced')
    ended,_=run('Илья и Соня попрощались и разошлись.','ended',depart=True)
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==ended
    next_state,job=run('Илья рассматривает улицу.')
    current=next_state['world_state']
    assert current['threads']['qa_meeting']['status']=='developing'
    assert 'ждёт' not in current['threads']['qa_meeting']['state']
    assert not current['characters'][b]['situation']
    assert current['characters'][b]['location_id']==ended['world_state']['characters'][b]['location_id']
    wire=json.loads(job['context_json']);assert 'Илья ждёт Соню' not in '\n'.join(m['content'] for m in wire if m['content'].startswith('Текущее состояние'))
    turn=repo.list_turns(sid)[-1];original_plan=recorded(wire)
    variant,vjob=run('Илья смотрит на вывеску.',kind='regenerate')
    assert recorded(json.loads(vjob['context_json']))==original_plan
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==next_state
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==ended
    branch,_=run('Илья смотрит на небо.')
    assert branch['world_state']['threads']['qa_meeting']['status']=='developing'
    with repo.connect() as db:history,_=read_history(db,branch['history_head'])
    assert 'Илья смотрит на вывеску.' not in [r['narrative'] for r in history['turns']]


def test_targeted_history_rejection_survives_long_tail_and_branch(tmp_path):
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.repository import append_history,continuity_reader
    snap=setup();s=snap['world_state']
    out=StateResolver(s,'Разговор завершён.','').resolve(payload(s,continuity_beats=[beat('rejected','opportunity')]))
    repo=Repository(tmp_path/'archive.sqlite')
    with repo.connect() as db:
        root=append_history(db,None,out.history);head=root
        for n in range(250):head=append_history(db,head,{'turns':[dict(turn_id=n+2)],'events':[]})
        sibling=append_history(db,None,{'events':[]})
    snap['world_state']=out.state
    p=permit(snap,{'_continuity_query':continuity_reader(repo,head)})
    assert p['recent_beats'][0]['status']=='rejected'
    assert not permit(snap,{'_continuity_query':continuity_reader(repo,sibling)})['recent_beats']


def test_milestone_relevance_decays_with_established_later_scenes_and_is_actor_known():
    from backend.runtime_v3.pacing import development_sources
    snap=setup();s=snap['world_state'];s['meta']['world_time']=1000
    scope=ContextScope('a',pov_actor_id='a',present_actor_ids={'a','b'})
    read=lambda **kw:[dict(id='move',category='relocation',actor_ids=['a'],minute=900,summary='Переехал',fact_id='secret')]
    first=development_sources(s,scope,read)
    later=development_sources(s,scope,read,{'turns':[dict(world_time=950,continuity={'progress':['scene']}) for _ in range(16)]})
    assert first[0]['freshness']>later[0]['freshness']>0
    assert first[0]['known_by']==['a'] and not s['threads'].get('move')


def test_external_decision_cannot_be_fabricated_in_continuity():
    s=setup()['world_state'];row=beat('resolved','decision');row['actor_id']='a'
    raw=payload(s,continuity_beats=[row])
    with pytest.raises(StructuralDeltaError):StateResolver(s,'Разговор завершён.','').resolve(raw)
    row['player_evidence']='Я решил.'
    assert StateResolver(s,'Разговор завершён.','Я решил.').resolve(raw).state


def test_unlinked_player_response_does_not_answer_all_pending_questions():
    from test_npc_initiative import payload as action_payload, permit as action_permit
    snap=setup(); player='Нет, на первый вопрос отвечаю отказом.'
    raw=action_payload(snap,response='player_supplied',player_evidence=player)
    out=StateResolver(snap['world_state'],raw['events'][0]['text'],player,
        initiative_decision=action_permit(snap),
        continuity_decision={'pending_response_ids':['first','second']}).resolve(raw)
    assert out.history['turns'][0]['continuity']['answered_response_ids']==[]


@pytest.mark.parametrize('reference,response,evidence',[
    ('missing','player_supplied','Нет.'), ('first','open','Нет.'),
    ('first','player_supplied','Да.')])
def test_response_reference_requires_pending_id_and_current_player_evidence(reference,response,evidence):
    from test_npc_initiative import payload as action_payload, permit as action_permit
    snap=setup();before=deepcopy(snap)
    raw=action_payload(snap,response=response,player_evidence=evidence,response_event_id=reference)
    with pytest.raises(StructuralDeltaError):
        StateResolver(snap['world_state'],raw['events'][0]['text'],'Нет.',
            initiative_decision=action_permit(snap),
            continuity_decision={'pending_response_ids':['first','second']}).resolve(raw)
    assert snap==before


def test_multiple_pending_responses_real_jobs_reload_regenerate_and_branch(tmp_path):
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.repository import read_history
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'responses.sqlite');sid=load_fixture(repo,'continuity')['save']
    a,b=ACTOR_ID,'qa_vera'
    def run(kind,answer=None):
        s=repo.get_snapshot(sid)['world_state']
        text='Соня спрашивает о работе. Соня спрашивает о поездке.' if answer is None else 'Соня принимает ответ о работе.'
        raw=dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids']),
                 events=[],scene_actions=[])
        for key in (['work','travel'] if answer is None else ['answer']):
            raw['events'].append(dict(id=key,text=text,evidence=text,participants=[a,b],witnesses=[a,b],medium='conversation'))
            claim=dict(actor_id=b,target_ids=[a],source_event_id=key,phase='continue',modality='speech',
                       interruptible=True,response='open' if answer is None else 'player_supplied',evidence=text)
            if answer is not None:claim.update(response_event_id=answer,player_evidence='На этот вопрос отвечаю: нет.')
            raw['scene_actions'].append(claim)
        job=repo.begin_job(sid,'' if kind=='start' else 'На этот вопрос отвечаю: нет.',kind,CONFIG)
        execute(repo,job,raw,text)
        job=repo.get_job(job);assert job['status']=='saved',job['error']
        snap=repo.get_snapshot(sid)
        with repo.connect() as db:history,_=read_history(db,snap['history_head'])
        return snap,history,job
    opened,history,_=run('start')
    pending=permit(opened,history)['pending_response_ids']
    assert len(pending)==2
    answered,history,job=run('turn',pending[0])
    assert history['turns'][-1]['continuity']['answered_response_ids']==[pending[0]]
    assert permit(answered,history)['pending_response_ids']==[pending[1]]
    repo=Repository(repo.path)
    assert repo.get_snapshot(sid)==answered
    turn=repo.list_turns(sid)[-1]
    regenerated,history,regen=run('regenerate',pending[0])
    assert recorded(json.loads(regen['context_json']))==recorded(json.loads(job['context_json']))
    assert permit(regenerated,history)['pending_response_ids']==[pending[1]]
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==answered
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==opened
    branched,history,_=run('turn',pending[1])
    assert history['turns'][-1]['continuity']['answered_response_ids']==[pending[1]]
    assert permit(branched,history)['pending_response_ids']==[pending[0]]
