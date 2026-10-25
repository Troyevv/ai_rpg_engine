# Приёмка Issue #44 / PR #116: release contract

## 1. Итог

**Статус:** инженерная проверка; живая приёмка не выполнена. G5 остаётся обязательным блокером продуктовой приёмки. Не утверждается подтверждённая стабильность DeepSeek.

Исходный HEAD и база ревью: `e17a7b90d2491a2a66fb67d726f6561a78ca73db`. Base master: `4bc5ec66a1a281ca7a3dc88776eb3df5e694d3aa`. Проверены актуальные AGENTS.md, Issue #44 и Epic #36. Существующая история PR сохранена; новый генератор, граф #117 и конвейер #105 не добавлялись. Миграций SQLite и формата старых сохранений нет.

Точный опубликованный SHA, ссылка на его CI и окончательные результаты verify/desktop/mobile фиксируются в [текущем отчёте PR #116](https://github.com/Troyevv/ai_rpg_engine/pull/116). Этот файл хранит воспроизводимые доказательства реализации; результаты предыдущего SHA не считаются результатами текущего. Merge и закрытие #44 не выполнялись.

## 2. Последние дефекты и системные исправления

| Дефект | Исходное приложение | Причина и исправление класса | Регрессия |
|---|---|---|---|
| F1 correction падает на форме отчёта | Прямые вызовы реальных parse/correction с null/scalar/list и basis:null | Обход до проверки типов; безопасное извлечение контекста, typed replacements/resolutions, подготовка внутри конечной стратегии | `test_correction_builder_handles_untrusted_item`, nested matrix, builder fault injection, API recovery |
| F2 quality теряет готовый результат | Реальный quality.complete с root array/null/string, null collections | Разные контракт и обработчик; отдельные DTO/schema для patches/preserved/mixed, атомарный trial/re-review и terminal partial | `test_quality_invalid_reply_preserves_checked_world`, valid forms, rollback, API quality_partial |
| F3 advisory блокирует отчёт | Реальный parse: неверный locator, basis, remove/patch | Изоляция раньше покрывала лишь DTO; единая политика всего пункта, warning и нулевые права записи | `test_bad_advisory_is_isolated`, entire-item matrix и required siblings |
| Соседние: неверные ID/списки и claims | Реальные normalize/inspect_candidate/merge_duplicates | Typed проверка перед hash, membership и обходом; точные пути; независимая хронология сохраняется | adjacent shape matrix, Knowledge/Relationship matrix |
| Соседние: regeneration JSON | Реальный decode_result | Использовался permissive json.loads; общий strict decoder, duplicate/nonfinite/depth guard | `test_strict_json_for_regeneration_and_depth_limit` |
| Соседние: quality running после restart, raw export | Реальные SQLite/API/lifespan | Атомарная финализация, защита late write, авторский экспорт diagnostics/raw | terminal/restart/internal-error tests |

Первый красный прогон F1–F3: **13 failed, 4 passed**. Дополнительная матрица соседних обработчиков до исправления: **7 failed, 8 passed**. Это тесты модулей приложения, не isolated_probes.py. Указанные сбои подтверждены; исторические probes повторно не выдаются за доказательство приложения.

### Границы недоверенных данных (A01)

| Стадия | Декодирование/проверка | Исход при отказе |
|---|---|---|
| Primary candidate / targeted regeneration | strict_loads, normalize, Runtime models, canonical_check | Точные диагностики, кандидат/raw сохранён, bounded repair |
| Review item | ReviewIssue + per-item semantic/path validation | Required → ReportError с partial siblings; явный advisory → warning без прав |
| Correction | Correction/Replacement + issue identity; явный legacy positional adapter | Прежний scope сохранён, следующая стратегия |
| Re-audit | Reaudit/Resolution/Basis + все IDs и реальные paths | Нет молчаливого удаления пункта; каждый явно replaced/disproved/unresolved |
| Repair | PatchReply/Operation + scope/hash/protected paths + canonical trial | Никакой частичной записи; RejectedTrial/NoProgress сохранены |
| Quality | QualityReply + scoped ops + source excerpt + overlap guard | Старый проверенный мир, partial/rejected/cancelled |
| Quality re-review | ReviewIssue; при preserve — QualityAudit/UnknownConfirmation | Проверка конкретных actor_id/field/path; blocker/malformed → rollback |

Форма проверяется до `.get`, membership, hashing, iteration. ProtocolError/ReportError содержат stage, version, code и report_path; при наличии добавляются world_path/issue_id. Неожиданная внутренняя ошибка не превращается в успешное исправление: верхний finalizer сохраняет internal_error в авторском журнале.

## 3. Соответствие заданию

| Код | Статус реализации | Реализация/регрессия | Ограничение |
|---|---|---|---|
| A01 | Выполнено инженерно | Карта выше, typed envelope, strict JSON, соседние валидаторы | Только поддерживаемый размер; не обещается приём любого JSON |
| A02 | Выполнено инженерно | Schemas/DTO/prompts, conditional rules, JSON Schema positive/negative tests | Legacy correction явно адаптируется |
| A03 | Выполнено инженерно | Подготовка в recovery, конечные persisted strategies, реальные плохие E4 bytes + controlled continuation до ready | Модель может исчерпать стратегии; успех не гарантируется |
| A04 | Выполнено инженерно | quality rollback, preserved-only/mixed, адресное подтверждение неизвестности | Семантическая точность проверяющей модели требует live |
| A05 | Выполнено инженерно | Все ветки advisory; конфликт blocker не понижается | Неопределённая классификация остаётся ошибкой |
| A06 | Выполнено инженерно | SQLite terminal states, restart/stale/manual guards, reservation tests | Неизвестная стоимость запроса не обнуляется |
| A07 | Выполнено инженерно | U01–U20: карта ниже, реальные обработчики, E1–E4, API | Controlled ответы не измеряют качество модели |
| A08 | Частично | Самопроверка, backend/build и browser CI | Live не выполнен |
| A09 | Частично | G1–G4 подтверждаются тестами/CI точного SHA | G5 не выполнен |
| A10 | Поставка в том же PR | Этот отчёт и итоговый отчёт PR по шаблону | Merge/закрытие оставлены пользователю |

Ранее реализованные R01–R15 не заменены новой архитектурой. Их regression suites включены в полный backend и browser CI; требование живой приёмки по-прежнему не выполнено.

## 4. Слои тестирования

Команды из корня репозитория; frontend команды из `frontend`:

- `HF_HUB_OFFLINE=1 python -m pytest -q tests/test_release_protocol.py tests/test_issue44_final.py tests/test_generation_stability.py tests/test_review_protocol.py` — 349 passed в промежуточном фокусном прогоне; окончательный полный набор включает их все.
- `HF_HUB_OFFLINE=1 python -m pytest -q` — окончательный результат приведён в PR и CI того же SHA.
- `npm run build`; `python -m pip check`; `git diff --check` — выполнены. Build: 3.14s, существующее предупреждение Vite о bundle >500 kB.
- `npx playwright test --project=desktop --reporter=line` и `--project=mobile` — CI точного SHA; локальный Chromium недоступен из-за `socket() failed: Operation not permitted`.
- Реальные вызовы DeepSeek: **0**. Изолированные probes не запускались как приёмка.

| U | Тесты приложения |
|---|---|
| U01–U05 | release protocol: builder, nested/property matrix (80 Hypothesis examples), schema/legacy/split; review_protocol sibling tests |
| U06–U09 | release quality malformed/valid forms/unknown owner/overlap/re-review/cancel; issue44_final quality |
| U10–U11 | release advisory entire-item matrix + good/bad blockers |
| U12 | release API nullable_review/advisory/quality_partial; E4 unchanged и independent edit |
| U13–U14 | review_protocol HTTP429/503; draft recovery/no-progress/cycles; E3 unchanged Resume; E4 contract upgrade |
| U15 | release terminal/restart/late journal; review_protocol old worker and manual revision guards |
| U16–U17 | E1–E4 replay; generation_scenarios six independent settings/IDs; E4 canonical gameplay assertions |
| U18 | draft-v4 Playwright: release nested/quality partial + existing error/calendar/editor flows, desktop/mobile |
| U19 | Полный suite: import/legacy, Runtime v3 и Tabletop; существующие browser smoke |
| U20 | release depth guard; 36/56 character boundary API + budget preflight; existing continuation and context-budget suites |

### E4 без ручного обхода

Candidate **366**. Fixture `generation_response_final.json`, SHA-256 `bce102a6c848ab4f5e7d83e7654668efe0b1f0ad5b55c53724b2fe8c2e7b155a`. Все файлы архива сверены с SHA256SUMS.json; E1–E4 совпадают байт-в-байт с прежними fixtures. Оригиналы не менялись и не копировались заново.

`test_e4_candidate366_resume_repair_quality_start_turn_reload_next[4-False]`: candidate_snapshot и candidate_text проверены на равенство оригиналу перед Resume. Новых первичных генераций **0**, title/hash ради обхода не менялись. Техническая адаптация: новая запись workspace/job, локальные revision/epoch и привязка сохранённого response_journal; экспортные requests/recovery/binding вынесены в соответствующие repository поля. Оригинальные responses, review_failures и история стратегий сохранены. Новая версия контракта 7 / recovery policy 3 делает прежний ошибочный ответ доступным обновлённой проверке; старый stop не стирается из fixture.

Реальные ошибочные reports → correction с реальными ошибочными bytes → scoped re-audit с явными решениями → адресные patches → quality/re-review → saved. Последующие ответы управляемые тестом; их нельзя считать реальными успешными ответами DeepSeek. Re-audit явно разрешает все замечания, включая синтаксически верные, но смыслово ошибочные; correction сохраняет корректных соседей кодом.

Confirm/Start Game → обычный ход → reopen SQLite → следующий ход: реальные repository/runtime пути, controlled narration/extraction. Сравниваются восемь персонажей, календарь и DOB, Knowledge и направленные отношения, canonical relations, прежняя закрытая военная роль, rifle/pack/tickets, предложение поездки без даты/принятого решения игрока, intentions controlled actor. Повтор Resume готового мира не вызывает провайдера. Независимый `[4-True]` меняет title как настоящую ручную правку и доказывает сохранение. E3 также проходит этот путь.

### Browser / #78 QA

Новые сценарии `TEST_RELEASE_NESTED` и `TEST_RELEASE_QUALITY`: новый workspace → описание → generation → saved без ручного repair/Resume → правдивый partial warning (quality case) → reload → confirm → Start Game → шесть choices → reload. Проверяются единственный primary request, raw review failures, отсутствие ложного Resume и горизонтального overflow. Скриншоты `release-TEST_RELEASE_*-desktop.png` / `*-mobile.png` прикладываются CI как browser-results artifacts. Существующие сценарии покрывают редактор, ошибки, календарь и действия на обоих размерах экрана.

## 5. Отказы и сохранность

| Сценарий | Terminal state / кандидат | Диагностика и расходы | Следующее действие |
|---|---|---|---|
| Повреждённая форма correction | Следующая конечная стратегия; saved при корректном re-audit | Raw/IDs/partial siblings сохранены; builder без вызова не списывает бюджет | Автоматически re-audit |
| Постоянно некооперативный reviewer | job error, review failed; checkpoint сохранён | История и exhausted сохранены | Доступный reviewer/новый контракт; идентичный Resume не делает платный цикл |
| Неверный quality response | quality partial/rejected; прежний проверенный мир ready | Raw response/diagnostics в авторском export | Можно играть с предупреждением |
| Quality re-review rejected | Trial отклонён, старый мир не изменён | review_response и rejection сохранены | Старый проверенный результат |
| Неверный advisory | Recommendation warning, обязательные ошибки остаются | Нулевые patch/remove/basis права | Обработать реальные blockers |
| Cancel/restart/stale | stopped/error; quality cancelled/partial, не running | Pending, reservations, revision/epoch сохранены | Resume лишь при известном исходе; late write не принимает новый мир |
| Budget/unknown outcome | error; кандидат/raw не потеряны | Reservation не обнуляется, неизвестные usage/cost не выдумываются | Не делать слепой повтор |
| Unexpected internal error | job error/internal_error, quality terminal | Авторская диагностика; не выдаётся за provider success | Исправление кода |

## 6. Живая приёмка

Безопасно настроенный `DEEPSEEK_API_KEY`: **нет**. Явно разрешённый конечный бюджет: **не задан**. Реальных запросов **0**, фактически потрачено в этой работе **$0**; токены/латентность/процент успешности/качество live: **не измерено**. Не было скрытых неудачных платных попыток.

Все 12 запусков (E4 с нуля, повседневность, история, custom calendar, усыновление/секрет, организации/неизвестное жильё/план ×2) **не выполнены**. Два отдельных live-gameplay smoke **не выполнены**. Gameplay в тестах и встроенном probe — controlled, не live.

Проверен интерфейс `python scripts/probe_generation_stability.py --help`; это не live. После безопасной настройки ключа и отдельного явного бюджета команда существующего probe:

```bash
python scripts/probe_generation_stability.py --budget-usd "$APPROVED_BUDGET_USD" --runs 2 --model deepseek-flash --output /path/to/new-probe-output
```

`APPROVED_BUDGET_USD` здесь — ещё не заданный конечный лимит, а не разрешение расхода. Probe сохраняет inputs/settings/model/SHA до вызовов, все outcomes/costs; неизвестные метрики остаются null. Два live-gameplay smoke и содержательная оценка мира остаются отдельной обязательной работой, probe их не подменяет.

## 7. Условия выпуска

| Gate | Состояние | Доказательство |
|---|---|---|
| G1 | Инженерные тесты; окончательный результат в CI/PR | Typed schema/DTO и negative/property matrix |
| G2 | Инженерные тесты; окончательный результат в CI/PR | API recovery, E4 unchanged, ready → gameplay → reload |
| G3 | Инженерные тесты; окончательный результат в CI/PR | Atomic rollback, manual/canon/budget/restart guards |
| G4 | Только результат CI опубликованного SHA | verify + desktop + mobile, ссылки/цифры в PR |
| G5 | **Не выполнено** | Нет безопасного ключа и заданного бюджета; 0 live calls |

**Вердикт:** без G5 нельзя заявлять продуктовую приёмку и подтверждённую стабильность новых генераций. Инженерные результаты и CI не заменяют живую проверку. Merge и решение о закрытии #44 остаются за пользователем; следующие задачи эпика не начаты.
