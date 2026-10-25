# Итоговый отчёт по Issue #44 / PR #116

Отчёт следует `acceptance_report_template.md` из итогового архива от 25.10.2026. Числа относятся к выполненным проверкам; replay и controlled continuation не являются измерением качества DeepSeek.

## 1. Версия и объём

- Исходный HEAD / база аудита: `6267be1d20a02bd6ef83700dcbf4bc54756d48c7`. В начале дерево чистое; удалённый PR имел тот же HEAD. Последующие изменения не откатывались.
- Master: `4bc5ec66a1a281ca7a3dc88776eb3df5e694d3aa`. Итоговые опубликованные SHA, tree, merge-tree и GitHub Actions записываются в описании существующего PR #116 после публикации, чтобы не создавать самоссылку SHA внутри коммита.
- Generation contract 5 сохранён; reviewer 6, recovery policy 2. Версия восстановления входит в signature вместе с кандидатом, авторским контекстом и конфигурацией провайдера. Quality policy 2.
- Изменены существующие review/repair/generation/quality, проекция календаря, ограничения manual edits, состояние recovery и соответствующие тесты/UI. `draft_review_recovery.py` — ограниченная процедура внутри прежнего конвейера, не второй генератор или Runtime.
- Подтверждены риски аудита: E4 `path=null` и неверные основания; terminal `review.running`; невозможность выйти из одинаковой коррекции; конфликт двух `/locations/-`; потеря Gregorian metadata; отсутствие детектора заглушек; циклы, разделённые Resume epoch. Исторический CI `40214844242`: backend/build success, desktop/mobile failure. Это не результат нового кода.

## 2. Закрытие требований

| Требование | Инженерное доказательство | Ограничение |
|---|---|---|
| R01 | AGENTS.md, полный #44 и #36, описание PR и аудит прочитаны; комментарии issue-thread PR отсутствовали. HEAD/base проверены повторно перед публикацией. | Merge и закрытие не выполняются. |
| R02 | Серверные manual_paths, clock/DOB provenance; атомарный trial; `test_manual_field_protected_against_direct_and_indirect_repair`, оба варианта `test_model_player_goal_recovery_preserves_source_agency`. | Проверка смысла источника использует bounded reviewer; не является формальным доказательством естественного языка. |
| R03 | Условная schema/DTO, legacy adapter, section/entity/field, серверный ID missing_record, Runtime-типы matcher, симметрия/фаза; basis без копирования value. Неверный advisory изолируется без mutation. | Неизвестное обязательное замечание не превращается в успешный review. |
| R04 | Сохранённые slots: review → correction по стабильным ID с возможностью split → один scoped re-audit с явными resolutions. E3/E4 и 6 новых workspace доходят до игры. | Неконструктивный провайдер после конечных стратегий останавливается; это отрицательный тест, не успешная генерация. |
| R05 | Terminal review помечается failed; старые зависшие записи имеют корректную read projection. Exhausted Resume отвергается до очистки результата, UI не предлагает его; ручная правка/новый контракт разблокируют новый scope. Shared browser/API fixture проверяет известный HTTP-отказ и успешный Resume. | Локальный Chromium не запускается; итоговый browser результат проверяется в CI. |
| R06 | Точные assignments, новые типизированные записи, связанные locations для residence/scene/organization, явные удаления с precondition, разные append ID, атомарность и проверка итоговых ссылок. | Произвольная замена мира/коллекций не разрешена. |
| R07 | Trial перед candidate_text; сохранение raw/diagnostics/hashes; ранее скрытая неизменённая intrinsic-ошибка отделяется от новой reference-регрессии. Нормализованный trial проверяет ручные поля. | Не используется эвристика «ошибок стало меньше». |
| R08 | E1/E2 реальные ложные замечания/невалидный repair; E3/E4 Knowledge без event, facts participants, отношения, жильё, авторский старт, роли и имущество. Закрытие проживания требует отдельного semantic decision, количество basis не даёт права закрытия. | Controlled continuation явно отделён от исторического replay. |
| R09 | Gregorian сохраняет names/seasons/observances; effective projection показывает built-in справочники, високосный февраль, неизвестный год. Custom и DOB покрыты календарными тестами. | Новые календарные системы не добавлялись. E4 не содержал праздников: это отдельная синтетическая регрессия. |
| R10 | Детерминированные пустые/placeholder поля поступают в ограниченное дополнение даже при пустом review; явная неизвестность может сохраняться с основанием из source. Cache привязан к данным/контексту/policy; неудача сохраняет мир и честный partial/warning. | Литературное качество новых реальных генераций не измерено без live. |
| R11 | Существующий lossless transport, pending/unknown outcomes, token/cost reservation и bounded HTTP retry сохранены. Циклы и semantic slots не обнуляются epoch. | Exactly-once billing не обещается. |
| R12 | Генерация, оба creation flow, JSON/TXT/MD, старые Motivation/сохранения, confirm, runtime и Tabletop проходят существующий общий валидатор и regression suite. | Импорт не получает творческое автодополнение. |
| R13 | T01–T32: карта ниже, оригинальные E1–E4, негативный replay, успешное восстановление, API/SQLite и browser fixtures. | Успешные mocks не считаются live-статистикой. |
| R14 | Зафиксированы `tests/fixtures/generation_scenarios/inputs_final.json`; probe расширен до confirm/start/turn/reload/next-turn с явно controlled gameplay и отдельной метрикой. | 12 live-генераций и 2 live-gameplay smoke **не выполнены**. |
| R15 | Full backend, build, focused, dependency/syntax/diff checks; окончательные SHA/CI — в PR. | До live-приёмки #44 не рекомендуется закрывать. |

