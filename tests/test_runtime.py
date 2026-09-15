import json
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.services.credentials import Credentials
from backend.services.usage import price_snapshot, cost
from context_builder import build_context, estimate
from llm import chat_stream
from storage import Storage
import engine
from test_engine import CONFIG, NARRATIVE, result, run, db


def generate(storage,sid,kind='turn',text='Я сажусь.',config=None,story=NARRATIVE):
    job=storage.begin_job(sid,text if kind=='turn' else '',kind,config or CONFIG)
    def stream(**kw):
        if kw.get('on_usage'):
            kw['on_usage']({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':800})
        if kw.get('response_format'):
            yield json.dumps(result(),ensure_ascii=False)
        elif 'Обнови компактную память' in kw['messages'][0]['content']:
            yield 'Собеседники встретились и договорились поговорить на кухне.'
        else:
            yield story
    with patch('engine.find_loaded_model',return_value={'config':{}}), patch('engine.chat_stream',side_effect=stream):
        engine.run_job(storage.path,job,engine.Worker())
    assert storage.get_job(job)['status']=='saved',storage.get_job(job)['error']
    return job


def test_variants_reuse_exact_context_restore_state_and_preserve_descendants(db):
    storage,_,sid=db
    generate(storage,sid,'start')
    first=storage.list_turns(sid)[0]
    initial_state=storage.get_save(sid)['state']
    original_context=storage.get_job(storage.latest_job(sid)['id'])['context_json']
    generate(storage,sid)
    second=storage.list_turns(sid)[1]
    generate(storage,sid)
    before_failure=storage.get_save(sid)
    with pytest.raises(ValueError,match='Подтверди'):
        storage.begin_job(sid,'','regenerate',{**CONFIG,'target_turn_id':first['id']})
    jid=storage.begin_job(sid,'','regenerate',{**CONFIG,'target_turn_id':first['id'],'rollback_following':True})
    assert storage.get_job(jid)['context_json']==original_context
    run(storage,jid,{'choices':[]})
    assert storage.get_save(sid)==before_failure
    assert len(storage.list_turns(sid))==3
    storage.retry_job(jid) # Preserve explicit rollback consent.
    run(storage,jid)
    assert len(storage.list_turns(sid))==1
    variants=storage.variants(first['node_id'])
    assert len(variants)==2
    assert storage.list_turns(sid)[0]['id']==first['id']
    assert storage.get_save(sid)['state']==initial_state
    generate(storage,sid)
    revision=storage.get_save(sid)['revision']
    with pytest.raises(ValueError,match='Подтверди'):
        storage.select_variant(sid,first['id'],first['active_variant_id'],revision)
    storage.select_variant(sid,first['id'],first['active_variant_id'],revision,True)
    assert len(storage.list_turns(sid))==1
    with storage.connect() as conn:
        assert conn.execute('SELECT 1 FROM response_variants WHERE id=?',(second['active_variant_id'],)).fetchone()
        assert conn.execute('SELECT COUNT(*) FROM archived_turns').fetchone()[0]>=3
    with pytest.raises(ValueError,match='изменился'):
        storage.select_variant(sid,first['id'],variants[1]['id'],revision)


def test_memory_compacts_archives_and_regeneration_uses_pre_response_memory(db):
    storage,_,sid=db
    cfg={**CONFIG,'recent_turns':2,'memory_batch':2}
    generate(storage,sid,'start',config=cfg)
    for i in range(5):
        generate(storage,sid,text=f'Действие {i}',config=cfg)
    state=storage.get_save(sid)['state']
    assert state['memory']['through_sequence']==2
    turns=storage.list_turns(sid)
    assert len(turns)==6
    assert sum(t['memory_archived'] for t in turns)==3
    assert turns[0]['assistant_text']==NARRATIVE
    job=storage.latest_job(sid)
    messages=json.loads(job['context_json'])
    assert sum(m['role']=='assistant' for m in messages)==2
    memory_before=json.loads(job['memory_before_json'])
    generate(storage,sid,'regenerate',config=cfg)
    replacement=storage.latest_job(sid)
    assert replacement['context_json']==job['context_json']
    assert json.loads(replacement['memory_before_json'])==memory_before
    with storage.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM memory_versions').fetchone()[0]==3
    restored=Storage(storage.path)
    assert restored.get_save(sid)['state']==storage.get_save(sid)['state']


def test_unknown_usage_prices_and_session_totals(db):
    storage,_,sid=db
    config={**CONFIG,'provider':'deepseek','model':'deepseek-flash','thinking':'low'}
    job=generate(storage,sid,'start',config=config)
    accounting=storage.accounting(sid)
    assert len(accounting['requests'])==2
    assert accounting['game']['input_tokens']==2000
    assert accounting['game']['cached_input_tokens']==1600
    assert float(accounting['game']['cost_usd'])>0
    storage.start_session(sid)
    assert storage.accounting(sid)['session']['input_tokens']==0
    assert storage.accounting(sid)['game']==accounting['game']
    generate(storage,sid,'regenerate',config=config)
    assert storage.accounting(sid)['game']['input_tokens']==4000
    assert storage.accounting(sid)['session']['input_tokens']==2000
    peak=price_snapshot(config,datetime(2026,9,15,7,tzinfo=timezone.utc))
    off=price_snapshot(config,datetime(2026,9,15,12,tzinfo=timezone.utc))
    assert cost(1000,100,800,peak)=='0.0001848'
    assert cost(1000,100,800,off)=='0.0000924'
    assert cost(None,None,None,peak) is None
    assert price_snapshot(dict(config,model='unknown'),datetime.now(timezone.utc)) is None


@pytest.mark.parametrize('level',['off','low','high'])
def test_thinking_and_usage_on_terminal_content_chunk(level):
    client,stream=MagicMock(),MagicMock()
    usage={'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':600}
    stream.__iter__.return_value=iter([NS(choices=[NS(delta=NS(content='Ответ'),finish_reason='stop')],usage=usage)])
    client.chat.completions.create.return_value=stream
    collected=[]
    with patch('llm.OpenAI',return_value=client):
        assert ''.join(chat_stream('deepseek-flash',[],provider='deepseek',api_key='secret',thinking=level,on_usage=collected.append))=='Ответ'
    options=client.chat.completions.create.call_args.kwargs
    assert options['extra_body']['thinking']['type']==('disabled' if level=='off' else 'enabled')
    assert options.get('reasoning_effort')==(None if level=='off' else level)
    assert ('temperature' in options)==(level=='off')
    assert collected==[usage]


def test_persistent_key_is_encrypted_and_not_returned(tmp_path,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    path=tmp_path/'game.db'
    with TestClient(create_app(path)) as client:
        assert client.put('/api/credentials/deepseek',json={'api_key':'private-key-123'}).json()=={'deepseek':True}
        assert client.get('/api/credentials').json()=={'deepseek':True}
    storage=Storage(path)
    assert Credentials(storage).resolve('deepseek')=='private-key-123'
    with storage.connect() as conn:
        assert 'private-key-123' not in '\n'.join(conn.iterdump())
    with TestClient(create_app(path)) as client, patch('llm.get_deepseek_models',return_value=['deepseek-flash']) as models:
        assert client.post('/api/models/list',json={'provider':'deepseek'}).status_code==200
        models.assert_called_once_with('private-key-123')
        assert client.delete('/api/credentials/deepseek').json()=={'deepseek':False}


def test_invalid_plan_is_reported_without_blocking_valid_event(db):
    storage,_,sid=db
    job=storage.begin_job(sid,'','start',CONFIG)
    bad=result()
    bad['plans']=[{'id':'p1','text':'Пойти в кино','character_ids':['character_1'],'status':'open','evidence':'Давай сходим в кино'}]
    run(storage,job,bad)
    assert storage.get_job(job)['status']=='saved'
    state=storage.get_save(sid)['state']
    assert not state.get('plans')
    assert state['events'][-1]['text']==bad['events'][0]['text']
    assert json.loads(storage.get_job(job)['warnings_json'])[0]['section']=='plans'


def test_retry_retains_historical_rollback_consent_with_new_model_config(db):
    storage,_,sid=db
    generate(storage,sid,'start')
    target=storage.list_turns(sid)[0]['id']
    generate(storage,sid)
    jid=storage.begin_job(sid,'','regenerate',{**CONFIG,'target_turn_id':target,'rollback_following':True})
    run(storage,jid,{'choices':[]})
    next_session = storage.start_session(sid)
    storage.retry_job(jid,{**CONFIG,'temperature':.5})
    assert storage.get_job(jid)['session_id'] == next_session
    assert json.loads(storage.get_job(jid)['config_json'])['rollback_following'] is True
    run(storage,jid)
    assert storage.get_job(jid)['status']=='saved'
    assert len(storage.list_turns(sid))==1


def test_partial_api_usage_is_recorded_and_cannot_commit(db):
    storage,_,sid=db
    cfg={**CONFIG,'provider':'deepseek','model':'deepseek-flash'}
    jid=storage.begin_job(sid,'','start',cfg)
    def broken(**kw):
        yield 'Черновик'
        raise RuntimeError('Связь оборвана')
    with patch('engine.chat_stream',side_effect=broken):
        engine.run_job(storage.path,jid,engine.Worker())
    requests=storage.request_log(save_id=sid)
    assert len(requests)==1
    assert requests[0]['status']=='error'
    assert requests[0]['input_tokens'] is None
    assert requests[0]['cost_usd'] is None
    assert storage.accounting(sid)['game']['unknown_requests']==1
    assert storage.list_turns(sid)==[]


def test_legacy_turn_migration_is_idempotent_and_does_not_invent_context(db):
    storage,_,sid=db
    generate(storage,sid,'start')
    with storage.connect() as conn:
        conn.execute('UPDATE turns SET node_id=NULL,active_variant_id=NULL')
        conn.execute('DELETE FROM response_variants')
        original=dict(conn.execute('SELECT * FROM turns').fetchone())
    migrated=Storage(storage.path)
    twice=Storage(storage.path)
    with twice.connect() as conn:
        row=dict(conn.execute('SELECT * FROM turns').fetchone())
        assert row['before_json']==original['before_json']
        assert row['after_json']==original['after_json']
        assert conn.execute('SELECT COUNT(*) FROM response_variants').fetchone()[0]==1
    with pytest.raises(ValueError,match='нет снимка'):
        migrated.begin_job(sid,'','regenerate',CONFIG)


def test_unsupported_provider_ignores_thinking():
    from llm import thinking_options
    assert thinking_options('local','local-model','high')==('off',{})
    assert thinking_options('deepseek','unlisted-model','high')==('off',{})
