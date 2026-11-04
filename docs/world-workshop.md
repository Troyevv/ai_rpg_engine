# Мастерская миров (#175)

Эталон: `world-workshop.html`, SHA-256 `4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1`.
Изучены исходные CSS, SVG-слои, разделы и обработчики прототипа, обзорное изображение. Демонстрационные данные и операции не используются.

## Матрица переноса

| Существующая возможность / поля | Раздел и действие | Контракт | Проверка |
|---|---|---|---|
| Идея, название, эпоха, география, жанр, календарь, связь | Идея и генерация; настройки; создание версии | WorldCreationSettings; draft/generate | draft-world, calendar-presets |
| Сценарист | Идея → Со Сценаристом | Preparation; onDraft | draft-world |
| TXT/MD/JSON, определение формата | Идея → Импортировать | draft/import | draft-world, worldImport |
| Черновики, корзина, восстановление | Переключатель мира / История и файлы | workspaces; delete/restore | draft-world |
| Streaming, попытка, диагностика, retry/resume/stop, кандидат | Идея и генерация / Проверка | useJob; draft/resume; jobs/stop; candidate | draft-recovery, draft-world |
| Все текстовые поля карточки, имя, алиасы | Досье: Основное / Личность | draft PATCH character | workshop, draft-world |
| birth_date, biological_sex, life_status, developmental_stage, appearance, physical_state, capabilities, personality, values, reproductive_capability, provenance/identity | Досье: Основное / Сейчас / Личность; типизированный редактор | editor.schemas; draft PATCH actor | workshop, draft-initial |
| Цели, намерения, обязательства; статус/происхождение записей | Досье: Цели | draft PATCH actor | structured editor, draft-world |
| Направленные чувства, dimensions, контекст, доступность | Связи и семьи / Досье: Связи | draft PATCH relationship | draft-world |
| objective_relations, периоды, история | Связи и семьи | существующие extension fields | draft-initial |
| Локации, организации, проживания, роли, имущество, контакты | Места и сообщества; смысловые подразделы | draft PATCH; dependencies | draft-world |
| threads / events / scheduled_events / reproductive_events / naming_decisions | Сюжеты / Хронология | draft PATCH соответствующей группы | draft-world |
| facts, Knowledge, secret / story_secret / ownership / claim | Факты и знания / Досье: Знания | серверная player/author проекция | draft-world, workshop |
| conditions / pregnancies | Досье: Сейчас / Места и сообщества / Связи и семьи | existing extension fields | draft-initial |
| Кампания, правила, calendar, communication; controlled actor отдельно от protagonist и camera | Сцена и правила; финальное подтверждение | CalendarProfileEditor; CommunicationEditor; draft/confirm | draft-world, calendar-presets |
| Ошибки, предупреждения, устаревший review, relation merge, исправление кандидата | Проверка мира | текущие validation/review/candidate/merge-relations | draft-recovery |
| AI instruction → preview → apply/reject/rollback, история, стоимость | Изменить с ИИ | WorldAIEditor (#173), без нового pipeline | world-ai-editor |
| Версии, append-only restore, исходный замысел, экспорт | История и файлы | draft PATCH restore; export | draft-world |
| Генерация поля / карточки, зависимости удаления | Досье и редакторы, явное подтверждение | draft/generate; dependencies | draft-world |
| Загрузка, кадрирование, оригинал, замена, удаление и история портретов | Досье → Портрет | общий PortraitControl; draft/save scoped assets | workshop-portraits, portraits |
| Процедурные SVG, seed + version + параметры, нейтральный fallback | Досье → Настроить иллюстрацию | versioned actor descriptor, общий CharacterAvatar | proceduralPortrait, workshop-portraits |

API и Runtime остаются источником канона. Поиск, навигация и буферы ввода — только UI-состояние. Просмотр автора явно запрашивает полную проекцию и не изменяет Knowledge.

## Архитектура и совместимость

- `WorkshopShell`, `CharacterCollection`, `CharacterDossier`, `RecordCollection` и `StructuredValueEditor` используют один workspace/revision и прежние операции `WorldWorkshop`. Формы вложенных полей получают определения из существующих Pydantic-схем; они не вычисляют канон.
- Буферы полей привязаны к workspace, объекту, полю и исходной revision. При изменении версии требуется явно разрешить использование старого ввода. Закрытие окна не стирает несохранённый текст. Поиск ограничен загруженной серверной проекцией.
- AI-редактор остаётся владельцем preview/apply/rollback по #173. Генерация и recovery #172/#182/#185 сохранены. Экспериментальный #117 не используется. Игровой интерфейс тайн из #183 не изменяется.
- Модель персонажа получает необязательный `procedural_portrait` (version 1, seed, ограниченные индексы элементов) и `portrait_mode`. Старые snapshots не переписываются. Для старых игровых персонажей без дескриптора остаётся прежний fallback.
- Просмотр черновика возвращает отдельную карту `portraits`; чтение не изменяет канонический `state` или историю. Настройка портрета записывает новую версию. При подтверждении стабильные начальные дескрипторы переносятся в настоящий Runtime. Имена, порядок персонажей и skin не участвуют в seed.
- Портреты не анализируют литературную внешность. Существующий selector определяет период жизни; неизвестные/детские/неподдерживаемые варианты получают нейтральную иллюстрацию. Случайные графические детали не становятся фактами Appearance. Смена периода не превращает детский портрет во взрослый.
- Загрузка и кадрирование используют общий `PortraitControl`, нормализацию изображений и общую операцию изменения metadata. Аддитивная SQL-миграция `portrait_asset_access_v2` добавляет область доступа draft/world. Старый `portrait_assets.world_id` остаётся действующим. Assets не публикуются через static.
- JSON-экспорт с изображениями — совместимая обёртка `{state, portrait_assets}`; MD/TXT сохраняют переносимые оригиналы в служебном комментарии. Без изображений формат остаётся прежним. Импорт переписывает asset IDs и создаёт локальные originals в одной транзакции; один чужой ID не даёт доступа к файлу. Байты не попадают в WorldState. История и оригиналы сохраняются при выборе процедурного варианта.
- Шрифты из макета поставляются локально с лицензией URW; SVG-слои доверенные и версионированы. Нет внешних avatar/image API, нейрогенерации, CDN-зависимости или изображений локаций.

## Осознанные отличия от HTML

| Отличие | Причина |
|---|---|
| Нет пейзажа в hero, миниатюры мира и картинок мест | Прямое требование автора: никаких изображений локаций |
| Реальная revision/состояние запроса вместо «сохранено в браузере», demo-процентов и таймеров | Источник истины — API, стоимость/прогресс показываются только по серверным данным |
| Явный авторский взгляд и предупреждение о спойлерах | Сохраняется действующая серверная player/author проекция; просмотр не создаёт Knowledge |
| Дополнительные подразделы досье и связанные Runtime-записи | Прототип не охватывает все уже реализованные поля и механики; функции сохранены |
| Пагинация по 12 карточек; поиск и выбор досье по всему составу | Проверена работа с 240 персонажами; сотни форм не монтируются одновременно |
| На мобильном быстрый выбор досье через именованный select вместо ряда миниатюр | Сохраняется быстрый доступ ко всему составу, компактность и управление с клавиатуры |
| Нейтральный вариант для неподдерживаемой внешности/стадии жизни | Нельзя приписывать канону возраст, вид или черты из имени и свободного текста |
| Оформление мастерской хранится отдельно от темы уже открытой игры | Просмотр скинов не меняет другое прохождение; игровые темы остаются прежними |
| Финальное подтверждение, revision-конфликты, recovery и связанные изменения | Обязательные реальные состояния API, которых нет в демонстрационной логике макета |

## Визуальная проверка и ограничения среды

Сверены исходные CSS, размеры колонок/панелей, набор шрифтов, SVG-геометрия и обработчики эталона, а затем реальные браузерные скриншоты приложения с `world-workshop-preview.jpg`. Исправлены обнаруженные конфликты старой типографики, ширины модальных окон и мобильного размещения действий портрета. Обзор, сетка, досье и AI-preview проверяются в Chromium, а не только сборкой.

Интерактивное открытие самого HTML в облачном браузере заблокировано политикой среды. Ограничение не обходилось; продолжение по исходному коду разрешено автором задачи. Поэтому не заявляется автоматическое пиксельное сравнение двух живых страниц и проверка браузерных анимаций исходного HTML. Playwright использует настоящий Chromium для приложения и настоящий HTTP/backend с контролируемым LLM-провайдером.

Live DeepSeek — **NOT RUN**: безопасный реальный ключ не предоставлен. Тестовый провайдер проверяет pipeline и сохранность данных, но не художественное качество живой модели. Мобильные проверки выполнены в эмуляции Chromium; физическая экранная клавиатура Android/Samsung Browser и Safari не проверены. 200% текста проверены независимым масштабированием вычисленных размеров шрифта в браузере, без изменения канонических данных.

Минимальные визуальные свидетельства (синтетические проверочные данные, не демонстрационный мир прототипа):

- [Desktop: обзор](images/world-workshop/desktop-overview.png)
- [Desktop: досье](images/world-workshop/desktop-dossier.png)
- [Mobile: досье](images/world-workshop/mobile-dossier.png)
- [Сложный сценарий: AI-preview связанных изменений](images/world-workshop/ai-preview.png)

При recovery дополнительно обнаружена и воспроизведена гонка существующего `useJob`: queued HTTP-снимок мог затереть уже наблюдаемый этап SSE в той же попытке. Регрессионный тест сначала падал; hook теперь сохраняет наблюдаемый этап, а новая `attempt_epoch` по-прежнему сбрасывает состояние. Это не изменение очереди/проверок Runtime. В тестовом провайдере исправлена обработка отсутствующего `phone_mode`, который сбрасывается сценариями AI-редактора.

## Проверки реализации

База ветки: `master` `08c4e973b0be33326a0efa54f0fdac8ffafb756b` (с исправлениями #185/#186).

| Команда / набор | Результат |
|---|---|
| `python -m pytest tests/test_draft*.py tests/test_initial_draft_v4.py tests/test_worlds.py tests/test_workshop_portraits.py tests/test_portraits.py tests/test_runtime_v3*.py -q --maxfail=5` | 461 passed |
| `python -m pytest tests/test_workshop_portraits.py -q` после добавления проверки ветвления | 6 passed |
| `npm --prefix frontend test` | 101 passed, 16 files |
| `npm --prefix frontend run build` | PASS; остаётся предупреждение Vite о размере основного chunk > 500 kB |
| Playwright: `context-settings.spec.ts runtime-presentation.spec.ts workshop175.spec.ts` | 12 passed, desktop/mobile |
| Playwright: `workshop175.spec.ts` после мобильной визуальной корректировки | 6 passed |
| Playwright: `workshop175.spec.ts -g 'survive Start Game'` с двумя ходами и reload | 2 passed, desktop/mobile |
| Playwright: `calendar-creation.spec.ts communication-profile.spec.ts draft-v4.spec.ts world-ai-editor.spec.ts` | 40 passed, desktop/mobile |
| Playwright: `draft-world.spec.ts creative172.spec.ts creative185-metadata.spec.ts portraits.spec.ts dossier-portraits.spec.ts --project=desktop` | 30 passed |
| Тот же набор с `--project=mobile` | 30 passed |
| Playwright: `review170.spec.ts` после исправления HTTP/SSE race | 12 passed, desktop/mobile |
| Playwright: `runtime-handoff.spec.ts secret-handoff181.spec.ts` | 4 passed: старый экспорт, recovery, ход/reload/ход, безопасные тайны и раскрытие |
| Playwright: `portrait-polish.spec.ts` | 12 passed, 4 штатных skips повторной mobile-матрицы; размеры 360/393/768/1440 проверены внутри desktop-проекта |

Все Playwright-команды запускались из корня как `E2E_OUTPUT=/tmp/<уникальный-каталог> npx --prefix frontend playwright test --config frontend/playwright.local175.config.ts frontend/e2e/<имя.spec.ts> ...`. Временная конфигурация наследовала действующий `frontend/playwright.config.ts` и меняла только путь/флаги Chromium: `/tmp/chromium` из `@sparticuz/chromium@153`, без `--single-process`. Причина — повреждённые ответы загрузчика стандартного браузерного архива в среде. Временная конфигурация и browser dependency не входят в PR. Для обычной среды используется штатная команда `npm --prefix frontend run test:e2e -- <имена.spec.ts>` с установленным Playwright Chromium.

E2E работают с настоящими FastAPI, SQLite, API ревизий, jobs и SSE. Подменяется LLM-провайдер через действующий `tests/e2e_server.py`; production-эндпоинты не имитируются. Тест старого силуэта явно использует сохранение без нового дескриптора; ошибка загрузки изображения в новом мире проверяет процедурный fallback. Desktop/mobile smoke подтверждает сохранность иллюстрации и пользовательского файла после двух обычных ходов с reload; backend отдельно проверяет ветку и независимое кадрирование.