### Соответствие опубликованному Issue #44

| Группа требований #44 / Epic #36 | Реализация / замена | Доказательство |
|---|---|---|
| Единый normalizer, typed validation и lossless Runtime mapping | Выполнено | `draft_initial`, canonical_check; initial/import/motivations/runtime suites |
| Все структуры #37–43, Knowledge, чувства, планы, possessions, contacts, POV/control, pacing/risk | Сохранены | Репрезентативные initial-world, migration, calendar, lifecycle, remote, runtime tests; E4 не наполняется чужими optional сущностями ради покрытия |
| Genre/custom/secondary, масштаб, expressiveness, оба creation flow | Сохранены | WorldCreationSettings, schema/settings tests, `draft-v4.spec.ts`, `test_generation_scenarios` |
| Состав автора, личности, неизвестность, source и ручные revisions | Сохранены; добавлена защита изменённых полей | Immutable source/journal и document_versions, manual_paths, E3/E4 сравнения, field/editor/restore tests |
| Отдельный обязательный blueprint/stages/batches/dependency graph | Явно заменено §1.2 итогового ТЗ и актуальным началом #44 | Один основной запрос мира + continuation; ограниченные review/repair/quality. #105 не переносился, #117 не дублировался |
| Обязательный отдельный реестр всех цитат/offsets | Явно не требуется §2.2 итогового ТЗ | Сохранён полный source; компактные provenance и basis-ссылки. Нет утверждения, что создан отдельный registry |
| Durable recovery, cancel, revisions, стоимость, неизвестный outcome | Сохранены и исправлены | SQLite journal, fragment/recovery tests, preflight и terminal status, stable strategies |
| Семья/компании/география, opening scene, различное знание | Сохранены | Volkov/ownership/adoption fixtures; E3/E4 facts ≠ Knowledge; initial calendar/scene checks |
| Содержательная готовность и литературное качество | Offline путь выполнен, live-приёмка не выполнена | Placeholder completion и examples ниже; mocks не доказывают качество модели |
| Ready-to-start, imports, legacy, обычная игра и Tabletop | Сохранены | Confirm/version guard, runtime/legacy/tabletop suites; start → turn → reopen SQLite → next turn |
| #78 и будущие задачи | QA ниже расширяет существующую документацию #78 | Нет нового тестового Runtime/генеалогии/экономики; #45 и следующие задачи не начаты |

