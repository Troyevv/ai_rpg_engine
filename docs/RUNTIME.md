# Память, варианты и журнал запросов

## Поведение

- Действие игрока (выбранное или введённое) хранится в `turns.user_text` и показывается перед соответствующим ответом ведущего. Стартовая сцена не имеет действия игрока.
- После неудачной проверки evidence выполняется одна попытка исправить извлечение. Если отдельные цитаты снова не подтверждаются, только эти изменения исключаются. Предупреждение с исходными отклонёнными данными сохраняется в `game_jobs.warnings_json`. Остальные валидные изменения, сцена и 6 действий сохраняются атомарно. Неправильная структура, количество вариантов и прочие ошибки по-прежнему блокируют запись.
- Сценарист, Генератор и Ведущий имеют независимый Thinking Off/Low/High. Список поддерживающих моделей приходит из `/api/capabilities`. Неподдерживаемые модели игнорируют Thinking. Извлечение и память используют модель/Thinking Ведущего. Reasoning входит в лимит output, при Thinking temperature не передаётся.

## Ключ

Ключ сохраняется при сохранении настроек либо при первом запросе с ключом, шифруется Fernet и хранится в SQLite. Ответ API содержит только признак наличия; ключ не отправляется обратно браузеру и не попадает в localStorage, контекст, журнал запросов или Git. Можно заменить/удалить его в настройках. `DEEPSEEK_API_KEY` остаётся запасным источником.

Ключ шифрования — `.credential-key` рядом с БД. Для полного переноса установки сохраняйте этот файл вместе с БД; при его утрате секрет восстановить нельзя. Это защита от чтения одной копии БД, а не от доступа к учётной записи ОС. На сервере хранится один ключ провайдера для этой установки, общий для её браузеров. Приложение по-прежнему не является многопользовательским публичным сервисом с авторизацией.

## SQLite и граф вариантов

Аддитивная миграция выполняется автоматически и идемпотентно. Старые `before_json`/`after_json`, миры, сейвы и архивы не переписываются.

| Сущность | Назначение |
|---|---|
| `turns` | Текущая каноническая последовательность; `node_id`, `active_variant_id`, `memory_archived` |
| `response_variants` | Неизменяемые ответы с полным before/after, исходным контекстом, памятью, `job_id`, порядковым номером и `parent_variant_id` |
| `llm_requests` | Каждая фактическая попытка: stage, модель, Thinking, сообщения запроса, диагностика, usage, стоимость и снимок тарифа |
| `play_sessions` | Явные сессии учёта расходов одного прохождения |
| `memory_versions` | Неизменяемые выжимки и диапазон обработанных ходов, ссылки на исходные node_id и предыдущую версию |
| `provider_credentials` | Зашифрованный ключ провайдера |
| `archived_turns` | Полные удалённые из канонической последовательности ходы при откатах и замене |

`node_id` идентифицирует логический ход независимо от порядкового номера и переиспользования SQLite id после отката. Варианты ссылаются на конкретный родительский вариант, поэтому потомки альтернатив остаются различимыми. Сейчас `turns` — одна активная проекция графа; в будущем именованная ветка может хранить вершину пути и собственную проекцию, не меняя формат ответов.

Перегенерация берёт **сохранённые сообщения запроса**, память и состояние до первоначального ответа. Текущие промпты, новое содержимое памяти и более поздние ходы не подмешиваются в запрос ведущего. Модель и параметры генерации можно поменять; это отражается в отдельном request. Если сохранённый запрос не помещается в новую модель, операция отклоняется без обрезки.

Для исторического ответа требуется явное `rollback_following=true`. Последующие ходы переносятся в архив лишь при успешном коммите новой генерации/выбора варианта. Ошибка, отмена и конфликт revision сохраняют канон. Переключение вариантов не вызывает LLM и не списывает токены. Все прежние расходы остаются учтёнными.

У ходов, созданных **до этого обновления**, исходный запрос не сохранялся. Их нельзя достоверно восстановить задним числом: точная перегенерация таких ходов недоступна. Они остаются читаемыми и допускают обычное продолжение. Старые архивы тоже доступны, без выдуманного контекста/usage.

## Контекст и автоматическая память

Контекст состоит из именованных блоков: постоянные правила, исходная выжимка мира, релевантные NPC и отношения, компактная память завершённых событий, важные события/знания/планы, текущая сцена и локации, последние N ходов, задача текущего хода. N означает пары «игрок — ведущий», а не количество сообщений HTTP.

