# Issue #99 — post-fix Live Retest и продолжение Stage C

Refs #99. QA PR [#230](https://github.com/Troyevv/ai_rpg_engine/pull/230).
**Stage C не завершена. Готовность к длительной пользовательской кампании не подтверждена.**
Продуктовый код не изменён, PR не мёрджится, Issue #99 остаётся открытой.

## Версии и воспроизводимость

- Свежий master: `25c834b094a9047471406d7166111c8b6b755f75`.
- Все платные действия выполнены на QA `9f83354de54488111ea9840475046d32be581234`.
  Последующие изменения — ожидание готового QA UI и этот отчёт; итоговый HEAD/CI указан в PR.
- Прочитаны AGENTS.md, #99, #36, #46, полный отчёт #219 и PR #224/#225/#227/#228/#229.
- Проверены ancestry и owning code: #220/PR224 `1b2e3e42`, #221/PR225 `a06caf7e`,
  #222/PR227 `8d281b0b`, #223/PR228 `68a584d2`, #226/PR229 `25c834b0`.
  Закрытый статус Issue не использовался как доказательство исправления.
- #219 остаётся открытым. Его QA-only commits перенесены на свежий master, чтобы
  переиспользовать тот же `devtools/live99`; второй harness не создавался.
- Production FastAPI, системный Chromium/Playwright, настоящий DeepSeek Flash,
  thinking off, отдельная SQLite-копия, loopback server. API-ключ доступен;
  ключ не передавался браузеру и не сохранялся в evidence.

Предыдущие SQLite/checkpoints/raw streams доступны. Исходные архивы #219 не изменены:
`live99-stage-c-evidence-20261107.tar.gz`, SHA-256
`1d4b5119bc20f11e66ec5384e6c8717ae48744c3e25dc23b4a3402bad9d74b13`;
`live99-stage-c-validation-20261107.tar.gz`, SHA-256
`396e36dcd7ed2d3ddde84e8ec2d9bbc06908328ec3fe8d4bb3b319c029a297d4`.
Семь перенесённых checkpoints прошли сравнение до/после загрузки новым Repository.
Для remote birth подготовлена дополнительная pregnancy fixture, но она не запускалась.

## Объём и бюджет

**28 новых QA-действий, 19 jobs с LLM, 42 вызова DeepSeek.**
18 jobs сохранены, 1 отклонён атомарно; saved не означает semantic pass.
Остальные 9 действий: 4 abandon, 3 восстановления старых повреждённых ветвей,
выбор sibling variant и rollback для branching. Автоматических повторов Narrative нет.
Одна regeneration выполнена явно как самостоятельная проверка и учтена в стоимости.

| Группа | QA-действия | LLM-вызовы | Saved / rejected jobs | Usage USD |
|---|---:|---:|---:|---:|
| Social | 2 | 2 | 0 / 1 | 0.003196722 |
| Family | 3 | 4 | 2 / 0 | 0.006511092 |
| Crisis | 2 | 2 | 1 / 0 | 0.002403660 |
| Knowledge | 9 | 16 | 8 / 0 | 0.027659028 |
| Campaign / LTA | 10 | 16 | 6 / 0 | 0.020268642 |
| Phone / UI | 2 | 2 | 1 / 0 | 0.002942964 |
| **Всего** | **28** | **42** | **18 / 1** | **0.062982108** |

Вызовы: 18 Narrative + 18 Extraction + 3 LTA Narrative + 3 LTA Extraction.
Repair/retry calls: **0**; отсутствие repair не означает отсутствие дефекта.
Input **526506**, в том числе cached **203136**; output **23112** токенов.
Все 42 ответа сохранены полностью, `finish_reason=stop`, точное совпадение
production response_text с независимыми provider streams: **42/42**.

Тарифы 7 ноября сверены по официальной
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing.md):
Flash peak/uncached input $0.30/M, cached $0.006/M, output $1.20/M.
Перед каждым dispatch резервируется весь возможный context 1048576 + output cap.
Консервативный расход нового прогона **$0.1856862**, остаток лимита $2 —
**$1.8143138**. Usage-сумма выше рассчитана по фактическим receipts/тарифу,
а не является выпиской долларового списания. Balance API: **17.01 → 16.66 CNY**,
USD balance 0; валютная конверсия не выдумывалась, возможны округления провайдера.

Исторический baseline сохранён: **205 calls / 124 actions**.
Теперь ledger содержит **247 calls / 152 actions**, unknown outcomes **0**.
Исторические строки и авторизации A/B/C не заменены; новый дополнительный предел
привязан один раз, resume не возобновляет $2. Остановка вызвана результатами QA,
а не исчерпанием бюджета.

## Targeted retest

