import streamlit as st
from scene_ui import scene_metadata


def move_character(ids, step):
    current = st.session_state.get('game_selected_character')
    position = ids.index(current) if current in ids else 0
    st.session_state.game_selected_character = ids[(position + step) % len(ids)]


def choose_character(state):
    query = st.text_input('Найти персонажа', key='game_character_search', placeholder='Имя или прозвище').strip().casefold()
    scope = st.radio('Показать персонажей', ['Все', 'Рядом'], horizontal=True, key='game_character_scope')
    present = scene_metadata(state)['present_ids']
    characters = {c['id']: c for c in state['characters']
                  if (not query or query in ' '.join([c['name'], *c.get('aliases', [])]).casefold())
                  and (scope != 'Рядом' or c['id'] in present)}
    if not characters:
        st.info('Персонажи не найдены. Измени поиск или фильтр.')
        return None
    ids = list(characters)
    if st.session_state.get('game_selected_character') not in characters:
        st.session_state.game_selected_character = ids[0]
    previous, following = st.columns(2)
    previous.button('← Назад', key='character_previous', disabled=len(ids) < 2,
                    on_click=move_character, args=(ids, -1))
    following.button('Вперёд →', key='character_next', disabled=len(ids) < 2,
                     on_click=move_character, args=(ids, 1))
    character_id = st.selectbox('Персонаж', ids, key='game_selected_character',
                                format_func=lambda cid: characters[cid]['name'])
    st.caption(f'{ids.index(character_id) + 1} из {len(ids)}')
    return characters[character_id]


def relationship_change(relationship):
    change = relationship.get('change')
    if not isinstance(change, dict):
        return None
    direction = change.get('direction')
    reason = str(change.get('reason') or '').strip()
    if direction not in ('up', 'down') or not reason:
        return None
    return direction, reason, change.get('turn')
