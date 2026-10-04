"""Source-bound agency through v3 extraction and committed turn diagnostics."""
import json
import pytest
from test_engine import db,CONFIG,NARRATIVE
from runtime_v3_fixture import execute
from backend.services.player_agency import supported_player_field
from backend.runtime_v3.models import identity, assert_world_state_v3_invariants
from backend.runtime_v3.lifecycle import active_texts


def seed(repo,sid):
    state=repo.get_snapshot(sid)
    state['world_state']['characters']['character_1'].update(goals=['Сохранить дом'],intentions=['Забрать письмо'],emotion='спокоен',obligations=[])
    state['world_state']=assert_world_state_v3_invariants(state['world_state'])
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state),sid))
    return state


def character_payload(fields,evidence=NARRATIVE,player_evidence=None):
    c=dict(id='character_1',situation='Стоит напротив Люды',evidence=evidence);c.update(fields)
    if player_evidence is not None:c['player_evidence']=player_evidence
    return dict(final_scene=dict(location_id=identity('location','кухня'),present_character_ids=['character_1','character_2']),character_changes=[c])


@pytest.mark.parametrize('text,fields',[
    ('Я подхожу к окну.',{'emotion':'тревожится'}),('Я сжимаю кулак.',{'emotion':'злится'}),
    ('Я отвожу взгляд.',{'emotion':'смущается'}),('Я подхожу к окну.',{'goals':['Вернуть Люду'],'intentions':['Добиться признания'],'emotion':'ревнует'}),
    ('Я смотрю в окно.',{'obligations':['Приехать завтра'],'emotion':'ревнует'})])
def test_unsupported_fields_drop_individually_and_commit(db,text,fields):
    repo,_,sid=db;before=seed(repo,sid);p=character_payload(fields)
    job=repo.begin_job(sid,text,'start',CONFIG)
    assert len(execute(repo,job,p,NARRATIVE))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    actor=repo.get_snapshot(sid)['world_state']['characters']['character_1']
    for field in fields:assert actor[field]==before['world_state']['characters']['character_1'][field]
    assert actor['situation']=='Стоит напротив Люды'
    warnings=repo.turn_diagnostics(sid)[0]['warnings']
    assert {w['field'] for w in warnings}==set(fields)
    assert all(w['section']=='characters' and w['index']==0 and w['entity']=='character_1' for w in warnings)


@pytest.mark.parametrize('text,field,value',[
    ('Я злюсь на неё.','emotion','злится'),('Я злюсь и сжимаю кулак.','emotion','злится'),
    ('Решаю завтра поговорить с Людой.','intentions',['Забрать письмо','поговорить с Людой завтра']),
    ('Теперь моя главная цель — найти сестру.','goals',['найти сестру']),
    ('Обещаю Люде приехать завтра к восьми.','obligations',['Приехать к Люде завтра к 08:00'])])
def test_explicit_player_declarations(db,text,field,value):
    repo,_,sid=db;seed(repo,sid)
    p=character_payload({field:value},player_evidence={field:text if field=='emotion' else [text]})
    job=repo.begin_job(sid,text,'start',CONFIG)
    assert len(execute(repo,job,p,NARRATIVE))==2
    actual=repo.get_snapshot(sid)['world_state']['characters']['character_1'][field]
    assert (actual if field=='emotion' else active_texts(actual))==value
    assert not repo.turn_diagnostics(sid)[0]['warnings']


def test_plain_evidence_can_confirm_explicit_player_source(db):
    repo,_,sid=db;seed(repo,sid);text='Я злюсь на неё.'
    job=repo.begin_job(sid,text,'start',CONFIG)
    execute(repo,job,character_payload({'emotion':'злится'},evidence=text),NARRATIVE)
    assert repo.get_snapshot(sid)['world_state']['characters']['character_1']['emotion']=='злится'


@pytest.mark.parametrize('text,evidence',[
    ('Я не злюсь на неё.','Я злюсь на неё.'),('Если я злюсь, я ухожу.','Я злюсь'),
    ('Я злюсь на неё?','Я злюсь на неё'),('Люда сказала: «Я злюсь на неё».','Я злюсь на неё'),
    ('Люда сказала: «Мне плохо. Я злюсь на неё. Не трогай меня».','Я злюсь на неё'),
    ('Я отвожу взгляд.','Я отвожу взгляд.'),('Я злюсь на неё, если она врёт.','Я злюсь на неё')])
def test_no_inference_from_negations_questions_gestures_or_other_speakers(text,evidence):
    assert not supported_player_field('emotion','злится','спокоен',text,evidence)


def test_narrative_cannot_become_player_source(db):
    repo,_,sid=db;before=seed(repo,sid);quote='Илья решает завтра поговорить с Людой.'
    p=character_payload({'intentions':['поговорить с Людой завтра']},evidence=quote)
    job=repo.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    execute(repo,job,p,NARRATIVE+' '+quote)
    assert repo.get_job(job)['status']=='saved'
    assert repo.get_snapshot(sid)['world_state']['characters']['character_1']['intentions']==before['world_state']['characters']['character_1']['intentions']


@pytest.mark.parametrize('fields',[{}, {'goals':[],'intentions':[]}, {'intentions':['поговорить с Людой завтра']}])
def test_omission_and_unapproved_replacement_are_no_change(db,fields):
    repo,_,sid=db;before=seed(repo,sid);text='Я подхожу к окну.'
    job=repo.begin_job(sid,text,'start',CONFIG);execute(repo,job,character_payload(fields),NARRATIVE)
    current=repo.get_snapshot(sid)['world_state']['characters']['character_1']
    for key in ('goals','intentions'):assert current[key]==before['world_state']['characters']['character_1'][key]


def test_explicit_clear_and_multiple_field_sources():
    assert supported_player_field('goals',[],['Найти сестру'],'Отказываюсь от всех прежних целей.',['Отказываюсь от всех прежних целей.'])
    assert not supported_player_field('goals',[],['Найти сестру'],'Я смотрю на дом.',['Я смотрю на дом.'])
    assert supported_player_field('intentions',['Найти карту','Поговорить с Людой'],[],
        'Решаю найти карту. Планирую поговорить с Людой.', ['Решаю найти карту.','Планирую поговорить с Людой.'])


def test_quote_must_support_specific_value(db):
    repo,_,sid=db;seed(repo,sid);text='Я злюсь на неё.'
    p=character_payload({'emotion':'боится'},player_evidence={'emotion':text})
    job=repo.begin_job(sid,text,'start',CONFIG);execute(repo,job,p,NARRATIVE)
    assert repo.get_snapshot(sid)['world_state']['characters']['character_1']['emotion']=='спокоен'
