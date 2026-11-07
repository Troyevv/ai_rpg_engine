# #99 — подготовка QA #219 → #230 к последовательному merge

Это **бесплатная интеграционная проверка**, не новый live-прогон и не завершение
Stage C. Issue #99 остаётся открытой; merge выполняет пользователь.

## База и граница результатов

Свежий master: `c1598de18f35e0b8e01a430c458211cfa86982b5`.
Проверены ancestry merge commits и фактические контракты в коде:

| Issue | Product PR / merge | Проверенный контракт |
|---|---|---|
| #220 | #224 / `1b2e3e42` | Event.minute в текущем игровом интервале |
| #221 | #225 / `a06caf7e` | due scene и off-camera pregnancy boundary |
| #222 | #227 / `8d281b0b` | транзакционный abandon без LLM и сохранение канона |
| #223 | #228 / `68a584d2` | уход без destination не является completed_arrival |
| #226 | #229 / `25c834b0` | физическое присутствие до History/Knowledge |
| #231 | #235 / `8411ed1c` | typed birth sex assessment, disclosure и reauthor guard |
| #232 | #234 / `c1598de1` | player action targets/meaning, Event provenance и Narrative conflict |
| #233 | #236 / `2bd13c67` | собственное decision evidence и bounded Extraction repair |

Наличие исправлений в master **не превращает прежние live failures в passes**.
Новый DeepSeek retest не запускался; устойчивость модели после этих исправлений
не подтверждается этой подготовкой. Runtime и frontend приложения не исправляются
в QA-ветках: их изменения приходят только из master.

Исходные отчёты остаются побайтно прежними:

- #219: исторический QA HEAD `07d646a4059e84ab2964f14bc08da21a8be65bce`,
  baseline `0c2f9fb042e6677d2b3ef03771556d5daa858344`, 35 действий / 59 calls,
  usage $0.098414214; [исходный отчёт](live99-stage-c-20261107.md).
- #230: live HEAD `9f83354de54488111ea9840475046d32be581234`, отчётный HEAD
  `454d4948cafc7a97f801ea3d1fd07c9672ed2a38`, baseline `25c834b094a9047471406d7166111c8b6b755f75`,
  28 действий / 42 calls, usage $0.062982108; [исходный отчёт](https://github.com/Troyevv/ai_rpg_engine/blob/454d4948cafc7a97f801ea3d1fd07c9672ed2a38/docs/manual_qa/narrative_v4/live99-stage-c-retest-20261107.md)
  добавляется только следующим PR #230.

Исторические commits сохраняются через merge, без rebase/force-push.
#230 уже содержал cherry-picked инфраструктуру #219; включение обновлённой ветки
#219 делает её предком #230. Сравнение #230 с #219 должно показывать только
post-fix QA additions, без второго harness и повторного добавления отчёта #219.

## Evidence: доступность и долговременное хранение

Архивы найдены и читаются в текущем **эфемерном workspace**. Размеры и SHA-256
совпадают с историческими references. Эти имена и прежние `/workspace/...` пути
**не являются download URLs или опубликованными GitHub artifacts**.
Подтверждённого долговременного внешнего размещения нет.

| Архив | Bytes | SHA-256 |
|---|---:|---|
| `live99-stage-b-final-evidence-20261106.tar.gz` | 29857056 | `851ae08b06d39b912c0e629bf430d5547516712662adf0ef520d0a9d8182056c` |
| `live99-stage-c-evidence-20261107.tar.gz` | 26465225 | `1d4b5119bc20f11e66ec5384e6c8717ae48744c3e25dc23b4a3402bad9d74b13` |
| `live99-stage-c-validation-20261107.tar.gz` | 18719872 | `396e36dcd7ed2d3ddde84e8ec2d9bbc06908328ec3fe8d4bb3b319c029a297d4` |
| `live99-stage-c-retest-evidence-20261107.tar.gz` | 31446864 | `966c43030151625858b947607dc809a4e4a7b91e30505931a8aa2094562f24fe` |
| `live99-stage-c-retest-validation-20261107.tar.gz` | 4949 | `ea14936550c27e375057c37828e6f1df33dfbbbc76282bc3379a1c47ac2e317b` |

Перед merge рекомендуется перенести эти неизменяемые архивы в **закрытое object
storage с versioning и retention** (например S3-compatible bucket, prefix
`qa/issue-99/2026-11-07/<sha256>/`), дать reviewers доступ и проверить SHA-256
после обратного скачивания. Альтернатива — Release assets в репозитории с подходящим
уровнем доступа; сырой SQLite/diagnostics не следует публиковать открыто без проверки
содержимого. Временные Actions artifacts с коротким retention не заменяют архив.
Загрузка в новое хранилище этой задачей не выполнялась; постоянные ссылки нужно
добавить в оба PR после переноса. Большие evidence-файлы не добавляются в Git.

Для проверки неизменности сохранён baseline hashes 1631 исторического файла,
включая архивы, snapshots/raw/checkpoints и shared ledger. Сравниваются также все
строки reservations/qa_actions, а не только итоги. Состояние ledger на начало
подготовки: 247 calls, 152 actions, 0 unknown outcomes. Ни run/resume/adopt старых
live-каталогов, ни новый paid run не разрешаются этой интеграционной проверкой:
Runtime изменился, исторические manifests остаются привязанными к своим SHA.

## Проверки и безопасный порядок

Профильные QA pytest запускаются на каждой ветке с удалённым `DEEPSEEK_API_KEY`.
Полный CI каждой итоговой ветки должен включать backend, Vitest/build, все
desktop/mobile smoke/full shards и оба E2E gates; одного зелёного verify мало.
Точные итоговые SHA, CI runs и результаты фиксируются в описаниях
[#219](https://github.com/Troyevv/ai_rpg_engine/pull/219) и
[#230](https://github.com/Troyevv/ai_rpg_engine/pull/230).

1. Сохранить evidence в долговременном хранилище, проверить ссылки/hashes;
   дождаться полного зелёного CI #219 и ревью QA diff относительно свежего master.
2. Пользователь мёрджит **#219 в master**, предпочтительно merge commit с сохранением
   ancestry. Не удалять ветку `qa/99-stage-c`, пока #230 использует её как base.
3. Переназначить base **#230 на master** после merge #219, проверить обновлённый diff
   и CI на фактической паре base/head. До merge #219 base #230 — `qa/99-stage-c`.
   При squash/rebase merge #219 сначала потребуется явно согласовать ancestry #230
   с новым master; нельзя повторно включать всю инфраструктуру как новый diff.
4. Только после этих проверок пользователь мёрджит **#230**. Никакой автоматической
   команды merge/close или нового PR подготовка не создаёт.

Оба PR — частичные QA-результаты. Remote birth/Knowledge, milestones, активные
коммуникации при кризисе и содержательный длительный lifecycle остаются непроверенными;
нужен отдельно разрешённый live-retest исправлений #231–#233 и требования #223.
Готовность движка к длительной пользовательской кампании не заявляется.
