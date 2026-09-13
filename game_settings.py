"""Controls scoped to game mode, independent of generator settings."""
import streamlit as st
from llm import get_available_models, get_loaded_models, load_model, unload_all_models


def render_game_settings():
    with st.sidebar:
        st.header('Настройки игры')
        st.toggle('Выделять имена персонажей', value=True, key='game_link_names')
        st.slider('Размер текста', 14, 24, 17, key='game_font_size')
        with st.expander('Модель ведущего'):
            # Browsing the game makes no network requests until explicitly requested.
            if st.button('Обновить список моделей', key='game_refresh_models'):
                try:
                    st.session_state.game_models = get_available_models()
                    st.session_state.game_loaded = get_loaded_models()
                except Exception as exc:
                    st.error(f'Не удалось подключиться к LM Studio: {exc}')
            models = st.session_state.get('game_models', [])
            model = st.selectbox('Модель', models, key='game_model')
            context = st.selectbox('Контекст', [8192, 16384, 32768], index=1, key='game_context')
            batch = st.selectbox('Eval Batch Size', [256, 512, 1024, 2048], index=1, key='game_batch')
            flash = st.toggle('Flash Attention', value=True, key='game_flash')
            kv = st.toggle('KV-cache на GPU', value=True, key='game_kv')
            load, unload = st.columns(2)
            if load.button('Загрузить', disabled=not model, key='game_load'):
                try:
                    with st.spinner('Загрузка модели…'):
                        unload_all_models()
                        load_model(model, context, batch, flash, kv)
                        st.session_state.game_loaded = get_loaded_models()
                except Exception as exc:
                    st.error(f'Ошибка загрузки: {exc}')
            if unload.button('Выгрузить', key='game_unload'):
                try:
                    unload_all_models()
                    st.session_state.game_loaded = []
                except Exception as exc:
                    st.error(f'Ошибка выгрузки: {exc}')
            for loaded in st.session_state.get('game_loaded', []):
                st.caption('Загружена: ' + str(loaded.get('display_name') or loaded.get('model_key')))
            st.slider('Temperature ведущего', 0.0, 1.5, 0.8, step=0.05, key='game_temperature')
            st.number_input('Max tokens ведущего', 256, 16000, 2000, step=256, key='game_max_tokens')
            st.caption('Параметры ведущего сохранены для подключения генерации игровых ходов.')
