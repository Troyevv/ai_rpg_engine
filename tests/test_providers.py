import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
import engine
from llm import chat_stream
from storage import Storage
from test_worlds import summary
from test_engine import CONFIG, NARRATIVE, result

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


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
         patch('engine.chat_stream', return_value=iter([json.dumps(result())])) as retry_stream:
        engine.run_job(storage.path, job, engine.Worker(api_key='new-private-key'))
    assert retry_stream.call_count == 1
    assert retry_stream.call_args.kwargs['api_key'] == 'new-private-key'
    assert len(storage.list_turns(save)) == 1
    assert all(call['provider'] == 'deepseek' and call['api_key'] == 'private-test-key' for call in calls)
    with storage.connect() as conn:
        dump = '\n'.join(conn.iterdump())
    assert 'private' not in dump


def test_all_remote_ui_generate_and_keep_independent_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'ui.sqlite3'))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'env-test-key')
    with patch('generator_ui.get_available_models', side_effect=AssertionError('local request')) as local, \
         patch('generator_ui.get_loaded_models', side_effect=AssertionError('local status')) as status, \
         patch('generator_ui.find_loaded_model', side_effect=AssertionError('local check')) as check, \
         patch('generator_ui.chat_stream', side_effect=lambda **kw: iter(['Сценарий'])) as stream:
        app = AppTest.from_file(APP)
        app.session_state['gen_idea_provider'] = 'deepseek'
        app.session_state['gen_summary_provider'] = 'deepseek'
        app.run()
        app.text_input(key='deepseek_api_key').input('session-test-key').run()
        app.text_input(key='gen_idea_api_model').input('deepseek-flash').run()
        app.text_input(key='gen_summary_api_model').input('deepseek-v4-pro').run()
        app.chat_input[0].set_value('Игра про друзей').run()
        assert not app.exception
        assert app.session_state['idea'] == 'Сценарий'
        assert stream.call_args.kwargs['provider'] == 'deepseek'
        assert stream.call_args.kwargs['api_key'] == 'session-test-key'
        stream.side_effect = lambda **kw: iter([summary()])
        app.button(key='start_summary').click().run()
        assert not app.exception
        assert app.session_state['summary_complete']
        assert stream.call_args.kwargs['model'] == 'deepseek-v4-pro'
        assert any(b.label == 'Сохранить выжимку' for b in app.button)
        def run_tab(label):
            # AppTest does not serialize the new stateful tab container yet.
            tabs = app._tree.get_widget_states()
            tabs.widgets.add(id=app.get('tab_container')[0].proto.id, string_value=label)
            app._run(tabs)
        run_tab('Игра')
        app.selectbox(key='game_provider').select('deepseek')
        run_tab('Игра')
        assert app.text_input(key='deepseek_api_key').value == 'session-test-key'
        app.text_input(key='game_api_model').input('deepseek-flash')
        run_tab('Игра')
        run_tab('Генерация выжимки')
        assert app.selectbox(key='gen_idea_provider').value == 'deepseek'
        assert app.text_input(key='gen_summary_api_model').value == 'deepseek-v4-pro'
        local.assert_not_called(); status.assert_not_called(); check.assert_not_called()


def test_mixed_providers_and_missing_key_do_not_start_job(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'mixed.sqlite3'))
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    with patch('generator_ui.get_available_models', return_value=['local-model']), \
         patch('generator_ui.get_loaded_models', return_value=[]), \
         patch('generator_ui.find_loaded_model', return_value=None), \
         patch('generator_ui.chat_stream', side_effect=lambda **kw: iter(['Сценарий'])) as stream:
        app = AppTest.from_file(APP)
        app.session_state['gen_idea_provider'] = 'deepseek'
        app.run()
        app.text_input(key='deepseek_api_key').input('test-key').run()
        app.chat_input[0].set_value('Друзья в городе').run()
        assert app.session_state['idea'] == 'Сценарий'
        assert app.selectbox(key='gen_summary_provider').value == 'local'
        app.button(key='start_summary').click().run()
        assert any('загрузи' in e.value for e in app.error)
        assert stream.call_count == 1
    storage = Storage()
    world = storage.save_world('Мир', summary())
    save = storage.create_save(world, 'Игра')
    with pytest.raises(ValueError, match='API-ключ'):
        engine.submit(storage, save, kind='start', config={**CONFIG, 'provider': 'deepseek'})
    assert storage.latest_job(save) is None


def test_local_settings_survive_provider_switch(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'switch.sqlite3'))
    with patch('generator_ui.get_available_models', return_value=['local-model']), patch('generator_ui.get_loaded_models', return_value=[]):
        app = AppTest.from_file(APP).run()
        app.selectbox(key='gen_context').select(32768).run()
        app.toggle(key='gen_flash').set_value(False).run()
        app.selectbox(key='gen_idea_provider').select('deepseek').run()
        app.selectbox(key='gen_summary_provider').select('deepseek').run()
        app.run()
        app.selectbox(key='gen_idea_provider').select('local').run()
        assert app.selectbox(key='gen_context').value == 32768
        assert app.toggle(key='gen_flash').value is False
        assert not app.exception
