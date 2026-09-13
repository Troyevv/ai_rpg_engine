"""World browser and independent playthrough snapshots."""
import sqlite3
import streamlit as st
from storage import Storage


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


def render_state(state):
    st.subheader('Текущая сцена')
    st.markdown(state['scene'])
    with st.expander('Жанр и тон'):
        st.markdown(state['sections']['tone'])
    # Cards can contain hidden feelings, so they belong to the spoiler section too.
    with st.expander('Персонажи — имена'):
        for character in state['characters']:
            st.write(character['name'])
    with st.expander('Локации'):
        st.markdown(state['sections']['locations'])
    with st.expander('Данные ведущего — спойлеры'):
        st.caption('Полные карточки, отношения, знания, тайны и сюжетные предпосылки.')
        for character in state['characters']:
            st.subheader(character['name'])
            st.markdown(character['text'])
        st.markdown(state['sections']['knowledge'])
        st.markdown(state['story_notes'])


def render_game():
    st.header('Игра')
    with st.expander('Загрузить готовую выжимку'):
        uploaded = st.file_uploader('Выжимка в Markdown (UTF-8)', type=['md'], key='world_upload')
        if uploaded is not None:
            try:
                markdown = uploaded.getvalue().decode('utf-8-sig')
            except UnicodeDecodeError:
                st.error('Файл должен быть в кодировке UTF-8.')
            else:
                save_summary_form(markdown, 'import_world')
    try:
        storage = Storage()
        worlds = storage.list_worlds()
        if not worlds:
            st.info('Сохранённых миров пока нет. Создай выжимку или загрузи готовый Markdown.')
            return
        by_id = {world['id']: world for world in worlds}
        pending = st.session_state.pop('pending_world_id', None)
        if pending in by_id:
            st.session_state.world_picker = pending
        if st.session_state.get('world_picker') not in by_id:
            st.session_state.world_picker = worlds[0]['id']
        world_id = st.selectbox('Мир', list(by_id), key='world_picker',
                                format_func=lambda key: f"{by_id[key]['name']} · версия {by_id[key]['version']}")
        world = storage.get_world(world_id)
        saves = storage.list_saves(world_id)
        save_by_id = {save['id']: save for save in saves}
        selection = st.selectbox('Мир / сохранение', [None, *save_by_id], key=f'save_picker_{world_id}',
                                 format_func=lambda key: 'Стартовая основа мира' if key is None else
                                 f"{save_by_id[key]['name']} · #{key} · {save_by_id[key]['updated_at']}")
        if selection is None:
            st.caption(f"Мир сохранён: {world['created_at']}")
            render_state(world['state'])
        else:
            save = storage.get_save(selection)
            st.caption(f"Прохождение: {save['name']}. Создано: {save['created_at']}")
            render_state(save['state'])
        st.download_button('Скачать исходную выжимку', world['source_md'],
                           file_name=f'world_{world_id}.md', mime='text/markdown')
        with st.form(f'new_save_{world_id}'):
            save_name = st.text_input('Название нового прохождения', value='Новое прохождение', max_chars=120)
            create = st.form_submit_button('Создать прохождение')
        if create:
            save_id = storage.create_save(world_id, save_name)
            st.session_state.pending_save = (world_id, save_id)
            st.rerun()
        st.info('Здесь можно подготовить и выбрать прохождение. Генерация игровых ходов — следующий этап движка.')
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f'Не удалось открыть данные игры: {exc}')