Перед новым ответом ходы за пределами N обрабатываются LLM пакетами ограниченного размера и превращаются в обновлённую выжимку до 8000 символов. Обычно после заполнения окна обрабатывается один новый старый ход; настройка размера пакета ограничивает объём одной обработки накопившейся истории. Это отдельные платные запросы `memory`. Предыдущая выжимка передаётся при обновлении. При ошибке или переполнении бюджета ход не коммитится, а старый сейв остаётся прежним.

Успешная память включается в снимок до генерации. После коммита соответствующие строки `turns` получают `memory_archived=1`; **их текст не удаляется** и по-прежнему виден в истории. Выбор варианта/откат восстанавливает его память и архивные признаки. В контекст попадают до 20 событий, 30 релевантных фактов, 20 открытых планов и 20 локаций плюс компактная выжимка; полные списки остаются в состоянии/журнале. При нехватке бюджета последние полные пары могут быть исключены; это видно в фактическом контексте. Основные блоки никогда не обрезаются молча.

Выжимка LLM может потерять нюансы: это не точное семантическое доказательство и не замена полного журнала. Версии и исходные сообщения сохраняются для дальнейшей проверки и улучшения памяти.

## Usage, стоимость, диагностика

Фактические input/output/cached input берутся из usage API, в том числе из последнего чанка с непустым `choices`. Каждый запрос сохраняется до обращения к провайдеру, включая неудачные и отменённые. Без usage счётчики и стоимость остаются NULL. При перезапуске незавершённые запросы помечаются interrupted. Локальные запросы имеют стоимость API 0, даже если сервер не отдаёт токены.

Стоимость USD рассчитывается Decimal: `(input-cached)*input_rate + cached*cache_rate + output*output_rate`, тарифы за миллион. Output уже включает reasoning, повторно reasoning не прибавляется. Снимок ставки, периода peak/off-peak и версии тарифа сохраняется у запроса. Неизвестная модель/неполный usage не получают выдуманной нулевой стоимости. Исторические ставки не пересчитываются автоматически.

Справочник DeepSeek проверен 2026-09-15: https://api-docs.deepseek.com/quick_start/pricing/ . Режимы Thinking: https://api-docs.deepseek.com/guides/thinking_mode . Streaming usage: https://api-docs.deepseek.com/api/create-chat-completion . Расчёт — оценка по опубликованному тарифу на момент начала запроса, не банковская выписка; кабинет провайдера авторитетнее. При изменении цен обновлять `backend/services/usage.py`, не старые записи.

Сессия расходов продолжается после закрытия вкладки/перезапуска до явной кнопки «Начать новую сессию». Итоги отдельно: сессия, всё прохождение и все прохождения данного мира. Расходы мастерской хранятся по workspace и видны отдельно. Неактивные варианты, ошибки, исправления evidence и память входят в расходы.

Панель «Контекст ведущего · Расходы» показывает реальные сохранённые запросы, используемые части памяти и оценки каждой части. Размер частей — консервативная UTF-8 оценка, **не точные токены модели**. Сумма частей плюс указанный служебный резерв даёт общий estimate. Фактический input и cache доступны после usage, cache по отдельным блокам API не сообщает. До первого запроса панель пуста; затем доступны также запросы незавершённых задач через «Обновить».

## API

- `GET/PUT/DELETE /api/credentials[/deepseek]`: наличие, запись и удаление секрета (GET без суффикса).
- `GET /api/capabilities`: поддержка Thinking по моделям.
- `GET /api/saves/{sid}/accounting`: расходы и журнал запросов.
- `POST /api/saves/{sid}/sessions`: начать следующую сессию расходов.
- `GET /api/workspaces/{wid}/requests`: запросы подготовки.
- `POST /api/saves/{sid}/turns`: дополнительно `target_turn_id`, `rollback_following` для regenerate.
- `POST /api/saves/{sid}/turns/{tid}/variant`: `variant_id`, `revision`, `rollback_following`.
- `GET /api/saves/{sid}/archive`: полный архив откатов.

Все бизнес-операции остаются в Python-сервисах/репозиториях без зависимости от FastAPI.

## Проверки этой версии

54 Python/API-теста: версии/исторический откат, атомарность, память и её снимки, usage/цены/сессии, ключ после перезапуска, evidence, миграция и существующие сценарии. 6 Playwright-проверок (desktop и Pixel 7): основной игровой цикл, disconnect/stop, ключ после reload, Thinking, выбранный/свободный ввод, историческая перегенерация, переключение варианта и расходы. TypeScript + production build проходят. LLM в проверках подменены; реальные платные запросы и Windows double-click не выполнялись.

## WorldDelta: validation and player agency

