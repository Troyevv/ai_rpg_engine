from runtime_v3_fixture import wire
from canonical_fixture import canonical, fixture_sequence
import json
from threading import Event
from unittest.mock import patch
import pytest
import engine
from backend.services.memory import compact
from backend.services.timeline import current_time,label
from test_engine import db,CONFIG,NARRATIVE,result
from test_runtime import generate
from llm import OutputLimitReached


def setup_job(repo,sid):
    generate(repo,sid,'start')
    for _ in range(3):generate(repo,sid)
    jid=repo.begin_job(sid,'Продолжить','turn',CONFIG)
    return repo.get_job(jid),repo.get_save(sid)['state'],repo.list_turns(sid)


@pytest.mark.parametrize('invalid',['', 'Я'*8001, 'length'])
def test_memory_repairs_before_advancing_cursor(db,invalid):
    repo,_,sid=db;job,state,history=setup_job(repo,sid);calls=[]
    def summarize(messages):
        calls.append(messages)
        if len(calls)==1:
            if invalid=='length':raise OutputLimitReached('length')
            yield invalid
        else:yield 'Собеседники встретились на кухне.'
    updated=compact(repo,job,state,history,{**CONFIG,'recent_turns':2,'memory_batch':2},summarize,Event())
    assert len(calls)>=3  # Objective retry plus actor-scoped summaries.
    assert updated['memory']['through_sequence']==1
    assert len(updated['memory']['summary'])<=8000
    assert not state.get('memory')


def test_repeated_invalid_memory_does_not_block_thirty_turns_or_archive_sources(db):
    repo,_,sid=db;cfg={**CONFIG,'recent_turns':2,'memory_batch':4}
    generate(repo,sid,'start',config=cfg)
    memory_calls=[]
    for index in range(30):
        jid=repo.begin_job(sid,'Действие','turn',cfg)
        def stream(**kw):
            if 'Обнови компактную память' in kw['messages'][0]['content']:
                memory_calls.append(jid);yield 'М'*9000
            elif kw.get('response_format'):
                change=result();change['scene']['time']=label(json.loads(repo.get_job(jid)['before_json'])['world_state']['meta']['world_time'])
                yield json.dumps(wire(canonical(change,fixture_sequence(repo,jid)),NARRATIVE,json.loads(repo.get_job(jid)['before_json'])),ensure_ascii=False)
            else:yield NARRATIVE
        with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    turns=repo.list_turns(sid)
    assert len(turns)==31 and not any(t['memory_archived'] for t in turns)
    assert not repo.get_save(sid)['state'].get('memory')
    assert memory_calls==[]  # No LLM memory in the normal-turn critical path.
    original=repo.get_save(sid)['state']
    last=repo.latest_job(sid)
    generate(repo,sid,'regenerate',config=cfg)
    assert repo.latest_job(sid)['memory_before_json']==last['memory_before_json']
    assert repo.get_save(sid)['state']==original
    for _ in range(4):generate(repo,sid,config=cfg)
    assert not repo.get_save(sid)['state']['memory']
    assert len(repo.list_turns(sid))==35
    assert not any(t['memory_archived'] for t in repo.list_turns(sid))


def test_cancelled_repair_does_not_write_memory_version(db):
    repo,_,sid=db;job,state,history=setup_job(repo,sid);cancel=Event()
    def summarize(messages):
        cancel.set();yield 'Неполный текст'
    updated=compact(repo,job,state,history,{**CONFIG,'recent_turns':2},summarize,cancel)
    assert updated==state
    with repo.connect() as conn:assert conn.execute('SELECT COUNT(*) FROM memory_versions').fetchone()[0]==0


def test_failed_actor_summary_does_not_publish_partial_batch(db):
    repo,_,sid=db;job,state,history=setup_job(repo,sid);calls=[]
    def summarize(messages):
        calls.append(messages)
        yield 'Объективная память.' if len(calls)==1 else 'X'*9000
    updated=compact(repo,job,state,history,{**CONFIG,'recent_turns':2,'memory_batch':2},summarize,Event())
    assert updated.get('memory')==state.get('memory')
    assert json.loads(repo.get_job(job['id'])['warnings_json'])[0]['section']=='Память'
    with repo.connect() as conn:assert conn.execute('SELECT COUNT(*) FROM memory_versions').fetchone()[0]==0
