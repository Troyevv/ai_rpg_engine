# AI RPG Engine

AI RPG Engine — локальный AI-RPG движок на **FastAPI + React + TypeScript** с SQLite. В одном приложении развиваются два разных игровых режима: Narrative для интерактивного повествования и Tabletop для настольной RPG с AI-DM и детерминированными правилами.

> Этот README описывает актуальное состояние разработки из **PR #33 / Universal Tabletop 2.0**. Часть описанных Tabletop-функций ещё находится в PR и не завершена; раздел «Статус разработки» отделяет реализованное от оставшейся работы.

## Режимы

### Narrative Mode

Narrative — самостоятельный runtime для интерактивного повествования: по сути «бесконечная книга», в которой игрок управляет выбранным персонажем, а LLM ведёт историю. Текст модели не является единственным состоянием игры: мир хранится отдельно в каноническом **World State**, поэтому персонажи, знания, отношения, события и время могут переживать отдельные сцены и ответы модели.

#### Игровой цикл

```text
Действие / реплика игрока
→ Context Builder собирает релевантное состояние
→ Ведущий генерирует продолжение сцены
→ отдельное extraction извлекает изменения мира
→ WorldDelta проходит структурную и семантическую проверку
→ валидные изменения применяются к canonical World State
→ ход, вариант, before/after state, usage и диагностика сохраняются атомарно
```

Обычный ход использует отдельные запросы для повествования и извлечения состояния. Валидация выполняется кодом. Repair допускается только для типизированных исправимых structural-ошибок; вторичные локальные проблемы могут детерминированно исключаться с диагностикой вместо разрушения всего хода. Неизвестные ошибки, конфликтующие ссылки, время/сцена и небезопасные изменения не игнорируются.

#### Canonical World State

World State хранит не только текущий текст сцены. В нём живут персонажи и их положение, факты и знания, отношения, планы и намерения, события, сюжетные линии, локации, игровое время и состояния параллельных сцен.

Состояние сохраняется снимками before/after. Это позволяет движку восстанавливать мир при переключении варианта или откате, а не пытаться реконструировать его из текста истории.

#### POV и Controlled Actor

**POV** определяет, чью перспективу сейчас показывает игра. **Controlled Actor** определяет персонажа, решения которого принадлежат игроку. Это разные понятия: камера может наблюдать мир без передачи персонажа под управление LLM.

Для controlled actor действует отдельное правило player agency. LLM не может сама назначить игроку новые цели, намерения, эмоции или обязательства только потому, что они появились в повествовании. Такие изменения требуют явного подтверждения в текущем вводе игрока. Отклонённые поля не стирают остальное валидное состояние персонажа.

Можно переключаться между персонажами и использовать режим **«Мир без ГГ»**, где повествование следует за другими участниками и событиями мира, не возвращая камеру к главному герою автоматически.

#### Знания и информация

Знание моделируется отдельно от глобальной истины мира. Персонаж может знать, подозревать или не знать информацию; новые знания должны иметь допустимый источник передачи или свидетельство.

Context Builder передаёт модели только информацию, которую текущая перспектива действительно может использовать. Это позволяет хранить секреты, параллельные события и сведения других персонажей без автоматического «всеведения» NPC.

#### Отношения, цели и намерения

Отношения направленные: отношение A к B не обязано совпадать с отношением B к A. Динамика отношений хранится в состоянии и может меняться вместе с событиями.

NPC могут иметь собственные цели, намерения, планы и текущее состояние. Движок отделяет эти данные от решений controlled actor, чтобы живой мир не отнимал управление у игрока.

#### Живой мир, время и параллельные события

Narrative Runtime поддерживает единое игровое время, actor scenes, события и фоновые процессы. Мир не обязан останавливаться вне текущего POV: персонажи могут находиться в других местах, а события — происходить параллельно.

Living World слой связывает персонажей, их сцены, знания, планы, события и время в единый canonical aggregate. Старые сохранения нормализуются через совместимые fallback-механизмы без переписывания исторических before/after snapshots.