| Проверка | Фактический результат |
|---|---|
| Campaign/014, #220 | Старый payload теперь отвергается `event_minute_invalid`. Новые Events: 2105840 внутри [2105840,2105842], 2105842 внутри [2105842,2105844]. History calendar_date/provenance и reload согласованы. **Пройдено в проверенном сценарии.** |
| Family, #221 | Сохранена прежняя остановка на due; после abandon локальная сцена продолжилась при minute=1980, затем birth_completed на 1980, clock=1982. Birth/parent links созданы. **Частично:** новая семантическая ошибка #231 останавливает группу; remote birth/Knowledge и последующие milestones не проверены. |
| Knowledge/001, #222 | Старый неподтверждённый commitment по-прежнему корректно отвергается бесплатным replay. UI abandon не вызвал LLM, сохранил Narrative/diagnostics и draft, не изменил canonical state. Новый явно согласованный ход сохранился; встреча 2026-10-06 15:00, Тимур приглашён, его согласие не заявлено. **Пройдено.** |
| Phone/006, #223 | NPC вышел из дома без названного назначения. Extraction вместо прежнего null придумал arrival в мастерскую. HTTP/job saved, но canonical destination не подтверждён Narrative. **Не пройдено; тот же regression requirement #223, без дублирующей Issue.** |
| Crisis/010, #226 | Вера остаётся дома и не попадает в participants/witnesses библиотечного Event; нет Knowledge acquisition. Физическое присутствие исправлено **в этом ответе**, но модель заменила выбранного игроком адресата Веру на Марину — #232. Продолжение группы остановлено. |

Бесплатные exact-payload replays также подтверждают сохранность отрицательных guards:
`ordinary_temporal_boundary`, `controlled_actor_unsupported`,
`continuity_external_decision`, `movement_endpoint_invalid`, `event_presence_invalid`.
Диагностические controls никогда не применялись к игровой SQLite.

## Подтверждённые дефекты — вне QA PR

Все новые Issues созданы после поиска дублей; severity **P2**, не P1.

