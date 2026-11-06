# Narrative Runtime v4 · интеграционная приёмка #46

Интеграция Runtime — `92f54e7cb55e3045b7526575f296defc27246c97`. Версия полного набора тестов после исправления замера mobile — `d0a337ce8a4f547f2b2b584c2e2cc1334b2e83f4`. В ветку #201 на `a53e181` влит master `609314ec24a41fec813ce852b32f002c174b61eb`, включающий #119/#109 и удаление Tabletop (#200/#125). Игровые данные хранятся в WorldStateV3 и SQLite History. Проверки используют мир #78, изолированные БД, реальные API и jobs с контролируемыми ответами провайдера.

## Требования и воспроизведение

Имена ниже обозначают модули в `tests/` (префикс `test_` и расширение `.py` опущены). В R17 указаны Playwright-спецификации из `frontend/e2e/`. Каждая строка связывает требование с воспроизводимой проверкой.

| ID | Существующий владелец и тесты | Сквозная граница или дополнительная проверка |
|---|---|---|
| R01 | Workspace/Initial State · draft_editor, workshop192, runtime_handoff, genre_catalog | J01, четыре входа, решения автора и независимость начатой игры |
| R02 | RawTurnResult/StateResolver · narrative_authority136, extraction_revision137, semantic_participation | J02 наблюдение и появление, J06 bounded repair; неверный источник рождения блокирует commit, повреждённая внешность отбрасывается локально |
| R03 | CalendarProfile/Locations · calendar_v2, holiday_localization, residence_roles | J02 чтение диапазона, J05 календарные 20 лет |
| R04 | Commitments/remote semantics · commitments, phone122, group166 | J02–03 план появляется в календаре на основании прочитанного ответа |
| R05 | Life/capabilities · life_social, protagonist, long_term_advance, remote_incapacitation | J04–05. Системный отбой при недееспособности, LTA и выбор следующего героя после смерти |
| R06 | Protagonist/Camera · player_agency, protagonist, pov_transitions | J05 ручная смена, смерть, reload, следующий герой |
| R07 | ObjectiveRelation/Kinship · life_social, public_family_directory | J05 бабушка → отец → ребёнок, property разводов, новых браков и архивных веток |
| R08 | Reproduction/BirthIdentity · reproduction, runtime_handoff | J05 рождение, взросление, сохранение факта рождения после смерти, видимость адресата |
| R09 | Residence/Role/Possession · residence_roles, possessions | J05 стабильные roles/residences после LTA, отдельные переходы владения в доменном наборе |
| R10 | History/Milestone/Feelings · milestones, personality, goals_values, relationship_evidence | J03 явный ответ → обоснованный сдвиг доверия одного направления, повтор worker |
| R11 | Knowledge/POV · knowledge_lifecycle, story_secrets178, secrets183 | J02 Knowledge с источником, J05/06 личная видимость и изоляция вариантов |
| R12 | Director/Pacing/Initiative · narrative_pacing, npc_initiative, narrative_continuity, narrative_authority136 | Обычный тихий ход; разрешённый исход без Director permit. Качество инициативы с реальной моделью — #99 |
| R13 | Remote/CommunicationProfile · communication_cycle, group166, historical_correspondence130, call_continuity | J02–04, запрет маршрутизации к неизвестному ребёнку. Явный отбой и системное завершение проверены вместе с Life, исходами LTA и History |
| R14 | Promotion/NPC review · npc_review, npc_review_revision, long_term_advance | J02 неподтверждённая карточка, следующий ход, телефон и Knowledge; J06 sibling без NPC |
| R15 | LTA/lifecycle · long_term_advance, reproduction | 5/15 лет в действующих регрессиях; J05 20 лет, следующий герой, обычный ход |
| R16 | Repository/History, epoch/revision · single_mode, runtime_v3_storage, runtime_handoff | J06, архивные payload и heads, повтор миграции; mixed WAL, backup, конкурирующее открытие в single_mode |
| R17 | React/Playwright · 00-workshop192, npc-review, group152, phone163, genealogy156, relationship-motion, streaming72, narrative-skins | Полные desktop/mobile gates на GitHub-hosted Chromium, включая мобильный телефон, Мастерскую, анимации отношений и родословную |
| R18 | ContextScope, запрос Milestones, genealogy, календарь, directory, LTA · runtime_properties46, long_term_advance, context_builder_v2 | Фактические размеры ниже; время — наблюдение, пороги CI используют размеры/бюджеты |