#### Context Builder и автоматическая память

Контекст Ведущего собирается из именованных блоков:

- постоянные правила;
- исходная выжимка мира;
- релевантные NPC и отношения;
- компактная память завершённых событий;
- важные факты, знания и планы;
- текущая сцена и релевантные локации;
- последние полные пары «игрок → ведущий»;
- задача текущего хода.

Старые ходы не удаляются. Когда история выходит за окно непосредственного контекста, они пакетами сворачиваются LLM в версионируемую память. Исходный журнал остаётся доступным, а memory versions сохраняют диапазон обработанных ходов и связь с предыдущей версией.

Если контекст не помещается, движок не должен молча обрезать основные блоки. Фактический контекст, оценки его частей и запросы можно смотреть в диагностике.

#### Варианты, перегенерация и откат

Каждый логический ход имеет стабильный `node_id`, а ответы хранятся как неизменяемые **response variants** с полным before/after state, исходным контекстом, памятью, моделью и параметрами запроса.

Перегенерация использует сохранённые сообщения исходного запроса, а не текущий изменившийся prompt или более позднюю память. Модель и параметры можно поменять, но исходный контекст хода остаётся тем же.

Переключение уже существующего варианта не вызывает LLM и не расходует токены. Для изменения исторического хода требуется явный rollback; последующие ходы архивируются только после успешного коммита нового варианта. Ошибка или отмена не повреждает текущий канон.

#### Диагностика WorldDelta

Extraction проходит Pydantic/JSON-проверку и семантическую валидацию на копии исходного состояния. Диагностика различает:

- structural validation;
- LLM repair;
- deterministic sanitization;
- evidence/player-agency rejection;
- fatal semantic errors.

Предупреждения и repair diagnostics сохраняются вместе с job/вариантом и переживают перезапуск. Это позволяет видеть, какие изменения модели были приняты, отклонены или исправлены, не скрывая проблемы за silent repair.

#### Модели, Thinking и расходы

Для **Сценариста**, **Генератора** и **Ведущего** можно независимо выбирать модель и Thinking Off/Low/High. Extraction и автоматическая память используют конфигурацию Ведущего. Неподдерживающие Thinking модели просто игнорируют этот параметр.

Каждая фактическая LLM-попытка сохраняется в журнале: stage, модель, Thinking, запрос, diagnostics, input/output/cached usage и оценка стоимости. Учитываются также неудачные запросы, regeneration, memory и repair. Локальные модели имеют нулевую API-стоимость.

Панель **«Контекст ведущего · Расходы»** показывает сохранённые запросы, состав контекста и статистику по текущей сессии, прохождению и миру.

#### Сохранения и безопасность операций

Narrative использует SQLite, revision checks и атомарные транзакции. Старые `before_json`/`after_json`, сохранения и архивы не переписываются при миграциях.

API-ключ провайдера сохраняется на backend в зашифрованном виде и не возвращается браузеру. Ключ не должен попадать в localStorage, LLM-контекст или журнал запросов.

Основные возможности Narrative в итоге включают свободный ввод и варианты действий, streaming, World State, Character Knowledge, отношения, NPC goals/intentions, POV/Controlled Actor, Living World, игровое время, параллельные события, «Мир без ГГ», автоматическую память, ветвящиеся варианты, точную перегенерацию, rollback/archive и подробную LLM/WorldDelta диагностику.

### Tabletop RPG / Universal Tabletop 2.0

Tabletop — отдельный runtime, а не вариант Narrative Mode. LLM играет роль **AI-DM**, но не определяет механический результат игры.

```text
Действие игрока
→ AI-DM интерпретирует намерение
→ Rules Engine определяет механику
→ проверка / бросок / стоимость ресурса
→ Dice Engine и Rules Engine вычисляют результат
→ состояние изменяется детерминированно
→ AI-DM описывает произошедшее
```

Критические игровые данные — HP, ресурсы, инвентарь, экипировка, условия, инициатива и результаты бросков — server-authoritative.

## Narrative и Tabletop — разные игровые системы

