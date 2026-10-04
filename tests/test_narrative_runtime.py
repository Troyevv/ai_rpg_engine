import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_engine import db, CONFIG
from test_runtime_v3_domain import initial
from test_runtime_v3_storage import snapshot_fixture
from test_runtime_v3_engine import raw_for, run
from backend.runtime_v3.models import Character, Motivation, ScheduledEvent, Relationship
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.time_skip import parse_skip, plan_skip, TimeSkipRequest, calendar_label
from backend.runtime_v3.migration import migrate_v2, initialize_calendar
from backend.runtime_v3.lifecycle import active_texts
from backend.runtime_v3.notifications import notifications
from backend.runtime_v3.history_selector import HistorySelector
from backend.runtime_v3.director import interval_candidates
from backend.runtime_v3.selectors import ui_view


def test_calendar_thursday_and_migration_stable():
    snapshot=snapshot_fixture();snapshot['world_state']['meta']['world_time']=3*1440+750
    first=migrate_v2(snapshot).snapshot
    state=first['world_state']
    assert calendar_label(state)=='День 1 · Чт · 12:30'
    assert calendar_label(state,state['meta']['world_time']+1440)=='День 2 · Пт · 12:30'
    assert calendar_label(state,state['meta']['world_time']+7*1440)=='День 8 · Чт · 12:30'
    assert migrate_v2(first).snapshot==first
    assert first['world_state']['characters']['a']['goals'][0]['id']==state['characters']['a']['goals'][0]['id']


@pytest.mark.parametrize('text,source,duration',[
 ('Сплю восемь часов.','sleep',480),('Ложусь спать до 07:00.','sleep',510),
 ('Жду до вечера.','wait',1170),('Следующие четыре часа разбираю документы.','long_action',240),
 ('Еду три часа.','travel',180),('Жду 10 минут.','wait',10)])
def test_time_skip_explicit(text,source,duration):
    request=parse_skip(text,22*60+30)
    assert request.source==source and request.target_minute-request.start_minute==duration


@pytest.mark.parametrize('text',['Ложусь спать.','Я не сплю восемь часов.','Если я сплю восемь часов?','Он сказал: «Сплю восемь часов».'])
def test_ambiguous_time_not_invented(text):
    assert parse_skip(text,1350) is None


def test_skip_interrupt_and_budget():
    state=initial();state['meta']['world_time']=1350
    state['scheduled_events']['wake']=ScheduledEvent(id='wake',description='Звонок герою',character_ids=['a'],due_minute=1637,interrupts=True).model_dump()
    state['scheduled_events']['hidden']=ScheduledEvent(id='hidden',description='Встреча',character_ids=['c'],due_minute=1500,interrupts=True).model_dump()
    result=plan_skip(state,TimeSkipRequest(1350,1920,'Сон','sleep'))
    assert result['actual_target']==1637 and result['interruption_event_id']=='wake'
    assert result['elapsed_minutes']==287 and result['interrupted']
    after=deepcopy(state);after['meta']['world_time']=1920
    after['characters']['c']['location_id']='hall'
    for i in range(30):after['scheduled_events'][str(i)]=ScheduledEvent(id=str(i),description=str(i),character_ids=['c'],due_minute=1500).model_dump()
    groups,diagnostics=interval_candidates(state,after)
    assert len(groups)==1 and diagnostics['merged_candidates']>=29


@pytest.mark.parametrize('field,text,evidence',[
 ('intentions','Ответить Юре про стоматолога','Я ответил Юре про стоматолога.'),
 ('goals','Получить документы','Я получил документы.')])
def test_complete_retains_history_and_projects_active(field,text,evidence):
    state=initial();state['characters']['a'][field]=[Motivation(id='item',text=text).model_dump()]
    p=dict(final_scene=dict(location_id='room',present_character_ids=['a']),character_changes=[dict(id='a',**{field+'_updates':[dict(id='item',status='completed',evidence=evidence)]})])
    resolved=StateResolver(state,evidence,evidence).resolve(p)
    assert resolved.state['characters']['a'][field][0]['status']=='completed'
    snapshot=snapshot_fixture();snapshot['world_state']=resolved.state
    view=ui_view(snapshot,resolved.history)
    assert not view['world']['characters']['a'][field]
    assert view['world']['characters']['a']['lifecycle'][field][0]['id']=='item'
    assert any(n['kind']=='lifecycle' for n in view['notifications'])


