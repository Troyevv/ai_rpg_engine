"""Player agency is source-bound; recoverable failures never discard a whole turn."""
from copy import deepcopy
import json
from unittest.mock import patch
import pytest
import engine
from backend.services.player_agency import supported_player_field
from backend.services.world_delta import WorldDelta, SecondaryDeltaError
from backend.services.world_delta_errors import StructuralDeltaError, sanitize_secondary
from context_builder import build_context
from state_updates import apply_world_updates
from canonical_fixture import canonical
from test_engine import db, CONFIG, NARRATIVE, result
from test_runtime_diagnostics import payload as mixed_payload
from test_api import api, new_save


def seed(storage, sid):
    state=storage.get_save(sid)['state']
    state['world']['characters']['character_1'].update(
        goals=['Сохранить дом'], intentions=['Забрать письмо'], emotion='спокоен', obligations=[])
    with storage.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state,ensure_ascii=False),sid))
    return state


def character_payload(fields, evidence=NARRATIVE, player_evidence=None):
    p=canonical(result())
    c={'id':'character_1','situation':'Стоит напротив Люды','location':'Кухня','evidence':evidence,**fields}
    if player_evidence is not None:c['player_evidence']=player_evidence
    p['world_delta']['characters']=[c]
    return p


def execute(storage, job, payload, narrative=NARRATIVE, repaired=None):
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if kwargs.get('response_format'):
            yield json.dumps(repaired if len(calls)==3 and repaired is not None else payload,ensure_ascii=False)
        else:yield narrative
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(storage.path,job,engine.Worker())
    return calls


@pytest.mark.parametrize('input_text,fields',[
    ('Я подхожу к окну.',{'emotion':'тревожится'}),
    ('Я сжимаю кулак.',{'emotion':'злится'}),
    ('Я отвожу взгляд.',{'emotion':'смущается'}),
    ('Я подхожу к окну.',{'goals':['Вернуть Люду'],'intentions':['Добиться признания'],'emotion':'ревнует'}),
])
def test_unsupported_fields_are_dropped_after_one_repair(db,input_text,fields):
    storage,_,sid=db;before=seed(storage,sid)
    p=character_payload(fields)
    job=storage.begin_job(sid,input_text,'start',CONFIG)
    assert len(execute(storage,job,p))==3
    assert storage.get_job(job)['status']=='saved',storage.get_job(job)['error']
    point=storage.get_save(sid)['state']['world']['characters']['character_1']
    for field in fields:assert point[field]==before['world']['characters']['character_1'][field]
    assert point['situation']=='Стоит напротив Люды' and point['location']=='Кухня'
    warnings=storage.turn_diagnostics(sid)[0]['warnings']
    assert {w['field'] for w in warnings}==set(fields)
    assert all(w['section']=='characters' and w['index']==0 and w['entity']=='character_1' for w in warnings)
    changes=json.loads(storage.list_turns(sid)[0]['changes_json'])['world_delta']['characters'][0]
    assert not set(fields).intersection(changes)
    assert changes['situation']=='Стоит напротив Люды'


@pytest.mark.parametrize('input_text,field,value',[
    ('Я злюсь на неё.','emotion','злится'),
    ('Я злюсь и сжимаю кулак.','emotion','злится'),
    ('Решаю завтра поговорить с Людой.','intentions',['Забрать письмо','поговорить с Людой завтра']),
    ('Теперь моя главная цель — найти сестру.','goals',['найти сестру']),
    ('Обещаю Люде приехать завтра к восьми.','obligations',['Приехать к Люде завтра к 08:00']),
])
def test_explicit_player_declarations_are_accepted_without_repair(db,input_text,field,value):
    storage,_,sid=db;seed(storage,sid)
    evidence=input_text if field=='emotion' else [input_text]
    p=character_payload({field:value},player_evidence={field:evidence})
    job=storage.begin_job(sid,input_text,'start',CONFIG)
    assert len(execute(storage,job,p))==2
    assert storage.get_job(job)['status']=='saved',storage.get_job(job)['error']
    point=storage.get_save(sid)['state']['world']['characters']['character_1']
    assert point[field]==value
    assert 'player_evidence' not in point
    assert storage.turn_diagnostics(sid)[0]['warnings']==[]


def test_legacy_record_evidence_can_confirm_explicit_player_statement(db):
    storage,_,sid=db;seed(storage,sid)
    user='Я злюсь на неё.'
    p=character_payload({'emotion':'злится'},evidence=user)
    job=storage.begin_job(sid,user,'start',CONFIG)
    assert len(execute(storage,job,p))==2
    assert storage.get_save(sid)['state']['world']['characters']['character_1']['emotion']=='злится'