Оба режима используют общий LLM/persistence/UI фундамент, но решают разные задачи.

| | Narrative | Tabletop |
|---|---|---|
| Основная идея | Интерактивная бесконечная история | Настольная RPG с AI-DM |
| Решение игрока | Свободное действие управляемого персонажа | Свободное намерение или структурированная игровая команда |
| Главный источник результата | Повествование + валидированный WorldDelta | Детерминированный Rules/Dice Engine |
| Состояние | World State, знания, отношения, планы, сцены, время | Character sheets, HP, resources, inventory, initiative, conditions |
| LLM | Ведущий, extraction, memory | DM interpretation, authoring, narration |
| Player agency | Controlled Actor защищён evidence-правилами | DM не имеет mechanical authority |
| Мир вне игрока | Living World, параллельные сцены и события | Campaign/Setting + NPC/creature runtime |
| Броски | Не являются основой Narrative runtime | Центральная D20-механика |

Поэтому Tabletop не строится поверх WorldDelta Narrative и не пытается превратить Narrative в D&D. Общими остаются инфраструктура моделей, сохранений и интерфейса, а игровые runtime и правила разделены.

## Universal Tabletop

Архитектура разделяет систему правил и содержание конкретного мира:

```text
Ruleset
  ↓
Setting
  ↓
Campaign
  ↓
Character
  ↓
Game
```

**Ruleset** задаёт стабильное D20/BG3-like ядро. **Setting** описывает, что существует в конкретной вселенной. **Campaign** создаёт конкретное приключение внутри выбранного мира. Кампания получает фиксированный snapshot Setting, поэтому последующее редактирование мира не должно менять уже начатую игру.

Setting может быть произвольным: движок не должен требовать отдельных `if fantasy`, `if cyberpunk` и других genre-specific веток. Сеттинг хранит собственный Content Registry с навыками, архетипами, происхождениями, существами, предметами, ресурсами, типами урона, способностями и world mechanics.

Генерация Setting и Campaign разбита на стадии с валидацией зависимостей, структурированными ошибками и ограниченным retry. Мир можно сохранять, версионировать, редактировать по секциям и использовать повторно в разных кампаниях.

## Tabletop: механическое ядро

Базовые характеристики фиксированы для всех сеттингов:

- **STR** — Strength;
- **DEX** — Dexterity;
- **CON** — Constitution;
- **INT** — Intelligence;
- **WIS** — Wisdom;
- **CHA** — Charisma.

Навыки могут зависеть от Setting и привязываются к этим характеристикам. Поддерживается альтернативная характеристика навыка.

D20-ядро включает:

- ability checks и saving throws;
- proficiency и DC;
- advantage / disadvantage;
- passive checks;
- initiative;
- attack и damage rolls;
- critical hits;
- conditions;
- resistance / vulnerability / immunity;
- ресурсы и costs;
- отдых и восстановление;
- Action / Bonus Action / Reaction / Movement;
- произвольные dice expressions.

В Tabletop есть exploration, dialogue и encounter/combat. Свободный текст остаётся доступен: AI-DM преобразует намерение в структурированное действие, после чего правила проверяются кодом.

## Персонажи

Character Creator работает с Content Registry выбранного Setting. Сборка персонажа включает архетип/класс, вид, background, навыки, способности, характеристики и стартовое снаряжение.

Для текущего D20-каталога реализована линейная система распределения характеристик: все шесть значений начинают с базового уровня, а игрок распределяет общий бюджет очков. Backend отдаёт preview производных параметров и валидирует итоговую сборку.

Background может задавать навыки, proficiencies, языки, инструменты, теги, hooks, знания, контакты, репутацию, features, стартовые предметы, ресурсы и деньги. Полная runtime-интеграция части background-данных ещё находится в работе.

## Предметы, экипировка и магазин

Setting содержит собственный каталог предметов. Предмет строится из компонентов, например weapon, armor, ammo, magazine, energy, tool, consumable/medical, container и identity-компонентов.

Поддерживаются:

