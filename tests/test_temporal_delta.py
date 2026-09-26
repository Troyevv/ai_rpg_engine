"""Event-time presence is not final camera membership, nor before/after union."""
import json
from copy import deepcopy
from unittest.mock import patch
from threading import Event
import pytest
from test_engine import db, CONFIG
from test_player_agency import execute
from state_updates import apply_world_updates
from backend.services.world_delta_errors import StructuralDeltaError
from backend.services.world_delta import WorldDelta
from backend.services.simulation import simulate

A='character_1';B='character_2';C='character_3'
QUOTE='Илья и Люда разговаривают в кабинете. Илья прощается и выходит в коридор. Люда идёт в ординаторскую.'

def setup(repo,sid,present=None,observer=False):
    state=repo.get_save(sid)['state'];present=present if present is not None else [A,B]
    state['world_clock']={'minute':540,'last_event_time':'День 1 09:00'}
    state['scene_meta']={'time':'День 1 09:00','location':'кабинет','present_ids':present}
    state['camera']={'scene_id':'office','mode':'observer' if observer else 'actor','scope':'scene'}
    state['controlled_actor_id']=None if observer else A
    state['world']['scenes']={'office':dict(id='office',location='кабинет',participants=present[:],start_minute=540,end_minute=540,status='active',text='Начало',event_ids=[])}
    for cid,p in state['world']['characters'].items():
        p.update(location='кабинет' if cid in present else 'коридор',scene_id='office' if cid in present else None)
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state),sid))
    return state

def move(actor,src,dst,minute=542,order=0):
    return dict(actor_id=actor,from_location=src,to_location=dst,minute=minute,order=order,evidence=QUOTE)

def payload(present=None,location='кабинет',transitions=(),event_minute=540,event_order=0,observer=False):
    return {'scene':{'text':'Завершённый ход','time':'День 1 09:03','elapsed_minutes':3,'location':location,'present_ids':present or [A]},
        'choices':[] if observer else [{'action':f'Действие {i}','speech':''} for i in range(6)],
        'world_delta':{'transitions':list(transitions),
         'facts':[dict(id='f',text='Анализ положительный',evidence=QUOTE)],
         'events':[dict(id='e',minute=event_minute,order=event_order,location='кабинет',text='Разговор',participants=[A,B],witnesses=[A,B],fact_ids=['f'],medium='conversation',evidence=QUOTE)],
         'knowledge':[dict(actor_id=B,fact_id='f',source_event_id='e',status='known',evidence=QUOTE)]}}

def apply(before,p,kind='turn'):
    return apply_world_updates(before,p,QUOTE,'Я выхожу в коридор.',1,kind,discard_unsupported=True)

@pytest.mark.parametrize('departures',[[A],[B],[A,B]])
def test_conversation_then_departure_preserves_event_knowledge_and_final_positions(db,departures):
    repo,_,sid=db;before=setup(repo,sid)
    dest={A:'коридор',B:'ординаторская'}
    p=payload(present=[A] if B in departures or A in departures else [A,B],location=dest[A] if A in departures else 'кабинет',
        transitions=[move(cid,'кабинет',dest[cid]) for cid in departures])
    p['world_delta']['characters']=[dict(id=B,location=dest[B] if B in departures else 'кабинет',situation='Завершила разговор',evidence=QUOTE)]
    p['world_delta']['relationships']=[dict(source_id=B,target_id=A,dimensions={'trust':30},context='После разговора',evidence=QUOTE)]
    original=deepcopy(before)
    state,_,_,audience,warnings=apply(before,p)
    assert before==original and warnings==[] and set(audience)=={A,B}
    w=state['world'];assert w['knowledge'][B+':f']['status']=='known'
    assert w['characters'][A]['location']==('коридор' if A in departures else 'кабинет')
    assert w['characters'][B]['location']==('ординаторская' if B in departures else 'кабинет')
    event=w['events']['e'];scene=w['scenes'][event['scene_id']]
    assert event['location']=='кабинет' and scene['participants']==[A,B] and scene['historical']
    assert w['characters'][B]['situation']=='Завершила разговор'
    assert w['scenes'][w['characters'][B]['scene_id']]['location']==w['characters'][B]['location']