## Сквозные маршруты

| ID | Как повторить (модуль pytest или подстрока для -k) | Что сравнивается |
|---|---|---|
| J01 | `generation_editor_start_turn_save_reload` | Генерация, JSON, экспортные MD и TXT → preview/reject/accept → восстановление двух версий → Start → два обычных хода с повторным открытием БД → новая авторская правка и второе прохождение. TXT/MD используют общий text-adapter. |
| J02 | `j02_pending` | Вход нового NPC, наблюдаемый отдельно Олег, pending review, ход, реальная отправка/ответ, до/после прочтения, календарь, источники и перезагрузка |
| J03 | `api_jobs_meeting_retry_variants_reload_and_cost` | Автономная серия в группе, вопрос, пауза при чтении, ответ, единый план, направленное доверие, повтор, SQLite, дальнейший ход |
| J04 | `j04_call` и `tests/test_remote_incapacitation.py` | Отбой NPC или явно заданный отбой игрока перед смертью → выбор героя и ход. При потере сознания без команды — один системный переход, reload и месяц LTA. Здоровый звонок блокирует LTA. Проверены regeneration, выбор варианта и rollback. |
| J05 | `j05_three_generations` и `hidden_birth_recipient` | Один мир #78 с действующими семейными связями и зачатием/рождением через Resolver; 20 лет → выросший ребёнок → смерть → сестра → ordinary turn. Проверены parent edges, возраст, способности, внешность, история беременности и личная Knowledge. |
| J06 | `j06_checkpoint`, `old_save_restore_regenerate_variant_rollback`, `retry_regenerate_variants_and_rollback` | На семейном checkpoint новый NPC, ошибочный Extraction, repair, ручной retry, исходный context, sibling без NPC, восстановление, rollback и сравнение архивных байтов; отдельный сохранённый legacy snapshot |

## Результат J04 после объединения

Git автоматически объединил общий файл `remote.py`: #201 ограничивает видимость неизвестного ребёнка при выборе адресата; #119 согласует уже существующий звонок с возможностями участников. Текстовых конфликтов не было. На первом объединённом дереве J04 воспроизвёл **конфликт порядка событий**: Вера положила трубку, Кирилл умер в том же ходе, но системное завершение опередило обработку явного отбоя. Resolver отверг ход при проверке уже закрытого звонка.

Resolver теперь применяет подтверждённый отбой до изменений Life на границе хода; переход присоединяется к тому же пакету Remote History. После Life штатная сверка #119 обрабатывает оставшиеся открытые звонки. Смерть, связь и History публикуются одной существующей транзакцией. Схему БД менять не потребовалось.

| Путь | Наблюдение в SQLite |
|---|---|
| Явный отбой NPC / подтверждённая команда героя, затем смерть героя | Ровно один `answered → ended` с фактическим инициатором и свидетельством. После выбора Веры и следующего хода событие остаётся единственным. Приписанный герою отбой без его команды отклоняет весь ход. |
| Кирилл теряет сознание, команды на отбой нет | После повторного открытия — `ended`, `system:participant_incapacitated`, один терминальный Event с причиной, без приписанного действия. LTA на месяц — **542 → 45 182**, 0 вызовов модели. Knowledge, POV и управляемый персонаж совпадают с исходными, недееспособность сохраняется. |
| Оба участника здоровы | Тот же LTA останавливается с `remote_call`, **542 → 542**. После regeneration здоровый вариант держит звонок открытым и имеет свою History. Выбор исходного варианта и rollback восстанавливают точные snapshots. |
| Реальная БД, созданная прежним HEAD #201 (`a53e181`) | Прежний движок сохранил недееспособность и открытый звонок. Новый прочитал тот же snapshot. Первый LTA закрыл звонок один раз и продвинул часы до 45 182. После rollback исходный snapshot восстановился. SHA-256 payload каждой из 10 прежних строк History и 4 вариантов совпал после чтения, LTA и rollback. |