`apply_world_updates` validates JSON/Pydantic structure, then applies semantic
checks on a fresh copy of the before-state. Explicit `SecondaryDeltaError` instances authorize deterministic sanitization
on the FIRST extraction, without an LLM repair request. Only typed repairable
`StructuralDeltaError` failures get one repair. The repaired candidate uses
the same sanitizer; another structural failure is fatal. Unexpected validator
exceptions and explicitly unsafe failures never trigger repair. `sanitize_secondary` removes the validator's
exact record or field path, records its original index and reason, and the entire
candidate is validated again from the original state before commit. Unknown
exceptions, invalid types, IDs, scene/time conflicts and dependent references
remain fatal; they are never ignored by a broad exception handler.

The same removal mechanism handles knowledge without a transmission path,
unknown relationship dimensions, unsupported record evidence, and unconfirmed
controlled-actor fields. A character's invalid emotion does not discard their
valid location or situation. Warnings retain `section`, original `index`,
`entity`, removed `field` where applicable, and `reason`; `cause_field` identifies
an evidence failure when the whole record must be removed. Warnings are stored
on the job and shown through the active turn variant in Diagnostics.

For the controlled actor, goals, intentions, emotion and obligations require
explicit current `player_input`. Narrative, gestures, character cards and
previous events cannot authorize those changes. `player_evidence` optionally
provides field-specific quotes (a string for emotion; a list of quotes for newly
added list items); legacy extraction can use record `evidence` when it directly
confirms the same explicit player statement. This extraction metadata is not
copied into WorldState. Omitted fields and rejected fields preserve existing
values. New list items must preserve old items unless the player explicitly
replaces/cancels them. Direct player editing APIs remain independent of this LLM
validation and do not require narrative evidence.

Source checking is deliberately conservative and deterministic: it recognizes
explicit Russian declarations, literal values, and a limited set of surface
forms (e.g. «я злюсь» / «злится», placing «завтра» before/after an intention).
It is not a general natural-language entailment model. Unsupported paraphrases,
questions, conditional claims and quoted third-party speech are rejected for
omission with a warning, rather than guessed into canon. Open-vocabulary emotions can
be expressed literally via «я чувствую …» / «я испытываю …». Additional forms
must be added with both acceptance and false-positive regression tests.
Normal turns still use two mandatory LLM requests; validation and sanitization
run entirely in code.


Repair diagnostics are persisted on the job in `repair_diagnostics_json` and
joined through the active response variant (including after restart). Each
entry includes stage, error type/code and message, with available path metadata.
Extraction and repair output is saved once per actual request in
`llm_requests.response_text`, alongside the existing input snapshot and usage.
Diagnostics separates LLM repair from deterministic sanitization and shows
repair rate over the last 30 active turns; legacy turns without request logs
are excluded from the denominator and shown as unknown. Secondary warnings have
`type=sanitized_delta` and stable codes. No semantic dimension mapping or
additional mandatory LLM calls are introduced. The sanitizer revalidates from
the original state after every deletion, checks progress, and has a 4096-step
hard limit. Event-time membership now uses the temporal contract below.


## Intra-turn chronology

`scene` is the final camera snapshot, not a history of presence. Optional
`world_delta.transitions` describes only location/membership changes:
`actor_id`, absolute `minute`, `order` (default 0), `from_location`,
`to_location`, exact `evidence`. Null source is allowed only for unknown prior
locations. Events have optional `location` and `order`; when transitions exist,
the event minute is required. Operations replay by minute, order, then events
before movements at equal coordinates. Two movements of one actor at the same
coordinate are rejected; array order cannot change their meaning.

The validator starts from the pre-turn character positions. It checks each
participant/witness at event time, then checks final character locations and
final camera participants. Departed actors can retain knowledge and receive
source-backed character/relationship updates. A Character update alone cannot
prove involvement. Temporal failures remain typed structural errors, with
section/index/field metadata; they are never hidden by dropping events.

Locations are currently canonical text labels, not a registered location-ID
catalog. A known position cannot change without a sourced transition. Static
legacy extractions may omit transitions/order. An imported initial scene with
no spatial information can be bootstrapped as stationary; known before/after
snapshots are never unioned. Old saved turns are not rewritten. New transitions
remain in the saved delta/variant, without a new table or LLM stage.

Events reference immutable historical scene snapshots. Live camera scenes and
character scene pointers follow final positions; moving a character later must
not remove them from an event's historical membership. Narrative recordings
link all new events of their turn, even when the final camera moved elsewhere.
The same validator runs for ordinary, start, POV, observer and simulated turns.
