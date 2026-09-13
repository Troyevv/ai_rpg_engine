import json
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from storage import Storage
from scene_ui import scene_metadata
from character_navigation import relationship_change
from test_worlds import summary


def setup_app(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'game.sqlite3'))
    storage = Storage()
    wid = storage.save_world('Мир', summary())
    sid = storage.create_save(wid, 'Прохождение')
    storage.update_scene_meta(sid, {'time': 'Пятница, 19:30', 'location': 'Кухня', 'present_ids': ['character_2', 'character_3']})
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
    app.session_state['app_mode'] = 'Игра'
    app.session_state[f'save_picker_{wid}'] = sid
    app.run()
    assert not app.exception
    return app, storage, wid, sid


def test_scene_patch_and_no_guessed_presence(tmp_path, monkeypatch):
    app, storage, wid, sid = setup_app(tmp_path, monkeypatch)
    state = storage.get_save(sid)['state']
    assert scene_metadata(state)['location'] == 'Кухня'
    assert 'scene_meta' not in storage.get_world(wid)['state']
    original = storage.get_world(wid)['state']
    assert scene_metadata(original)['time'] == '18:20'
    assert scene_metadata(original)['location'] == ''
    assert scene_metadata(original)['present_ids'] == []
    with pytest.raises(ValueError):
        storage.update_scene_meta(sid, {'time': '20:00', 'location': 'Двор', 'present_ids': ['missing']})
    assert storage.get_save(sid)['state'] == state
    assert len([b for b in app.button if b.key and b.key.startswith('nearby_')]) == 2


def test_reading_and_npc_navigation(tmp_path, monkeypatch):
    app, storage, wid, sid = setup_app(tmp_path, monkeypatch)
    app.button(key='reading_toggle').click().run()
    assert not app.exception
    assert app.session_state['game_reading'] is True
    assert app.session_state['game_panel_open'] is False
    component = app.get('bidi_component')[0]
    events = WidgetStates()
    event = events.widgets.add()
    event.id = component.proto.id
    event.json_value = json.dumps({'character': 'character_3'})
    app._run(events)
    assert not app.exception
    assert app.session_state['game_reading'] is True
    assert app.selectbox(key='game_selected_character').value == 'character_3'
    app.button(key='reading_toggle').click().run()
    assert app.session_state['game_reading'] is False
    assert app.session_state['game_panel_open'] is True
    assert app.selectbox(key=f'save_picker_{wid}').value == sid


def test_navigation_search_nearby_and_previous(tmp_path, monkeypatch):
    app, storage, wid, sid = setup_app(tmp_path, monkeypatch)
    app.button(key='nearby_character_2').click().run()
    assert not app.exception
    assert app.selectbox(key='game_selected_character').value == 'character_2'
    app.radio(key='game_character_scope').set_value('Рядом').run()
    assert len(app.selectbox(key='game_selected_character').options) == 2
    app.button(key='character_next').click().run()
    assert app.selectbox(key='game_selected_character').value == 'character_3'
    app.text_input(key='game_character_search').input('несуществующее').run()
    assert any('не найдены' in i.value for i in app.info)
    app.button(key='nearby_character_2').click().run()
    assert not app.exception
    assert app.text_input(key='game_character_search').value == ''
    assert app.selectbox(key='game_selected_character').value == 'character_2'


def test_relationship_direction_requires_explicit_change():
    assert relationship_change({'text': 'Любит'}) is None
    assert relationship_change({'change': {'direction': 'up'}}) is None
    assert relationship_change({'change': {'direction': 'up', 'reason': 'Помог в трудный момент', 'turn': 4}}) == ('up', 'Помог в трудный момент', 4)
    assert relationship_change({'change': {'direction': 'down', 'reason': 'Нарушил обещание'}}) == ('down', 'Нарушил обещание', None)
