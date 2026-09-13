from pathlib import Path
import sqlite3
from unittest.mock import patch
import pytest
from storage import Storage
from world_parser import parse_summary


def summary():
    cards = []
    for i in range(7):
        cards.append(f'''👤 Персонаж {i}{' (ГГ)' if i == 0 else ''}

· Статус: Живёт в городе.
· Внешность: Рыжие волосы.
· Суть: Подробный характер.\nВторая строка характера.
· Сейчас: На кухне.
· Отношение к Персонаж 1: Знакомы с детства.
· Чего хочет: Приготовить ужин.
''')
    return '''# ВЫЖИМКА
## ГЛАВНОЕ СЕЙЧАС
### Где сейчас ГГ:
Пятница, 18:20. Кухня. Все собрались.
# ЖАНР И ТОН
Современная драмеди.
# КЛЮЧЕВЫЕ NPC
''' + '\n---\n'.join(cards) + '''
# ЧТО ЗНАЮТ / ЧТО ТАЙНА
## 🟢 ОБЩЕИЗВЕСТНО
Все живут вместе.
## 🔴 ТАЙНЫ
Персонаж 1 планирует переезд.
# МИР
## Город
Небольшой город.
## Кухня
Большой стол.
# ОСОБЕННЫЕ МОМЕНТЫ
Переезд ещё не решён.
'''


def test_parse_preserves_details():
    state = parse_summary(summary())
    assert len(state['characters']) == 7
    assert 'Вторая строка' in state['characters'][0]['fields']['Суть']
    assert state['relationships'][0]['target_name'] == 'Персонаж 1'
    assert len(state['locations']) == 2
    assert 'переезд' in state['knowledge'][1]['text']


def test_versions_dedup_and_independent_saves(tmp_path):
    path = tmp_path / 'nested' / 'rpg.sqlite3'
    db = Storage(path)
    world_id = db.save_world('Мир', summary())
    assert db.save_world('мир', summary()) == world_id
    save_a = db.create_save(world_id, 'Первое')
    save_b = db.create_save(world_id, 'Второе')
    new_id = db.save_world('Мир', summary().replace('18:20', '19:20'))
    assert db.get_world(new_id)['version'] == 2
    assert '18:20' in Storage(path).get_save(save_a)['state']['scene']
    state = db.get_save(save_a)['state']
    state['characters'][0]['name'] = 'Изменено'
    assert db.get_save(save_b)['state']['characters'][0]['name'] != 'Изменено'
    assert db.get_world(world_id)['source_md'] == summary()


def test_invalid_import_does_not_write(tmp_path):
    db = Storage(tmp_path / 'rpg.sqlite3')
    for value in ['', summary().replace('👤 Персонаж 6', 'Персонаж 6'), summary().replace('(ГГ)', ''),
                  summary().replace('# МИР', '# ПРОПУЩЕНО')]:
        with pytest.raises(ValueError):
            db.save_world('Мир', value)
    assert db.list_worlds() == []


def test_transaction_rolls_back_parts_failure(tmp_path):
    db = Storage(tmp_path / 'rpg.sqlite3')
    with db.connect() as conn:
        conn.execute("CREATE TRIGGER reject_part BEFORE INSERT ON world_parts BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        db.save_world('Мир', summary())
    assert db.list_worlds() == []


def test_streamlit_offline_world_selection_and_save(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'ui.sqlite3'))
    db = Storage()
    world_id = db.save_world('Тестовый мир', summary())
    with patch('generator_ui.get_available_models', side_effect=ConnectionError('offline')), \
         patch('generator_ui.get_loaded_models', return_value=[]):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        assert not app.exception
        assert [tab.label for tab in app.tabs] == ['Генерация выжимки', 'Игра']
        assert app.selectbox(key='world_picker').value == world_id
        next(button for button in app.button if button.label == 'Создать прохождение').click().run()
        assert not app.exception
        assert len(db.list_saves(world_id)) == 1
        assert app.selectbox(key=f'save_picker_{world_id}').value == db.list_saves(world_id)[0]['id']


def test_generator_save_form(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'ui.sqlite3'))
    with patch('generator_ui.get_available_models', return_value=[]), \
         patch('generator_ui.get_loaded_models', return_value=[]):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.session_state['summary'] = summary()
        app.session_state['summary_complete'] = True
        app.run()
        assert not app.exception
        next(field for field in app.text_input if field.label == 'Название мира').input('Новый мир')
        next(button for button in app.button if button.label == 'Сохранить выжимку').click().run()
        assert not app.exception
        assert Storage().list_worlds()[0]['name'] == 'Новый мир'
        app.run()
        assert not app.exception
        assert app.selectbox(key='world_picker').value == Storage().list_worlds()[0]['id']


def test_draft_cannot_be_saved(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'draft.sqlite3'))
    with patch('generator_ui.get_available_models', return_value=[]), patch('generator_ui.get_loaded_models', return_value=[]):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.session_state['summary'] = summary()
        app.session_state['summary_complete'] = False
        app.run()
        assert not app.exception
        assert not any(button.label == 'Сохранить выжимку' for button in app.button)


@pytest.mark.parametrize('reason', ['stop', 'length', None])
def test_stream_completion_and_cleanup(reason):
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock
    from llm import chat_stream
    client = MagicMock()
    stream = MagicMock()
    stream.__iter__.return_value = iter([NS(choices=[NS(delta=NS(content='Текст'), finish_reason=reason)])])
    client.chat.completions.create.return_value = stream
    with patch('llm.OpenAI', return_value=client):
        if reason == 'stop':
            assert list(chat_stream('model', [], require_complete=True)) == ['Текст']
        else:
            with pytest.raises(RuntimeError):
                list(chat_stream('model', [], require_complete=True))
    stream.close.assert_called_once()
    client.close.assert_called_once()


def test_existing_generator_finishes_and_exposes_save(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('RPG_DB_PATH', str(tmp_path / 'generated.sqlite3'))
    with patch('generator_ui.get_available_models', return_value=['test-model']), \
         patch('generator_ui.get_loaded_models', return_value=[]), \
         patch('generator_ui.chat_stream', return_value=iter([summary()])):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.session_state['idea'] = 'Согласованный сценарий'
        app.session_state['generation_mode'] = 'summary'
        app.run()
        assert not app.exception
        assert app.session_state['summary_complete'] is True
        assert app.session_state['summary'] == summary()
        assert any(button.label == 'Сохранить выжимку' for button in app.button)
