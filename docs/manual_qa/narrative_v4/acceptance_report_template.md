# Приёмка PR #116 — identity / Runtime handoff / opening scene

> Отчёт по единому ТЗ runtime_handoff_and_start. Контролируемые ответы ниже синтетические; оригинальный пользовательский extraction отсутствует. Приёмка кода завершена на 8931928b2a6b249c2bed675354f8dbf74b39dea6. Точный SHA/tree доставки этого отчёта и повторный полный CI последнего SHA аттестуются в описании [PR #116](https://github.com/Troyevv/ai_rpg_engine/pull/116) после завершения jobs: собственный SHA невозможно встроить в содержимое коммита. Последняя поставка меняет только этот отчёт и отключает анимацию в screenshot-командах теста.

## 1. Версия

- Исходный HEAD: 58c8e2967470b5c9f461d887016387f2f29d2142 (проверен повторно перед публикацией).
- Проверенный код HEAD / tree: `8931928b2a6b249c2bed675354f8dbf74b39dea6` / `084e05330536e035ef6520772af53a45ca50711e`. Итоговый SHA/tree доставки отчёта и его CI — в аттестации PR #116.
- Изменения после 58c8e29 сохранены: Да. Перед первой публикацией свежий remote HEAD равнялся базе; перед уточнениями — f3328793ba49860d2f4bc12ca3e7aba778ee27c2. Все последующие публикации также fast-forward с expected_sha, без force; 9b19b4e и 8931928 сохранены в цепочке.
- CI проверенного кода: **PASS**, [run 40307123750](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40307123750). verify `121518878143`: 2106 passed + build; desktop `121521723565`: 118 passed; mobile `121521723611`: 108 passed, 10 существующих desktop-only skipped. Полный CI последнего SHA доставки отчёта — в итоговой записи PR #116.
- Локальная среда и ограничения: Linux, Python 3.12, Node; pytest и npm build доступны. Playwright CDN вернул повреждённый архив Chromium; browser acceptance выполняется в GitHub Actions.

## 2. Причины и доказательства

| Область | Подтверждённая причина / что не подтверждено | Файлы и тесты |
|---|---|---|
| Имена / скрытие обычных персонажей | DOB-only birth_provenance ошибочно считался реальным рождением: baseline API выдавал только ilya=Без имени. | birth_identity, reproduction, kinship; original_export test |
| Draft → canonical Runtime | В canonical были все 19 actors и cards, потеря происходила в проекции. Добавлен pre-confirm projection consistency check. | drafts.confirm_draft; exact_handoff test |
| API/UI и контекст | Truthiness читали selectors/context/portraits/life/protagonist_creation. Все переведены на общий контракт; secret name читается через visible_name. | tests/test_runtime_handoff.py, reproduction, remote tests |
| Первая сцена / scene_arrival_unsupported | Prompt требовал movements лишь вне final_scene; resolver требовал основание для нового участника. Generic situation quote разрешал чужое прибытие. Реальный исходный extraction неизвестен. | raw/context_contract/resolver; synthetic A01–A08 |
| Повторная обработка / единственный commit | Существующий bounded repair сохранён; terminal arrival diagnostic, epoch и UI/API pending guard дополнены. | engine, engine_storage, Game; real_start/retry/epoch tests |

Исходный пользовательский игровой job/extraction/SQLite **не предоставлены**. Проверены исходный экспорт, локальная baseline-реплика старого save и явно синтетические ответы provider. Generation E5 не является gameplay-log.

## 3. Контракт и совместимость

- DOB metadata до/после, real-birth metadata, mixed case: Новые записи: birth_date_provenance (DOB), birth_provenance (игровой процесс). Общий discriminator читает старые DOB-only payloads без выдачи прав/Knowledge. Mixed сохраняет process, повреждённый pregnancy_id даёт конкретную ошибку; unknown provenance fail-closed.
- Поведение старого Draft/save, миграционного кеша, rollback/variants: Совместимое чтение на копии через assert_world_state_v3_invariants/migrate_v2; старый JSON не переписывается GET. Старый canonical snapshot реально получен import→confirm на 58c8; restore/start/regenerate/variant/rollback проверены.
- Защита скрытого рождения, именования и Knowledge: Существующие reproduction/kinship tests плюс новые hidden-ID и mixed/manual-DOB tests. Известное рождение не даёт известного имени. Настоящие unborn не становятся actors.
- Сохранность всех DOB, ручной биографии Марины и manual_paths: Exact baseline canonical comparison, character_cards и authoring равны исходному экспорту. Все общие поля исходных entities сравнены напрямую; v2-only thread public_state/visible_to_ids/last_event_id и fact owner_id/evidence сохранены существующим immutable History, а не выдуманы в canonical схеме. Все 19 DOB сохранены; ни один Knowledge не добавлен ради имени.
- Нужны ли действия пользователя для его существующего save и какие именно (без перегенерации): После обновления открыть существующий save; для сохранённого неприменённого текста — «Повторить обработку состояния». Не генерировать мир и не создавать ГГ. Подтверждение совместимости относится к локальной baseline-реплике; SQLite пользователя не предоставлена.

## 4. Трассировка исходного мира

| Граница | ID / имена / карточки | Герой / управление / сцена | Связи / Knowledge | Артефакт |
|---|---|---|---|---|
| Draft | 19 точных исходных ID/имён | ilya, один в кабинете | 18 directional; 37 Knowledge | immutable world.json |
| Миграция | 19 actors + 19 cards | та же камера | 23 objective, 19 facts, 4 threads | exact baseline comparison |
| SQLite save | все ID/поля равны baseline | те же места | граф не урезан | saves.state_json + read-only dump test |
| Игровой API | 19 точных имён, не Без имени | ilya / ilya_cabinet | target_name восстановлены | original_export API test |
| UI desktop/mobile | PASS на 8931928, desktop и mobile | реальные API, не page.route | 19 имён проверены | runtime-handoff.spec.ts |
| Narrative context | 1 полная карточка + ограниченный индекс | Ilya один | POV Knowledge не расширен | context_retains_bounded test |
| Extraction context | Viktoria по существующему ID/имени | origin=salon_lak | типизированный arrival contract | context_retains_bounded test |
| Успешный первый commit | 19 прежних ID | Ilya+Viktoria в кабинете | Knowledge прежний | real_start_repair test |
| Turn → reopen/reload → next turn | 19 прежних ID | три commits, +3 минуты | остальные NPC не перемещены | API cycle + desktop/mobile 8931928 PASS |

## 5. Прогон требований и тестов

Статусы: PASS / FAIL / NOT RUN. Отдельно указать red до исправления и green после, а не заявлять red без запуска.

| ID | Статус | Реальная команда/тест/артефакт | Ограничение |
|---|---|---|---|
| R01 | PASS | red original_export; exact_handoff; API/context trace | No original gameplay-log replay |
| R02 | PASS | birth_identity + DOB writes; metadata matrix | No original gameplay-log replay |
| R03 | PASS | known_birth/visible_name/portraits/context/life/phone; full regression | No original gameplay-log replay |
| R04 | PASS | exact API names + hidden birth pruning; desktop/mobile real API | Original user gameplay log absent |
| R05 | PASS | context_retains_bounded_identity; scope/full-card limits | No original gameplay-log replay |
| R06 | PASS | imported real API + exact_handoff; pre-confirm guard | No original gameplay-log replay |
| R07 | PASS | legacy read-only + old_save_restore_regenerate_variant_rollback | No original gameplay-log replay |
| R08 | PASS | red wrong-actor; structured arrival diagnostics and repair request | No original gameplay-log replay |
| R09 | PASS | arrival positive/negative; same-narrative bounded repair | No original gameplay-log replay |
| R10 | PASS | failed_extraction_retry; epoch/stale/repeated retry guards | No original gameplay-log replay |
| R11 | PASS | precise author diagnostics; safe player repairs + pending message | No original gameplay-log replay |
| R12 | PASS | calendar/start-policy/reproduction/Knowledge regressions | No original gameplay-log replay |
| R13 | PASS | 2 real baseline reds; 40 focused tests, provider-only new integration tests | No original gameplay-log replay |
| R14 | PASS | Full code-SHA CI, 2106 backend + 118 desktop + 108 mobile; last delivery SHA attested in PR | No original gameplay-log replay |

| Тест | Статус | Red / Green / фактическое доказательство |
|---|---|---|
| T01 | PASS | original_export (red→green) |
| T02 | PASS | e5_candidate_failed_review_handoff; existing calendar_start_policy |
| T03 | PASS | primary_provider_normalization through /generate |
| T04 | PASS | exact_handoff baseline equality and fixture expectations |
| T05 | PASS | dob_metadata matrix; generation_calendar manual/explicit/unknown/twins |
| T06 | PASS | dob_metadata ordinary child; birth privacy independent of age |
| T07 | PASS | existing reproduction hidden/known-name/unborn tests |
| T08 | PASS | manual_dob_keeps_game_birth_metadata + compatibility recovery |
| T09 | PASS | malformed_real_birth_reference; mixed source/process; unknown fail-closed |
| T10 | PASS | context_retains_bounded_identity + legacy_context |
| T11 | PASS | API exact identity; browser cards, relations, expanded thread participant names, camera, controlled actor |
| T12 | PASS | reproduction/portraits/kinship regression; common discriminator |
| T13 | PASS | actual baseline legacy_snapshot + read-only restore |
| T14 | PASS | old_save_restore_regenerate_variant_rollback + migration idempotence |
| T15 | PASS | nonfixture_identity renamed synthetic copy |
| T16 | PASS | real_start_repair_turn_reopen_next_turn A01 |
| T17 | PASS | same narrative first missing claim then bounded repair |
| T18 | PASS | archive_negative_narratives: actual A03/A04/A05 prose → real API → rejected presence → repair → one commit; assertion/anchor matrix. Semantic classification remains extraction responsibility |
| T19 | PASS | wrong actor red→green; wrong destination/evidence/origin/conflict matrix |
| T20 | PASS | parent/independent × elapsed 0/1 matrix; real start/turn |
| T21 | PASS | failed_extraction_retry after Repository reopen |
| T22 | PASS | epoch/stale/duplicate retry guards; cancellation blocks commit |
| T23 | PASS | saves bytes/revision/history unchanged on failure |
| T24 | PASS | runtime-handoff.spec.ts desktop/mobile: real import→confirm→identity views→rejected opening→retry→accepted scene |
| T25 | PASS | real API start→turn→reopen→next turn |
| T26 | PASS | 2106 full-suite CI PASS on 8931928; final delivery SHA CI attestation in PR #116 |

## 6. Retry и транзакционность

- Narrative hash до/после повтора: Тест сравнивает побайтно сохранённый narrative до/после; тот же A01, SHA-256 ниже.
- Before snapshot / branch / revision: before_json и memory_before_json равны до/после retry; revision должен совпадать с job. Stale revision отвергается до вызова провайдера.
- Сколько extraction-попыток, сколько принятых ходов: Автоисправление: 1 narrative + 2 extraction = 1 commit. Exhaustion/reopen/retry: 1 narrative + 2 отклонённых extraction + 1 успешный = 1 commit. Затем два обычных хода = всего 3 commits.
- Ошибка не записала частичный state/history/time: Raw saves.state_json/revision и список turns равны before при отказе; успешный ход меняет минуту ровно на 1, сохраняет Knowledge и места всех непричастных NPC.
- Двойной клик / stale / поздний ответ: Active/saved retry guards, revision check, transactional commit и persisted attempt_epoch. Старый worker не меняет статус новой попытки и не может commit; повтор saved retry отклонён.
- Восстановление после перезапуска: Repository reopen и retry через штатный API; тот же durable job и before snapshot. Ошибочные llm_requests неизменны, исправление — отдельная запись.

## 7. Слои проверки и расходы

| Слой | Что действительно выполнялось | Результат |
|---|---|---|
| Анализ оригинальных файлов | world SHA verified, E5 read, 5 original screenshots viewed | PASS |
| Production unit/schema/projection | actual production functions; no replacement of resolver/migration/repo | PASS |
| API с controlled provider | real import/generate/confirm/jobs/retry/turn/reopen | PASS |
| Browser с реальными API/проекциями | 8931928: desktop 118 passed; mobile 108 passed / 10 skipped; all eight handoff screenshots inspected | PASS |
| User gameplay-log replay, если предоставлен | Not provided. E5 is generation-only. | NOT RUN |
| Синтетический негативный extraction | wrong actor/destination/origin/quote/assertion, no partial commit | PASS |
| Live DeepSeek | No key/budget; no paid calls | NOT RUN |

- Реальных вызовов, токенов и расходов: 0 live-вызовов. Синтетические ответы не сообщают usage: cost_usd остаётся unknown/null, не ноль выдуманной стоимости.
- Безопасно доступный ключ и согласованный бюджет (только наличие, без значений ключа): Не предоставлены. Тестовая строка credentials используется только заглушкой внешнего provider boundary.
- Live не выполнен: Да: ключ/бюджет не предоставлены; платные вызовы не запускались.

## 8. Gates и вывод

| Gate | PASS / FAIL / NOT RUN | Доказательство / блокер |
|---|---|---|
| G1 Контракт identity | PASS | See production/API tests and provenance above |
| G2 Передача мира | PASS | See production/API tests and provenance above |
| G3 Первая сцена и восстановление | PASS | API and both browser viewports: saved narrative retry, one first commit, ordinary turn, reload, next turn |
| G4 Старое прохождение | PASS | See production/API tests and provenance above |
| G5 CI / инженерная приёмка | PASS | Full code-SHA CI 8931928; exact final report-delivery SHA and repeated CI attestation in PR #116 |
| G6 Честное разделение доказательств | PASS | See production/API tests and provenance above |

- Оставшиеся функциональные блокеры: не выявлены. CI последнего SHA доставки отчёта аттестуется отдельно в PR; зелёный CI предыдущего SHA не выдаётся за его результат.
- Отдельные ограничения прежней live-приёмки #44: Этот отчёт не объявляет live DeepSeek качество/стоимость подтверждёнными и не заменяет отсутствующий пользовательский gameplay-log.
- Новый PR / merge / закрытие issue не выполнялись: Да: обновляется только существующий #116; merge и закрытие #44 не выполняются.

Вывод: исходные персонажи доступны через игровой API/UI; после отклонённой первой обработки тот же текст успешно принят, затем приняты два обычных хода через reload. Время 18:00→18:03, 3 commits, 19 прежних ID; непричастные NPC и Knowledge сохранены. Только видимый текст не использовался как критерий успеха.

## Команды и артефакты

- Baseline: `python -m pytest -q tests/test_runtime_handoff.py`: **2 failed**, API identity and wrong-actor evidence; `/tmp/handoff-red.log`.
- Full local: `python -m pytest -q`: **2095 passed in 308.47s**; `/tmp/handoff-full3.log` (before the final focused additions).
- Focused final identity/phone: **63 passed in 22.60s**; `/tmp/handoff-finaldomain.log`.
- `npm run build` passed; existing bundle-size advisory remains.
- `git diff --check` passed.
- Synthetic A01 narrative SHA-256: `7eee1eb974b0ee590f62a5fac54a79dab86c2036b425566c327c13941a1f4194`.
- New large-world provider tests explicitly use context_length=131072; production defaults/retries/output budgets unchanged. The existing 32768 saturated triplet test remains mandatory and passes after lossless instruction deduplication.
- Unknown origin in old flat geography retains existing final_scene semantics; a known different origin or structured destination requires actor-bound arrival. No parent hierarchy shortcut was introduced.

## Дополнительный финальный прогон

- `python -m pytest -q`: **2103 passed in 296.11s** (`/tmp/handoff-release-full.log`).
- DOB/old-cache/birth/context focused checks: **78 passed in 22.75s**; два appearance-adapter checks — **2 passed**.
- Browser test discovery: **236 tests / 38 files** (118 per viewport); no browser execution claimed by discovery.
- Initial published `f332879` verify: **2100 passed**, build success. Mobile: **108 passed, 10 skipped**, 9.6m. Three handoff screenshots inspected: 19-card selector and Ilya name; rejected text with retry and no Start; committed minute 18:03 with Ilya/Viktoria scene. [Mobile artifact](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40299902387/artifacts/12640582249). Desktop first attempt hit the unchanged 20-minute job limit after a slow Chromium install; a job retry was requested. Final refinement SHA attestation is recorded in PR #116 after CI completes.

- Final handoff suite including archive A03/A04/A05 API repair: `python -m pytest -q tests/test_runtime_handoff.py` — **40 passed in 19.27s** (`/tmp/handoff-all-final.log`).

- `9b19b4e` CI: backend **2103 passed in 326.50s**, build PASS. Browser: desktop **117 passed / 1 failed**, mobile **107 passed / 10 skipped / 1 failed**. New test searched a full participant name before opening the collapsed thread. The test now opens the actual thread detail before asserting names; expected names and timeouts are unchanged. This failed run is not claimed as acceptance.

- `8931928b2a6b249c2bed675354f8dbf74b39dea6` verify CI: **2106 passed in 302.65s**, frontend build PASS. [Run 40307123750](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40307123750).

## Завершённая браузерная приёмка кода

- `npx playwright test --project=desktop --reporter=line`: **118 passed (7.8m)**.
- `npx playwright test --project=mobile --reporter=line`: **108 passed, 10 skipped (9.8m)**. Пропуски — прежние desktop-only сценарии; новых skip нет.
- [Desktop screenshots](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40307123750/artifacts/12644290283), [mobile screenshots](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40307123750/artifacts/12644620388).
- Просмотрены `handoff-identities`, `handoff-camera`, `handoff-rejected`, `handoff-played` на обоих viewport. Имена/19-card selector сохранены; неприменённая сцена явно помечена, retry доступен, Start отсутствует; после принятого цикла часы показывают 18:03. Мобильный заголовок сцены использует штатное многоточие; horizontal overflow отсутствует.
- Кадр камеры попал на fade-in. В финальной поставке только screenshot-команды используют `animations: 'disabled'`, чтобы последний CI сохранил стабильные кадры; анимации приложения, тестовые ожидания и timeout не изменены.
- Финальная аттестация последнего SHA и его скриншотов публикуется в PR #116 после повторного полного CI.