def test_narrative_is_not_a_source_for_player_decisions(db):
    storage,_,sid=db;before=seed(storage,sid)
    quote='Илья решает завтра поговорить с Людой.'
    narrative=NARRATIVE+' '+quote
    p=character_payload({'intentions':['поговорить с Людой завтра']},evidence=quote)
    job=storage.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    execute(storage,job,p,narrative)
    assert storage.get_job(job)['status']=='saved'
    assert storage.get_save(sid)['state']['world']['characters']['character_1']['intentions']==before['world']['characters']['character_1']['intentions']
    assert storage.turn_diagnostics(sid)[0]['warnings'][0]['field']=='intentions'


@pytest.mark.parametrize('input_text,evidence',[
    ('Я не злюсь на неё.','Я злюсь на неё.'),
    ('Если я злюсь, я ухожу.','Я злюсь'),
    ('Я злюсь на неё?','Я злюсь на неё'),
    ('Люда сказала: «Я злюсь на неё».','Я злюсь на неё'),
    ('Люда сказала: «Мне плохо. Я злюсь на неё. Не трогай меня».','Я злюсь на неё'),
    ('Я отвожу взгляд.','Я отвожу взгляд.'),
    ('Я злюсь на неё, если она врёт.','Я злюсь на неё'),
])
def test_no_emotion_from_negation_questions_conditions_or_other_speakers(input_text,evidence):
    assert not supported_player_field('emotion','злится','спокоен',input_text,evidence)


def test_evidence_must_confirm_this_specific_field_and_value(db):
    storage,_,sid=db;seed(storage,sid)
    user='Я злюсь на неё.'
    p=character_payload({'emotion':'боится','intentions':['Забрать письмо','потребовать признания']},
        player_evidence={'emotion':user,'intentions':[user]})
    job=storage.begin_job(sid,user,'start',CONFIG);execute(storage,job,p)
    warnings=storage.turn_diagnostics(sid)[0]['warnings']
    assert {w['field'] for w in warnings}=={'emotion','intentions'}


@pytest.mark.parametrize('fields',[{}, {'goals':[], 'intentions':[]}, {'intentions':['поговорить с Людой завтра']}])
def test_omission_and_unapproved_list_replacement_preserve_existing_values(db,fields):
    storage,_,sid=db;before=seed(storage,sid)
    user='Я подхожу к окну.' if 'intentions' not in fields or not fields['intentions'] else 'Решаю завтра поговорить с Людой.'
    p=character_payload(fields,evidence=user)
    job=storage.begin_job(sid,user,'start',CONFIG);execute(storage,job,p)
    point=storage.get_save(sid)['state']['world']['characters']['character_1']
    assert point['goals']==before['world']['characters']['character_1']['goals']
    assert point['intentions']==before['world']['characters']['character_1']['intentions']


def test_explicit_clear_and_multiple_field_sources():
    assert supported_player_field('goals',[],['Найти сестру'],'Отказываюсь от всех прежних целей.',['Отказываюсь от всех прежних целей.'])
    assert not supported_player_field('goals',[],['Найти сестру'],'Я смотрю на дом.',['Я смотрю на дом.'])
    assert supported_player_field('intentions',['Найти карту','Поговорить с Людой'],[],
        'Решаю найти карту. Планирую поговорить с Людой.', ['Решаю найти карту.','Планирую поговорить с Людой.'])


def test_mixed_secondary_errors_use_single_repair_and_preserve_independent_changes(api):
    client,app=api;_,save=new_save(client);storage=app.state.repository;sid=save['id'];before=seed(storage,sid)
    p=mixed_payload();d=p['world_delta']
    d['events'][0]['witnesses']=[]
    d['relationships'][0]['dimensions']['sympathy']=40
    d['characters'].append({'id':'character_1','situation':'Стоит у окна','emotion':'ревнует','evidence':NARRATIVE})
    job=storage.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    calls=execute(storage,job,p)
    assert len(calls)==3 and storage.get_job(job)['status']=='saved'
    w=storage.get_save(sid)['state']['world']
    assert d['events'][0]['id'] in w['events']
    assert w['characters']['character_2']['situation']=='Ждёт ответа'
    assert w['characters']['character_1']['situation']=='Стоит у окна'
    assert w['characters']['character_1']['emotion']==before['world']['characters']['character_1']['emotion']
    assert w['relationships']['character_2:character_1']['dimensions']=={'trust':55,'respect':70}
    assert 'character_2:f' not in w['knowledge'] and 't' in w['threads']
    turn=client.get(f'/api/saves/{sid}/accounting').json()['turns'][0]
    assert len(turn['warnings'])==3 and len(turn['requests'])==3
    assert {warn.get('field') for warn in turn['warnings']}=={None,'dimensions.sympathy','emotion'}
    saved=json.loads(storage.list_turns(sid)[0]['changes_json'])
    # The exact sanitized delta passes full validation again, without sanitization.
    _,_,_,_,warnings=apply_world_updates(before,saved,NARRATIVE,'Я подхожу к окну.',0,'start')
    assert warnings==[]