@pytest.mark.parametrize('arrival,event_time,accepted',[(541,542,True),(542,541,False)])
def test_arrival_before_or_after_event(db,arrival,event_time,accepted):
    repo,_,sid=db;before=setup(repo,sid,[A])
    p=payload([A,B],transitions=[move(B,'коридор','кабинет',arrival)],event_minute=event_time)
    p['world_delta']['events'][0]['participants']=[A]
    if accepted:assert apply(before,p)[0]['world']['knowledge'][B+':f']['status']=='known'
    else:
        with pytest.raises(StructuralDeltaError) as error:apply(before,p)
        assert error.value.code=='event_witness_not_present'

def test_departed_witness_is_rejected(db):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload(transitions=[move(B,'кабинет','коридор',541)],event_minute=542)
    p['world_delta']['events'][0]['participants']=[A]
    with pytest.raises(StructuralDeltaError) as error:apply(before,p)
    assert error.value.code=='event_witness_not_present'

def test_before_after_union_does_not_prove_meeting(db):
    repo,_,sid=db;before=setup(repo,sid,[A],observer=True)
    p=payload([B],transitions=[move(A,'кабинет','коридор',541),move(B,'коридор','кабинет',542)],event_minute=542,observer=True)
    with pytest.raises(StructuralDeltaError):apply(before,p,'background')

@pytest.mark.parametrize('event_order,accepted',[(0,True),(2,False)])
def test_same_minute_order_is_deterministic(db,event_order,accepted):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload(transitions=[move(B,'кабинет','коридор',540,1)],event_minute=540,event_order=event_order)
    if accepted:apply(before,p)
    else:
        with pytest.raises(StructuralDeltaError):apply(before,p)

@pytest.mark.parametrize('defect,code',[
    ('final_location','character_location_inconsistent'),('random_npc','character_not_involved'),
    ('origin','transition_location_invalid'),('time','temporal_order_invalid'),('same_order','temporal_order_invalid'),
    ('missing_time','temporal_order_invalid'),('evidence','transition_invalid')])
def test_structural_failures_are_not_sanitized(db,defect,code):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload(transitions=[move(B,'кабинет','коридор')])
    if defect=='final_location':p['scene']['present_ids']=[A,B]
    if defect=='random_npc':p['world_delta']['characters']=[dict(id=C,emotion='радуется',evidence=QUOTE)]
    if defect=='origin':p['world_delta']['transitions'][0]['from_location']='подвал'
    if defect=='time':p['world_delta']['transitions'][0]['minute']=539
    if defect=='same_order':p['world_delta']['transitions'].append(move(B,'коридор','кабинет'))
    if defect=='missing_time':del p['world_delta']['events'][0]['minute']
    if defect=='evidence':p['world_delta']['transitions'][0]['evidence']='Нет такой цитаты'
    with pytest.raises(StructuralDeltaError) as error:apply(before,p)
    assert error.value.code==code
    assert repo.get_save(sid)['state']==before

@pytest.mark.parametrize('kind',['start','turn','regenerate'])
def test_normal_movement_uses_two_calls_and_variant_keeps_own_state(db,kind):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload([A],location='коридор',transitions=[move(A,'кабинет','коридор')])
    if kind in ('turn','regenerate'):
        first=repo.begin_job(sid,'','start',CONFIG)
        static=payload([A,B]);static['scene']['time']='День 1 09:00';static['scene']['elapsed_minutes']=0
        assert len(execute(repo,first,static,QUOTE))==2
        if kind=='turn':p['world_delta']['events'][0]['id']='e2';p['world_delta']['knowledge'][0]['source_event_id']='e2'
    job=repo.begin_job(sid,'Я выхожу в коридор.',kind,CONFIG)
    assert len(execute(repo,job,p,QUOTE))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    diag=repo.turn_diagnostics(sid)[0]
    assert diag['repairs']==[] and diag['warnings']==[] and len(diag['requests'])==2
    assert repo.get_save(sid)['state']['world']['characters'][B]['location']=='кабинет'
    event=repo.get_save(sid)['state']['world']['events']['e2' if kind=='turn' else 'e']
    assert event['source_record_id']