Отдельная проверка ошибки записи на обычном ходу J04 установила в изолированной БД триггер `RAISE(ABORT)` на обновление `saves.state_json`. После сбоя и открытия новой Repository совпали все строки save, History (9), ходов (3) и вариантов (3). После снятия триггера ручной Retry выполнил только один Extraction. Затем прошли LTA, явное переключение на Веру и обычный ход. В History остался ровно один системный отбой, Кирилл по-прежнему был без сознания.

## Воспроизведение

Из корня репозитория сквозной набор выполняется одной командой:

```sh
python -m pytest -qs tests/test_runtime_integration46.py tests/test_remote_incapacitation.py \
  tests/test_runtime_properties46.py tests/test_call_continuity.py tests/test_single_mode.py \
  tests/test_draft_editor.py::test_generation_editor_start_turn_save_reload \
  tests/test_group166.py::test_api_jobs_meeting_retry_variants_reload_and_cost \
  tests/test_runtime_handoff.py::test_old_save_restore_regenerate_variant_rollback_keeps_legacy_bytes \
  tests/test_npc_review.py::test_retry_regenerate_variants_and_rollback
```

Проверка `birth_cannot_commit_as_optional_warning` запускает обычный ход с уже наступившим сроком рождения близнецов. Раньше неверная ссылка на Event давала успешный ход без детей. Теперь две ошибочные попытки Extraction оставляют исходный save, History и список ходов на месте. После исправления источника Retry публикует обоих детей за один Extraction, сохраняя валидное описание внешности первого ребёнка.

## Результаты проверок

| Набор | Верификация |
|---|---|
| Выделенный набор выше | **68 passed**, включая свойства, реальные API/SQLite и шесть маршрутов J01–J06 |
| Полный backend | **3058 passed, 1 skipped** локально и в Actions. Пропуск — приватный экспорт для `RPG_REVIEW170_EXPORT`. |
| Frontend | **148 passed** в Vitest, `npm run build` успешно выполнил TypeScript и production build Vite. |
| Playwright desktop/mobile | Матрица — 337 тестов на проект, на mobile 24 платформенных пропуска. [Итоговые четыре полных шарда и точные результаты на HEAD PR](https://github.com/Troyevv/ai_rpg_engine/pull/201/checks). Четыре smoke-шарда считаются отдельно. |

Первый [полный CI после merge](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42208037447) дал **337 passed** на desktop и **312 passed, 24 skipped, 1 failed** на mobile. В проверке W01–W69 `getBoundingClientRect()` во время входа в досье вернул высоту кнопки `43.99998474121094` при CSS-размере `44px`. Для повторного прогона проверка ждёт окончания собственной анимации диалога и проверяет все три кнопки с исходным минимумом `44 × 44` CSS-пикселя. Стили и анимации приложения прежние. [Итоги повторного прогона, SHA и ссылка на workflow](https://github.com/Troyevv/ai_rpg_engine/pull/201).

## Бюджеты и границы

`python -m pytest -qs tests/test_runtime_properties46.py`. На мире из 112 персонажей, с синтетической нагрузкой в 96 архивных пакетов, запрос вернул 8 milestones, окно истории — 64 пакета, родословная — 24 узла с признаком усечения, адресная книга — 111 адресатов. Для обычного хода локальная оценка составила 24 617 токенов при окне 32 768 и резерве 2 000, для 15 лет LTA — 0 модельных вызовов. Отдельная генерируемая проверка использует до 163 персонажей и 2 751 исторического события. Бюджеты относятся к возвращённому результату: SQLite-запрос Milestones всё ещё может обходить всю ancestry выбранной ветки.

Новый формат сохранений и миграция истории не требуются. Доставка/семантика модели проверены на детерминированных ответах. Биллинг, полнота понимания произвольной прозы и широкая живая игра с DeepSeek относятся к #99.
