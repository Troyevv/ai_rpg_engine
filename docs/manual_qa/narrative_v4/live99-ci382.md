# CI #382: причина отмены backend и бюджет полного job

Продолжение PR #202, ветка `qa/99-live-deepseek`. База master —
`57c173d8ece34f29cb3af37e6b28beb208e9bf63` (включает #204 / fix #203).
Исследован [run #382](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42235447072)
на HEAD `4df339057a1b07bfb7002738a26f2eb98f5db818`.
Результаты текущего HEAD и его SHA доступны в [проверках PR #202](https://github.com/Troyevv/ai_rpg_engine/pull/202/checks);
неизменяемая ссылка на итоговый run и оценка готовности публикуются в описании PR после завершения CI.

## Подтверждённая причина

Аннотация GitHub для [backend job 127951712463](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42235447072/job/127951712463):

> The job has exceeded the maximum execution time of 20m0s

Это **job timeout**, не отмена пользователем или новым workflow и не доказательство
flaky-теста, зависания или недостатка ресурсов. Полный pytest дошёл до `[100%]`
и напечатал успешный итог до отмены шага при завершении процесса.

| Событие #382 | UTC / длительность |
|---|---|
| Начало backend job | 14:36:36 |
| Начало pytest после checkout, setup-python и pip | 14:37:53; setup 77 s |
| Полный итог pytest | 14:56:41.571; **3105 passed, 1 skipped, 1125.21 s** |
| `The operation was canceled.` | 14:56:44.501 |
| Summary и загрузка JUnit | 14:56:44–46; success |
| Завершение job | 14:56:49; cancelled |

[Сохранённый JUnit #382](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42235447072/artifacts/13511708385)
содержит 3106 cases, **0 failures, 0 errors, 1 skipped**, suite time 1125.157 s.
На 24 QA #99 cases приходится 5.022 s (около 0.45% суммарного времени cases).
Самый долгий case — `test_100_jobs_through_engine_with_pov_background_and_reload`,
38.534 s; следующий — historical dozen letters, 17.845 s.
Никакой тест не остался незавершённым в этом XML. Признаков зависшего QA-теста нет.
Единственный существующий skip — `test_review170::test_real_export_evidence`:
приватный export не опубликован, требуется `RPG_REVIEW170_EXPORT`.

Frontend, все desktop/mobile shards, `e2e-full` и `e2e-smoke` в #382 успешны.
`verify` корректно завершился failure, потому что результат backend — cancelled.
Успешная строка pytest не заменяет успешный статус job. Старый #381 и его
отдельный POV failure не следует смешивать с этим run.

## Минимальное исправление

Только backend job получает **25 минут** вместо 20. Расчёт основан на измерениях:

```text
77 s setup + 1286.16 s предыдущий полный локальный pytest
           + 10 s завершение/отчёт + 120 s запас = 1493.16 s < 1500 s
```

Даже более быстрый #382 требует 77 + 1125.21 = 1202.21 s без завершения и выгрузки,
что уже превышает 1200 s. Лимит включает setup, а время в строке pytest — нет.
Запас ограничен двумя минутами; таймауты отдельных тестов, других jobs и Playwright
не меняются. Полный набор, assertions, verify gate и команды CI сохранены.
Повторные попытки и пропуск тестов не добавлены; #382 не перезапускался для сокрытия ошибки.

`tests/test_ci_backend_budget.py` проверяет расчёт для обоих измеренных прогонов,
неизменность полного pytest command и фактическое выполнение shell gate для
success/failure/cancelled/skipped. Последние три результата обязаны проваливать gate.

QA checkpoint adoption дополнительно допускает ровно два CI-пути:
`.github/workflows/verify.yml` и `tests/test_ci_backend_budget.py`.
Иначе это изменение CI ошибочно считалось бы изменением продукта и блокировало
совместимое продолжение QA. Отдельные проверки сохраняют запрет Runtime/Frontend
diff и грязного checkout. Состояние игры, manifest, ledger и оплаченные запросы
эта правка не изменяет; Runtime и продуктовый frontend не правились.

## Проверки текущего изменения

Полный локальный backend: **3105 passed, 1 skipped, 1 warning за 1126.85 s
(18:46), exit code 0**. Набор был собран до добавления 10 новых CI/recovery cases;
все они затем прошли в профильном наборе ниже. CI итогового HEAD собирает весь
набор вместе. Самый долгий локальный case (Runtime 100 jobs) завершился за 29.31 s.

Полный локальный запуск: `python -m pytest -q -p ci382_timing --junitxml=/workspace/work/ci382-full-pytest.xml --durations=30`.
Плагин `ci382_timing` находится вне репозитория и только сохраняет длительности.
Регрессия дополнительно проверена на временной копии старой конфигурации:
20-минутный лимит ожидаемо проваливает оба измеренных сценария бюджета.

- CI budget/gate, CI selection и QA #99 budget/evidence/recovery/retest:
  **57 passed**, 5.28 s. Включены 10 новых регрессионных cases.
- Frontend: **148 passed / 22 files**, production build success.
- Полная desktop/mobile Playwright-матрица выполняется в CI итогового HEAD;
  её окончательный статус фиксируется в описании PR и по ссылке проверок выше.
- Команды Python выполнялись с `DEEPSEEK_API_KEY` удалённым из окружения процесса.
  **Новых платных запросов: 0; новых токенов и расходов: 0.**
- Сравнение `reservations`, `qa_actions`, `spending_caps` общего SQLite ledger
  с ранее сохранённым архивом: таблицы совпадают. Сохраняются 34 dispatch и
  28 action reservations; счётчики, allowance и receipts не сбрасывались.

Полные логи, оригинальный JUnit, аннотации, timestamps и сверка ledger сохранены
вне Git в `/workspace/work/ci382-*`. Исходные QA-каталоги и архивы не удалялись
и не заменялись. Локальный полный pytest дополнительно пишет время каждого case
в отдельный JSONL через внешний measurement-only plugin, без изменения поведения тестов.

## Ограничения #99

История живого тестирования и доказательства остаются в
[отчёте Knowledge / Phone](live99-smoke-20261106.md).
В этой итерации DeepSeek не вызывался: прежние результаты не выдаются за новый live smoke.
Суммарно 34 dispatch, usage estimate $0.050146260, conservative peak/cold $0.1394298.

- Вопрос Вере после #204 принимается без `continuity_external_decision`; live optional
  beat не сохранён (`continuity_player_interaction_unconfirmed`). Synthetic control
  не заменяет живое подтверждение beat.
- Phone остаётся остановлен: Extraction выдаёт недопустимый маршрут `contact_id`
  в `remote_initiative`; Runtime корректно возвращает `remote_unreachable`.
- Semantic retrieval работал через structural fallback. Длинная кампания,
  полное покрытие семейного сценария и этапы B/C не выполнены.
- Исторические локальные E2E-находки о фиксированном порте, общем fixture state
  и locator закрывающегося POV-диалога документированы в прежнем отчёте.
  Их первопричины не исправляются этим изменением CI; отсутствие повторения
  в #382 само по себе не доказывает устранение.

Зелёный CI позволяет оценивать merge именно QA-инфраструктуры, а не закрытие
Issue #99 или полноту продуктового Live Gameplay QA. PR #202 не мёрджится,
Issue #99 остаётся открытой, этапы B/C не запускаются.
