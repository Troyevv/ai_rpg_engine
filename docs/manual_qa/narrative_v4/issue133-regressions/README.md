# PR #133: исправление регрессий пользовательского тестирования

База до исправлений: `a8c5e80328500208e19788837091118fe8d313b1`, существующая ветка `codex/issue122-phone-scenes-commitments`. Рабочий master до PR: `50d6694db0ee838c99a34f2159386e05e04186a8`. Прочитаны AGENTS, Issue #122 и Epic #36. Новый PR не создаётся, Issue не закрывается, PR остаётся draft.

## P0: DeepSeek

**Установленный дефект запроса:** новый semantic prompt не содержал слова JSON ни в system, ни в user message. При этом запрос включал `response_format={"type":"json_object"}`. Сериализация JSON-схемы в строку сама по себе не добавляет слово JSON: старый воспроизводимый payload теста его не содержит. Рабочий remote decision prompt содержит явную JSON-инструкцию.

[Официальный контракт JSON Output](https://api-docs.deepseek.com/guides/json_mode/) требует JSON-инструкцию и пример. Добавлены оба. `remote_initiative`, `remote_decision`, Runtime communication lifecycle и количество автоматических Retry не изменены. Схема передаётся **в prompt**, не как неподдерживаемый `json_schema` API-параметр.

`tests/test_phone133.py` пропускает запрос через настоящий OpenAI SDK и `llm.chat_stream` до HTTP-транспорта: `/chat/completions`, `deepseek-flash`, `stream=true`, `include_usage=true`, thinking disabled, исходный лимит update_tokens, `json_object`. Контролируемый HTTP-сервер отвергает старый payload и принимает новый. Это проверка контракта, **не live-вызов DeepSeek**. Фактический fixture-payload: **10 659 байт**, 5045 оценочных входных токенов, `max_tokens=4096`, окно 32768; [неперсональные параметры](sdk-request-metadata.json). Размер дополнительно ограничен тестом; canonical context budget и полный исходный текст сообщений сохранены.

**Граница доказательства:** ключ DeepSeek в среде отсутствует; исходное тело ответа API из пользовательского запуска не предоставлено. Поэтому именно причина того production HTTP 400 не подтверждена ответом сервера. Отсутствующая JSON-инструкция — конкретный воспроизведённый дефект и объяснение, согласующееся с симптомом, но не основание объявлять live-проверку пройденной. PR остаётся draft до такой проверки.

Теперь настоящий HTTP-отказ сохраняет в существующей общей диагностике статус, допустимый тип/параметр ошибки, классификацию известного сообщения, SHA-256 тела и неперсональные размеры/параметры запроса. Тело ошибки, произвольный server echo и ключи не публикуются и не сохраняются. Неизвестная причина обозначается `unclassified_rejection`, а не выдумывается. Тест подставляет ключ и персональный echo в ответ и проверяет их отсутствие в SQLite.

Semantic Extraction сохранён. Он вызывается только для новых принятых текстовых источников; чтение, открытие/сворачивание телефона, набор/завершение звонка не запускают его. При новом свободном тексте один вызов нужен, чтобы отличить бытовую реплику от намерения или договорённости: эвристика по словам «привет»/«встреча» не используется. Повторная обработка accepted journal не повторяет send/read/reply. Обычный голосовой разговор использует прежний Narrative → Extraction.

## P0: варианты физической сцены

Первопричины: `save.turns.at(-1)?.choices` выбирал последний **канонический** ход, включая телефонную квитанцию/разговор; общий `!pending` дополнительно удалял весь блок при телефонной обработке; выделение сбрасывалось от идентичности последнего телефонного варианта и busy.

Теперь API вычисляет `physical_choice_source` из активной History и существующего after snapshot. Проверяется владелец/POV и применимость к физической сцене: место, присутствующие, ситуация, состояние жизни/условия, значимые предметы. Принятое внешнее физическое событие в смешанном звонке инвалидирует старые предложения. Новый физический ход с пустыми choices не заставляет возвращаться к ещё более старым.

Frontend использует идентичность этого источника для списка, анимации и выделения. Телефонные jobs временно блокируют отправку, сохраняя предложения. Rollback/variant/reload пересчитывают ту же проекцию; нового Runtime, choice store или фиктивного хода нет. Черновики и anchors остаются у прежних владельцев #72.

## P1: игровой телефон

Уточнение пользователя заменяет старое R02 о диагностике в телефоне. Удалены `activity`, история jobs, технические подробности/JSON, квитанции saved jobs и пояснение внутренних таймаутов. Сохранены контакты, личные/групповые переписки, статусы доставки/чтения и журнал реальных вызовов. Ошибка и «Повторить» привязаны к нужной переписке/вызову.

В общей «Диагностике» есть «История и восстановление»: существующие средства вариантов/регенерации используются повторно, без второго текста/streaming buffer. Там же доступны usage, provider rejection и прежний журнал checkpoints. Сцена звонка показывает литературный текст и игровые действия; developer controls в ней больше нет. Backend/History не удаляются.

Дополнительно устранены гонки позднего ответа HTTP, стиравшего следующий черновик, и автоматического read, позволявшего нажать кнопку до отображения блокировки. Непрочитанный перенос/отмена теперь сохраняет прежний известный план через существующую History; фильтрация применяется до context relevance/pacing.

## Проверки и воспроизведение

| Сценарий | Автоматическая проверка |
| --- | --- |
| A | `phone133.spec.ts`: настоящее создание/start job, обычный ход, две реплики и ответы; `test_phone133.py`: настоящий SDK/HTTP transport, точная реплика из отчёта |
| B | Тот же browser flow проверяет источник и текст choices после send, соединения, разговора, сворачивания и отбоя; unit/API tests — streaming/error/commit/variant/rollback и физическая инвалидизация |
| C | `test_phone122.py`, `phone122.spec.ts`: 11:00 от предложения в 09:00, unread/read, календарь, оба участника, перенос/отмена, intentions, группы, Time Skip, resolved и следующий ход |
| D | SDK/API и browser: отказ semantic stage, reload, Retry, ровно два remote decisions, только повтор semantic, два сообщения и одна минута |
| E | Реальный Chromium: desktop, mobile 360/393, Graphite/Parchment; нет технических меню в Phone/CallScene, инструменты доступны в Diagnostics |
| F | `phone133.spec.ts`: обычный ход → переписка → звонок → отбой → обычный ход → reload → следующий ход; календарь и права дополнительно в #122 API smoke |
| #72 | `phone122-streaming.spec.ts`: длинный bursty SSE, независимые anchors, reduced motion, восстановление и возврат |

```bash
python -m pytest -q
cd frontend
npm test
npm run build
npx playwright test --reporter=line
```

В этой среде браузер запускается с `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/issue133-browser/chrome-headless-shell-linux64/chrome-headless-shell` (Chromium 134); штатный CDN-загрузчик Playwright вернул повреждённый архив. CI использует штатную установку. Видео записаны настоящим браузером, не сгенерированы. Для world-authoring fixture JSON используется chunk 512, для narrative — прежние 60 символов; искусственная задержка growing schema больше не создаёт ложные таймауты UI.

Локально: **2190 backend tests passed**, **31 frontend tests passed**, production build пройдён; focused phone/calendar/context **56 passed**, усиленная проверка исходного времени и HTTP contract **20 passed**. Финальный локальный browser-прогон: **38 passed (5.5m)**, baseline: **4 passed** (три в исходном прогоне, один после ожидания отображения initial choices; два неприменимых recovery assertions пропущены на baseline). CI фиксируется в [PR #133](https://github.com/Troyevv/ai_rpg_engine/pull/133) на соответствующем HEAD. Числа пересекаются и не суммируются.

## Реальные материалы до/после

| Состояние | До (`a8c5e80`) | После |
| --- | --- | --- |
| Телефон desktop | [Graphite](before-desktop-graphite-messages.png) | [Graphite](after-desktop-graphite-messages.png) |
| Основные choices после сообщений | [Graphite](before-desktop-graphite-choices.png) | [Graphite](after-desktop-graphite-choices.png) |
| Сцена звонка mobile | [Parchment](before-mobile-parchment-call.png) | [Parchment](after-mobile-parchment-call.png) |
| Возврат к сцене | [Parchment](before-mobile-parchment-return.png) | [Parchment](after-mobile-parchment-return.png) |

[Desktop до](before-desktop-graphite.webm) · [Desktop после](after-desktop-graphite.webm) · [Mobile до](before-mobile-parchment.webm) · [Mobile после](after-mobile-parchment.webm). В каталоге — обе темы/устройства и read-projection JSON со связями choices/RemoteInteractions/History. До запускается отдельный worktree исходного PR, меняется только транспорт тестового провайдера.

Платных вызовов: 0, фактические расходы $0. HTTP-contract fixture не сообщает token usage: значение неизвестно, не ноль. Общие старые browser fixtures могут содержать синтетические counters; они не измеряют live-расход. Реальная iOS/Android клавиатура и качество семантики конкретного live DeepSeek остаются вне автоматического подтверждения. Миграции БД и изменений Tabletop нет.