- [#231](https://github.com/Troyevv/ai_rpg_engine/issues/231): Narrative и Event
  говорят «девочка», а предопределённый canonical child остаётся male.
  Job `163b64b414184760b47c27af15b789d9`, child `character_827f657aa87adc1fb374`.
  Пол ребёнка не был раскрыт Narrative-контексту, Extraction видел canonical male,
  но сохранил противоречивый Event; Knowledge о наблюдаемом поле не создан.
  Это дефект согласования модели/контекста/Extraction, не разрешение менять
  предопределённый пол или раскрывать скрытые сведения всем NPC.
- [#232](https://github.com/Troyevv/ai_rpg_engine/issues/232): действие Нины
  «спрашиваю Веру» стало разговором с Мариной и было принято как
  `player_interaction` с исходным несовпадающим player_evidence.
  Job `8fb7802584e741d89804bfbfc0119e4a`.
  Новый дефект семантики agency; это не повторный false-presence #226.
- [#233](https://github.com/Troyevv/ai_rpg_engine/issues/233): явно заданное
  согласие сортировать фотографии потеряло обязательный beat.player_evidence.
  Job `8d37b2ab234a4f2f99d76d391982a9f9`. Runtime корректно отклонил decision;
  exact replay повторяет отказ, добавление только исходного player input в beat
  проходит. В отличие от #203/#207 это настоящий decision, а не optional question/proposal.
- [#223](https://github.com/Troyevv/ai_rpg_engine/issues/223) остаётся непройденным
  по требованию «не выдумывать destination». Job `2e8ae5133f71476483c86b27cc5a469c`:
  location Тимура стала `location_567f2d7db666cb5e4abf` (мастерская), хотя он лишь
  вышел из дома. Exact replay принимает эту ошибочную Extraction; control без
  неподтверждённого movement сохраняет уход и устанавливает unknown location.

Social, Family, Crisis и Phone удерживаются semantic receipts, включая saved jobs.
Новые доказательства не маскируются успешными HTTP status или повторной генерацией.

## Продолжительные последовательности и качество

**Knowledge:** 8 последовательных saved turns (retest + 7 continuation), clock
553 → 568. Предположение о каталоге, вопрос о firsthand/hearsay, явная поправка,
передача поправки, проверка источника, сокрытие письма и предложение проверить
публичное расписание. Тимур правильно отличает услышанное от увиденного; Вера
не придумывает, что ранее отдельно пересылала сообщение. Вопросы/предложения не
вынуждают player consent. Facts и Knowledge коллекции остались буквально прежними;
player emotion/goals/intentions/obligations не изменились. **Это подтверждает
диалоговую последовательность и отсутствие замеченной утечки, но не полноценную
механику новых, ошибочных или устаревающих Knowledge.** Новых relationship changes нет.

**Campaign:** 2 retest turns, regeneration, возврат sibling, rollback, новая ветка,
observer/background и годовой LTA. Regeneration использует побайтно тот же исходный
Narrative context. Выбор варианта и rollback восстановили точные World State и
history_head; прежние siblings не изменены. В новой ветке NPC предлагают помощь,
не назначая решения игроку. Обещание звонка осталось в thread/situation, без
structured scheduled event; наличие календарного commitment не утверждается.

LTA `f4b7379c7ea24104a7d02c74ef40cd95`: **2030-10-06 → 2031-10-06**, 6 вызовов,
1 accepted group, 13 unresolved. Из них 11 `budget` (лимит вызовов конкретного LTA),
2 `unresolved` / `invalid_outcome` (нет принятого Event). Единственное изменение —
Event и thread фонового персонажа 6 о продолжении записей в тетради; персонажи,
Knowledge и отношения не изменились. Все шесть LTA raw responses сохранены,
включая два пустых Extraction outcomes. Это ожидаемая честная диагностика
unresolved, но недостаточное доказательство содержательного развития мира.
Пятилетнее расширение остановлено без увеличения лимитов. После явного observer
mode controlled_actor=None; будущие first-person действия требуют предварительного
явного выбора героя, план автоматически не исполнялся дальше.

Повествование читаемо, голоса NPC различимы, встречаются самостоятельные предложения
и уход NPC. Однако повторяются паузы, чашки, «ждёт решения Кирилла»; LTA почти
повторяет исходное утро. Описание ребёнка как малыша на руках сохраняется через
годы. Это замечания к качеству/контексту и гипотеза о сюжетном застое; отдельный
доказанный Runtime-дефект из этого не выводится.

**Не проверены:** remote birth и его POV/Knowledge, взросление/характер/milestones,
новая смерть/недееспособность во время активного канала, полноценное развитие
отношений, новая серия direct/group/call после #223, пятигодовой LTA и закрытие
существенных обязательств. Все шесть групп были затронуты, но полное покрытие
шести групп отсутствует.

## Сохранность и среда

Run: `/workspace/work/live99-stage-c-retest-20261107`;
parent: `/workspace/work/live99-stage-c-20261107`;
общий исторический ledger: `/workspace/work/live99-smoke-20261106/budget.sqlite`.
Каждый шаг сохраняет intent, action, before/after, delta, History, diagnostics,
request/job IDs, модель, usage, finish_reason, raw responses и UI projection.

Старые некорректные Campaign/Crisis History сохранены как исторические ветви.
В новой копии выполнен штатный UI rollback до безопасных snapshots; это не
переписывание старых Events. На новых активных ветвях не найдено нарушений
проверенных временных интервалов. Все предыдущие варианты сохранили hashes.
Social refusal атомарен. Resume обоих phases повторно дал **0 calls / 0 actions**,
сохранил snapshots, requests, ledger и hashes всех исходных step artifacts;
held-группы не разблокировались, Knowledge не запустился заново.

Семантический retrieval в среде возвращал `OSError` и использовал предусмотренный
структурный fallback: локальный embedding model не был доступен. Это ограничение
контекста проверки, не mock DeepSeek. Доказательств поведения с активным embedding
retrieval этот прогон не даёт.

## Проверки

| Проверка | Результат |
|---|---|
| `tests/test_live99*.py` | 63 passed; бюджет, unknown outcome, recovery/resume, retest и semantic hold |
| Runtime targeted #220/#221/#222/#223/#226 | 60 passed |
| Frontend Vitest | 148 passed / 22 files |
| TypeScript / production build | passed; существующее предупреждение о размере chunks |
| Live preflight | 6 групп × desktop/mobile |
| Финальный read-only Chromium | 12/12: все 6 групп × desktop/mobile; данные родословной/календаря загружены, reload не меняет snapshots, 0 provider calls |
| Полный CI live-code HEAD `9f83354` | [run 42358111364](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42358111364): backend **3322 passed, 1 skipped**, 1236.49s; frontend, все desktop/mobile smoke/full shards, e2e-full/e2e-smoke/verify success |
| Итоговый HEAD после QA UI wait / отчёта | [PR checks](https://github.com/Troyevv/ai_rpg_engine/pull/230/checks); точные SHA/run/results — в описании PR |

Один существующий backend skip требует приватный RPG_REVIEW170_EXPORT; новых skip
и ослаблений assertions нет. Первый локальный focused-запуск без разрешённого
loopback остановлен до завершения; его лог сохранён, причина зависания не доказана.
Правильно разрешённый socket-запуск прошёл 60 тестов. Это не объявляется flaky.
Первый набор финальных UI screenshots поймал загрузку lazy workspace;
он сохранён как evidence недостатка QA ожидания. Повторная проверка ожидает
отображённые family nodes/calendar days. Продуктовый UI не меняется.

## Решение

QA-инфраструктура и доказательства пригодны для review после зелёного итогового CI.
Движок **не подтверждён для длительной пользовательской кампании**: #231–#233,
непройденное требование #223, частичный Family/Crisis/Phone и слабый результат LTA.
Перед дальнейшими платными прогонами исправить отдельные продуктовые Issues,
повторить точные сохранённые payload бесплатно, затем согласованно продолжить
held checkpoints/изолированные fixtures с прежним ledger. Не объявлять #99
или Stage C завершёнными и не мёрджить этот PR автоматически.
