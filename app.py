import streamlit as st
from game_ui import render_game
from generator_ui import render_generator

st.set_page_config(page_title="AI RPG Engine", page_icon="🎭", layout="wide")
st.title("AI RPG Engine")
notice = st.session_state.pop("world_notice", None)
if notice:
    st.success(notice)

# Preserve mode-specific widget choices when their tab/panel is not mounted.
for key in list(st.session_state):
    if key.startswith(('gen_', 'save_picker_')) or key in {
        'world_picker', 'game_selected_character', 'game_panel_section',
        'game_link_names', 'game_font_size', 'game_model', 'game_context',
        'game_batch', 'game_flash', 'game_kv', 'game_temperature', 'game_max_tokens',
    }:
        st.session_state[key] = st.session_state[key]

pending = st.session_state.pop('pending_save', None)
if pending:
    world_id, save_id = pending
    st.session_state[f'save_picker_{world_id}'] = save_id

generator_tab, game_tab = st.tabs(["Генерация выжимки", "Игра"], key='app_mode', on_change='rerun')
# Mount only the active mode so left-side controls never mix.
if generator_tab.open:
    with generator_tab:
        render_generator()
if game_tab.open:
    with game_tab:
        render_game()
