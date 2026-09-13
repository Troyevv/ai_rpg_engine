from pathlib import Path
import streamlit as st
import streamlit.components.v2 as components
from character_links import linked_markdown
from turn_ui import controls

UI = Path(__file__).resolve().parent / 'ui'


def open_character(character_id, characters):
    if character_id not in {character['id'] for character in characters}:
        return False
    st.session_state.game_selected_character = character_id
    st.session_state.game_panel_section = 'Персонажи'
    st.session_state.game_character_search = ''
    st.session_state.game_character_scope = 'Все'
    st.session_state.game_panel_open = True
    return True


def narrative(text, characters, key, context):
    def on_character():
        if st.session_state.get('game_active_context') != context:
            return
        event = st.session_state.get(key, {})
        open_character(event.get('character'), characters)

    npc_links = components.component('rpg_npc_links', js=(UI / 'npc_links.js').read_text(),
                                      css=(UI / 'npc_links.css').read_text())
    npc_links(data={'html': linked_markdown(text, characters if st.session_state.get('game_link_names', True) else []),
                    'font_size': st.session_state.get('game_font_size', 17),
                    'line_height': st.session_state.get('game_line_height', 1.7)}, key=key,
              on_character_change=on_character)


def render_chat(storage, world, save):
    state = save['state'] if save else world['state']
    context = (world['id'], save['id'] if save else None)
    identity = f"{world['id']}_{save['id'] if save else 'world'}"
    st.subheader('Игровой чат')
    turns = storage.list_turns(save['id']) if save else []
    with st.container(height=600, key='game_chat_scroll'):
        if not turns:
            st.caption('Исходная ситуация')
            with st.chat_message('assistant'):
                narrative(world['state']['scene'], state['characters'], f'scene_{identity}', context)
        for turn in turns:
            if turn['kind'] != 'start':
                with st.chat_message('user'):
                    narrative(turn['user_text'], state['characters'], f'user_{identity}_{turn["id"]}', context)
            with st.chat_message('assistant'):
                narrative(turn['assistant_text'], state['characters'], f'assistant_{identity}_{turn["id"]}', context)
    if save:
        controls(storage, save, turns)
    else:
        st.info('Создай прохождение в правой панели, затем нажми «Начать игру».')
