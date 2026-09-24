from canonical_fixture import canonical
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
import engine
from llm import chat_stream
from storage import Storage
from test_worlds import summary
from test_engine import CONFIG, NARRATIVE, result



@pytest.mark.parametrize('provider', ['local', 'deepseek'])
def test_stream_routes_and_closes(provider):
    client, stream = MagicMock(), MagicMock()
    stream.__iter__.return_value = iter([
        NS(choices=[NS(delta=NS(content=None, reasoning_content='hidden'), finish_reason=None)]),
        NS(choices=[NS(delta=NS(content='Текст'), finish_reason='stop')]),
    ])
    client.chat.completions.create.return_value = stream
    with patch('llm.OpenAI', return_value=client) as factory:
        assert list(chat_stream('model', [], provider=provider, api_key='test-key', require_complete=True,
                                response_format={'type': 'json_object'})) == ['Текст']
    options = factory.call_args.kwargs
    assert options['base_url'] == ('https://api.deepseek.com' if provider == 'deepseek' else 'http://localhost:1234/v1')
    assert options['api_key'] == ('test-key' if provider == 'deepseek' else 'lm-studio')
    request = client.chat.completions.create.call_args.kwargs
    assert request['response_format'] == {'type': 'json_object'}
    assert ('extra_body' in request) == (provider == 'deepseek')
    stream.close.assert_called_once()
    client.close.assert_called_once()


def test_missing_key_and_safe_api_error(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    with pytest.raises(ValueError, match='API-ключ'):
        list(chat_stream('model', [], provider='deepseek'))
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception('sensitive-test-key')
    with patch('llm.OpenAI', return_value=client):
        with pytest.raises(RuntimeError) as error:
            list(chat_stream('model', [], provider='deepseek', api_key='sensitive-test-key'))
    assert 'sensitive-test-key' not in str(error.value)
    client.close.assert_called_once()


def test_deepseek_game_retry_and_no_persisted_credentials(tmp_path):
    storage = Storage(tmp_path / 'game.sqlite3')
    world = storage.save_world('Мир', summary())
    save = storage.create_save(world, 'Игра')
    config = {**CONFIG, 'provider': 'deepseek', 'model': 'deepseek-flash'}
    with patch('engine.launch') as launch:
        job = engine.submit(storage, save, kind='start', config=config, api_key='private-test-key')
    assert launch.call_args.kwargs['api_key'] == 'private-test-key'
    calls = []
    def stream(**kwargs):
        calls.append(kwargs)
        if kwargs.get('response_format'):
            raise RuntimeError('temporary')
        yield NARRATIVE
    with patch('engine.find_loaded_model', side_effect=AssertionError('must not call LM Studio')), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(storage.path, job, engine.Worker(api_key='private-test-key'))
    assert storage.get_job(job)['status'] == 'error'
    assert storage.get_job(job)['narrative_complete']
    with patch('engine.launch'):
        engine.retry(storage, job, config, api_key='new-private-key')
    with patch('engine.find_loaded_model', side_effect=AssertionError('must not call LM Studio')), \
         patch('engine.chat_stream', return_value=iter([json.dumps(canonical(result()))])) as retry_stream:
        engine.run_job(storage.path, job, engine.Worker(api_key='new-private-key'))
    assert retry_stream.call_count == 1
    assert retry_stream.call_args.kwargs['api_key'] == 'new-private-key'
    assert len(storage.list_turns(save)) == 1
    assert all(call['provider'] == 'deepseek' and call['api_key'] == 'private-test-key' for call in calls)
    with storage.connect() as conn:
        dump = '\n'.join(conn.iterdump())
    assert 'private' not in dump
