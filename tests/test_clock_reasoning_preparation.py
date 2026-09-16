import json
import hashlib
from pathlib import Path
from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import patch, MagicMock
import pytest
from backend.services.timeline import advance, current_time, label, parse_time
from backend.services.answer_stream import AnswerStream
from backend.services.world import normalize, knowledge_for
from backend.repositories.preparation import Repository
from backend.services.preparation import Preparation, Handle
from world_parser import parse_summary
from test_worlds import summary
from test_engine import db, CONFIG, run, result
from llm import chat_stream


def test_clock_rollover_and_explicit_zero():
    before={'world_clock':{'minute':7*1440-2}}
    after={};scene={'time':'00:01'}
    advance(before,after,scene,elapsed=3)
    assert scene['time']=='День 8 (Пн) 00:01'
    advance(after,{}, {'time':scene['time']},elapsed=0,minimum=1)
    assert parse_time(label(7*1440+1))==7*1440+1
    with pytest.raises(ValueError):advance(before,{}, {'time':'День 6 19:00'},elapsed=3)


def test_repeated_turns_advance_and_regeneration_does_not_double_time(db):
    repo,_,sid=db
    jid=repo.begin_job(sid,'','start',CONFIG);run(repo,jid)
    start=current_time(repo.get_save(sid)['state'])
    for i in range(3):
        change=result();change['scene']['time']=label(start+i)
        jid=repo.begin_job(sid,'Говорить','turn',CONFIG);run(repo,jid,change)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        assert current_time(repo.get_save(sid)['state'])==start+i+1
    jid=repo.begin_job(sid,'','regenerate',CONFIG);run(repo,jid,change)
    assert repo.get_job(jid)['status']=='saved'
    assert current_time(repo.get_save(sid)['state'])==start+3
    repo.rollback_last(sid)
    assert current_time(repo.get_save(sid)['state'])==start+2


@pytest.mark.parametrize('size',[1,2,7,1000])
def test_reasoning_tags_never_stream_even_across_chunks(size):
    value='<think>Приватные рассуждения <analysis>секрет</analysis></think>Ответ **готов** <thinking>ещё секрет</thinking>.'
    stream=AnswerStream()
    output=''.join(stream.feed(value[i:i+size]) for i in range(0,len(value),size))+stream.feed('',final=True)
    assert output=='Ответ **готов** .'


@pytest.mark.parametrize('provider',['local','deepseek'])
def test_separate_reasoning_and_inline_reasoning_filtered_before_persistence(provider):
    client=MagicMock();stream=MagicMock()
    stream.__iter__.return_value=iter([
        NS(choices=[NS(delta=NS(content=None,reasoning_content='секрет'),finish_reason=None)]),
        NS(choices=[NS(delta=NS(content='<thi'),finish_reason=None)]),
        NS(choices=[NS(delta=NS(content='nk>секрет</think>Готовый текст'),finish_reason='stop')]),
    ])
    client.chat.completions.create.return_value=stream
    with patch('llm.OpenAI',return_value=client):
        assert ''.join(chat_stream('deepseek-flash',[],provider=provider,api_key='test',thinking='high',require_complete=True))=='Готовый текст'


def test_unclosed_thinking_does_not_escape():
    stream=AnswerStream()
    assert stream.feed('<think>Незавершённое рассуждение')+stream.feed('',final=True)==''
    stream=AnswerStream()
    assert stream.feed('x < y и **markdown**')+stream.feed('',final=True)=='x < y и **markdown**'


def small_world():
    text=summary();start=text.index('👤 Персонаж 2');end=text.index('# ЧТО ЗНАЮТ')
    text=text[:start]+text[end:]
    text=text.replace('Понедельник, 18:20. Кухня. Все собрались.', 'Время: Пятница 09:00\nМесто: Кухня\nРядом: Персонаж 0')
    text=text.replace('Персонаж 1 планирует переезд.', '- Планирует переезд | Знают: Персонаж 1 | Подозревают: никто | Основание: собственный план')
    text=text.replace('Все живут вместе.', '- Все живут вместе | Знают: все | Подозревают: никто | Основание: проживание')
    return text


def test_generated_metadata_imports_clock_cast_and_private_knowledge():
    state=normalize(parse_summary(small_world()))
    assert len(state['characters'])==2
    assert label(current_time(state))=='День 5 (Пт) 09:00'
    assert state['world']['scenes'][state['camera']['scene_id']]['participants']==['character_1']
    assert len(knowledge_for(state['world'],'character_1'))==1
    assert len(knowledge_for(state['world'],'character_2'))==2
    assert any(f['secret'] for f in state['world']['facts'].values())
    assert normalize(state)==state


def test_generated_summary_can_start_game(tmp_path):
    from test_engine import run
    repo=Repository(tmp_path/'game.db');w=repo.create_workspace('План')
    cfg={**CONFIG,'provider':'local'}
    with repo.connect() as conn:conn.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('Два персонажа',w['id']))
    jid=repo.begin_preparation(w['id'],'summary','',cfg,0)
    with patch('backend.services.preparation.find_loaded_model',return_value={'config':{}}),patch('backend.services.preparation.chat_stream',return_value=iter([small_world()])):
        Preparation(repo).run(jid,cfg,None,Handle())
    assert repo.preparation_job(jid)['status']=='saved'
    wid=repo.save_world('Мир',repo.workspace(w['id'])['summary']);sid=repo.create_save(wid,'Игра')
    jid=repo.begin_job(sid,'','start',CONFIG)
    change=result();change['scene']['time']='Пятница 09:00';run(repo,jid,change)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']


@pytest.mark.parametrize("hash_list",[False,True])
def test_default_prompt_upgrade_preserves_custom_and_restore(tmp_path,monkeypatch,hash_list):
    import backend.repositories.documents as documents
    repo=Repository(tmp_path/'game.db')
    root=tmp_path/'prompts';root.mkdir()
    for name in documents.PROMPT_NAMES:(root/name).write_text('Новая версия '+name)
    names=['idea_prompt.md','summary_prompt.md']
    old='Старый встроенный промпт'
    (root/'default_updates.json').write_text(json.dumps({n:([hashlib.sha256(b'older').hexdigest(),hashlib.sha256(old.encode()).hexdigest()] if hash_list else hashlib.sha256(old.encode()).hexdigest()) for n in names}))
    with repo.connect() as conn:
        conn.execute('DELETE FROM prompt_upgrades')
        oldid=repo._record_document(conn,'prompt',names[0],old)
        repo._record_document(conn,'prompt',names[1],'Мой промпт')
    monkeypatch.setattr(documents,'ROOT',root)
    repo.init_documents()
    assert repo.prompt_snapshot()[names[0]]['content']=='Новая версия '+names[0]
    assert repo.prompt_snapshot()[names[1]]['content']=='Мой промпт'
    head=repo.prompt_snapshot()[names[0]]['id']
    repo.change_document('prompt',names[0],'',head,source_id=oldid)
    repo.init_documents()
    assert repo.prompt_snapshot()[names[0]]['content']==old