- стоимость и стартовая доступность;
- инвентарь;
- профили и слоты экипировки;
- ограничения рук и брони;
- оружие и броня;
- ammunition/magazine;
- single / burst / automatic resource costs;
- инструменты и расходники;
- declarative effects и requirements;
- стартовый магазин.

Покупка и экипировка разделены: купленный предмет сначала попадает в инвентарь, а не надевается автоматически. Неизрасходованные стартовые деньги остаются у персонажа.

Часть component behavior, item-granted effects и расширенных firing mechanics ещё дорабатывается.

## Существа и встречи

Setting хранит **CreatureTemplate**, а конкретная кампания создаёт экземпляры существ. Шаблон содержит шесть базовых характеристик, HP, защиту, скорость, навыки, saves, атаки, features, damage modifiers, ресурсы, AI profile, habitats, rarity и threat.

Encounter generation использует детерминированную оценку threat/budget вместо передачи баланса целиком LLM.

## Проверки и кубики

Проверки используются не только в бою, но и в исследовании, диалогах и контекстных действиях. Rules Engine рассчитывает модификаторы и условия, а Dice Engine является источником результата.

Поддерживаются d4, d6, d8, d10, d12, d20, d100 и составные выражения. Результаты, modifiers и механические события сохраняются в истории.

## Бой

Tabletop использует пошаговый encounter runtime:

- initiative;
- очередность участников;
- Action / Bonus Action / Reaction / Movement;
- выбор цели;
- атаки и урон;
- HP и условия;
- reactions;
- ресурсы;
- spells/features;
- combat event history;
- preview механических последствий.

AI-DM описывает результат после применения механики, но не может самостоятельно изменить canonical state.

## LLM и AI-DM

Поддерживаются локальные модели через **LM Studio** и OpenAI-compatible providers, включая DeepSeek. Для задач можно выбирать provider/model, temperature, output limit и Thinking Off/Low/High.

Narrative и Tabletop используют LLM для разных задач. В Tabletop модель интерпретирует свободное намерение, генерирует авторский контент и narration; Rules Engine остаётся источником механической истины.

Генерация мира и кампании использует отдельные authoring pipelines. Результат проходит schema/reference/semantic validation до попадания в игру.

## UI и мобильная версия

Frontend адаптирован для desktop и mobile/PWA. В Narrative и Tabletop используется общий Choice UI: пользовательские выборы не должны открывать нативные Android/iOS `<select>` picker-ы. Для мобильных используются собственные sheets/popovers, а build guard запрещает возвращать native select/option/datalist в пользовательский интерфейс.

Tabletop UI включает wizard создания кампании, Setting Editor, Character Creator, Starting Shop, историю, персонажа, инвентарь, журнал, партию, карту, броски, DM settings и боевые действия.

## Запуск в Windows

Нужны **Python 3.10+** и **Node.js 22.12+ с npm**.

1. Обнови репозиторий.
2. Запусти **`start.bat`** двойным кликом.
3. При первом запуске создастся `.venv`, установятся Python/npm-зависимости и соберётся React.
4. Launcher дождётся FastAPI и откроет **http://127.0.0.1:8000**.
5. Для остановки используй **`stop.bat`**.

Повторный запуск открывает уже работающий экземпляр. Backend log: `.runtime/server.log`.

Ручной запуск:

```bash
python launcher.py start
python launcher.py stop
```

Production build React раздаётся FastAPI. `RPG_PORT` меняет порт, `RPG_DB_PATH` — SQLite-файл, `RPG_HOST` — интерфейс прослушивания.

## Телефон и PWA

Для мобильного интерфейса предусмотрена отдельная компоновка. Для локальной установки PWA можно один раз выполнить `setup_https.bat`, установить локальный CA на телефоне и использовать HTTPS-адрес launcher.

Подробности: [docs/MOBILE_PWA.md](docs/MOBILE_PWA.md).

## Настройка моделей

**LM Studio:** запусти Local Server, обычно на `http://localhost:1234`, затем выбери локальную модель в настройках приложения.