def test_agency_and_obligation_explicit_source():
    state=initial();quote='Хорошо, завтра отвезу тебя.'
    p=dict(final_scene=dict(location_id='hall',present_character_ids=['a']),character_changes=[dict(id='a',situation='У двери',emotion='злится',evidence='Я сжал кулак у двери.',
      intentions_updates=[dict(text='Ударить Юру',status='active',evidence='Я сжал кулак у двери.')],
      obligations_updates=[dict(text='Отвезти тебя завтра',status='active',evidence=quote)])])
    result=StateResolver(state,'Я сжал кулак у двери.',quote).resolve(p)
    actor=result.state['characters']['a']
    assert actor['location_id']=='hall' and actor['situation']=='У двери'
    assert not actor['emotion'] and not actor['intentions']
    assert active_texts(actor['obligations'])==['Отвезти тебя завтра']
    p['character_changes']=[dict(id='a',emotion='страшно',player_evidence={'emotion':'Мне страшно'})]
    result=StateResolver(state,'Герой улыбается.','Мне страшно.').resolve(p)
    assert result.state['characters']['a']['emotion']=='страшно'
    assert result.state['characters']['a']['emotion_source_sequence']==0


def test_irrelevant_evidence_does_not_complete():
    state=initial();state['characters']['a']['intentions']=[Motivation(id='x',text='Получить документы').model_dump()]
    p=dict(final_scene=dict(location_id='room',present_character_ids=['a']),character_changes=[dict(id='a',intentions_updates=[dict(id='x',status='completed',evidence='Я посмотрел в окно.')])])
    r=StateResolver(state,'Я посмотрел в окно.','').resolve(p)
    assert r.state['characters']['a']['intentions'][0]['status']=='active'


def test_relationship_semantics_hidden_new_pairs():
    state=initial();state['relationships']['a:b']=Relationship(source_id='a',target_id='b',dimensions=dict(trust=10,irritation=0)).model_dump()
    p=dict(final_scene=dict(location_id='room',present_character_ids=['a']),relationship_changes=[dict(source_id='a',target_id='b',dimensions=dict(trust=15,irritation=5),evidence='Разговор окончен.')])
    result=StateResolver(state,'Разговор окончен.','').resolve(p)
    notice=notifications(result.state,result.history)[0]
    assert notice['direction']=='mixed' and notice['deltas']==dict(trust=5,irritation=5)
    hidden=StateResolver(state,'Разговор окончен.','',observed=False).resolve(p)
    assert notifications(hidden.state,hidden.history)==[]
    state['relationships']={};fresh=StateResolver(state,'Разговор окончен.','').resolve(p)
    assert not notifications(fresh.state,fresh.history)


def test_history_bounded_and_legacy_memory_excluded():
    snapshot=snapshot_fixture();snapshot['memory']={'summary':'STALE PROSE MUST NOT BECOME TRUTH'}
    events=[dict(id=str(i),text='Подробность '*100,participants=['a'],location_id='room') for i in range(50)]
    selected=HistorySelector(snapshot['world_state'],dict(events=events)).select('a','room',['a'],[],600)
    assert len(selected)<=1
    from context_builder import build_context,estimate
    messages=build_context(snapshot,[],'Продолжить','turn',32768,2000,world_history=dict(events=events))
    assert 'STALE PROSE' not in str(messages) and estimate(messages)<30768


