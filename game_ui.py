"""World browser and independent playthrough snapshots."""
import sqlite3
import streamlit as st
from chat_ui import render_chat
from game_settings import render_game_settings
from storage import Storage
from scene_ui import render_scene_bar, render_scene_editor
from reading_ui import reading_controls
from character_navigation import choose_character, relationship_change


def save_summary_form(markdown, key):
    with st.form(key):
        name = st.text_input('Название мира', max_chars=120)
        st.caption('Изменённая выжимка с тем же названием сохраняется новой версией мира.')
        submitted = st.form_submit_button('Сохранить выжимку', type='primary')
    if submitted:
        try:
            world_id = Storage().save_world(name, markdown)
        except (ValueError, sqlite3.Error, OSError) as exc:
            st.error(f'Не удалось сохранить мир: {exc}')
        else:
            st.session_state.world_notice = 'Мир сохранён и доступен во вкладке «Игра».'
            st.session_state.pending_world_id = world_id
            st.rerun()



def render_import():
    with st.expander('Загрузить готовую выжимку'):
        uploaded = st.file_uploader('Выжимка в Markdown (UTF-8)', type=['md'], key='world_upload')
        if uploaded is not None:
            try:
                markdown = uploaded.getvalue().decode('utf-8-sig')
            except UnicodeDecodeError:
                st.error('Файл должен быть в кодировке UTF-8.')
            else:
                save_summary_form(markdown, 'import_world')


def render_relationships(state, character_id=None):
    characters = {c['id']: c['name'] for c in state['characters']}
    relationships = state.get('relationships', [])
    selected = [r for r in relationships if character_id is None or r['source_id'] == character_id]
    if not selected:
        st.caption('Отношения пока не описаны.')
    for relationship in selected:
        source = characters.get(relationship['source_id'], relationship['source_id'])
        target = characters.get(relationship.get('target_id'), relationship.get('target_name', 'Неизвестно'))
        st.markdown(f'**{source} → {target}**')
        st.markdown(relationship['text'])
        change = relationship_change(relationship)
        if change:
            direction, reason, turn = change
            st.markdown(':green[↑ Улучшение]' if direction == 'up' else ':red[↓ Ухудшение]')
            st.caption(reason + (f' · Ход {turn}' if turn is not None else ''))


def render_world_data(world, save, storage):
    state = save['state'] if save else world['state']
    with st.expander('О мире и сохранении'):
        st.write(f"Мир: {world['name']}")
        st.write(f"Версия выжимки: {world['version']}")
        st.caption(f"Создан: {world['created_at']}")
        if save:
            st.write(f"Прохождение: {save['name']} · #{save['id']}")
            st.caption(f"Обновлено: {save['updated_at']}")
        else:
            st.caption('Показана стартовая основа мира.')
    section = st.selectbox('Раздел', ['Мир', 'Сцена', 'Персонажи', 'Отношения', 'Тайны', 'Сюжет'], key='game_panel_section')
    if section == 'Мир':
        st.markdown(state['sections']['tone'])
        st.markdown(state['sections']['locations'])
    elif section == 'Сцена':
        st.markdown(state['scene'])
        render_scene_editor(storage, save)
    elif section == 'Персонажи':
        character = choose_character(state)
        if character is None:
            return
        character_id = character['id']
        st.subheader(character['name'])
        st.caption('Карточка ведущего: может содержать скрытые намерения.')
        for name, text in character['fields'].items():
            if not name.startswith('Отношение к '):
                st.markdown(f'**{name}**')
                st.markdown(text)
        st.markdown('**Текущие отношения**')
        render_relationships(state, character_id)
    elif section == 'Отношения':
        render_relationships(state)
    elif section == 'Тайны':
        st.caption('Данные ведущего — спойлеры.')
        st.markdown(state['sections']['knowledge'])
    else:
        st.markdown(state['story_notes'])


