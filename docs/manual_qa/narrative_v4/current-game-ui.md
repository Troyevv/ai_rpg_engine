> Updated phone contract and **public DOB/family policy**: [current acceptance report](phone-contract-public-family.md). Conflicting historical visibility expectations below are superseded.

# Issue 45 implementation and preservation plan

**Текущий результат: [итоговая приёмка PR #120](#pr120-final-acceptance).** Более ранние прогоны ниже сохранены как история; итоговая матрица заменяет промежуточный статус и прежние ограничения телефона.

Base: master 318a8f1, includes merged #116 (ffddf3f) and completed #44.

## Navigation and ownership
Desktop: existing shell → current-save “Игра” → Time / Characters / Chronology / Settings.
Mobile: same entry → full-width sheet → one selected destination. Scene fixation stays above story.
Phone: one mounted edge device → expanded nonmodal device → same edge device. Incoming calls never open it automatically.
#45 owns controls/calendar/phone and initial genealogy. #83 will refine the same genealogy/dossier; #86 retains the single Inspector width; #87 reading surface and #72 streaming remain untouched.

| Existing feature | Integration boundary |
| --- | --- |
| Time Skip / LTA | Existing components and endpoints, distinct operations |
| permanent / temporary / observe | Existing protagonist and camera services, no dialogue commands |
| pacing / risk / outcomes | Existing NarrativePolicy and revision guards |
| portraits | Existing PortraitControl, shared authorized asset API |
| genealogy | Existing knowledge-filtered server projection |
| global provider / theme | Existing Settings unchanged |
| relationship notices | Existing local preference and key, one control in current-game settings |
| Tabletop | No changes to its screens or rules |

## Dependency audit
Existing Motion 12 (MIT), Radix Dialog 1 (MIT), Lucide and skin tokens are reused. No new design system.
FullCalendar React evaluated: capable event scheduler but its editing/resource features and Gregorian date model are unnecessary for a read-only arbitrary-calendar projection.
React DayPicker 9 (MIT) adopted behind Calendar adapter for Gregorian keyboard navigation/localized month grids. Custom profiles retain server day/weekday arithmetic; no JS Date interpretation of fictional dates. Year overview is bounded monthly navigation, not an event store.
React Flow 12 (MIT) and Dagre 1 (MIT) provide graph navigation and bounded layout; only authorized graph nodes enter them. No persisted graph state. Added libraries add frontend bundle cost; lazy loading is preferred for secondary views.

## Interaction policy / state matrix
Modal Current Game/calendar/protagonist/Inspector takes priority over nonmodal phone. Opening a modal collapses the device, preserving per-actor per-conversation drafts in component memory. Escape collapses phone and restores its trigger; modal Escape belongs to Radix. Incoming notifications never steal focus. Generation locks canonical commands, not browsing. No panel opening submits a turn. Phone is outside story flow; scroll and game input drafts survive.

| Surface | States to exercise |
| --- | --- |
| phone | peek, unread, ringing, answered, expanded, keyboard, reduced motion, actor change |
| calendar | unknown date, empty, birthday, pending/resolved/cancelled/rescheduled, custom calendar |
| protagonist | active, incapacitated, dead, observer, temporary control |
| portrait | missing, upload, crop, error, history, original viewer |

Use existing #78 isolated loader and checkpoints. Keep base unchanged. Start Game → ordinary turn → reload → next turn; then Time Skip, LTA, temporary/observe/permanent switch. Change pacing/risk/outcome, reload and verify only future policy changes. Toggle notices and reload. Exercise phone message drafts across chats/closing and channel focus. Compare genealogy before/after knowledge/control change. Calendar navigation must not change save revision/world_time. Test 360/393 px, tablet/desktop, two contrasting skins and reduced motion. Record actual executed checks separately; this itinerary is not a claim of passing QA.

## Delivered behavior and compatibility

`CurrentGame` composes separate `GameCalendar`, `Genealogy`, `WeatherSettings`, and chronology surfaces. Time Skip and LTA remain their original distinct services and now open as sibling dialogs, avoiding stacked focus traps. Shared eligibility covers send button, submit callback, choices and Ctrl/Cmd+Enter. Incapacitation permits observation; death uses the existing required protagonist transition.

The calendar filters the canonical state on the server **before** building events, markers or counts. An NPC birthday needs known structured birthday evidence; own commitments and explicitly known scheduled events are visible. Existing fixture checkpoints now record the knowledge they intended to exercise. The shared genealogy endpoint applies the same birthday restriction; graph limits are 80 nodes / depth 1–6. Portraits remain consumers of #74 authorized assets.

Weather is an optional versioned, reproducible daily projection of persisted profile + canonical region + world minute. Explicit configuration uses the existing revision-guarded history/rollback transaction. Old snapshots default to `weather: null`; no SQL migration or rewriting historical snapshots. Unsupported regions/calendars do not acquire invented terrestrial seasons. Configuration begins at the current minute; earlier weather remains unknown, and future weather is omitted. No LLM calls or live weather service. Calendar month requests remain bounded; multi-year skips compute only requested days. The same projection supplies scene, calendar and model context.

Library choices: DayPicker 9.14 (MIT), React Flow 12.12 (MIT), Dagre 1.1.8 (MIT). Calendar and graph are lazy chunks (~86 kB / ~228 kB minified); the existing main bundle still triggers Vite's >500 kB advisory. DayPicker retains its keyboard-aware DayButton; Radix handles modal semantics, React Flow provides pan/zoom and an accessible text list, and existing skin/motion tokens and reduced-motion preferences apply. Phone uses transform-based continuity without a second dialog or state store.

## Executed validation (2026-10-26)

- `python -m pytest -q`: **2111 passed** (391.61 s).
- `python -m pytest -q tests/test_current_game_ui.py tests/test_narrative_pacing.py`: **97 passed**, after transaction cleanup.
- `npm --prefix frontend run build`: TypeScript and production build passed; bundle-size advisory above.
- Focused Playwright `current-game`, `calendar`, `long-term`, `narrative-skins`: **20 passed**. Includes all shipped skins; mobile widths 360/390/412/430; Time Skip and rollback; LTA preview/commit/reload; calendar browsing without revision/time mutations.
- Focused Playwright `current-game`, `phone`, `protagonist`, `narrative-pacing`, `portraits`, `runtime-handoff`: **32 passed** on desktop/mobile. Includes Start Game → ordinary turn → persisted reload → next turn, PR #116 original-export/rejected-opening recovery, explicit climate/reload, temporary control ownership, calls/emergency/group contacts, per-chat drafts, portrait upload/crop/history/delete, manual and death-triggered protagonist transitions.

Browser command prefix used in this environment:

```sh
PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell npx playwright test
```

An isolated temporary config selected port 8012 and a separate results directory for focused runs. Normal checked-in `playwright.config.ts` remains unchanged. Fixtures use temporary databases and deterministic fake providers; this is not a live-model quality assessment.

## Evidence

All images below are browser captures, not design mockups. Before images are from untouched master `318a8f1`; after images use the same phone checkpoint.

| Surface | Desktop | Narrow mobile |
| --- | --- | --- |
| Before: phone entry | [desktop](issue45-evidence/desktop-before-phone-resting.png) | [393px](issue45-evidence/mobile-before-phone-resting.png) |
| Before: generic phone dialog | [desktop](issue45-evidence/desktop-before-phone-expanded.png) | [393px](issue45-evidence/mobile-before-phone-expanded.png) |
| After: same device at rest | [desktop](issue45-evidence/desktop-phone-resting.png) | [393px](issue45-evidence/mobile-phone-resting.png) |
| After: messenger + incoming call | [desktop](issue45-evidence/desktop-phone-expanded.png) | [393px](issue45-evidence/mobile-phone-expanded.png) |
| Calendar, Parchment | [desktop](issue45-evidence/desktop-calendar.png) | [360px](issue45-evidence/mobile-calendar.png) |
| Genealogy, Graphite | [desktop](issue45-evidence/desktop-family-graphite.png) | [360px](issue45-evidence/mobile-family-graphite.png) |
| Genealogy, Parchment | [desktop](issue45-evidence/desktop-family-parchment.png) | [360px](issue45-evidence/mobile-family-parchment.png) |

## Remaining limits

Browser mobile emulation does not certify a physical Android keyboard, OS Back gesture, GPU animation timing or pinch interaction. Escape, modal dismissal, reduced motion and short-viewport behavior are tested; no new OS navigation interception was introduced. Phone drafts live only in component memory and intentionally disappear on full reload. Weather is a simple deterministic daily climate model, without hourly fronts, external forecasts or custom-world season inference. Genealogy exposes bounded depth/recentering; the later #83 visual redesign remains out of scope. No Tabletop domain changes, provider-setting changes, merges or follow-on issues.

Final responsive pass after focus/date/keyboard refinements: `current-game` + `calendar`, **16 passed** (45.1 s). Added composer non-overlap assertions at 393×500, Escape focus restoration, 820px tablet and 125% root text sizing. Evidence: [short viewport](issue45-evidence/mobile-phone-short-viewport.png), [tablet enlarged text](issue45-evidence/desktop-calendar-tablet-large-text.png). This simulates reduced available height; it does not emulate a real OS keyboard.

Full exploratory browser run (started before the UI fixes): **226 passed, 10 failed, 10 skipped**. Five failures were #45 graph layout/modal lifecycle/test-fixture defects, fixed and covered by the passing focused runs above. Five were existing generator waits (`draft-v4` structured motivations on both projects; `draft-world` creation at desktop 1280/1440 and mobile 412). An independent untouched-master worktree reproduces the same failure classes: **10 passed, 8 failed** across 18 baseline/creation checks, with failing viewport cases varying between runs. Both fail waiting for the generator to leave `generating` / open its result within the existing 12 s assertion budget. No timeout inflation or out-of-scope generator change was made; the full suite is **not reported green**.

Final server confidentiality check also removes private observance definitions from `world_clock.calendar`, not only its event markers. The final targeted backend command, `python -m pytest -q tests/test_current_game_ui.py tests/test_narrative_pacing.py tests/test_calendar_v2.py tests/test_commitments.py`, passed **152 tests** (13.14 s).

## PR120 final acceptance

Доработка по `codex_pr120_ui_completion_spec.md`, 2026-10-26. Прочитаны AGENTS.md, #45, Epic #36, #70 и применимые границы #83/#86. Начальная версия этой доработки — **3bc9e4a970a51d2585770bf33bfb782b8e813472**, потомок базы аудита `8a6c181`. Все изменения между ними сохранены. Актуальный master — `318a8f1`, интеграция #44 и #116 сохранена. Обновляется только существующая ветка PR #120; merge не выполнялся.

### Владельцы экранов и границы

Существующий `App` владеет общей рабочей областью календаря/родословной и прямыми входами desktop/mobile. Контекстные входы открывают те же `GameCalendar` и `Genealogy`. Смонтированный `Game` сохраняет текст и позицию истории; скрытая область inert. Escape отдаётся верхнему диалогу, затем рабочей области; возвращается фокус. `CurrentGame` сохраняет настройки прохождения, отдельные Time Skip/LTA и переходы управления. Семь Inspector views и глобальные настройки остаются прежними.

`Phone` — одно устройство с тремя экранами, локальными черновиками/scroll по save/owner/chat. Черновики теперь переживают reload в той же вкладке через sessionStorage; это не каноническое хранилище сообщений и не синхронизация между устройствами. Канон, доставка, контакты, вызовы и история остаются в #70. Контакты имеют компактный список и отдельные детали; переименование/блокировка вынесены в раскрываемые дополнительные действия. Чат держит composer видимым, история прокручивается независимо. Открытие устройства показывает уведомления, но не читает inbox; чтение происходит при открытии беседы.

### Контракт обработки связи

`POST /phone/dispatch` принимает **либо** существующую типизированную send/call-команду, **либо** Continuation(source_event_id, owner_id, request_id). Команда и регистрация job выполняются в одной транзакции; модель запускается после commit. Это ограниченный orchestration поверх существующих jobs, proposals, accept, remote.apply, snapshots и commit_job, без второго Runtime.

- Общий предел — **4 решения модели на весь цикл**, включая группу и установление неизвестного адресата. Максимум ответа модели — min(1200, update_tokens). Контекст укладывается в выбранное окно; необязательные Knowledge/кандидаты сокращаются до обращения к провайдеру. Если исходный контекст не помещается, возникает явная ошибка.
- Каждый запрос связан только с исходным событием. После принятого read возможен следующий optional reply. Null, отклонённое решение, отказ, недоступность или отправленный ответ прекращают цикл. Нет обхода всего списка контактов, обязательного ответа каждого участника, LLM polling или retry-until-reply.
- Отправка/ответ/отказ и явное дополнительное ожидание расходуют **1 игровую минуту**. Неотвеченный вызов доходит только до канонического ring_timeout_minutes (профиль 1–60, по умолчанию 2); это суммарный предел дозвона, а не четыре обычных хода. UI показывает настроенный срок. Просмотр, анимация и status polling не двигают время и не вызывают модель. Time Skip и LTA сохраняют отдельные контракты.
- Провайдер может ошибиться после read: отправленное сообщение уже сохранено, промежуточная реакция не публикуется частично. Явный Retry переиспользует записанные завершённые решения и продолжает оставшуюся работу. Нет автоматического технического retry. Usage/ошибки/попытки идут через tracked_stream; итог содержит decisions, accepted/rejected, elapsed_minutes и outcome.
- Receipt по действующей history lineage, revision, owner и request id предотвращает повтор отправки/времени. Один request id с другим намерением отклоняется. Regenerate использует записанный исходный контекст, создаёт новый допустимый вариант; дальнейший контекст обусловлен его собственными принятыми решениями. Выбор варианта/rollback восстанавливает соответствующий звонок и время. Старый command после смены ветки не запускает новую обработку; stopped worker не может записать результат.
- После answer выбран канал «По телефону» и доступен переход к основному composer. Никакой реплики за игрока не создаётся. «Рядом» — явный физический канал. Входящий вызов не принимается физическим действием. Завершение убирает call channel; удалённый собеседник не перемещается в сцену.

### R01–R11

| ID | Реализация и доказательство |
| --- | --- |
| R01 | Отдельные пункты существующей левой навигации и mobile menu; общая рабочая область, draft/focus/scroll сохраняются. `pr120-completion`, `current-game`; запись workspace. |
| R02 | Общие skin tokens, круглые портреты, focus/reduced-motion, компактные mobile headers, состояния загрузки/ошибки/пустых данных. Снимки двух контрастных скинов; остальные скины проверены `narrative-skins`. |
| R03 | Основная сетка месяца + agenda справа, mobile agenda ниже; статусы, интервалы и участники. Мини-календари года, custom профиль 2 месяца/5 дней недели. `completion-matrix`, `calendar`. |
| R04 | B04–B06 сохранены и перепроверены: диапазон согласован с выбранной датой, labels не возвращают сырой профиль, приватная Observance валидна и остаётся в каноне. Данные помечены revision/owner/range, старый ответ не отображается. `test_current_game_ui`, T04–T09. |
| R05 | Разрешённые корни включают известного человека без родственников и отдельную семью. Поиск не выдаёт полный roster. Один граф, bounded 80 nodes/depth 1–6, fit/pan/zoom, карточка узла, доступный список. Развод, партнёрство, усыновление, подозреваемая опека различимы; длинные партнёрские связи обходят карточки сверху. |
| R06 | Контакты → детали, переписки → чат, журнал/текущий вызов; единый корпус/нижняя навигация, отдельные unread/read, сохранённые группы и службы. `phone`, `phone-completion`; before/after и записи. |
| R07 | Автоматический bounded дозвон через job: answer/decline/null/unavailable. Канал, переход к разговору, отмена/завершение. T15–T17 через действующий сервер/Runtime. |
| R08 | Точный send → read → optional reply в исходном чате; error/retry, явное ожидание, no-action и групповой общий предел. Черновики и scroll по беседе. T18/T19/T22. |
| R09 | Сохранён и проверен B02: NPC отвечает в существующий direct conversation без обратного контакта. Membership, блокировки, доступность и каналы проверяются перед применением. `test_remote_communication`, `test_communication_cycle`. |
| R10 | Типизированное продолжение, atomic registration, receipt/lineage, revision/owner/epoch, checkpoints/retry/regenerate, bounded model/time, штатная диагностика. T20–T24. |
| R11 | Handoff #116, ordinary turns, Time Skip, LTA, pacing/risk/outcomes, notices, weather, portraits, управление/наблюдение/death и Tabletop проверены перечисленными ниже наборами. Нет SQL-миграций, переписывания истории, новых production dependencies или отдельного Inspector. |

### T01–T26

Все строки выполнены на указанном уровне. Детерминированный провайдер выдаёт решения в настоящие обработчики; исходящие answered/reply не подставляются заранее. Входящий вызов/непрочитанное сообщение в seed — исходные условия сценария.

| ID | Проверка и результат |
| --- | --- |
| T01 | `runtime-handoff`: Start Game → обычный ход → сохранённый reload → следующий обычный ход, desktop/mobile. Пройдено. |
| T02 | Тот же тест использует original export #116 и recovery отклонённой первой сцены; backend legacy/save tests и `test_phone_ordinary_cycle_and_legacy_disabled`. Пройдено. |
| T03 | `pr120-completion`, `current-game`: прямые/контекстные входы, смена месяца/семьи, Escape, возврат с draft и фокусом. Пройдено. |
| T04 | `completion-matrix`: длинные русские названия, несколько событий дня, пустой месяц, Graphite/Parchment. Снимки просмотрены; заголовок/участники разделены, mobile без overflow. |
| T05 | Следующий месяц и назад, согласованная выбранная дата, revision/world_clock неизменны. Пройдено. |
| T06 | Год из 12 мини-календарей; отдельный custom profile 20/25 дней, 5 weekdays, переход 42 → 43. Пройдено. |
| T07 | Pending/overdue/resolved/cancelled видны в UI; backend проверяет перенос без старой копии и известный/неизвестный birthday. Пройдено. |
| T08 | Валидная private Observance, сохранность канона, filtered save/calendar/markers; свои даты сохранены. Backend + UI. Пройдено. |
| T09 | Backend visibility/observer и одинаковая weather projection; UI climate/reload, Time Skip/rollback, смена управления; revision/owner cache guards. Пройдено на этих уровнях. |
| T10 | Выбор Тимура из несвязанной семьи; проверка неизменных revision/controlled_actor. Пройдено. |
| T11 | Известный Олег без родства: разрешён в общем выборе, корректное пустое состояние; постоянный контекстный вход не зависит от social rows. `completion-matrix` также открывает пустую семью непосредственно из досье, desktop/mobile. |
| T12 | Развод/новое партнёрство/усыновление/опека; 100 дополнительных родственников → максимум 80 nodes, fit/zoom/recenter/list. Скриншоты и render metrics. Пройдено. |
| T13 | Зоя отсутствует в поиске/графе; backend hidden/known/suspected/name-history/adoption и временный observer проверены `test_life_social`. Пройдено. |
| T14 | Resting/unread/open/chat/close, две темы, точное сохранение draft; прочтение только при открытии беседы. Пройдено и записано. |
| T15 | Contact → call → model answer → точная реплика игрока в Narrative → ответ → end. Проверены физическая сцена и каналы, desktop/mobile. Пройдено и записано. |
| T16 | Decline и bounded no-action в UI; unavailable (0 model calls) через настоящий runtime cycle. Пройдено; вечного ringing/spinner нет. |
| T17 | Incoming → обычное физическое действие без answer → answer → физический/телефонный каналы → end, draft сохранён. Пройдено и записано. |
| T18 | Send → actual read/send decisions → ответ в той же canonical conversation; reload сохраняет сообщения и новый draft. Пройдено. |
| T19 | Read-only/null завершаются, явное ожидание создаёт ровно один commit; backend доказывает 1 минуту и общий group budget с остановкой после reply. Пройдено. |
| T20 | Удалён обратный контакт, planner/accept/delivery дают ответ в исходную direct conversation; новый контакт не синтезируется. Пройдено. |
| T21 | Existing #70 tests: blocked contacts, бывший/новый участник, unread restrictions, неизвестные endpoints, организации/службы. UI groups/emergency сохранены. Пройдено. |
| T22 | Повтор идентичного HTTP dispatch, provider error после read, reload/Retry, checkpoint replay; один outgoing, один ответ, один advance. Pending duplicate и cancel защищены backend. Пройдено. |
| T23 | Reload активного/завершённого канала, regeneration answer→decline, исходный variant, rollback к ringing; stale retry/command/worker отклонены. Пройдено. |
| T24 | `phone`/`protagonist`/`current-game`: временный владелец, observer, incapacitated button/shortcut/submit guard, death-required переход, permanent/generated/manual protagonist. Пройдено. |
| T25 | Desktop 1440×1000; mobile 360/393 и 390/412/430; tablet 820; text 125%; 393×500 с reduced motion и доступной кнопкой отправки; Escape/focus/draft/scroll. Chromium viewport/touch emulation; физический Android/OS keyboard не заявляется. |
| T26 | Calendar/Time Skip/rollback, LTA preview/commit/reload, pacing/risk/outcomes, notices, portrait crop/history/delete, все основные скины; 5 Tabletop сценариев на каждом project. Пройдено. |

### Выполненные команды

Из корня репозитория: `python -m pytest -q` — **2123 passed (317.58 s)**. После изменений ядра целевой набор `tests/test_communication_cycle.py tests/test_remote_communication.py tests/test_engine.py tests/test_current_game_ui.py tests/test_narrative_test_world.py` — **72 passed**. `npm --prefix frontend run build` — TypeScript/Vite успешно; сохранено предупреждение о main chunk >500 kB, календарь/родословная загружаются лениво.

Из `frontend`, с `PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell`:

```sh
npx playwright test phone-completion.spec.ts completion-matrix.spec.ts pr120-completion.spec.ts current-game.spec.ts phone.spec.ts calendar.spec.ts long-term.spec.ts narrative-pacing.spec.ts narrative-skins.spec.ts portraits.spec.ts protagonist.spec.ts runtime-handoff.spec.ts tabletop.spec.ts
```

Итог этого применимого acceptance набора — **74 passed (5.5 min)**. Это не полный E2E репозитория. После добавления контекстного входа из даты сцены и проверки пустого досье: `npx playwright test completion-matrix.spec.ts runtime-handoff.spec.ts` — **12 passed (45.8 s)**, включая повтор обязательного smoke. Последняя фиксация телефонного evidence ожидает фактический read перед снимком: `phone-completion.spec.ts` — **12 passed (52.4 s)**. [Логи](pr120-final-evidence/README.md#логи-проверок). Ранее целевой прогон 34 passed и отдельный 22 passed не суммируются с ним. В ходе проверки исправлены локальное затенение `time` в тестовом провайдере и гонка теста ожидания commit (ожидание реальной revision вместо мгновенного чтения; timeout не увеличен). Исторические проблемы generator suite из предыдущего раздела этим набором не сертифицируются и не объявляются исправленными.

### Визуальная приёмка и evidence

[Индекс before/after, экранов и записей](pr120-final-evidence/README.md). Before — неизменённый **3bc9e4a**, after — текущая доработка. Сравнения используют одинаковые размеры и fixtures: `family-seed` для calendar/year/family, `phone-seed?unread=true` для входящего/контактов/чата. Новые насыщенные/пустые сценарии сняты отдельно и не выдаются за идентичные before данные.

Просмотрены реальные browser captures. Исправлены тесные mobile заголовки, наложение линии партнёрства на карточки, слитные подписи календаря, scroll после read и clipping send при уменьшенной высоте. На desktop сетка занимает рабочую область, agenda читается отдельно; mobile сохраняет последовательность сетка → детали. В телефоне composer и нижняя навигация остаются достижимы, последние ответы читаются, длинная история прокручивается. Записи охватывают открытие/сворачивание, смену экранов, исходящий разговор, read/reply, входящий вызов, смену семьи и возврат к Narrative. Reduced-motion проверен; инструментального GPU/fps аудита не проводилось.

Новые воспроизводимые checkpoints #78: `ui-calendar`, `ui-calendar-custom`, `ui-family`, `ui-family-dense` в существующем loader, например:

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint ui-family --db data/dev-ui.sqlite3
```

### G1–G7 и ограничения

| Gate | Итог |
| --- | --- |
| G1 | Выполнен: прямые общие входы desktop/mobile и сохранение контекста (R01/T03). |
| G2 | Выполнен: месяц/год/custom profile, details/statuses и B04–B06 (R03–R04/T04–T09). |
| G3 | Выполнен: отдельная/пустая/большая семья с авторизацией наблюдателя (R05/T10–T13). |
| G4 | Выполнен: три законченных экрана одного телефона, notification/read и composer (R06/T14/T25). |
| G5 | Выполнен: автоматический исходящий разговор и read→optional reply, допустимые отказ/молчание и bounded budgets (R07–R09/T15–T21). |
| G6 | Выполнен: серверная фильтрация, idempotency/owner/revision/lineage и сохранения (R04/R10/T08/T13/T22–T24). |
| G7 | Выполнен в описанной среде: обязательный smoke и применимая T01–T26 матрица; ограничения ниже не скрыты. |

Физическое устройство Android, настоящая экранная клавиатура/OS Back, GPU timing и платный live LLM не проверялись: выполнены Chromium emulation, reduced viewport и настоящие API/Runtime/jobs с детерминированным провайдером. Причина молчания в конкретном пользовательском save не исследовалась; B02 доказан на валидных синтетических мирах. Dense graph — ограниченная навигация с 80 nodes и recenter, а не обещание одновременной читаемости всех 100+ родственников. Погода остаётся прежней ограниченной детерминированной дневной моделью. Полный browser suite не объявляется зелёным. Эти результаты заменяют прежний незавершённый статус PR; новых задач #83/#86 целиком и следующих задач эпика здесь нет.
