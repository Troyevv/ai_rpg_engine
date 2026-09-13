import streamlit as st


def toggle_reading():
    enabled = not st.session_state.get('game_reading', False)
    st.session_state.game_reading = enabled
    if enabled:
        st.session_state.game_panel_before_reading = st.session_state.get('game_panel_open', True)
        st.session_state.game_panel_open = False
    else:
        st.session_state.game_panel_open = st.session_state.get('game_panel_before_reading', True)


def reading_controls():
    enabled = st.session_state.get('game_reading', False)
    st.button('Выйти из чтения' if enabled else 'Режим чтения', key='reading_toggle', on_click=toggle_reading)
    with st.popover('Настройки текста'):
        st.slider('Размер текста', 14, 24, 17, key='game_font_size')
        st.slider('Межстрочный интервал', 1.3, 2.2, 1.7, step=0.1, key='game_line_height')
        st.slider('Ширина текста при чтении', 600, 1100, 800, step=50, key='game_reading_width')
    if enabled:
        width = int(st.session_state.get('game_reading_width', 800))
        st.html(f'''<style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{display:none !important;}}
        .st-key-game_chat_scroll {{max-width: {width}px; margin-inline: auto;}}
        </style>''')
