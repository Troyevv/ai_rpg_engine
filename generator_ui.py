from pathlib import Path

import streamlit as st

from game_ui import save_summary_form

from llm import (
    chat_stream,
    find_loaded_model,
    get_available_models,
    get_loaded_models,
    load_model,
    unload_all_models,
)


# =========================================================
# Paths
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

IDEA_PROMPT_PATH = (
    BASE_DIR
    / "prompts"
    / "idea_prompt.md"
)

SUMMARY_PROMPT_PATH = (
    BASE_DIR
    / "prompts"
    / "summary_prompt.md"
)

SUMMARY_TEMPLATE_PATH = (
    BASE_DIR
    / "prompts"
    / "summary_template.md"
)


# =========================================================
# Helpers
# =========================================================

def load_text_file(
    path: Path,
) -> str:

    if not path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {path}"
        )

    return path.read_text(
        encoding="utf-8"
    )


def reset_game():

    st.session_state.idea_messages = []

    st.session_state.idea = ""
    st.session_state.summary = ""
    st.session_state.summary_complete = False

    st.session_state.generation_mode = None

    st.session_state.partial_idea = ""
    st.session_state.partial_summary = ""


def build_idea_messages() -> list[dict]:

    messages = [
        {
            "role": "system",
            "content": IDEA_PROMPT,
        }
    ]

    if st.session_state.idea:

        messages.append(
            {
                "role": "system",
                "content": f"""
Ниже находится ТЕКУЩИЙ СЦЕНАРНЫЙ ПЛАН.

Он является актуальной версией концепции игры.

Если пользователь просит изменить,
дополнить или переработать что-либо:

- внеси требуемые изменения;
- сохрани остальные решения;
- обнови связанные элементы;
- проверь внутреннюю непротиворечивость;
- снова верни ПОЛНЫЙ сценарный план.

--- НАЧАЛО ТЕКУЩЕГО ПЛАНА ---

{st.session_state.idea}

--- КОНЕЦ ТЕКУЩЕГО ПЛАНА ---
""".strip(),
            }
        )

    for message in (
        st.session_state.idea_messages
    ):
        if message["role"] == "user":
            messages.append(
                message
            )

    return messages


def build_summary_messages() -> list[dict]:

    return [
        {
            "role": "system",
            "content": SUMMARY_PROMPT,
        },
        {
            "role": "user",
            "content": f"""
Создай полную выжимку ролевой игры
на основе следующего сценарного плана.

==================================================
СЦЕНАРНЫЙ ПЛАН
==================================================

{st.session_state.idea}

==================================================
ОБЯЗАТЕЛЬНЫЙ ШАБЛОН
==================================================

{SUMMARY_TEMPLATE}

==================================================
ЗАДАЧА
==================================================

Используй сценарный план как основной источник фактов.

Раскрой его подробно и естественно.

Не меняй основные сценарные решения.

Не добавляй дополнительных ключевых персонажей.

В разделе "КЛЮЧЕВЫЕ NPC" должно остаться
ровно 7 ключевых персонажей вместе с главным героем.

Строго соблюдай структуру шаблона.

Верни только готовую полную выжимку в Markdown.
""".strip(),
        },
    ]


def format_bool(
    value,
):
    return (
        "Да"
        if value
        else "Нет"
    )


def render_loaded_model_info():

    try:
        loaded_models = (
            get_loaded_models()
        )

    except Exception as e:
        st.caption(
            f"Не удалось получить статус: {e}"
        )
        return

    if not loaded_models:

        st.caption(
            "В памяти сейчас нет модели."
        )

        return

    for loaded in loaded_models:

        config = loaded.get(
            "config",
            {},
        )

        name = (
            loaded.get("display_name")
            or loaded.get("model_key")
            or "Модель"
        )

        st.success(
            f"Загружена: {name}"
        )

        context_length = config.get(
            "context_length"
        )

        eval_batch_size = config.get(
            "eval_batch_size"
        )

        flash_attention = config.get(
            "flash_attention"
        )

        kv_gpu = config.get(
            "offload_kv_cache_to_gpu"
        )

        if context_length is not None:
            st.caption(
                "Контекст: "
                f"{context_length:,} токенов"
            )

        if eval_batch_size is not None:
            st.caption(
                f"Eval batch: {eval_batch_size}"
            )

        if flash_attention is not None:
            st.caption(
                "Flash Attention: "
                f"{format_bool(flash_attention)}"
            )

        if kv_gpu is not None:
            st.caption(
                "KV-cache на GPU: "
                f"{format_bool(kv_gpu)}"
            )