### Карта T01–T32

Пути ниже относительно `tests/`; полные имена находятся в указанных файлах.

| ID | Проверки |
|---|---|
| T01–T03 | `test_issue44_final`: reference_type_matrix, record_symmetry_invalid_match_and_stable_split_identity, actual E4; `test_generation_stability`: missing_predicate_roundtrip |
| T04–T06 | `test_review_protocol`: sibling preservation; `test_issue44_final`: stable split, advisory_wrong_basis; E3 реальные empty/repeated corrections |
| T07–T08 | E3 noncooperative stop, contract_upgrade_releases_old_stop, browser_provider_protocol_recovers_after_known_outage, cancelled_review_has_terminal_projection |
| T09 | E2 actual bad repair, partial_phase_year_cannot_become_invented_january_first, typed/reference trials |
| T10–T12 | two_append_operations_and_scene_location_are_atomic; generation_calendar linked repair; stale revision/worker/ownership and concurrent Resume tests |
| T13 | hidden_intrinsic_error_is_not_misreported_as_new_damage |
| T14–T17 | generation_calendar residence/Knowledge preservation, E2 closure rejection, E3/E4 full replay-to-game |
| T18–T20 | generation_stability directed/Knowledge duplicate tests, draft_relations semantic repair, draft_motivations lifecycle/import, both player-goal recovery cases |
| T21–T24 | Gregorian metadata/effective leap projection, generation_calendar and calendar_v2 suites, server-clock protection, explicit zero/unknown schedule tests |
| T25–T26 | quality_empty_review_still_completes_and_author_unknown_can_remain, bounded_quality_rollback_and_rereview, E4 actual placeholders |
| T27 | value_cycle_is_persisted_across_resume_epoch; unresolved_semantics_cannot_save_and_repair_budget_is_shared; content fingerprints normalize whitespace |
| T28–T29 | draft_response_v4, fragment_recovery, initial persistent_journal_restart_and_unknown_outcome, stale-worker/revision guards |
| T30 | initial_draft_v4, draft_motivations imports, draft_world import/restore/confirm, six generation_scenarios, E1/E3/E4 start/turn/reload/next |
| T31 | draft-v4 desktop/mobile (including automatic alternate audit and outage Resume), runtime-presentation; effective calendar unit tests |
| T32 | Runtime v3 engine/legacy tests, Tabletop suite and browser campaign smoke |

## 3. Исходные журналы и восстановление

Оригиналы не редактировались. Fixture filenames отличаются только для удобства репозитория.

| Кейс | SHA-256 | Реальные плохие ответы / продолжение | Первичная повторная генерация | Start / turn / reload / next |
|---|---|---|---:|---|
| E1, 329 | `e1825af870cae2d8326bc2e70cbd8da43738c3fcd4d4852a569f04f0a7c19e58` | Replay + controlled residence adjudication; время/DOB кодом | 0 | Да, controlled |
| E2, 339 | `9d4c22292be2ccd3bee8ba78e7c7b58f452a5d55521e412c5dc128c41b353372` | Реальный `until_date=2022` и ложное закрытие отвергаются; отдельно обозначенная реконструкция до repair | 0 | Отдельный полный игровой прогон E2 не заявляется |
| E3, 351 | `1963faa9457d186438678fee4d31be22fd622d0d346a2044488c8ba7a343dad4` | Реальные collection-reference ответы, сохранённые fact remarks; alternate audit + controlled continuation | 0 | Да, controlled |
| E4, 366 | `bce102a6c848ab4f5e7d83e7654668efe0b1f0ad5b55c53724b2fe8c2e7b155a` | Все реальные review replies проходят отрицательный replay; exact candidate через API, не responses.world; локальный repair/quality | 0 | Да, controlled |

