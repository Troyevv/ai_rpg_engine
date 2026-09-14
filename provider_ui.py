"""Independent provider settings; credentials never enter save/job config."""
import streamlit as st
from llm import deepseek_key, get_deepseek_models


def remember(key):
    st.session_state['pref_' + key] = st.session_state[key]


def setting(widget, label, key, default, **kwargs):
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get('pref_' + key, default)
    return widget(label, key=key, on_change=remember, args=(key,), **kwargs)


def api_key():
    return st.session_state.get('deepseek_api_key', st.session_state.get('pref_deepseek_api_key', ''))


def render_credentials():
    setting(st.text_input, 'API-ключ DeepSeek', 'deepseek_api_key', '', type='password',
            help='Можно оставить пустым, если задана переменная DEEPSEEK_API_KEY. Ключ не сохраняется в SQLite.')
    st.caption('Выбранные для DeepSeek запросы отправляются в API DeepSeek.')
    if st.button('Обновить модели DeepSeek', key='refresh_deepseek'):
        try:
            st.session_state.deepseek_models = get_deepseek_models(api_key())
            st.success('Соединение с DeepSeek установлено.')
        except Exception as exc:
            st.error(str(exc))
    if st.session_state.get('deepseek_models'):
        st.caption('Доступны: ' + ', '.join(st.session_state.deepseek_models))


def render_provider(prefix, label):
    disabled = prefix.startswith('gen_') and st.session_state.get('generation_mode') is not None
    provider = setting(st.selectbox, label, prefix + '_provider', 'local',
                       options=['local', 'deepseek'], disabled=disabled,
                       format_func=lambda value: 'Локальная модель (LM Studio)' if value == 'local' else 'DeepSeek API')
    if provider == 'deepseek':
        setting(st.text_input, 'Модель DeepSeek', prefix + '_api_model', 'deepseek-flash', disabled=disabled,
                help='Идентификатор модели из списка DeepSeek; можно указать другой доступный ID.')
    return provider


def provider_config(prefix, local_model):
    provider = st.session_state.get(prefix + '_provider', 'local')
    return {'provider': provider,
            'model': st.session_state.get(prefix + '_api_model', 'deepseek-flash').strip() if provider == 'deepseek' else local_model}


def ready(config, local_check):
    if not config['model']:
        st.error('Выбери модель в настройках.')
        return False
    if config['provider'] == 'local':
        if local_check(config['model']):
            return True
        st.error('Сначала загрузи выбранную локальную модель кнопкой «Загрузить».')
        return False
    try:
        deepseek_key(api_key())
        return True
    except ValueError as exc:
        st.error(str(exc))
        return False
