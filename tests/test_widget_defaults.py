import logging
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from streamlit.elements.lib import policies
from storage import Storage
from test_worlds import summary
from test_engine import run


def test_settings_rerun_switch_and_start_without_default_conflict(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'widgets.sqlite3'))
    storage = Storage()
    world = storage.save_world('Мир', summary())
    save = storage.create_save(world, 'Игра')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
    app.session_state['app_mode'] = 'Игра'
    app.session_state['game_models'] = ['test']
    app.session_state[f'save_picker_{world}'] = save

    def check_run():
        # Streamlit normally logs only the first conflict process-wide.
        monkeypatch.setattr(policies, '_shown_default_value_warning', False)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            app.run()
        assert not app.exception
        assert not any('was created with a default value' in r.message for r in caplog.records)

    with patch('generator_ui.get_available_models', return_value=['test']), patch('generator_ui.get_loaded_models', return_value=[]), \
         patch('engine.launch', side_effect=lambda path, job: run(storage, job)):
        check_run()
        check_run()
        app.toggle(key='game_link_names').set_value(False)
        app.slider(key='game_font_size').set_value(21)
        app.selectbox(key='game_context').select(32768)
        check_run()
        app.session_state['app_mode'] = 'Генерация выжимки'
        check_run()
        app.slider(key='gen_idea_temperature').set_value(1.2)
        check_run()
        app.session_state['app_mode'] = 'Игра'
        check_run()
        assert app.toggle(key='game_link_names').value is False
        assert app.slider(key='game_font_size').value == 21
        assert app.selectbox(key='game_context').value == 32768
        app.button(key=f'start_game_{save}').click()
        check_run()
        assert storage.list_turns(save)[0]['kind'] == 'start'
        app.session_state['app_mode'] = 'Генерация выжимки'
        check_run()
        assert app.slider(key='gen_idea_temperature').value == 1.2
