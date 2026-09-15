> Этот документ описывает исходный этап переноса со Streamlit. Последующее развитие памяти, ключей, вариантов и usage описано в [RUNTIME.md](RUNTIME.md).

# FastAPI + React: аудит и план миграции

## Источник истины
GitHub 15.09.2026: master 80333dc; DeepSeek ещё в открытом PR #2,
ветка codex/deepseek-provider 9d014b9. Миграция строится поверх PR #2.
Сверены Git blob SHA; два отличавшихся старых примера промптов восстановлены.

## Карта функционального паритета
- Сценарист: история требований, правки полного плана, streaming, stop/черновик,
  очистка, Markdown, скачивание.
- Выжимка: план + системный промпт + шаблон, отдельные параметры, streaming/stop,
  признак завершённости, скачивание, сохранение мира, импорт UTF-8 Markdown.
- Миры: версии/дедупликация, независимые прохождения, выбор основы либо сейва,
  исходный Markdown и метаданные.
- Игра: старт, шесть действий и свободный ввод, черновик во время генерации,
  stop, повтор извлечения, перегенерация/откат последнего хода, архив/revision guard.
- Инспектор: мир/локации, сцена и её редактор, персонажи/поиск/псевдонимы/рядом/
  prev-next, отношения и стрелки, тайны/знания/носители, сюжет/планы.
- Чтение: ссылки NPC, скрытие панелей, размер/интервал/ширина текста.
- LLM: локальный список/статус/load/unload, context/batch/flash/KV,
  Local/DeepSeek по задаче, API-ключ в памяти, API models, temperature/max tokens.

## Модули и связность
Оставить storage.py, engine_storage.py, world_parser.py, state_updates.py,
context_builder.py, character_links.py — независимая бизнес-логика/хранение.
engine.py оставить с общим координатором доступа к локальной модели.
llm.py расширить реестром OpenAI-compatible адаптеров.
Из scene_ui.py вынести scene_metadata; из generator_ui.py — сбор сообщений.
Session State сейчас хранит историю требований, текст/черновики генератора и
настройки; перенести первые в SQLite, настройки — в отдельные профили.
Все UI-модули Streamlit и ui/npc_links.* удалить только после browser-паритета.

## Целевые каталоги
backend/api — DTO, HTTP, SSE; backend/services — подготовка и координация задач;
backend/repositories — новые SQLite-таблицы. Существующие независимые корневые
модули остаются стабильными импортами: перенос ради каталогов не нужен.
frontend/src — typed API, SSE, экраны игры/подготовки/настроек, инспектор,
components/ui — shadcn; launcher.py + start.bat + stop.bat; tests; docs.

## Контракт /api
GET health; GET/POST worlds; GET worlds/{id}; GET/POST worlds/{id}/saves.
GET saves/{id} (state, turns, job); PATCH saves/{id}/scene;
POST saves/{id}/turns (kind, text, config, revision); POST .../rollback.
GET jobs/{id}; GET jobs/{id}/events; POST jobs/{id}/stop; POST .../retry.
GET/POST workspaces; GET workspaces/{id}; POST .../generate, .../reset, .../world.
GET/PUT settings/{profile}; POST models/list, models/load, models/unload.
POST markdown — безопасный Markdown и ссылки NPC. Точные DTO доступны /docs.
Ключ только в теле POST, никогда в URL, ответах или БД.

## SSE вместо WebSocket
Команды — HTTP, текст/статусы — SSE StreamingResponse. POST создаёт долговечный
job; GET events выдаёт актуальные снимки черновика при изменениях и heartbeat.
Reconnect заменяет текст свежим snapshot без дублей. Disconnect прекращает
наблюдение, но не генерацию; stop отдельной командой. Двусторонний realtime
протокол не нужен. https://fastapi.tiangolo.com/advanced/custom-response/

## SQLite / дальнейшее развитие
Остаются worlds, world_parts, saves, turns, game_jobs, archived_turns и путь
 data/rpg.sqlite3 (либо RPG_DB_PATH). Старые JSON не перепарсиваются, включая
старые сейвы с 7 персонажами. Только идемпотентные добавления таблиц
preparation_workspaces, preparation_jobs, client_settings; без удаления данных.
Состояние привязано к save_id/workspace_id, не к UI-сеансу. Transport не хранит
глобального player_id. Будущие POV, память, ветки — новые доменные команды,
не frontend state. Сейчас один backend process; масштабирование worker-ов
потребует общего координатора моделей. Удалённый публичный доступ требует auth/TLS.

## Этапы
1. Аудит и контракт (этот документ).
2. Добавить сервис подготовки и FastAPI рядом с рабочим Streamlit.
3. React production UI + launcher; оба запуска остаются доступны.
4. Проверить старую БД, сценарий→выжимка→мир→сейв→ход, stop/retry/rollback,
   SSE reconnect, локальные модели, desktop/mobile, production build.
5. После паритета удалить Streamlit/UI-тесты, сохранить доменные регрессии,
   добавить API/browser-тесты, обновить README/PR.

Новые игровые механики не реализуются. «Ветки» зарезервированы в типах
навигации, но не представлены как работающая функция.

## Результат проверки

- До удаления Streamlit прошли все 38 исходных регрессий.
- После переноса: 32 независимых Python/API/launcher теста.
- 4 Playwright проверки прошли на Chromium 153, desktop 1440×1000 и Pixel 7.
  Проверен полный пользовательский сценарий, повторный вход после reload,
  NPC-ссылки, шесть действий, свободный черновик во время ответа, чтение,
  перегенерация/откат, разрыв соединения и stop подготовки.
- Production build TypeScript/Vite проходит; внешний dev server не используется.
- Launcher в чистой .venv без Streamlit установил зависимости, собрал frontend,
  поднял сервер, отдал HTML и JS; повторный start не создал второй процесс,
  stop завершил только свой сервер по управляющему токену.
- Исходные JSON старой схемы с 7 персонажами и историей остались побайтно
  неизменными после двух последовательных инициализаций схемы.
- Проверена синтаксическая совместимость Python 3.10 и отсутствие импортов Streamlit.

Границы проверки: среда Linux; нативный двойной клик Windows bat не выполнялся.
LLM в тестах подменён; реальные LM Studio и платный DeepSeek не вызывались.
Chromium скачан через npm-дистрибутив, поскольку CDN Playwright был недоступен.
Тесты принимают PLAYWRIGHT_EXECUTABLE_PATH для такого окружения; обычный путь —
`npx playwright install chromium`.
