# #249: evidence-first Extraction, кандидат D

Исходный HEAD PR #248: `4dc593e798892f0cfb3d1764468dd5516ce3bb85`.
Дата: 2026-11-08. Новых платных вызовов: **0**. Live C/D: **NOT RUN**.
PR остаётся draft; семантическое преимущество D и готовность к merge не доказаны.

## Доказательства и подтверждённые причины

[Последний сравнительный Live QA A/B/C](https://github.com/Troyevv/ai_rpg_engine/pull/248#issuecomment-6720846564)
уже выполнен: у B и C по 2/7 корректных первых Extraction, 5/7 после одного repair.
Старый отчёт «B/C не запускались» описывает предыдущий этап, а не текущее положение.
Phone/001 содержит незаданный отказ от чая; обе версии пропустили его. C также требовала
repair времени Knowledge и связей Arrival; Detail остался ошибочным. B ошиблась в Family basis.
Эта маленькая выборка не измеряет общую надёжность модели.

Оригинальный архив A доступен: SHA256
`4306f22a7d9ffd01b45f066afbd5e740d21e9e1b5963ae1706ba6dc2ac509b17`.
До изменений проверены 284/284 внутренних хеша, read-only SQLite integrity и исходные
Narrative/Extraction/repair. Выполнены baseline 128 тестов и 12 SQLite replays на копиях.
Исходные базы, ответы и request messages не изменялись.
Raw-каталоги последнего платного B/C в этой среде недоступны: их точный повтор **не выполнен**.
Для B/C основания — опубликованный сравнительный отчёт; нельзя выдавать authored controls
или повтор A за воспроизведение тех же B/C ответов.

Подтверждённые недостатки представления на исходном HEAD:

- Review содержал status и actions из ввода, но не типизированную инвентаризацию решений,
  добавленных полным Narrative. Вход и полная проза уже передавались модели.
- Цитата ввода независимо генерировалась в PlayerAction и каждом Event, создавая лишний
  источник несовпадений. Пропущенный target_mode превращался в interaction по default.
- Model-facing schema удаляла descriptions, включая неоднозначные minute/targets/birth
  source. Это факт о схеме; причинное влияние на ошибки Flash остаётся гипотезой.
- QA смешивал Phone/001 с Phone/002 и требовал agency в hidden background. Это ошибки
  идентификации/runner, не доказательства ошибки production background.

## Изменения

- Существующий PlayerAgencyReview расширен `narrative_audit`: короткий материал из прозы,
  классификация и ссылка на текущий проверенный PlayerAction. Порядок модели:
  actions → audit → status. Нет chain-of-thought, новой стадии или разбора прозы Python.
- Типизированные unauthorized_choice/uncertain не допускают commit при preserved.
  Такой конфликт проверяется до ремонтируемых ошибок источника действия и ведёт в
  существующий reauthor/abandon. Отсутствующий обязательный audit, неверная ссылка и
  отсутствующий explicit target_mode остаются ремонтируемыми структурными ошибками.
- В v2 Event может не повторять player_evidence. Нормализация наследует только отсутствующий
  ключ из явно указанного проверенного действия. Явные null/пустая/чужая цитата отвергаются;
  actor, message author, targets, contact/delivery и aggregate subset/union не ослаблены.
  History сохраняет прежние канонические поля provenance. Никаких выдуманных Events из input.
- Server-owned `_extraction_contract=2` записывается в job config. Модель и параметры retry
  не могут выбрать legacy. Старые jobs и их regenerated siblings остаются v1; новые ходы
  в старом сейве используют v2. SQLite schema/API и исторические snapshots не мигрируются.
- Narrative оставляет незаданный ответ открытым, включая жесты и молчание; разрешает
  исполнение, непроизвольные реакции, самостоятельные NPC и их ошибочные интерпретации.
- Схема остаётся производной от существующих моделей: адресные descriptions, понятные
  имена повторных records, final_scene после событий. Два полных NarrativeAgencyItem-примера
  валидируются той же моделью; это не неполные WorldDelta. Capability pruning, все домены,
  Knowledge и новые места сохранены.
- Repair сохраняет полный список diagnostics, но перестаёт второй раз повторять длинную
  первую ошибку в summary. Это удерживает прежние 32K сценарии; retries не добавлены.
- Runner использует общие production helpers для ordinary/hidden-background границ.
  Case ID теперь различает phone_refusal_001 и phone_npc_interpretation_002 и дополняется
  checkpoint/job/request ID и хешами before/input/Narrative/messages.

## Проверки и ограничения проверки

Профильные команды выполнялись через Python 3.12 с requirements проекта:

```sh
python -m pytest -q tests/test_evidence_first249.py tests/test_comparison249.py
python -m pytest -q tests/test_context_builder_v2.py tests/test_context_compaction.py tests/test_movement_semantics223.py tests/test_extraction_semantics248.py tests/test_evidence_first249.py tests/test_comparison249.py tests/test_narrative_phone138.py
python tests/replay_live248_sqlite.py EXTRACTED_ARCHIVE NEW_REPLAY_DIRECTORY --final
python -m pytest -q --junitxml=pytest-results.xml --durations=15
cd frontend
npm test
npm run build
npx playwright test evidence-first249.spec.ts
```

Новый контракт проверен через реальные Context Builder, StateResolver, API/jobs, Repository,
History и SQLite: negative audit атомарен; retry не повторяет Narrative; abandon/reload,
rollback, regeneration/sibling selection и legacy version сохраняются. Проверены несколько
действий, отдельные/group Events, reference, partial/deferred, неверные ссылки/цитаты,
неподтверждённая доставка, неизменность NPC reply и отсутствие программного создания Event.
На копиях реальных Knowledge/Family с явно обозначенными protocol controls сохраняются
4/10 приобретений, источники и только фактические слушатели, включая неизвестного врача.

12/12 повторов полных SQLite достигли ожидаемых исходов. Phone/001 original saved остаётся
**семантическим FAIL**; тестовый violated control не считается ответом DeepSeek. Старые raw
replays запускаются как исторические v1 jobs; новые v2 controls проверены отдельно.
Массовые изменения старых scripted providers добавляют поля протокола, не ослабляют guards.
Оригинальные архивные JSON не дополнены audit задним числом.

Профильный итог после сокращения Extraction: **143 passed**; после финальной компактной
Narrative-инструкции и общего elapsed guard: **108 passed** (agency/time/repair/genre),
**104 passed** (Narrative/group/POV); runner с записью transport failure: **4 passed**.
После окончательного удаления дублей schema/instructions: **76 passed**, включая насыщенный
32K phone, Context Builder, compact schema, новый audit, provenance и C/D runner.
Наборы пересекаются, их числа не следует складывать как уникальные тесты.
Frontend: **151 passed**,
production build passed (существующее предупреждение о размере chunk).
Полный локальный backend: **3661 passed / 57 failed / 1 skipped**, 1607.90 s.
Процесс загрузил код до последних сокращений текстов; ошибки 16K/32K budgets, старого
заголовка и устаревших movement providers исправлены. Все **57/57** упавших тестов
повторно прошли на финальном коде (26.37 s). Это не объявляется полным зелёным прогоном
финального HEAD. Итоговый полный gate — GitHub CI; ссылка и статус в описании PR.
Лимиты тестов/моделей не повышались, CI не ослаблялся.

Добавлены 6 desktop/mobile E2E saved/missing-audit/reauthor с reload, retry, abandon и
проверкой отсутствия raw audit в UI. Локальный Chromium не запустился из-за
`socket() failed: Operation not permitted`: browser PASS локально **нет**.
Три сценария того же provider отдельно прошли через настоящие API/jobs без браузера;
это не заменяет браузерную проверку. Её gate — итоговый полный GitHub CI.

## Размер относительно очищенного C

Измерены полные paired запросы на неизменных before/input/Narrative и output cap.
UTF-8 bytes — точный размер текста, estimates — прежний консервативный estimator проекта,
**не фактические DeepSeek tokens**. D сохраняет то же capability/budget сокращение схемы C.

| Случай | C bytes | D bytes | Разница | Разница % | Estimates C → D |
|---|---:|---:|---:|---:|---:|
| Crisis | 66093 | 66073 | −20 | −0.03% | 33528 → 33518 |
| Phone/001 | 62385 | 62365 | −20 | −0.03% | 31674 → 31664 |
| Knowledge | 72274 | 72254 | −20 | −0.03% | 36619 → 36609 |
| Family birth | 60093 | 60310 | +217 | +0.36% | 30529 → 30637 |
| Background arrival | 50838 | 50006 | −832 | −1.64% | 25901 → 25485 |

На всех 24 случаях: 1503998 → 1503891 bytes (−0.007%, практически без изменения). Схема выросла, повторяющиеся
инструкции сокращены. Полные Narrative/input не обрезались. Все prepared запросы проходят
старые hard budgets. Narrative agency contract: 493 → 499 UTF-8 bytes (+6); новые правила
помещаются в прежние 16K genre/style сценарии без повышения лимита.
Новый audit увеличит часть output, отсутствие Event quote сэкономит
другую часть; итоговые output tokens, стоимость и задержка **ещё не измерены**.
Дополнительные обязательные LLM stages: 0; обычный путь остаётся Narrative + Extraction,
с максимум одним прежним bounded repair. Ускорение не заявляется.

## Зафиксированный C/D план

Бесплатная подготовка, без dispatch:

```sh
python -m devtools.live99.extraction_compare EXTRACTED_ARCHIVE NEW_C_INPUTS
python -m devtools.live99.extraction_compare249 NEW_C_INPUTS NEW_CD_PLAN
```

C использует очищенные контракты HEAD `4dc593e`; D меняет agency/schema/инструкции на
том же тексте. Общие deterministic Runtime и bounded repair feedback одинаковы для обеих
ветвей; C использует legacy agency shape, D требует v2. Это новый paired experiment,
не побайтный replay прошлых B/C repair messages. A повторно не оплачивается.

Корпус: 10 оригинальных сцен + 10 прежних authored holdouts + 4 новых (незаданный/явно
заданный жест согласия на помощь, непроизвольная реакция, частичный групповой контакт).
Phone/001, detail и обе help-пары повторяются по два раза; остальные по одному.
Итого **28 paired trials, 56 первых Extraction, максимум 112 calls с repair**.
Порядок C/D чередуется. Manifest заранее фиксирует schedule, hashes, ожидания и лимиты.
Никаких reroll до PASS или исключения неудачных результатов.

`run_pair(case, variant, generate, record)` исполняет один элемент schedule с максимум одним repair.
`generate` после отдельного разрешения — существующий `Budget.wrap` вокруг штатного
инструментированного transport; thinking=off, deepseek-flash, исходные temperature/output cap.
Recorder сохраняет request/raw response/receipts/diagnostics каждой попытки, включая
частичный ответ при ошибке транспорта. Semantic result всегда HUMAN_REVIEW_REQUIRED,
даже при accepted JSON. После отдельного разрешения, с уже настроенным штатным Budget
и инструментированным transport, последовательный запуск выглядит так:

```python
from devtools.live99.extraction_compare249 import read, run_pair
from devtools.live99.evidence import write

# plan/results: Path; results — новая папка. budget/stream — существующие владельцы.
generate = budget.wrap(stream)
for trial in read(plan / 'manifest.json')['schedule']:
    case = read(plan / (trial['case'] + '.json'))
    for variant in trial['order']:
        folder = results / trial['case'] / str(trial['repeat']) / variant
        folder.mkdir(parents=True, exist_ok=False)
        result = run_pair(case, variant, generate,
            record=lambda row: write(folder / f"attempt-{row['attempt']}.json", row))
        write(folder / 'result.json', result)
```

Ошибка транспорта останавливает запуск; неизвестный расход удерживает прежний reservation.
Не запускать этот блок без нового разрешения и конкретного денежного лимита.
Новую систему бюджета не вводить; старое разрешение или остаток не переиспользовать.

Оценка по предыдущему B/C: $0.00623 за вызов → **$0.349–0.698** для этого плана.
Это исторический ориентир, не текущая тарифная гарантия и не авторизация расхода.
Отдельный бюджет и действующий reserve/receipt gate обязательны; остановка gate означает
неполный эксперимент, а не разрешение увеличить лимит.

Метрики: false commit известных незаданных решений/невозможного контакта; false refusal
разрешённой сцены; пропуск/ошибка audit; schema/enum, ID/reference, time и semantic ошибки
раздельно; первый ответ и итог repair; конкретные 4/10 acquisitions/provenance; все calls,
input/output tokens, receipts и полная Extraction+repair latency. Ordinary/background отдельно.
Успех при плохой прозе — безопасный reauthor, а не saved. Известный false commit блокирует
семантическую приёмку; безопасные detail/explicit consent/arrival/background должны проходить.
При такой выборке нельзя обещать общую частоту ошибок или устойчивую p95.

Новый Narrative authoring проверять отдельно, не смешивая с фиксированной Extraction:
четыре production input (сортировка без ответа; явное согласие; незакрытый вопрос NPC;
несколько адресатов с отсутствующим NPC), по одному обычному ходу после отдельного разрешения.
Это ещё 8 основных вызовов, максимум 12 при repair; исторический ориентир $0.05–0.075,
но Narrative имеет другую длину, поэтому оценка слабая. В 56/112 выше этот этап не включён.

## Оставшиеся риски

Тот же Extraction может опустить решение, вернуть пустой audit или неверную классификацию.
Runtime проверяет типизированное заключение, а не истинность смысла прозы; тест прямо
фиксирует эту границу. Согласованно выдуманные события также требуют семантической оценки.
Без Live C/D нельзя назвать D лучшим или задачу семантически решённой.
Фактическое влияние на output/стоимость/latency неизвестно. Старые v1 jobs не получают
новый audit задним числом. Известный sticky Phone retry отдельно не исправлялся.
Stage C/#99 не закрывать автоматически. Не мёрджить PR по одному зелёному CI.