**DeepSeek/OpenAI-compatible:** API key можно указать в UI или через поддерживаемую переменную окружения. Ключ не должен попадать в URL и публичные ответы API.

Thinking задаётся отдельно для поддерживаемых задач/моделей. Reasoning-контент не должен попадать в игровой текст.

## Сохранения

Основная БД по умолчанию: **`data/rpg.sqlite3`**.

Narrative сохраняет миры, прохождения, snapshots, варианты, память и историю. Tabletop сохраняет drafts, Settings, Campaign state, историю и usage. Runtime использует revision/idempotency-проверки, чтобы конфликтующие запросы не коммитили частичное состояние.

Существующие Narrative saves сохраняют обратную совместимость; новые Tabletop структуры не должны требовать переписывания старых Narrative миров.

## Архитектура

```text
backend/
  api/                  FastAPI и общие HTTP/SSE API
  services/             Narrative services
  repositories/         persistence/settings
  tabletop/             отдельный Tabletop runtime
    content.py           Setting/Content Registry contracts
    setting_generation.py
    campaign_generation.py
    compiler.py          Campaign validation/compiler
    rules.py             deterministic rules
    dice.py              dice engine
    encounter.py         encounter mechanics
    equipment.py
    features.py
    spells.py
    runtime.py
    repository.py

frontend/src/
  tabletop/              Tabletop UI
  components/choice/     общий Choice UI
  ...
```

Narrative-ядро также использует `engine.py`, `context_builder.py`, `state_updates.py`, `storage.py`, `engine_storage.py`, `world_parser.py` и `llm.py`.

## Разработка и проверки

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q

cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser/E2E тесты используют FastAPI, SQLite и production frontend с тестовым LLM adapter. Fixture-тесты генерации не являются подтверждением качества реального внешнего LLM.

## Статус Universal Tabletop 2.0

PR #33 — **WIP**, поэтому этот раздел важен: наличие schema/API ещё не означает полный runtime acceptance.

На текущем checkpoint реализованы:

- reusable/versioned SettingDefinition и ContentRegistry;
- fixed Setting snapshots в Campaign;
- staged Setting/Campaign authoring;
- strict schemas, dependency validation и structured semantic issues;
- Setting Editor и выбор сохранённого мира;
- custom skills и alternate abilities;
- CreatureTemplate/instances и threat budgeting;
- custom resources и damage modifiers;
- magazines/reload и базовые firing modes;
- declarative effects и contextual actions;
- profile-driven equipment slots;
- Starting Shop;
- общий Choice UI без native mobile picker;
- desktop/mobile сценарии создания Setting → Campaign → Character → Shop → Game → reload.

Остаётся завершить:

- setting-first flow как основной путь вместо legacy one-shot generation;
- сохранение и resume промежуточных стадий authoring с реальным progress;
- полный runtime/UI path всех item/object components;
- item-granted effects и requirements;
- generic equipment conflict preview без legacy slot assumptions;
- полную интеграцию background contacts/knowledge/reputation;
- custom damage types во всех power paths;
- расширенную механику firing modes;
- аудит generated-world context и semantic cross-references;
- end-to-end сценарий нового Setting через checks → combat → loot → настоящий server restart;
- smoke tests с реальными LLM на нескольких несвязанных пользовательских мирах;
- финальный visual/acceptance audit.

Текущие authoring-тесты используют fixtures, поэтому они не доказывают стабильность реальной модели. До закрытия этих пунктов Universal Tabletop 2.0 не считается завершённым.

Подробный checkpoint: [docs/UNIVERSAL_TABLETOP_2_STATUS.md](docs/UNIVERSAL_TABLETOP_2_STATUS.md).

## Документация

- [Narrative runtime](docs/RUNTIME.md)
- [Living World](docs/LIVING_WORLD.md)
- [POV и версии](docs/POV_AND_VERSIONS.md)
- [POV transitions](docs/POV_TRANSITIONS.md)
- [Mobile/PWA](docs/MOBILE_PWA.md)
- [Universal Tabletop 2.0 status](docs/UNIVERSAL_TABLETOP_2_STATUS.md)
