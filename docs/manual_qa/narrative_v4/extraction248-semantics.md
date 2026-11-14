# PR #248: согласованный Extraction, без новых платных вызовов

> Исторический отчёт предыдущего этапа. После него [Live A/B/C](https://github.com/Troyevv/ai_rpg_engine/pull/248#issuecomment-6720846564)
> выполнен; утверждения ниже «B/C не запускались» больше не описывают текущий статус.
> Актуальная доработка #249 и ещё не запущенный C/D: [evidence-first249.md](evidence-first249.md).

Исходный HEAD: `87abdb8dbe67fbe191cadd30fe2aa785672bde01`. Дата: 2026-11-08.
Новые вызовы DeepSeek: **0**. B/C ещё не оценивались моделью. PR остаётся draft.

## Доказательства и первопричины

Исходные части объединены в порядке part00 → part01. Получен gzip/tar размером
109621029 bytes, SHA256 `4306f22a7d9ffd01b45f066afbd5e740d21e9e1b5963ae1706ba6dc2ac509b17`.
CRC gzip и **284/284** внутренних SHA256 проверены; четыре game.sqlite и два ledger.sqlite
проходят read-only integrity_check. Оригиналы не открывались через Repository и не изменялись.
Все операции Repository/rollback/abandon выполнялись на отдельных SQLite-копиях.

Последний [Live QA](https://github.com/Troyevv/ai_rpg_engine/pull/248#issuecomment-6714788310)
и технический аудит проверены по исходным сообщениям, а не только по описанию PR.
Архив содержит исторические requests: все payloads шести фикстур #245 из
`tests/fixtures/issue247/{crisis,phone,family,knowledge,social,campaign}.json` совпали с
сохранёнными ответами SQLite. Отдельного полного raw-пакета #245 в этом запуске нет;
использованы его оригинальные ответы/сохранения, сохранённые в предоставленном архиве.

1. **Default ошибочно признан override.** Штатный `state_update_prompt.md` из `2abe43a8`
   имеет SHA256 `3578e11b08ffa894a0ed7644e2f1839139a2cecda4519401625b0fa32d141310`.
   Он отсутствовал в `default_updates.json`, как и другие исторические версии. Его
   8628 UTF-8 bytes отправлялись перед актуальным контрактом. Старые инструкции разрешали
   NPC arrival без Movement и предлагали опускать Knowledge при неполной цепочке.
   Все 10 отобранных A-запросов побайтно совпали с request messages provider streams.
2. **Visibility подменяет contact.** `event_presence` добавлял camera.location для observed
   participant в conversation, но не для witness. Удаление Веры из witnesses легализовало
   разговор, хотя она оставалась дома. Точный repair `e056ffdaff6347a79bf9a450972e1b4f`
   принят на исходном коде и отклонён с исправлением (`event_presence_invalid`).
3. **Agency review не покрывает незаписанные решения.** Phone Narrative сам выбрал отказ
   от чая жестом; JSON объявил preserved и не создал Event отказа. Это семантическая ошибка,
   которую Python без интерпретации прозы не обнаружит. Оригинальный JSON всё ещё структурно
   допустим; тест прямо фиксирует этот предел вместо ложного заявления об исправлении.
4. **Repair оптимизировал валидность, не смысл.** Фактически он удалил witness, сохранив
   невозможный контакт. Feedback теперь требует сверки исходной сцены и связанных последствий,
   а не удаления события/свидетеля/знания ради saved.

## Реализация и границы

- Один существующий registry: добавлены точные хеши 13 пропущенных исторических defaults.
  DocumentStorage и ExtractionContextBuilder читают его через общий helper. Нет fuzzy matching
  или классификации по фрагментам текста. Реальная пользовательская правка сохраняется.
  Старые document_versions, job configs, Narrative, snapshots и request logs не мигрируются;
  обычное существующее обновление активного штатного prompt остаётся append-only.
- Ядро контракта организовано по источникам/результатам, месту/наблюдению/контакту,
  Event–Fact–Knowledge и текущему состоянию персонажа. Дублирующие правила сокращены.
  Домены plans/life/social/residence/roles/personality/motivations/values/reproduction/
  appearance/possessions/scene_actions/continuity/remote/letters/choices/time сохранены.
- Agency проверяется в обе стороны по **всему** Narrative: покрытие ввода и отсутствие новых
  добровольных ответов, решений, обещаний, согласия/отказа, включая жесты. Физическая детализация
  заданного действия допустима; NPC может самостоятельно действовать и ошибочно трактовать
  молчание, не создавая решение игрока. Нарушение самой прозы → существующий violated/reauthor.
- Repair сохраняет реальные авторство, witnesses, Events и Knowledge; исправляет связанные
  ссылки вместе. Не придумывает прибытие, согласие, неизвестного говорящего и не подменяет
  его ближайшим NPC. Корректный Narrative не генерируется повторно.
- Observed больше не доказывает conversation. Наблюдение поддержано отдельно; типизированный
  completed interaction нельзя легализовать сменой medium на observation. Общая каноническая
  география и последовательность движений остаются владельцами physical contact; отвеченный
  call/доставленное сообщение используют существующие каналы. Нет NLP/regex по прозе.
- Разговор через проём допустим при установленном общем месте без нового boundary-узла.
  Если персонаж после ухода имеет unknown location, новая беседа требует настоящего возвращения
  с существующим Event/Movement. Старый synthetic journey неверно считал observed достаточным:
  исправлены его provider-данные и текст фактического возвращения, не Runtime guards.
- Новые локации, самостоятельные маршруты NPC и существующий background путь сохранены.
  Отдельная проверка background на исходном Phone checkpoint создаёт новую фотолабораторию,
  перемещает Тимура, сохраняет игрока/его Knowledge и откатывается через штатный rollback.
- Публичные API/SQLite schema не меняются. Дополнительных стадий, retries и обязательных
  LLM-вызовов нет. Provider/model/thinking/temperature/output limits не менялись.

## Проверка

Основные команды:

```sh
python -m pytest -q tests/test_extraction_semantics248.py tests/test_live248_recovery.py tests/test_integrated_repair247.py tests/test_event_presence.py tests/test_movement_semantics223.py tests/test_departure_extraction.py tests/test_due_boundary_repair.py tests/test_narrative_authority136.py tests/test_context_builder_v2.py tests/test_pov_documents.py tests/test_e2e_arrival_fixtures.py
python tests/replay_live248_sqlite.py EXTRACTED_ARCHIVE NEW_REPLAY_DIRECTORY --final
python -m devtools.live99.extraction_compare EXTRACTED_ARCHIVE NEW_REQUEST_DIRECTORY
```

12/12 SQLite replays на полных исходных базах достигли ожидаемого результата. Проверены
точные checkpoint/History через штатный rollback, старые siblings, reload, атомарность,
abandon, неизменность Narrative и оригинальных файлов. Knowledge — 4 приобретения,
Family — 10, только настоящим слушателям. Исправленный контроль violated — явно тестовый,
не ответ модели. Phone original saved — **семантический FAIL**, не положительный контроль.

Регрессии включают все 16 исторических версий default, настоящие overrides, обычный ход,
retry, regeneration, sibling selection/rollback, отсутствие второго Narrative на retry,
observation/doorway/call/arrival, создание локации и скрытое от игрока фоновое перемещение.
Промпт помещается в прежние hard limits; бюджетные assertions не повышались.

Профильный набор: 243 passed; дополнительные legacy extraction/corpus проверки: 48 passed.
После финального сокращения формулировок: 95 passed (remote/context/defaults/agency/choices).
Сценарий возвращения из browser provider отдельно прошёл через настоящие jobs без браузера.
Frontend unit: 151 passed; production build passed (прежнее предупреждение о крупном chunk).
Локальные browser E2E запускались, но Chromium завершился до страницы: `socket() failed:
Operation not permitted`; это не pass и не дефект UI. Browser gate — итоговый GitHub CI.
Полный backend и итоговый CI отражаются отдельно в актуальном описании PR; ранние падения
при редактировании не выдаются за финальный результат.
Полный локальный процесс, запущенный до последних правок: 3678 passed / 9 failed / 1 skipped
за 1479.48 s. Все девять исправленных случаев повторно прошли на финальном коде: 9 passed.
Это не равнозначно полному зелёному запуску на финальном HEAD; его gate — GitHub CI.
CI #480 на `7075926`: backend 3687 passed / 1 failed / 1 skipped; frontend 151 passed,
desktop 358 passed, mobile 334 passed / 24 штатных skips. Единственное падение — старый
assert на заголовок «Live regression» в `test_goals_values`; содержательное lifecycle-правило
сохранено. Проверка теперь требует само правило завершённого результата и различение
предложения поездки / долгосрочной цели. Дополнительный commit меняет только этот тест
и отчёт; production-код остаётся тем же. Результат повторного CI — в описании PR.

## A/B/C: фиксированные данные, а не новый harness

`devtools/live99/extraction_compare.py` только подготавливает файлы; в нём **нет dispatch**.
Используются существующие live99 evidence и Runtime. Платный этап должен использовать
существующие Budget/receipts, без второй системы лимитов или изменения старых reservations.

- **A:** 10 исходных завершённых Extraction-запросов последнего QA, их сохранённые ответы
  и 5 полных repair. Не повторять A платно. Прерванный исторический request 323 не
  переоценивается и не превращается в complete; он вне выбранной завершённой выборки.
- **B:** тот же A, удалён только точный исторический default. Остальные messages/схема/
  Narrative/canon/параметры сохранены.
- **C:** тот же B, заменены только актуальный Extraction и agency contracts.
- **Holdout:** ещё 10 явно обозначенных авторских перефразировок на исходных checkpoints,
  без совпадения с few-shot примерами. Есть разрешённый отказ и ошибка интерпретации NPC,
  незаданный promise, фактическое прибытие, намерение, детализация действия, реальный источник,
  сохранение Knowledge и background arrival. Для background используется штатный `observe`
  и ContextBuilder; это отдельный режим, не всеведущая вставка в обычный ход игрока.
  У holdouts **нет сохранённых A-ответов** и нет результатов модели.

При подготовке проверяются hashes, integrity, неизменность данных между B/C, json_object,
thinking=off, схема и текущий hard budget. Полученные файлы — сопоставимые кандидаты для
будущего опыта, а не доказательство качества.

Ручная оценка **только выбранных 10 исходных A случаев**, не статистика модели вообще:

| Метрика | Наблюдение A | B/C |
|---|---|---|
| Первое структурное сохранение | 5/10 | Не запускались |
| Первое семантически корректное завершение | 4/10; Phone agency saved, но FAIL | Не запускались |
| Успешный bounded repair по смыслу | 4/5; Crisis repair saved, но FAIL | Не запускались |
| Семантически приемлемый результат после repair | 8/10 | Не запускались |
| Agency | Незаданный отказ в Phone; невозможный completed contact в Crisis | Нужна модель |
| Прибытия | Уход с unknown endpoint сохранён; новое реальное прибытие в выбранных исходниках не возникло | Нужны holdouts |
| PlayerAction/Event coverage | Knowledge/Social/Campaign восстановлены; Crisis completed недостоверен | Проверять отдельно от saved |
| Knowledge/provenance | Knowledge 4; Family 10 только родителям, неизвестный врач сохранён после repair | Проверять полноту и источники |

Для B/C считать отдельно false commit, false refusal, agency, intention/arrival confusion,
Event/action coverage, сохранность каждого acquisition, правильный источник/слушателей.
Для исходно ошибочного Narrative правильный violated/reauthor — успех, saved — провал.
Для корректного Narrative необоснованный reauthor — провал. В repair denominator включать
только случаи, дошедшие до единственного штатного repair; различать correct repair и refusal.
Не усреднять background и обычный ход как один вид latency.

## Короткий Live QA — план, не разрешение

Первый блок: `crisis`, `knowledge`, `phone_agency`, `family_birth`, `intent_holdout`,
`arrival_holdout`, `detail_holdout`, `background_arrival_holdout` для B и C.
Это **16 первых Extraction**, максимум **16 bounded repair**, без новых Narrative.
Чередовать B/C, сохранить каждый первый ответ; ни reroll ради PASS, ни повторного успешного
Narrative. Восемь случаев выбраны до вызовов; остальные 12 уже подготовлены для следующего
блока, если короткий этап оправдает продолжение. Три ongoing-labor исходника, Social,
Campaign и негативные/позитивные agency-контроли не объявляются проверенными этим первым блоком.

Flash, `thinking=off`, temperature=0.1, context=65536, output=8192, json_object.
Предлагаемый предел блока — **32 calls / $1**, новое явное разрешение обязательно; сейчас 0.
Ориентир по исходным usage/размеру запросов: примерно $0.15–0.40 с repair, не гарантия счёта.
При 65536 input + 8192 output на все 32 вызова расчёт peak/cold = $0.9437184. Это оценка по
настроенному объёму, не замена существующего более консервативного reservation на 1M input:
его не снижать. Неизвестный исход/недостаточный остаток останавливает этап по существующим
правилам; старый остаток разрешения не переиспользовать.

При выборе C после семантической проверки — отдельные короткие production jobs/API/UI/reload
на копиях тех же SQLite, включая reauthor/abandon, корректное сохранение и sibling/rollback.
Никаких полной кампании/LTA и автоматического merge. Новые платные шаги сначала оценить
внутри отдельно разрешённого бюджета.

## Размер, скорость и источники

A: 182743 реальных input / 11124 output токенов суммарно по 10 первым Extraction;
медиана записанной duration — 5.55 s. Это время прошлых запросов, не измерение B/C.
Размеры A/B/C автоматически выводятся в `summary.json` (UTF-8 conservative estimate
отделён от настоящего usage). C удаляет **8602 UTF-8 bytes (8.40 KiB)** system context относительно A;
относительно уже очищенного B добавлено **27 bytes**, полный функциональный охват
сохранён. Repair feedback короче прежнего. Новых обязательных LLM-вызовов **0**.
Фактическую задержку B/C измерять receipts; улучшение скорости не заявляется без модели.

Официальная [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
рекомендует json_object, слово JSON, пример формата и достаточный max_tokens. Они сохранены;
добавлены контрастные JSON-фрагменты с правильной интерпретацией. JSON-valid не означает
semantic-correct. [Тарифы Flash](https://api-docs.deepseek.com/quick_start/pricing/):
peak/cold $0.30/M input, $1.20/M output, проверены 2026-11-08; перепроверить перед оплатой.
Thinking не включался и не входит в план.
