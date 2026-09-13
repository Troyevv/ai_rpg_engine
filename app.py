import streamlit as st
from game_ui import render_game
from generator_ui import render_generator

st.set_page_config(page_title="AI RPG Engine", page_icon="🎭", layout="wide")
st.title("AI RPG Engine")
notice = st.session_state.pop("world_notice", None)
if notice:
    st.success(notice)

pending = st.session_state.pop('pending_save', None)
if pending:
    world_id, save_id = pending
    st.session_state[f'save_picker_{world_id}'] = save_id

generator_tab, game_tab = st.tabs(["Генерация выжимки", "Игра"])
# Render the browser first so worlds remain usable even if generator setup fails.
with game_tab:
    render_game()
with generator_tab:
    render_generator()
