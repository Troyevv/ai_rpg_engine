# #99 — повторная подготовка после #241–#244

Refs #99. Продолжение QA #239. **Live Retest не запускался; Stage C не завершён.**
Это отчёт бесплатной подготовки, а не подтверждение семантической надёжности DeepSeek.
Продуктовый код, исходные fixtures и исторические отчёты не изменены.

## Версия и границы проверки

- Свежий `origin/master`: `d81a52c9980b79d1be99acfde9fc1a1452d71176`.
- #237 / PR #241: `6c90b5de0bc5b3c8b659ddb364fd9224238d9d94`.
- #240 / PR #242: `7dc9be11ebaa828bbe6b7aa8eae64393ae7efc1c`.
- #238 / PR #243: `a2649d13fe626e31158bc7572967b93b4e4ed5a0`.
- #223 / PR #244: `7351cf43b8bf3caafefb0065e8c18e87a38cb745`.
- Прочитаны AGENTS.md, #99, отчёт #239, четыре Issues и четыре исправления;
  проверены реальные Context Builder, engine/jobs, RawTurnResult, repair,
  StateResolver, completion/provenance, temporal boundary и persistence пути.
- Бесплатные тесты используют существующие repository fixtures, настоящий Runtime,
  FastAPI/jobs и SQLite с детерминированными ответами провайдера. Ключ DeepSeek
  удалён из окружения тестовых процессов. Новые live-миры не создавались.

## Доступность исходных артефактов — BLOCKED

В текущем окружении не найдены исходные `game.sqlite`, `budget.sqlite`, checkpoints
и архивы предыдущего QA. Поиск охватил workspace, доступные shared/library/scratch
каталоги и `/tmp`. Найденные pytest SQLite не являются исходными QA-сохранениями.
GitHub releases listing возвращает `qa-99-campaign-evidence-20261107` без assets;
запрос release по tag возвращает 404. Доступной ссылки на полный архив не получено.

Ожидаемый основной архив из #239:

- `live99-campaign-evidence-20261107.tar.gz`, 29,089,712 байт;
- SHA256 `3979c8b87ce923ccf21737c8a7cd17718f218b36535997b752c5118d4d15a277`;
- 353 файла согласно прежнему индексу; **в этом запуске архив не проверен**.

Доступны три сохранённых исходных extract из этого архива:
[`tests/fixtures/issue238`](../../../tests/fixtures/issue238/README.md).
Это World State до хода, user input, Narrative, initial Extraction и failed repair
для Social/001, Knowledge/001 и Campaign/011. Их происхождение задокументировано
в #243, но сравнить их с отсутствующим полным архивом заново нельзя.
В тестах эти состояния получают изолированную fixture lineage; это не replay
полной исходной SQLite с её историческими siblings.

Для Crisis, Family и Phone доступны эквивалентные воспроизведения из исправлений.
Они проверяют четыре класса дефектов, но не заменяют запрошенный replay оригиналов.
Восстановление исходного архива и ledger — обязательное условие платного этапа.
Нельзя реконструировать бюджет из итогового числа или создавать чистый ledger.

## Бесплатные replay и регрессия

Окончательные результаты текущих команд и хеши доступны в соседнем
`live99-post-fixes-preflight-20261107.json`.

- Целевые backend replay: **145 passed** (266.18 s): completion 29, group completion
  27, provenance 43, due boundary 21, movement 25.
- Полный backend: **3583 passed, 1 failed, 1 skipped** (752.15 s). Падение —
  `test_npc_initiative.py::test_pacing_and_silence_never_require_or_forbid_ordinary_initiative`:
  Hypothesis `FlakyFailure/DeadlineExceeded`, первый `calm/False` пример 1232.02 ms
  при deadline 200 ms, повтор внутри Hypothesis 30.33 ms. Поведенческого assertion
  failure нет. Отдельный диагностический запуск **того же теста без изменений**:
  **1 passed in 1.08 s**; deadline не отключён, проверки не ослаблены.
  Первичный неуспешный full-run сохранён и **не объявляется зелёным**. Точная причина
  вариативности wall-clock не установлена; нельзя выдавать её за доказанную ошибку
  NPC semantics или списывать на конкретный системный фактор без измерения.
  Поиск GitHub Issues по DeadlineExceeded/имени теста совпадений не дал;
  продуктовая Issue по одному timing failure не создавалась.
  Skip — существующий `test_review170::test_real_export_evidence`, приватный экспорт
  не опубликован (`RPG_REVIEW170_EXPORT`).
- SQLite `PRAGMA integrity_check`: **118/118 ok** на изолированных базах целевого
  прогона. Assertions в тестах дополнительно проверяют reload/History/Knowledge
  и применимые rollback/siblings; integrity_check сам по себе этого не доказывает.
