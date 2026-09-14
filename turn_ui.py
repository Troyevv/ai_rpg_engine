"""Game controls with a background worker and an editable draft during inference."""
import json
import streamlit as st
import engine
from engine_storage import ACTIVE
from state_updates import choice_input
from storage import Storage
from provider_ui import provider_config, api_key


def config():
    return {**provider_config('game', st.session_state.get('game_model')),
            'context_length': int(st.session_state.get('game_api_context', 32768) if st.session_state.get('game_provider') == 'deepseek' else st.session_state.get('game_context', 16384)),
            'temperature': float(st.session_state.get('game_temperature', 0.8)),
            'max_tokens': int(st.session_state.get('game_max_tokens', 2000)),
            'update_tokens': int(st.session_state.get('game_update_tokens', 4096))}


def start_turn(path, save_id, kind='turn', choice=None, expected_revision=None):
    try:
        player_input = choice_input(choice) if choice else st.session_state.get(f'player_draft_{save_id}', '')
        settings = config()
        if expected_revision is not None:
            settings['expected_revision'] = expected_revision
        engine.submit(Storage(path), save_id, player_input if kind != 'start' else '', kind, settings, api_key=api_key() if settings['provider'] == 'deepseek' else None)
        if kind == 'turn' and choice is None:
            st.session_state[f'player_draft_{save_id}'] = ''
    except Exception as exc:
        st.session_state.game_action_error = str(exc)


@st.fragment(run_every=0.5)
def watch_job(path, job_id):
    storage = Storage(path)
    job = storage.get_job(job_id)
    if job['status'] not in ACTIVE:
        st.rerun()
    labels = {'generating': 'Пишет продолжение…', 'extracting': 'Обновляет состояние и готовит 6 действий…', 'validating': 'Проверяет и сохраняет…'}
    st.info(labels[job['status']])
    if job['narrative']:
        with st.container(height=300):
            st.markdown(job['narrative'])
    if not engine.live(job_id):
        st.warning('Обработка не работает в этом процессе. Если приложение перезапускалось, останови черновик и повтори запрос.')
    if st.button('Остановить генерацию', key=f'stop_job_{job_id}'):
        engine.stop(storage, job_id)
        st.rerun()


def controls(storage, save, turns):
    save_id = save['id']
    job = storage.latest_job(save_id)
    active = job and job['status'] in ACTIVE
    error = st.session_state.pop('game_action_error', None)
    if error:
        st.error(error)
    if active:
        watch_job(str(storage.path), job['id'])
    elif job and job['status'] in ('error', 'stopped'):
        st.warning('Ход не сохранён. Состояние мира не изменилось.')
        if job['error']:
            st.error(job['error'])
        if job['narrative']:
            with st.expander('Черновик ответа', expanded=True):
                st.markdown(job['narrative'])
        if job['narrative_complete'] and job['revision'] == save['revision']:
            if st.button('Повторить обработку состояния', disabled=engine.live(job['id']), key=f'retry_job_{job["id"]}'):
                try:
                    engine.retry(storage, job['id'], config(), api_key=api_key())
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    if not turns:
        st.button('Начать игру', type='primary', disabled=bool(active), key=f'start_game_{save_id}',
                  on_click=start_turn, args=(str(storage.path), save_id, 'start', None, save['revision']))
    else:
        choices = json.loads(turns[-1]['choices_json'])
        if choices:
            st.caption('Выбери действие или напиши своё ниже.')
            columns = st.columns(2)
            for index, choice in enumerate(choices):
                label = '**' + choice['action'] + '**' + (': «' + choice['speech'] + '»' if choice['speech'] else '')
                columns[index % 2].button(label, key=f'choice_{turns[-1]["id"]}_{index}', disabled=bool(active),
                                          use_container_width=True, on_click=start_turn,
                                          args=(str(storage.path), save_id, 'turn', choice, save['revision']))
        regen, undo = st.columns(2)
        regen.button('Перегенерировать последний ход', key=f'regen_{save_id}', disabled=bool(active),
                     on_click=start_turn, args=(str(storage.path), save_id, 'regenerate', None, save['revision']))
        if undo.button('Откатить последний ход', key=f'undo_{save_id}', disabled=bool(active)):
            try:
                storage.rollback_last(save_id, save['revision'])
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    # The editor remains enabled during inference; only sending is blocked.
    st.text_area('Своё действие или реплика', key=f'player_draft_{save_id}', height=100,
                 placeholder='Что делает или говорит твой персонаж?')
    st.button('Отправить действие', type='primary', key=f'send_action_{save_id}',
              disabled=bool(active) or not turns, on_click=start_turn, args=(str(storage.path), save_id, 'turn', None, save['revision']))