def selected_data(storage, worlds):
    by_id = {world['id']: world for world in worlds}
    pending = st.session_state.pop('pending_world_id', None)
    if pending in by_id:
        st.session_state.world_picker = pending
        st.session_state.game_panel_open = True
    if st.session_state.get('world_picker') not in by_id:
        st.session_state.world_picker = worlds[0]['id']
    world = storage.get_world(st.session_state.world_picker)
    saves = {save['id']: save for save in storage.list_saves(world['id'])}
    selection = st.session_state.get(f'save_picker_{world["id"]}')
    save = storage.get_save(selection) if selection in saves else None
    return world, save


def render_game():
    render_game_settings()
    st.html("""<style>
    .st-key-game_chat_scroll {height: max(360px, calc(100dvh - 340px)) !important;}
    .st-key-game_world_panel {height: max(420px, calc(100dvh - 265px)) !important;}
    </style>""")
    st.session_state.setdefault('game_panel_open', True)
    # A pending import should reveal the newly saved world even after the panel was closed.
    if st.session_state.get('pending_world_id'):
        st.session_state.game_panel_open = True
    toolbar, reading, button = st.columns([3, 1.5, 1.5])
    toolbar.header('Игра')
    with reading:
        reading_controls()
    if button.button('Скрыть панель' if st.session_state.game_panel_open else 'Мир и персонажи',
                     key='game_toggle_panel', use_container_width=True):
        st.session_state.game_panel_open = not st.session_state.game_panel_open
        st.rerun()
    if st.session_state.game_panel_open:
        center, right = st.columns([3, 1.35], gap='large')
    else:
        center, right = st.container(), None
    try:
        storage = Storage()
        worlds = storage.list_worlds()
        world, save = selected_data(storage, worlds) if worlds else (None, None)
        if right:
            with right:
                with st.container(height=760, border=True, key='game_world_panel'):
                    st.subheader('Мир и сохранение')
                    render_import()
                    if worlds:
                        by_id = {w['id']: w for w in worlds}
                        world_id = st.selectbox('Мир', list(by_id), key='world_picker',
                                                format_func=lambda key: f"{by_id[key]['name']} · версия {by_id[key]['version']}")
                        world = storage.get_world(world_id)
                        saves = {s['id']: s for s in storage.list_saves(world_id)}
                        selection = st.selectbox('Мир / сохранение', [None, *saves], key=f'save_picker_{world_id}',
                                                 format_func=lambda key: 'Стартовая основа мира' if key is None else
                                                 f"{saves[key]['name']} · #{key}")
                        save = storage.get_save(selection) if selection is not None else None
                        context = (world_id, selection)
                        if st.session_state.get('game_active_context') != context:
                            st.session_state.game_active_context = context
                            st.session_state.game_selected_character = world['state']['characters'][0]['id']
                            st.session_state.game_panel_section = 'Мир'
                            st.session_state.game_character_search = ''
                            st.session_state.game_character_scope = 'Все'
                        with st.expander('Создать прохождение'):
                            with st.form(f'new_save_{world_id}'):
                                name = st.text_input('Название нового прохождения', value='Новое прохождение', max_chars=120)
                                create = st.form_submit_button('Создать прохождение')
                            if create:
                                save_id = storage.create_save(world_id, name)
                                st.session_state.pending_save = (world_id, save_id)
                                st.rerun()
                        render_world_data(world, save, storage)
                        st.divider()
                        st.download_button('Скачать исходную выжимку', world['source_md'],
                                           file_name=f'world_{world_id}.md', mime='text/markdown')
                    else:
                        st.info('Создай выжимку или загрузи готовый Markdown.')
        with center:
            if world:
                render_scene_bar(save['state'] if save else world['state'])
                render_chat(storage, world, save)
            else:
                st.info('Выбери мир в правой панели, чтобы открыть игровой чат.')
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f'Не удалось открыть данные игры: {exc}')