def ensure_selected_model_loaded(
    model: str,
) -> dict | None:

    try:
        return find_loaded_model(
            model
        )

    except Exception as e:

        st.error(
            f"Не удалось проверить модель: {e}"
        )

        return None


def render_generator():
    import engine
    if engine.busy():
        st.info('Идёт игровой ход. Дождись завершения или останови его во вкладке «Игра».')
        return
    global IDEA_PROMPT, SUMMARY_PROMPT, SUMMARY_TEMPLATE
    # =========================================================
    # Prompts
    # =========================================================

    try:

        IDEA_PROMPT = load_text_file(
            IDEA_PROMPT_PATH
        )

        SUMMARY_PROMPT = load_text_file(
            SUMMARY_PROMPT_PATH
        )

        SUMMARY_TEMPLATE = load_text_file(
            SUMMARY_TEMPLATE_PATH
        )

    except Exception as e:

        st.error(
            str(e)
        )

        st.stop()


    # =========================================================
    # State
    # =========================================================

    if "idea_messages" not in st.session_state:
        st.session_state.idea_messages = []

    if "idea" not in st.session_state:
        st.session_state.idea = ""

    if "summary_complete" not in st.session_state:
        st.session_state.summary_complete = False

    if "summary" not in st.session_state:
        st.session_state.summary = ""

    if "generation_mode" not in st.session_state:
        st.session_state.generation_mode = None

    if "partial_idea" not in st.session_state:
        st.session_state.partial_idea = ""

    if "partial_summary" not in st.session_state:
        st.session_state.partial_summary = ""


    # =========================================================
    # LM Studio
    # =========================================================

    try:

        available_models = (
            get_available_models()
        )

    except Exception as e:

        st.error(
            "Не удалось подключиться к LM Studio.\n\n"
            "Проверь, что Local Server запущен "
            "на http://localhost:1234"
        )

        st.code(
            str(e)
        )

        available_models = []


    if not available_models:

        st.warning(
            "LM Studio не вернул ни одной модели."
        )



    # =========================================================
    # Sidebar
    # =========================================================

    with st.sidebar:

        st.header(
            "LM Studio"
        )

        selected_model = st.selectbox(
            "Модель",
            available_models,
            key="gen_model",
        )

        st.subheader(
            "Загрузка"
        )

        context_length = st.selectbox(
            "Контекст",
            key="gen_context",
            options=[
                8192,
                16384,
                32768,
            ],
            index=1,
            format_func=lambda x: (
                f"{x:,} токенов"
            ),
        )

        eval_batch_size = st.selectbox(
            "Eval Batch Size",
            key="gen_batch",
            options=[
                256,
                512,
                1024,
                2048,
            ],
            index=1,
        )

        flash_attention = st.toggle(
            "Flash Attention",
            key="gen_flash",
            value=True,
        )

        kv_cache_gpu = st.toggle(
            "KV-cache на GPU",
            key="gen_kv",
            value=True,
        )

        load_col, unload_col = (
            st.columns(2)
        )

        with load_col:

            if st.button(
                "Загрузить",
                use_container_width=True,
                type="primary",
                disabled=(
                    not available_models or st.session_state.generation_mode
                    is not None
                ),
            ):

                try:

                    unload_all_models()

                    with st.spinner(
                        "Загрузка модели..."
                    ):

                        load_model(
                            model=selected_model,
                            context_length=int(
                                context_length
                            ),
                            eval_batch_size=int(
                                eval_batch_size
                            ),
                            flash_attention=(
                                flash_attention
                            ),
                            offload_kv_cache_to_gpu=(
                                kv_cache_gpu
                            ),
                        )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Ошибка загрузки: {e}"
                    )

        with unload_col:

            if st.button(
                "Выгрузить",
                use_container_width=True,
                disabled=(
                    st.session_state.generation_mode
                    is not None
                ),
            ):

                try:

                    unload_all_models()

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Ошибка выгрузки: {e}"
                    )

        st.divider()

        render_loaded_model_info()

        st.divider()

        st.subheader(
            "Генерация"
        )

        idea_temperature = st.slider(
            "Temperature сценариста",
            key="gen_idea_temperature",
            min_value=0.0,
            max_value=1.5,
            value=1.0,
            step=0.05,
        )

        summary_temperature = st.slider(
            "Temperature выжимки",
            key="gen_summary_temperature",
            min_value=0.0,
            max_value=1.5,
            value=0.8,
            step=0.05,
        )

        idea_max_tokens = st.number_input(
            "Max tokens сценариста",
            key="gen_idea_max_tokens",
            min_value=1000,
            max_value=16000,
            value=6000,
            step=1000,
        )

        summary_max_tokens = st.number_input(
            "Max tokens выжимки",
            key="gen_summary_max_tokens",
            min_value=2000,
            max_value=32000,
            value=12000,
            step=1000,
        )

        st.divider()

        if st.button(
            "Очистить сценарий и выжимку",
            use_container_width=True,
            disabled=(
                st.session_state.generation_mode
                is not None
            ),
        ):

            reset_game()
            st.rerun()

        if st.session_state.idea:

            st.download_button(
                "Скачать сценарный план",
                data=st.session_state.idea,
                file_name="idea.md",
                mime="text/markdown",
                use_container_width=True,
            )

        if st.session_state.summary:

            st.download_button(
                "Скачать выжимку",
                data=st.session_state.summary,
                file_name="summary.md",
                mime="text/markdown",
                use_container_width=True,
            )


    # =========================================================
    # Columns
    # =========================================================

    idea_column, summary_column = st.columns(
        [1, 1],
        gap="large",
    )


    # =========================================================
    # Scenario
    # =========================================================

    with idea_column:

        st.header(
            "1. Сценарий"
        )

        st.caption(
            "Маленькая модель разрабатывает "
            "персонажей, отношения, завязку, "
            "локации и открытые линии."
        )

        # -----------------------------------------------------
        # Generation in progress
        # -----------------------------------------------------

        if (
            st.session_state.generation_mode
            == "idea"
        ):

            if st.button(
                "⏹ Остановить генерацию",
                key="stop_idea",
                type="primary",
                use_container_width=True,
            ):

                # Сохраняем то, что уже успело
                # сгенерироваться.
                if (
                    st.session_state.partial_idea
                    .strip()
                ):
                    st.session_state.idea = (
                        st.session_state.partial_idea
                    )

                st.session_state.partial_idea = ""

                st.session_state.generation_mode = None

                # Старая выжимка всё равно
                # уже не актуальна.
                st.session_state.summary = ""

                st.rerun()

        # -----------------------------------------------------
        # Completed result
        # -----------------------------------------------------

        elif st.session_state.idea:

            with st.status(
                "Сценарий готов",
                state="complete",
                expanded=False,
            ):

                st.markdown(
                    st.session_state.idea
                )

        else:

            st.info(
                "Напиши коротко, какую игру хочешь.\n\n"
                "Например: современность, компания друзей, "
                "ГГ 24 года, бытовые сцены, "
                "юмор и романтика."
            )

        if st.session_state.idea_messages:

            with st.expander(
                "История требований",
                expanded=False,
            ):

                for message in (
                    st.session_state.idea_messages
                ):

                    if (
                        message["role"]
                        == "user"
                    ):

                        with st.chat_message(
                            "user"
                        ):

                            st.markdown(
                                message[
                                    "content"
                                ]
                            )


    # =========================================================
    # Summary
    # =========================================================

    with summary_column:

        st.header(
            "2. Выжимка"
        )

        st.caption(
            "После утверждения сценария "
            "выгрузи маленькую модель, "
            "загрузи Mistral и создай выжимку."
        )

        if (
            st.session_state.generation_mode
            == "summary"
        ):

            if st.button(
                "⏹ Остановить генерацию",
                key="stop_summary",
                type="primary",
                use_container_width=True,
            ):

                if (
                    st.session_state.partial_summary
                    .strip()
                ):
                    st.session_state.summary = (
                        st.session_state.partial_summary
                    )

                st.session_state.partial_summary = ""

                st.session_state.generation_mode = None
                st.session_state.summary_complete = False

                st.rerun()

        elif st.session_state.summary:

            with st.status(
                "Выжимка готова" if st.session_state.summary_complete else "Черновик выжимки",
                state="complete",
                expanded=False,
            ):

                st.markdown(
                    st.session_state.summary
                )

            if st.session_state.summary_complete:
                save_summary_form(st.session_state.summary, "save_generated_world")
            else:
                st.warning("Генерация не завершена. Черновик можно скачать; для сохранения мира заверши генерацию.")

        elif st.session_state.idea:

            st.info(
                "Сценарий готов.\n\n"
                "1. Выгрузи маленькую модель.\n"
                "2. Выбери Mistral.\n"
                "3. Выбери 16K или 32K контекст.\n"
                "4. Нажми «Загрузить».\n"
                "5. Нажми «Создать выжимку»."
            )

        else:

            st.info(
                "Сначала создай сценарный план."
            )

        if (
            st.session_state.idea
            and st.session_state.generation_mode
            is None
        ):

            if st.button(
                "Создать выжимку",
                use_container_width=True,
                type="primary",
                key="start_summary",
            ):

                loaded_model = (
                    ensure_selected_model_loaded(
                        selected_model
                    )
                )

                if not loaded_model:

                    st.error(
                        "Сначала загрузите выбранную "
                        "модель кнопкой «Загрузить»."
                    )

                else:

                    st.session_state.partial_summary = ""
                    st.session_state.summary_complete = False

                    st.session_state.generation_mode = (
                        "summary"
                    )

                    st.rerun()


    # =========================================================
    # Scenario input
    # =========================================================

    idea_input = st.chat_input(
        "Опиши идею игры или напиши, что изменить...",
        disabled=(
            st.session_state.generation_mode
            is not None
        ),
    )


    if idea_input:

        loaded_model = (
            ensure_selected_model_loaded(
                selected_model
            )
        )

        if not loaded_model:

            st.error(
                "Сначала загрузите выбранную модель "
                "кнопкой «Загрузить»."
            )

            st.stop()

        st.session_state.idea_messages.append(
            {
                "role": "user",
                "content": idea_input,
            }
        )

        st.session_state.partial_idea = ""

        st.session_state.generation_mode = (
            "idea"
        )

        st.rerun()


    # =========================================================
    # Run scenario generation
    # =========================================================

    if (
        st.session_state.generation_mode
        == "idea"
    ):

        with idea_column:

            with st.status(
                "Сценарист работает...",
                expanded=True,
            ) as status:

                output_placeholder = st.empty()

                generated_text = (
                    st.session_state.partial_idea
                )

                try:

                    for chunk in chat_stream(
                        model=selected_model,
                        messages=build_idea_messages(),
                        temperature=idea_temperature,
                        max_tokens=int(
                            idea_max_tokens
                        ),
                    ):

                        generated_text += chunk

                        # Сохраняем постоянно,
                        # чтобы при Stop не потерять
                        # уже полученный текст.
                        st.session_state.partial_idea = (
                            generated_text
                        )

                        # Главное отличие от write_stream:
                        # настоящий Markdown.
                        output_placeholder.markdown(
                            generated_text
                        )

                    if not generated_text.strip():

                        raise RuntimeError(
                            "Сценарист вернул пустой ответ."
                        )

                    st.session_state.idea = (
                        generated_text
                    )

                    st.session_state.partial_idea = ""

                    st.session_state.summary = ""

                    st.session_state.generation_mode = None

                    status.update(
                        label="Сценарий готов",
                        state="complete",
                        expanded=False,
                    )

                    st.rerun()

                except Exception as e:

                    # Если run был остановлен кнопкой,
                    # Streamlit сам прервёт выполнение.
                    # Обычные ошибки покажем пользователю.

                    status.update(
                        label="Ошибка генерации сценария",
                        state="error",
                        expanded=True,
                    )

                    st.error(
                        f"Ошибка сценариста: {e}"
                    )

                    st.session_state.generation_mode = None


    # =========================================================
    # Run summary generation
    # =========================================================

    if (
        st.session_state.generation_mode
        == "summary"
    ):

        with summary_column:

            with st.status(
                "Генератор выжимки работает...",
                expanded=True,
            ) as status:

                output_placeholder = st.empty()

                generated_text = (
                    st.session_state.partial_summary
                )

                try:

                    for chunk in chat_stream(
                        model=selected_model,
                        messages=build_summary_messages(),
                        require_complete=True,
                        temperature=summary_temperature,
                        max_tokens=int(
                            summary_max_tokens
                        ),
                    ):

                        generated_text += chunk

                        st.session_state.partial_summary = (
                            generated_text
                        )

                        # Markdown обрабатывается
                        # на каждом обновлении.
                        output_placeholder.markdown(
                            generated_text
                        )

                    if not generated_text.strip():

                        raise RuntimeError(
                            "Генератор выжимки "
                            "вернул пустой ответ."
                        )

                    st.session_state.summary = (
                        generated_text
                    )
                    st.session_state.summary_complete = True

                    st.session_state.partial_summary = ""

                    st.session_state.generation_mode = None

                    status.update(
                        label="Выжимка готова",
                        state="complete",
                        expanded=False,
                    )

                    st.rerun()

                except Exception as e:

                    status.update(
                        label="Ошибка генерации выжимки",
                        state="error",
                        expanded=True,
                    )

                    st.error(
                        "Ошибка генератора "
                        f"выжимки: {e}"
                    )

                    st.session_state.summary = generated_text
                    st.session_state.summary_complete = False
                    st.session_state.generation_mode = None
