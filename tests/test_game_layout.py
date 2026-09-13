import json
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from character_links import linked_markdown
from storage import Storage
from test_worlds import summary


def test_safe_links_and_ambiguous_names():
    characters = [
        {'id': 'one', 'name': 'Анна Орлова', 'aliases': ['Аня', 'Анне']},
        {'id': 'two', 'name': 'Анна Иванова'},
        {'id': 'three', 'name': 'Илья Морозов (ГГ)'},
    ]
    html = linked_markdown('**Анна Орлова** и Анна. Аня говорит Илье. Анне ответили.\n'
                           '`Анна Орлова` [Анна Орлова](https://example.org)\n'
                           '<script>alert(1)</script>\n```\nАня\n```', characters)
    assert html.count('data-character-id="one"') == 3
    assert '<strong><button' in html
    assert '<code>Анна Орлова</code>' in html
    assert '<a href="https://example.org">Анна Орлова</a>' in html
    assert '<script>' not in html
    assert 'и Анна.' in html
    assert linked_markdown('Илья', characters).count('data-character-id="three"') == 1


def test_panel_close_reopen_settings_and_current_relationships(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'rpg.sqlite3'))
    storage = Storage()
    world_id = storage.save_world('Мир', summary())
    save_id = storage.create_save(world_id, 'Сейв')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
    app.session_state['app_mode'] = 'Игра'
    app.session_state[f'save_picker_{world_id}'] = save_id
    app.run()
    assert not app.exception
    assert 'Настройки игры' in [header.value for header in app.sidebar.header]
    assert not any(slider.label == 'Temperature сценариста' for slider in app.sidebar.slider)
    app.selectbox(key='game_panel_section').select('Отношения').run()
    state = storage.get_save(save_id)['state']
    state['relationships'][0]['text'] = 'После ссоры держит дистанцию.'
    with storage.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(state, ensure_ascii=False), save_id))
    app.run()
    assert any('После ссоры' in element.value for element in app.markdown)
    # Immutable world is unchanged; the panel is rendering the save.
    assert 'После ссоры' not in json.dumps(storage.get_world(world_id)['state'], ensure_ascii=False)
    app.button(key='game_toggle_panel').click().run()
    assert not app.exception
    assert not any(select.label == 'Раздел' for select in app.selectbox)
    app.button(key='game_toggle_panel').click().run()
    assert app.selectbox(key=f'save_picker_{world_id}').value == save_id
    assert app.selectbox(key='game_panel_section').value == 'Отношения'
    assert not app.exception


def test_mode_switch_keeps_settings_and_draft(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'modes.sqlite3'))
    with patch('generator_ui.get_available_models', return_value=[]), patch('generator_ui.get_loaded_models', return_value=[]):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.session_state['idea'] = 'Не терять сценарий'
        app.run()
        app.slider(key='gen_idea_temperature').set_value(1.2).run()
        app.session_state['app_mode'] = 'Игра'
        app.run()
        assert not any(slider.label == 'Temperature сценариста' for slider in app.slider)
        app.slider(key='game_font_size').set_value(21).run()
        app.session_state['app_mode'] = 'Генерация выжимки'
        app.run()
        assert app.slider(key='gen_idea_temperature').value == 1.2
        assert app.session_state['idea'] == 'Не терять сценарий'
        app.session_state['app_mode'] = 'Игра'
        app.run()
        assert app.slider(key='game_font_size').value == 21
        assert not app.exception


def test_npc_event_opens_closed_panel_without_changing_save(tmp_path, monkeypatch):
    from streamlit.proto.WidgetStates_pb2 import WidgetStates
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'click.sqlite3'))
    storage = Storage()
    world_id = storage.save_world('Мир', summary())
    save_id = storage.create_save(world_id, 'Сейв')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
    app.session_state['app_mode'] = 'Игра'
    app.session_state[f'save_picker_{world_id}'] = save_id
    app.run()
    app.button(key='game_toggle_panel').click().run()
    assert app.session_state['game_panel_open'] is False
    component = app.get('bidi_component')[0]
    events = WidgetStates()
    event = events.widgets.add()
    event.id = component.proto.id
    event.json_value = json.dumps({'character': 'character_2'})
    app._run(events)
    assert not app.exception
    assert app.session_state['game_panel_open'] is True
    assert app.selectbox(key='game_panel_section').value == 'Персонажи'
    assert app.selectbox(key='game_selected_character').value == 'character_2'
    assert app.selectbox(key=f'save_picker_{world_id}').value == save_id
    # Closing again must not replay the previous transient click.
    app.button(key='game_toggle_panel').click().run()
    assert not app.exception
    assert app.session_state['game_panel_open'] is False