- Frontend Vitest: **151 passed / 23 files**. Production build успешен;
  предупреждение о JS chunk >500 kB сохраняется.
- Playwright: **12/12 passed**, desktop 6 + mobile 6, retries=0, системный Chromium,
  production `create_app` с test-only endpoints и scripted provider. Это реальный
  browser/HTTP/SQLite, но не реальный DeepSeek.
- Дополнительно визуально просмотрены Phone desktop 1440×1000 и Family mobile
  390×844 через production `create_app` без test endpoints на копии тестовой SQLite;
  генерация отключена guard. Narrative и controls видимы, JS page errors отсутствуют,
  reload сохраняет state/turns. Phone: Тимур отсутствует, location=null; Family:
  world_time=1980, pregnancy=due. Это UI-проверка fixtures, не старых live-checkpoints.

| Сценарий | Проверяемое поведение | Источник |
| --- | --- | --- |
| Crisis / #237 | Удаление отсутствующей Веры из participants не легализует completed; attempted/deferred сохраняются без телепортации и Knowledge; повторная ошибка атомарна; reload и siblings | `test_player_action_completion.py`, `test_player_action_group_completion.py`; эквивалентный replay |
| Social + Knowledge / #238 | Исходные общие цитаты отвергаются; точные цитаты и отдельные Events закрывают оба действия; один repair; отсутствие чужого согласия; History/reload | `test_action_provenance_repair.py`; исходные payload, изолированная lineage |
| Campaign/011 / #238 | Minute и отсутствующие action ID/evidence диагностируются вместе; один исправленный ответ сохраняет неизменный исходный Narrative; повторный дефект не коммитится | Тот же набор; исходные payload после LTA |
| Family / #240 | elapsed 2→0 через один repair; продолжающиеся роды не создают ребёнка; несколько нулевых ходов, действительное рождение, пол/Knowledge/POV, reload/rollback | `test_due_boundary_repair.py`; эквивалентный replay |
| Phone / #223 | Уход и future intent не требуют прибытия; unknown location; настоящее прибытие в новое/существующее место и создание локаций разрешены | `test_movement_semantics223.py`; эквивалентные и gold responses |

Для #223 сохраняется существенное ограничение: структурно валидная, но ложная
`completed_arrival` всё ещё принимается Runtime. Исправление меняет инструкции
Extraction; Runtime не интерпретирует прозу. Детерминированный тест подтверждает
это ограничение, а не доказывает, что живая модель перестала ошибаться.

Команды (артефакты вне git в `work/live99-retest`):

```bash
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_player_action_completion.py tests/test_player_action_group_completion.py \
  tests/test_action_provenance_repair.py tests/test_due_boundary_repair.py \
  tests/test_movement_semantics223.py \
  --basetemp=/workspace/work/live99-retest/focused-tmp \
  --junitxml=/workspace/work/live99-retest/focused.xml
PYTHONPATH=/workspace/work/live99-retest/test-deps env -u DEEPSEEK_API_KEY \
  .venv/bin/python -m pytest -n 4 -q \
  --basetemp=/workspace/work/live99-retest/full-tmp \
  --junitxml=/workspace/work/live99-retest/backend.xml
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_npc_initiative.py::test_pacing_and_silence_never_require_or_forbid_ordinary_initiative \
  --basetemp=/workspace/work/live99-retest/npc-timing-tmp \
  --junitxml=/workspace/work/live99-retest/npc-timing.xml
cd frontend
npm test
npm run build
env -u DEEPSEEK_API_KEY PATH=/workspace/ai_rpg_engine/.venv/bin:$PATH \
  PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium E2E_PORT=8123 \
  E2E_DB_PATH=/workspace/work/live99-retest/browser.sqlite \
  E2E_OUTPUT=/workspace/work/live99-retest/browser-results npm run test:e2e -- \
  player-completion.spec.ts action-provenance.spec.ts due-boundary.spec.ts departure223.spec.ts
```

Первый запуск полного backend остановился до collection: отсутствовал pytest-xdist.
Он установлен только в рабочий каталог (`pytest-xdist 3.8.0`, `execnet 2.1.2`),
без изменения зависимостей продукта. Первый browser launcher выбрал системный
Python без requests; PATH исправлен на существующую `.venv`. Это ошибки запуска
окружения, а не продуктовые дефекты и не платные повторы.

## Бюджет: оценка, не новое разрешение

Новых оплачиваемых inference-вызовов: **0**; расходы этого запуска: **$0**.
Выполнены только бесплатные GET balance/models и чтение официальных тарифов.
Аккаунт доступен, модель `deepseek-flash` присутствует. Данные баланса аккаунта
сообщены отдельно; баланс аккаунта не равен QA-разрешению.