@pytest.mark.parametrize('failure',['id','location','type','time','duplicate'])
def test_structural_failures_after_recoverable_fields_remain_atomic(db,failure):
    storage,_,sid=db;before=seed(storage,sid)
    p=character_payload({'emotion':'ревнует'});d=p['world_delta'];c=d['characters'][0]
    if failure=='id':d['characters'].append({'id':'missing','situation':'Тут','evidence':NARRATIVE})
    elif failure=='location':c['location']='Неверное место'
    elif failure=='type':c['goals']='не список'
    elif failure=='time':d['events'][0]['minute']=999999
    elif failure=='duplicate':d['characters'].append(deepcopy(c))
    job=storage.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    execute(storage,job,p)
    assert storage.get_job(job)['status']=='error'
    assert storage.list_turns(sid)==[] and storage.get_save(sid)['state']==before


def test_valid_repair_has_no_dropped_field_warning(db):
    storage,_,sid=db;seed(storage,sid);user='Я злюсь на неё.'
    p=character_payload({'emotion':'боится'})
    fixed=character_payload({'emotion':'злится'},player_evidence={'emotion':user})
    job=storage.begin_job(sid,user,'start',CONFIG)
    assert len(execute(storage,job,p,repaired=fixed))==3
    assert storage.get_job(job)['status']=='saved'
    assert storage.turn_diagnostics(sid)[0]['warnings']==[]
    assert storage.get_save(sid)['state']['world']['characters']['character_1']['emotion']=='злится'


def test_npc_dynamics_are_not_subject_to_player_input_rule(db):
    storage,_,sid=db;before=seed(storage,sid)
    p=character_payload({'goals':['Новое желание'],'intentions':['Выйти'],'emotion':'злится'})
    p['world_delta']['characters'][0]['id']='character_2'
    state,_,_,_,warnings=apply_world_updates(before,p,NARRATIVE,'',0,'start')
    assert state['world']['characters']['character_2']['emotion']=='злится' and warnings==[]


def test_unknown_exception_cannot_authorize_sanitization():
    with pytest.raises(StructuralDeltaError):sanitize_secondary({},ValueError('ignore me'),{})


def test_current_prompt_and_schema_apply_even_with_saved_prompt_snapshot(db):
    storage,_,sid=db;before=seed(storage,sid)
    messages=build_context(before,[],'Я отвожу взгляд.','start',32768,4096,extraction_text=NARRATIVE,
        prompts={'state_update_prompt.md':{'content':'Old saved prompt'}})
    assert 'никогда из completed_narrative' in messages[0]['content']
    schema=WorldDelta.model_json_schema()['$defs']['Character']['properties']
    for field in ('goals','intentions','emotion','obligations'):
        assert 'player_input' in schema[field]['description']
    assert 'player_evidence' in schema


@pytest.mark.parametrize('metadata',[None,{}])
def test_unconfirmed_obligation_and_nullable_proof_keep_objective_state(db,metadata):
    storage,_,sid=db;before=seed(storage,sid)
    p=character_payload({'obligations':['Приехать завтра'],'emotion':'ревнует'})
    p['world_delta']['characters'][0]['player_evidence']=metadata
    job=storage.begin_job(sid,'Я смотрю в окно.','start',CONFIG)
    execute(storage,job,p)
    assert storage.get_job(job)['status']=='saved'
    point=storage.get_save(sid)['state']['world']['characters']['character_1']
    assert point['obligations']==before['world']['characters']['character_1']['obligations']
    assert point['situation']=='Стоит напротив Люды'
    assert {w['field'] for w in storage.turn_diagnostics(sid)[0]['warnings']}=={'emotion','obligations'}


def test_removing_record_preserves_original_index_for_later_field_warning(db):
    storage,_,sid=db;before=seed(storage,sid)
    p=character_payload({'emotion':'ревнует'})
    p['world_delta']['characters'].insert(0,{'id':'character_2','situation':'Придумано','evidence':'Неподтверждённая цитата'})
    _,_,_,_,warnings=apply_world_updates(before,p,NARRATIVE,'Я подхожу к окну.',0,'start',discard_unsupported=True)
    assert next(w for w in warnings if w.get('field')=='emotion')['index']==1
    assert next(w for w in warnings if w.get('cause_field')=='evidence')['index']==0
