"""Review #169: real job lineage, observer context, domain edits and profile CAS."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from test_engine import db, CONFIG
from test_npc_review import start, command, promoted
from test_runtime_v3_engine import raw_for, run
from backend.services.npc_review import edit, generate
from backend.services.npc_review_context import profile_state, context
from backend.runtime_v3.repository import read_history
from backend.services.world import CARD_FIELDS


def evolve(repo, sid):
    snapshot=repo.get_snapshot(sid); state=snapshot['world_state']; observer=state['camera']['controlled_actor_id']
    raw=raw_for(snapshot)
    text='Лада решилась открыть мастерскую. Теперь у неё короткие волосы.'
    raw.update(
        facts=[dict(id='new_look',text=text,character_ids=['new_npc'],evidence=text)],
        events=[dict(id='decision',text=text,participants=['new_npc',observer],witnesses=['new_npc',observer],fact_ids=['new_look'],medium='conversation',evidence=text)],
        knowledge_gained=[dict(actor_id=observer,fact_id='new_look',source_event_id='decision',evidence=text)],
        appearance_deltas=[dict(actor_id='new_npc',item_id='hair',operation='establish',category='presentation',kind='hairstyle',text='Короткие волосы',expected_revision=0,source_event_id='decision',fact_id='new_look',assertion='established_visual_outcome',transition='voluntary',evidence=text)],
        development_evidence=[dict(id='resolve',actor_id='new_npc',source_event_id='decision',meaning='Решилась начать своё дело',kind='turning_point',assertion='completed',evidence=text)],
        personality_deltas=[dict(actor_id='new_npc',evidence_ids=['resolve'],rationale='Поворотный опыт самостоятельности',developmental_fit='established_capability',evidence=text,operations=[dict(item_id='resolve',field='traits',operation='establish',text='Решительная и самостоятельная',expected_text=None,expected_revision=0)])],
        character_changes=[dict(id='new_npc',goals=['Открыть мастерскую'],physical_state='Бодра',situation='Обсуждает своё дело',evidence=text)],
        life_changes=[dict(id='new_npc',life_status='alive',fact_id='new_look',assertion='established',evidence=text)],
        role_changes=[dict(id='craft',actor_id='new_npc',kind='occupation',title='Мастер',fact_id='new_look',evidence=text)],
        residence_changes=[dict(id='home',actor_id='new_npc',location_id=next(iter(state['locations'])),fact_id='new_look',evidence=text)])
    jid=repo.begin_job(sid,'Слушаю Ладу.','turn',CONFIG)
    def stream(**kwargs):yield json.dumps(raw,ensure_ascii=False) if kwargs.get('response_format') else text+' «Я справлюсь сама», — сказала Лада.'
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    for _ in range(2):
        jid=repo.begin_job(sid,'Продолжаем разговор.','turn',CONFIG);run(repo,jid,raw_for(repo.get_snapshot(sid)))
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    return repo.get_snapshot(sid)


def test_full_lifecycle_generation_sees_history_and_preserves_profiles(db):
    repo,_,sid=db;start(repo,sid)
    edit(repo,sid,'new_npc',**command(repo,sid,'defer',character={'life_status':'alive'}))
    before=evolve(repo,sid); actor=before['world_state']['characters']['new_npc']
    assert actor['appearance']['items']['hair']['text']=='Короткие волосы'
    assert actor['personality']['items']['resolve']['text']=='Решительная и самостоятельная'
    calls=[]
    def provider(**kwargs):calls.append(kwargs);yield '{"value":"Лада открыла мастерскую после решительного разговора."}'
    with patch('llm.chat_stream',side_effect=provider):
        response=generate(repo,sid,'new_npc',field='Биография',revision=repo.get_save(sid)['revision'],review_revision=1,config=dict(CONFIG,provider='compatible'),api_key=None)
    payload=json.loads(calls[0]['messages'][1]['content']); ctx=payload['context']
    assert 'Я справлюсь сама' in json.dumps(ctx,ensure_ascii=False)
    assert ctx['current_card']['fields']['Внешность']=='Короткие волосы'
    assert ctx['current_card']['fields']['Характер']=='Решительная и самостоятельная'
    assert ctx['character']['goals']==['Открыть мастерскую']
    assert ctx['roles'][0]['label']=='Мастер' and ctx['residences']
    assert ctx['relationships'][0]['context']=='Познакомились.'
    assert len(ctx['witnessed_narrative'])>=2 and ctx['facts'] and ctx['events']
    assert repo.get_snapshot(sid)==before
    fields=dict.fromkeys(CARD_FIELDS,'Старое описание');fields['Биография']=response['value']
    with pytest.raises(ValueError,match='Канонический профиль отличается'):
        edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,operation='confirm-late',character={'life_status':'alive'}))
    assert repo.get_snapshot(sid)==before
    acknowledgements={k:v['revision'] for k,v in profile_state(before,'new_npc').items() if k in CARD_FIELDS}
    cmd=command(repo,sid,'confirm',fields,operation='confirm-late',character={'life_status':'alive'},profile_acknowledgements=acknowledgements)
    edit(repo,sid,'new_npc',**cmd);after=repo.get_snapshot(sid)
    edit(repo,sid,'new_npc',**cmd);assert repo.get_snapshot(sid)==after
    for field in ('personality','appearance','life_fact_id','goals','obligations'):
        assert after['world_state']['characters']['new_npc'][field]==actor[field]
    for section in ('relationships','objective_relations','roles','residences','knowledge'):
        assert after['world_state'][section]==before['world_state'][section]
    from storage import Storage
    repo=Storage(repo.path);assert repo.get_snapshot(sid)==after
    jid=repo.begin_job(sid,'Говорим дальше.','turn',CONFIG);run(repo,jid,raw_for(after));assert repo.get_job(jid)['status']=='saved'


def test_context_never_inherits_other_actor_secrets(db):
    from backend.runtime_v3.models import Fact, Knowledge, Motivation, PersonalityItem
    repo,_,sid=db;start(repo,sid);snapshot=evolve(repo,sid);s=snapshot['world_state'];observer=s['camera']['controlled_actor_id']
    s['facts']['secret']=Fact(id='secret',text='HIDDEN_PASSWORD',visibility='secret',character_ids=['new_npc']).model_dump()
    s['knowledge']['new_npc:secret']=Knowledge(actor_id='new_npc',fact_id='secret',status='known').model_dump()
    s['characters']['new_npc']['goals'].append(Motivation(id='secret_goal',text='HIDDEN_GOAL',source_event_id='private_event').model_dump())
    s['characters']['new_npc']['personality']['items']['hidden']=PersonalityItem(field='fears',text='HIDDEN_FEAR',source_ids=['private_event'],witnesses=['new_npc'],fact_ids=['secret']).model_dump()
    with repo.connect() as conn:history,_=read_history(conn,snapshot['history_head'])
    history['events'].append(dict(id='private_event',text='HIDDEN_EVENT',participants=['new_npc'],witnesses=['new_npc'],fact_ids=['secret']))
    history['events'].append(dict(id='not_learned',text='HIDDEN_UNLEARNED_EVENT',participants=['new_npc'],witnesses=[observer],fact_ids=['secret']))
    s['characters']['new_npc']['goals'].append(Motivation(id='unlearned_goal',text='HIDDEN_UNLEARNED_GOAL',source_event_id='not_learned').model_dump())
    turns=repo.list_turns(sid)+[dict(sequence=40,kind='background',pov_actor_id='new_npc',audience_json='["new_npc"]',assistant_text='HIDDEN_PROSE')]
    ctx=context(snapshot,'new_npc',snapshot['pending_reviews']['new_npc'],turns,history)
    assert 'HIDDEN_' not in json.dumps(ctx)
    assert ctx['observer_id']==observer and ctx['facts']


def test_review_birth_date_provenance_and_atomic_invalid_stage(db):
    repo,_,sid=db
    from backend.runtime_v3.models import Calendar
    initial=repo.get_snapshot(sid);initial['world_state']['meta']['calendar']=Calendar(start_date='2026-10-31',start_minute=0,start_weekday=5).model_dump()
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(initial),sid))
    start(repo,sid);fields=dict.fromkeys(CARD_FIELDS,'Описание')
    before=repo.get_snapshot(sid)
    with pytest.raises(ValueError):
        edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,character={'birth_date':'2026-01-01','developmental_stage':'adult'}))
    assert repo.get_snapshot(sid)==before
    edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,character={'birth_date':'1999-04-12','developmental_stage':'adult','biological_sex':'female'}))
    after=repo.get_snapshot(sid);actor=after['world_state']['characters']['new_npc']
    assert actor['birth_date_provenance']['source']=='npc_review'
    with repo.connect() as conn:history,_=read_history(conn,after['history_head'])
    change=next(c for c in history['state_changes'] if c.get('kind')=='birth_date_established')
    assert change['before']['birth_date'] is None and change['after']['birth_date']=='1999-04-12'
    attribute_change=next(c for c in history['state_changes'] if c.get('kind')=='npc_review_attributes')
    assert 'new_npc' in attribute_change['names']


def test_stale_generation_result_is_not_returned(db):
    repo,_,sid=db;start(repo,sid)
    revision=repo.get_save(sid)['revision']
    def provider(**kwargs):
        edit(repo,sid,'new_npc',**command(repo,sid,'save'))
        yield '{"value":"Устаревшее предложение"}'
    with patch('llm.chat_stream',side_effect=provider),pytest.raises(ValueError,match='Мир изменился'):
        generate(repo,sid,'new_npc',field='Биография',revision=revision,review_revision=0,config=dict(CONFIG,provider='compatible'),api_key=None)
    assert repo.get_snapshot(sid)['pending_reviews']['new_npc']['proposals']=={}


def test_profile_acknowledgement_cannot_cover_a_later_revision(db):
    repo,_,sid=db;start(repo,sid);snapshot=evolve(repo,sid)
    acknowledgements={k:v['revision'] for k,v in profile_state(snapshot,'new_npc').items() if k in CARD_FIELDS}
    fields=dict.fromkeys(CARD_FIELDS,'Черновик')
    edit(repo,sid,'new_npc',**command(repo,sid,'save',fields,profile_acknowledgements=acknowledgements))
    raw=raw_for(snapshot);observer=snapshot['world_state']['camera']['controlled_actor_id']
    raw.update(facts=[dict(id='hair_change',text='Волосы стали синими.',character_ids=['new_npc'],evidence='Покрасила волосы.')],
        events=[dict(id='hair_change_event',text='Покрасила волосы.',medium='observation',participants=['new_npc'],witnesses=[observer],fact_ids=['hair_change'],evidence='Покрасила волосы.')],
        knowledge_gained=[dict(actor_id=observer,fact_id='hair_change',source_event_id='hair_change_event',evidence='Увидел.')],
        appearance_deltas=[dict(actor_id='new_npc',item_id='hair',operation='update',category='presentation',kind='hairstyle',text='Синие короткие волосы',expected_revision=1,source_event_id='hair_change_event',fact_id='hair_change',assertion='established_visual_outcome',transition='voluntary',evidence='Покрасила волосы.')])
    jid=repo.begin_job(sid,'Смотрю.','turn',CONFIG);run(repo,jid,raw);assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    before=repo.get_snapshot(sid)
    with pytest.raises(ValueError,match='Внешность'):
        edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,operation='stale-profile-ack',profile_acknowledgements=acknowledgements))
    assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('attributes',[
    {'biological_sex':'male'}, {'biological_sex':None}, {'capabilities':{'can_speak':False}},
    {'life_status':'missing'}, {'life_status':'dead'}, {'developmental_stage':'adult'},
    {'reproductive_capability':'neither'}, {'emotion':'Уверена','situation':'Ждёт','physical_state':'Отдохнула'},
])
def test_review_canonical_edits_keep_dependencies_and_history(db, attributes):
    repo,_,sid=db;start(repo,sid)
    for _ in range(2):
        jid=repo.begin_job(sid,'Продолжаем.','turn',CONFIG);run(repo,jid,raw_for(repo.get_snapshot(sid)))
        assert repo.get_job(jid)['status']=='saved'
    before=repo.get_snapshot(sid);fields=dict.fromkeys(CARD_FIELDS,'Описание')
    cmd=command(repo,sid,'confirm',fields,character=attributes)
    edit(repo,sid,'new_npc',**cmd);after=repo.get_snapshot(sid)
    actor=after['world_state']['characters']['new_npc']
    for field,value in attributes.items():
        if field=='capabilities':assert actor[field]['can_speak'] is False
        else:assert actor[field]==value
    for section in ('knowledge','relationships','roles','residences'):
        assert before['world_state'][section]==after['world_state'][section]
    if attributes.get('life_status')=='dead':
        assert 'new_npc' not in after['world_state']['camera']['present_character_ids']
        assert all(m['status']!='active' for m in actor['obligations'])
    else:assert actor['obligations']==before['world_state']['characters']['new_npc']['obligations']
    with repo.connect() as conn:history,_=read_history(conn,after['history_head'])
    assert history['state_changes'][-1]['kind']=='npc_card_review'
    edit(repo,sid,'new_npc',**cmd);assert repo.get_snapshot(sid)==after


def test_generation_context_stays_bounded_and_handles_changed_pov(db):
    repo,_,sid=db;start(repo,sid);snapshot=evolve(repo,sid);s=snapshot['world_state']
    with repo.connect() as conn:history,_=read_history(conn,snapshot['history_head'])
    turns=repo.list_turns(sid);actor=s['camera']['controlled_actor_id']
    for i in range(100):
        history['events'].append(dict(id=f'noise{i}',participants=['new_npc'],witnesses=[actor],text='x'*10000,fact_ids=[],turn_id=i))
    result=context(snapshot,'new_npc',snapshot['pending_reviews']['new_npc'],turns,history)
    assert len(result['events'])==16 and all(len(e['text'])<=1600 for e in result['events'])
    s['camera']['pov_actor_id']=next(cid for cid in s['characters'] if cid not in ('new_npc',actor))
    result=context(snapshot,'new_npc',snapshot['pending_reviews']['new_npc'],turns,history)
    assert result['observer_id']!=actor and result['facts']==[]
    assert 'Я справлюсь сама' not in json.dumps(result,ensure_ascii=False)


@pytest.mark.parametrize('character',[{}, {'biological_sex':'unknown'}])
def test_pre_upgrade_receipt_remains_idempotent(db, character):
    repo,_,sid=db;start(repo,sid);cmd=command(repo,sid,'save',character=character)
    edit(repo,sid,'new_npc',**cmd)
    before=repo.get_snapshot(sid)
    before['pending_reviews']['new_npc']['receipt']['request'].pop('profile_acknowledgements')
    before['pending_reviews']['new_npc']['receipt']['request']['character']=character
    before['pending_reviews']['new_npc'].pop('profile_acknowledgements')
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    edit(repo,sid,'new_npc',**cmd)
    assert repo.get_snapshot(sid)==before