По опубликованному индексу #239: 283 исторических вызова, 175 операций,
0 неизвестных исходов, использовано $0.3586539 из разрешения $2,
остаток **$1.6413461**. **Это последняя отчётная сумма, а не повторно сверенный
фактический остаток**: исходный ledger сейчас недоступен.

[Тариф](https://api-docs.deepseek.com/quick_start/pricing/) проверен 2026-11-07:
DeepSeek-V4.1-Flash-1017, peak input cache miss $0.30/M, cache hit $0.006/M,
output $1.20/M; off-peak вдвое дешевле. Для лимита используются peak/cold ставки,
для оценки фактической стоимости — реальные usage/cache/time каждого вызова.
Прежний прогон стоил $0.059934474 по usage и $0.1729677 по peak/cold за 36 вызовов;
это ориентир, а не гарантия цены следующей сцены.

### Предлагаемый платный этап 1

| Операции | Предел inference-вызовов |
| --- | ---: |
| Crisis: тот же ввод к отсутствующей Вере | 3 |
| Social и Knowledge: по одному исходному вводу | 6 |
| Campaign/011: Extraction retry сохранённого Narrative, без повторной Narrative | 2 |
| Family: продолжающиеся роды, следующий нулевой ход, завершение только если оно описано | 9 |
| Phone: уход/future intent, фактическое прибытие в существующее и в новое место | 9 |
| Общий резерв на предусмотренные production Remote/background стадии | 7 |
| **Всего, включая repair и любые фоновые вызовы** | **36** |

Ожидаемо $0.06–0.20; предлагаемый жёсткий предел **$0.60** по peak/cold.
Это максимум, не обязательное число запросов. Один автоматический Extraction
repair разрешён существующим Runtime; оплаченные успешные операции не повторять.
Если свободный Narrative не создаёт нужную ситуацию, результат «не покрыто»,
без бесконтрольных попыток. Остановка при дефекте, неизвестном исходе, превышении
числа вызовов или невозможности полной предварительной денежной резервации.
Полный context reservation существующего guard может остановить прогон раньше
номинального денежного лимита — уменьшать эту защиту ради выполнения плана нельзя.

Этап 2 пока не разрешён. После семантически успешного этапа 1 планируется до
16 ограниченных операций продолжения (NPC initiative, relationships/Knowledge,
secrets/POV, phone/messages/group, движения/presence, local/remote family,
regeneration/branch/rollback) и LTA на год, затем условно пять лет.
Ориентир: до 64 вызовов с учётом 8 на годовой LTA, 8 на пятилетний и
48 на обычные/remote операции; ожидаемо $0.15–0.40. Перед этим этапом нужны
конкретный план из полученных checkpoints, сверка остатка и отдельное согласие.
`LongTermAdvanceRequest.max_llm_calls` ограничен 8; увеличивать продуктовый лимит
или дробить неудачный LTA на повторы ради принятого исхода не планируется.
Календарный сдвиг без принятых событий, изменений персонажей и History не проходит
годовой gate и запрещает переход к пяти годам.

## Условия продолжения и отчётность

1. Получить оригинальный архив; проверить SHA256 и внутренние хеши. Сделать
   отдельные копии SQLite/checkpoints/ledger, сохранив исторический prefix.
2. Проверить SQLite integrity/reload, исходные holds/jobs/siblings и действительное
   число settled/unknown reservations, baseline разрешения и фактический остаток.
3. Выполнить replay исходных Crisis/Family/Phone и Context preflight всех шести
   групп на текущем master. Не применять исправленные test payload к live-save.
4. После явного согласия применить отдельный лимит этапа 1 к изолированной копии
   ledger, сохранив общий прежний потолок. Штатный старый prepare не запускать
   вслепую: он создаёт symlink к родительскому ledger и меняет его; в этом QA
   исходные артефакты должны оставаться неизменными.
5. Запускать через production FastAPI и browser, проверяя UI и канон, не только
   HTTP status. Для Campaign сохранить hash исходного Narrative при retry.
6. На каждой операции сохранять checkpoint + master SHA, input, Narrative,
   initial/repair Extraction, diagnostics, World State до/после, History/Knowledge,
   job status, все actual calls/tokens/cost, SQLite reload и UI-результаты.

Новых подтверждённых продуктовых дефектов на момент подготовки не заявлено.
Live-статус всех четырёх исправлений: **NOT RUN / BLOCKED**.
Продолжение кампании и LTA: **NOT RUN**. Исходная семантическая оценка #239
не заменяется зелёными тестами. Этот PR не закрывает #99 и не подлежит auto-merge.
