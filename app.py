import streamlit as st
from game_ui import render_game
from generator_ui import render_generator
import engine

st.set_page_config(page_title="AI RPG Engine", page_icon="🎭", layout="wide")
st.title("AI RPG Engine")
notice = st.session_state.pop("world_notice", None)
if notice:
    st.success(notice)

# Only write back settings whose widgets are hidden. Writing active settings
# makes Streamlit see both a Session State assignment and a widget default.
mode = st.session_state.get('app_mode', 'Генерация выжимки')
game_setting_keys = {
    'game_update_tokens', 'game_line_height', 'game_reading_width',
    'game_link_names', 'game_font_size', 'game_model', 'game_context',
    'game_batch', 'game_flash', 'game_kv', 'game_temperature', 'game_max_tokens',
}
local_keys = {'model', 'context', 'batch', 'flash', 'kv'}
game_local_hidden = st.session_state.get('game_provider', st.session_state.get('pref_game_provider')) == 'deepseek'
generator_local_hidden = all(st.session_state.get(f'gen_{task}_provider', 'local') == 'deepseek' for task in ('idea', 'summary'))
for key in list(st.session_state):
    if key.startswith(('gen_', 'save_picker_', 'player_draft_')) or key in {
        'game_update_tokens', 'game_line_height', 'game_reading_width', 'game_character_search', 'game_character_scope',
        'world_picker', 'game_selected_character', 'game_panel_section',
        'game_link_names', 'game_font_size', 'game_model', 'game_context',
        'game_batch', 'game_flash', 'game_kv', 'game_temperature', 'game_max_tokens',
    }:
        if key in game_setting_keys and mode == 'Игра' and not (game_local_hidden and key.removeprefix('game_') in local_keys):
            continue
        if key.startswith('gen_') and mode == 'Генерация выжимки' and not engine.busy() and not (generator_local_hidden and key.removeprefix('gen_') in local_keys):
            continue
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