E4 before/after:

- Все восемь ID/имён сохранены; часы и DOB совпадают с candidate 366. Неизвестная абсолютная дата не заменяется выдуманной датой ради дня рождения.
- Knowledge сохранён целиком, включая исходное знание с `source_event_id=null`; directed relationships сохранены целиком.
- `f1.character_ids=[c1]`, `f2.character_ids=[c8]`; текст фактов не стирается и знание других участников не удаляется.
- Отдельно добавлены четыре parent, sibling и установленные дружеские связи. Усыновление/романтика не выдумываются. Три текущие профессии и закрытая историческая военная роль Алексея имеют canonical records без придуманного точного дня.
- Жильё Марины, Сергея и Алексея связано с известной квартирой. Илья не переселён к Кате; его добровольное решение не принято кодом.
- Рюкзак, винтовка и билеты находятся в possessions. Намерение Кати и условный план поездки отделены от согласия Ильи; due time неизвестен, план остаётся pending после игровых ходов. Ошибочное «уже едет» в thread исправлено на текущее пребывание на вокзале.
- Тестовая ручная правка названия переживает review, repair, повторный Resume и gameplay. Отдельный отрицательный тест запрещает модели переписать вручную изменённую биографию.
- Шесть «неизвестно» во внешности дополнены controlled provider; исходные внешний образ Ильи/Сони и биографии не переписаны. Например, у Тимура — следы масла на пальцах и короткая стрижка; у Марины — собранные волосы и домашний кардиган; у Алексея — усталый внимательный взгляд и поношенная куртка. Это примеры проверки применения разрешённых дополнений, не образцы живого ответа DeepSeek.

## 4. Команды и слои тестирования

Локальный полный прогон: **1731 passed in 213.87s**. Последний focused contract/regression прогон: **72 passed in 20.61s**. Frontend build: **passed, 3.43s** (существующее предупреждение о chunk >500 kB). Compileall, pip check и diff check успешны. Итоговый CI опубликованного SHA фиксируется в PR; локальный backend результат не подменяет browser CI. Команды воспроизводимы из корня репозитория:

```bash
HF_HUB_OFFLINE=1 python -m pytest -q
HF_HUB_OFFLINE=1 python -m pytest -q tests/test_issue44_final.py tests/test_generation_calendar.py tests/test_generation_stability.py tests/test_generation_scenarios.py tests/test_review_protocol.py tests/test_draft_motivations.py tests/test_fragment_recovery.py tests/test_draft_relations.py
python -m compileall -q backend scripts/probe_generation_stability.py
python -m pip check
git diff --check
cd frontend
npm run build
npx playwright test --project=desktop --reporter=line
npx playwright test --project=mobile --reporter=line
```

Локальная попытка Playwright с `/tmp/calendar-browser/chrome-linux64/chrome` завершилась ошибкой запуска `socket() failed: Operation not permitted`; страницы не открылись, локальные скриншоты/визуальная приёмка не заявляются. Browser jobs CI проверяют опубликованный код. Снижение ожидания `saved` до `error`, скрытие теста или увеличение timeout не применялись: старый fixture теперь моделирует известный HTTP-отказ альтернативного аудита, а отдельный browser-тест проверяет автоматическое восстановление без Resume.

## 5. Живая приёмка

- Безопасный механизм ключа: переменная `DEEPSEEK_API_KEY`; в этой среде не настроена. Проверено только наличие; значение не выводилось.
- Явный конечный бюджет для текущей работы не задан.
- **Новых реальных DeepSeek calls: 0** (world, review, correction, repair, quality и gameplay). Новых платных расходов нет. Исторические requests E1–E4 не являются новыми вызовами. Стоимость будущего успешного мира неизвестна, а не нулевая.
- Входы заранее зафиксированы в `tests/fixtures/generation_scenarios/inputs_final.json`. Шесть fresh-workspace offline сценариев используют controlled world/review/gameplay; они не измеряют творческую способность модели.