def test_observer_and_automatic_background_share_temporal_contract(db):
    repo,_,sid=db;state=setup(repo,sid,[B,C],observer=True)
    p=payload([B],transitions=[move(C,'кабинет','коридор')],observer=True)
    p['world_delta']['events'][0].update(participants=[B,C],witnesses=[B,C])
    p['world_delta']['knowledge'][0]['actor_id']=C
    assert apply(state,p,'background')[0]['world']['knowledge'][C+':f']['status']=='known'
    # Simulation replays a historical interval only up to its current world time.
    state['world_clock']['minute']=543
    p['scene']['elapsed_minutes']=0
    calls=[];warnings=[]
    def generate(stage,*args,**kwargs):
        calls.append(stage);yield QUOTE if stage=='world_simulation' else json.dumps(p)
    with patch('backend.services.simulation.background_candidate',return_value={'actor_id':B,'reason':'test','scheduled_id':None}):
        updated=simulate(deepcopy(state),state,2,32768,CONFIG,generate,Event(),warnings=warnings)
    assert calls==['world_simulation','world_simulation_delta'] and not warnings
    assert updated['world']['knowledge'][C+':f']['status']=='known'

def test_optional_schema_and_stale_prompt_receive_temporal_contract(db):
    from context_builder import build_context
    repo,_,sid=db;before=setup(repo,sid)
    schema=WorldDelta.model_json_schema()
    assert 'transitions' not in schema.get('required',[])
    assert 'order' not in schema['$defs']['Event'].get('required',[])
    messages=build_context(before,[],QUOTE,'turn',32768,4096,extraction_text=QUOTE,prompts={'state_update_prompt.md':{'content':'Old prompt'}})
    assert 'КОНЕЧНОЕ состояние камеры' in messages[0]['content']

def test_temporal_failure_rolls_back_whole_job_after_one_repair(db):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload(transitions=[move(B,'кабинет','коридор',541)],event_minute=542)
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,QUOTE))==3
    assert repo.get_job(job)['status']=='error'
    assert repo.get_save(sid)['state']==before and repo.list_turns(sid)==[]
    reason=json.loads(repo.get_job(job)['repair_diagnostics_json'])[0]
    assert reason['repair_error_code']=='event_participant_not_present'
    assert reason['section']=='events' and reason['index']==0

def test_promoted_npc_can_arrive_and_leave_before_final_scene(db):
    from backend.services.world import CARD_FIELDS
    repo,_,sid=db;before=setup(repo,sid,[A])
    p=payload(transitions=[move('new',None,'кабинет',540),move('new','кабинет','коридор',542)],event_minute=541)
    p['world_delta']['promotions']=[dict(id='new',name='Новый',fields={f:'Описание' for f in CARD_FIELDS},evidence=QUOTE)]
    p['world_delta']['events'][0].update(participants=[A,'new'],witnesses=[A,'new'])
    p['world_delta']['knowledge'][0]['actor_id']='new'
    state=apply(before,p)[0]
    assert state['world']['characters']['new']['location']=='коридор'
    assert state['world']['knowledge']['new:f']['status']=='known'

def test_pov_turn_and_historical_membership_survive_later_movement(db):
    from backend.services.pov import transition
    repo,_,sid=db;before=transition(setup(repo,sid),B)
    p=payload([B],location='ординаторская',transitions=[move(B,'кабинет','ординаторская')])
    state=apply(before,p,'pov')[0]
    assert state['controlled_actor_id']==B and state['world']['characters'][A]['location']=='кабинет'
    historical_id=state['world']['events']['e']['scene_id']
    snapshot=deepcopy(state['world']['scenes'][historical_id])
    next_payload=payload([B],location='кабинет',transitions=[move(B,'ординаторская','кабинет',544)])
    next_payload['scene'].update(time='День 1 09:06',elapsed_minutes=3)
    next_payload['world_delta']['events']=[];next_payload['world_delta']['knowledge']=[];next_payload['world_delta']['facts']=[]
    after=apply_world_updates(state,next_payload,QUOTE,'',2,'turn')[0]
    assert after['world']['scenes'][historical_id]==snapshot

def test_array_order_does_not_change_chronology_or_last_event(db):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload(transitions=[move(B,'коридор','ординаторская',542),move(B,'кабинет','коридор',541)])
    early=p['world_delta']['events'][0]
    late={**early,'id':'later','minute':542,'order':1,'participants':[A],'witnesses':[A]}
    p['world_delta']['events']=[late,early]
    state=apply(before,p)[0]
    assert state['world']['characters'][A]['last_event_id']=='later'
    assert state['world']['characters'][B]['location']=='ординаторская'
