"""Scene facts are explicit metadata; mentions never imply presence."""
import re
import streamlit as st
from chat_ui import open_character


def scene_metadata(state):
    if isinstance(state.get('scene_meta'), dict):
        meta = state['scene_meta']
        known = {c['id'] for c in state['characters']}
        return {'time': str(meta.get('time', '')), 'location': str(meta.get('location', '')),
                'present_ids': [cid for cid in meta.get('present_ids', []) if cid in known]}
    text = state.get('scene', '')
    values = {}
    for key, labels in [('time', 'Время'), ('location', 'Место|Локация'), ('nearby', 'Рядом|Присутствуют')]:
        match = re.search(r'(?mi)^\s*(?:[-*·]\s*)?(?:\*\*)?(?:' + labels + r')\s*:(?:\*\*)?\s*([^\n]+)', text)
        values[key] = match[1].strip() if match else ''
    if not values['time']:
        times = set(re.findall(r'\b(?:[01]?\d|2[0-3]):[0-5]\d\b', text))
        if len(times) == 1:
            values['time'] = next(iter(times))
    names = {n.strip().casefold() for n in re.split(r'[,;]', values['nearby'])}
    present = [c['id'] for c in state['characters'] if c['name'].casefold() in names]
    return {'time': values['time'], 'location': values['location'], 'present_ids': present}


def render_scene_bar(state):
    meta = scene_metadata(state)
    with st.container(border=True, key='game_scene_bar'):
        time, place, nearby = st.columns([1, 1.5, 2])
        time.caption('Время')
        time.write(meta['time'] or 'Не указано')
        place.caption('Место')
        place.write(meta['location'] or 'Не указано')
        with nearby:
            st.caption('Рядом')
            characters = [c for c in state['characters'] if c['id'] in meta['present_ids'] and not c.get('is_player')]
            if not characters:
                st.write('Никого' if 'scene_meta' in state or meta['present_ids'] else 'Не указано')
            for character in characters:
                st.button(character['name'], key=f'nearby_{character["id"]}',
                          on_click=open_character, args=(character['id'], state['characters']))


def render_scene_editor(storage, save):
    if not save:
        st.caption('Создай прохождение, чтобы уточнить время, место и присутствующих.')
        return
    state = save['state']
    meta = scene_metadata(state)
    characters = {c['id']: c['name'] for c in state['characters']}
    with st.expander('Уточнить строку сцены'):
        with st.form(f'scene_meta_{save["id"]}'):
            time = st.text_input('Время', value=meta['time'], max_chars=120)
            location = st.text_input('Место', value=meta['location'], max_chars=200)
            present = st.multiselect('Присутствующие (включая ГГ)', list(characters), default=meta['present_ids'],
                                    format_func=lambda cid: characters[cid])
            submit = st.form_submit_button('Сохранить строку сцены')
        if submit:
            storage.update_scene_meta(save['id'], {'time': time.strip(), 'location': location.strip(), 'present_ids': present})
            st.rerun()