| Сценарий | Повтор 1 | Повтор 2 | Live requests/tokens/cost | Live gameplay |
|---|---|---|---|---|
| E4 с нуля | Не запускался | Не запускался | Не измерено | Не выполнен |
| Повседневность | Не запускался | Не запускался | Не измерено | Не выполнен |
| Исторический мир | Не запускался | Не запускался | Не измерено | Не выполнен |
| Custom календарь | Не запускался | Не запускался | Не измерено | Не выполнен |
| Усыновление / секрет | Не запускался | Не запускался | Не измерено | Не выполнен |
| Организации / неизвестные адреса | Не запускался | Не запускался | Не измерено | Не выполнен |

После безопасной настройки ключа и отдельного задания бюджета:

```bash
python scripts/probe_generation_stability.py \
  --budget-usd "$APPROVED_BUDGET_USD" --runs 2 \
  --output /tmp/pr116-live-final
```

Запуск фиксирует SHA/inputs/settings до начала, сохраняет все 12 исходов и каждый request, неизвестную стоимость оставляет null. После успешной живой генерации проверяет editor/confirm и **controlled**, а не live, gameplay с повторным открытием SQLite и следующим ходом. Два настоящих gameplay smoke на E4-мире и другом сценарии остаются отдельной обязательной живой проверкой. Здесь выполнен только `--help`; платный probe не запускался.

## 6. Оставшиеся вопросы и #78 manual QA

Обязательный продуктовый блокер: 12 свежих live-генераций и два live-gameplay smoke на окончательном SHA с безопасным ключом и конечным бюджетом. Нельзя рекомендовать закрытие #44 по offline mocks. Итоговый CI отдельно проверяется после публикации; pending/failure не считается успехом.

Необязательные будущие задачи эпика не выполнялись. Формальные гарантии литературной согласованности не заявляются; все реальные провалы будущего live-набора должны сохраняться, а не заменяться удачными попытками.

Расширение существующей #78 QA-документации (без нового тестового Runtime):

1. В изолированной dev SQLite выполнить существующий loader/checkpoint `calendar-evening`; проверить календарь и переход даты по `calendar-generation-acceptance.md`. Затем использовать новый workspace для создания мира — не изменять baseline fixture.
2. В author editor открыть «Начало игры»: встроенные месяцы/неделя видны без ручного заполнения; неизвестный год не превращается в выбранный год; пустые seasons/observances показываются как «Не заданы». Проверить populated Gregorian и custom profile.
3. Для воспроизводимого негативного пути запустить `test_issue44_final.py`: это загружает исходный candidate 366, реальные неверные отчёты и контролируемое продолжение через тот же API. Проверить восстановленные структуры и сохранность Knowledge/agency по assertions, не только сообщение об успехе.
4. В browser fixture `TEST_REVIEW_AUTOMATIC` дождаться готового мира без действий пользователя. `TEST_REVIEW_PROTOCOL` моделирует известный отказ провайдера; после reload одна доступная команда Resume завершает альтернативный аудит. Не добавлять ручной JSON repair.
5. Запустить Start Game, обычный ход, reload и следующий ход; сравнить canonical snapshots. Для legacy/import использовать существующие Motivation/WorldState fixtures, не запускать их через творческое дополнение. Сохранить обычные rollback/branch regressions полного набора.

Пояснение для будущего закрытия #44: архитектурная замена §1.2 выполнена в рамках одного исходного генератора. Закрытие допустимо только после merge пользователем и подтверждённой конечной live-приёмки. PR не мёрджится, #44 не закрывается, следующие задачи не начинаются автоматически.

## 7. Заключение

До итогового CI готовность инженерной части не утверждается. При зелёных backend/build/desktop/mobile проверках опубликованного SHA статус: **«Инженерная часть готова; живая приёмка не выполнена»**. Это не рекомендация закрыть #44.