def test_manual_skip_regenerate_rollback_and_zero_memory(db):
    repo,_,sid=db
    start=repo.begin_job(sid,'','start',CONFIG);run(repo,start,raw_for(repo.get_snapshot(sid)))
    before=repo.get_snapshot(sid)
    cfg=dict(CONFIG,time_skip={'duration':10,'reason':'Пауза'})
    job=repo.begin_job(sid,'Жду 10 минут.','turn',cfg)
    with patch('engine.compact',side_effect=AssertionError('Memory LLM called')):
        calls=run(repo,job,raw_for(before))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert len(calls)==2
    after=repo.get_snapshot(sid)
    assert after['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+10
    assert after['last_time_skip']['source']=='manual'
    turn=repo.list_turns(sid)[-1];variant=turn['active_variant_id']
    job=repo.begin_job(sid,'','regenerate',CONFIG);run(repo,job,raw_for(before))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==after['world_state']['meta']['world_time']
    repo.select_variant(sid,turn['id'],variant,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before


def test_wait_arrival_interrupts_only_at_waiting_location():
    state=initial();state['meta']['world_time']=720
    request=parse_skip('Жду Юру до 18:00.',720,[dict(id='b',name='Юра')])
    assert request.wait_for_actor_id=='b'
    state['scheduled_events']['arrival']=ScheduledEvent(id='arrival',description='Юра приходит',type='arrival',location_id='room',character_ids=['b'],due_minute=920).model_dump()
    assert plan_skip(state,request)['actual_target']==920
    state['scheduled_events']['arrival']['location_id']='hall'
    assert plan_skip(state,request)['actual_target']==1080


def test_long_skip_batch_hidden_state_and_knowledge(db):
    import engine
    repo,_,sid=db
    start=repo.begin_job(sid,'','start',CONFIG);run(repo,start,raw_for(repo.get_snapshot(sid)))
    snapshot=snapshot_fixture();s=snapshot['world_state'];s['camera']['present_character_ids']=['a']
    s['characters']['b']['location_id']='hall';s['characters']['c']['location_id']='hall'
    s['scheduled_events']['due']=ScheduledEvent(id='due',description='Тайный разговор',character_ids=['b','c'],due_minute=60).model_dump()
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    job=repo.begin_job(sid,'Сплю восемь часов.','turn',CONFIG);calls=[]
    def stream(**kw):
        calls.append(kw)
        if not kw.get('response_format'):yield 'Разговор окончен.';return
        current=json.loads(next(m['content'] for m in kw['messages'] if m['content'].startswith('Текущее состояние')).split('\n',1)[1]);camera=current['camera'];hidden=camera['mode']=='observer'
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0))
        if hidden:
            raw.update(facts=[dict(id='secret',text='Тайна',evidence='Разговор окончен.')],events=[dict(id='e',text='Тайный разговор',participants=['b','c'],witnesses=['a','b','c'],fact_ids=['secret'],medium='conversation',evidence='Разговор окончен.')],
                knowledge_gained=[dict(actor_id=cid,fact_id='secret',source_event_id='e',evidence='Разговор окончен.') for cid in ['a','b','c']],
                relationship_changes=[dict(source_id='b',target_id='c',dimensions={'trust':30},evidence='Разговор окончен.')])
        yield json.dumps(raw)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    after=repo.get_snapshot(sid);state=after['world_state']
    assert len(calls)==4 and state['meta']['world_time']==480
    assert 'a:secret' not in state['knowledge'] and 'b:secret' in state['knowledge']
    assert not repo.get_save(sid)['state']['notifications']
    assert after['last_time_skip']['living_world_llm_calls']==2
    assert state['camera']==s['camera']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==snapshot


def test_confirmed_scene_can_refresh_controlled_situation_without_emotion():
    state=initial();state['characters']['a']['situation']='Сидит дома'
    evidence='Разговор окончен. Все стоят у двери.'
    raw=dict(final_scene=dict(location_id='hall',present_character_ids=['a'],situation='Стоит у двери после разговора',situation_evidence=evidence))
    result=StateResolver(state,evidence,'').resolve(raw)
    assert result.state['characters']['a']['situation']=='Стоит у двери после разговора'
    assert not result.state['characters']['a']['emotion']


def test_lifecycle_rollback_and_regeneration(db):
    repo,_,sid=db
    start=repo.begin_job(sid,'','start',CONFIG);run(repo,start,raw_for(repo.get_snapshot(sid)))
    before=repo.get_snapshot(sid);actor=before['world_state']['camera']['controlled_actor_id']
    before['world_state']['characters'][actor]['intentions']=[Motivation(id='reply',text='Ответить собеседнику').model_dump()]
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    text='Я ответил собеседнику.';raw=raw_for(before);raw['character_changes']=[dict(id=actor,intentions_updates=[dict(id='reply',status='completed',evidence=text)])]
    job=repo.begin_job(sid,text,'turn',CONFIG);run(repo,job,raw)
    assert repo.get_snapshot(sid)['world_state']['characters'][actor]['intentions'][0]['status']=='completed'
    job=repo.begin_job(sid,'','regenerate',CONFIG);run(repo,job,raw_for(before))
    assert repo.get_snapshot(sid)['world_state']['characters'][actor]['intentions'][0]['status']=='active'
    assert not repo.get_save(sid)['state']['notifications']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==before


def test_answering_is_complete_but_promised_trip_is_still_active():
    state=initial();state['characters']['a']['intentions']=[Motivation(id='answer',text='Ответить Юре про стоматолога').model_dump()]
    quote='Хорошо, завтра отвезу тебя.'
    raw=dict(final_scene=dict(location_id='room',present_character_ids=['a','b']),character_changes=[dict(id='a',
        intentions_updates=[dict(id='answer',status='completed',evidence=quote)],
        obligations_updates=[dict(text='Отвезти тебя завтра',status='active',evidence=quote)])])
    result=StateResolver(state,'Юра кивнул.',quote,actor_names={'b':'Юра'}).resolve(raw)
    assert result.state['characters']['a']['intentions'][0]['status']=='completed'
    assert result.state['characters']['a']['obligations'][0]['status']=='active'
    # Ambiguous interlocutor must not complete a reply to somebody else.
    result=StateResolver(state,'Сергей кивнул.',quote,actor_names={'b':'Сергей'}).resolve(raw)
    assert result.state['characters']['a']['intentions'][0]['status']=='active'
