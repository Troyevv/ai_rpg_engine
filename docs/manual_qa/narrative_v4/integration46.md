# Narrative Runtime v4 · интеграционная приёмка #46

База — master `421cb216e7ac1c370b8bfe89df1a2ef555fca11f`, merge #200 / #125 после #199.
v4 обозначает этап интеграции существующего Narrative. Данные остаются в WorldStateV3 и SQLite History.
Новые проверки используют #78, локальную SQLite и контролируемые ответы провайдера. Точный проверенный head и итоговые CI gates публикуются в PR.

## Требования и воспроизведение

Имена ниже обозначают модули в `tests/` (префикс `test_` и расширение `.py` опущены). Матрица связывает критерий с проверяемой границей. Конкретные утверждения о результате относятся к указанным маршрутам. Для J04 отдельно указан красный результат на базе.

| ID | Существующий владелец и тесты | Сквозная граница или дополнительная проверка |
|---|---|---|
| R01 | Workspace/Initial State · draft_editor, workshop192, runtime_handoff, genre_catalog | J01, четыре входа, решения автора и независимость начатой игры |
| R02 | RawTurnResult/StateResolver · narrative_authority136, extraction_revision137, semantic_participation | J02 наблюдение и появление, J06 bounded repair, отсутствие частичного commit |
| R03 | CalendarProfile/Locations · calendar_v2, holiday_localization, residence_roles | J02 чтение диапазона, J05 календарные 20 лет |
| R04 | Commitments/remote semantics · commitments, phone122, group166 | J02–03 план появляется в календаре на основании прочитанного ответа |
| R05 | Life/capabilities · life_social, protagonist, long_term_advance | J04–05. Открытый блокер incapacitation #109 |
| R06 | Protagonist/Camera · player_agency, protagonist, pov_transitions | J05 ручная смена, смерть, reload, следующий герой |
| R07 | ObjectiveRelation/Kinship · life_social, public_family_directory | J05 бабушка → отец → ребёнок, property разводов, новых браков и архивных веток |
| R08 | Reproduction/BirthIdentity · reproduction, runtime_handoff | J05 рождение, взросление, сохранение факта рождения после смерти, видимость адресата |
| R09 | Residence/Role/Possession · residence_roles, possessions | J05 стабильные roles/residences после LTA, отдельные переходы владения в доменном наборе |
| R10 | History/Milestone/Feelings · milestones, personality, goals_values, relationship_evidence | J03 явный ответ → обоснованный сдвиг доверия одного направления, повтор worker |
| R11 | Knowledge/POV · knowledge_lifecycle, story_secrets178, secrets183 | J02 Knowledge с источником, J05/06 личная видимость и изоляция вариантов |
| R12 | Director/Pacing/Initiative · narrative_pacing, npc_initiative, narrative_continuity, narrative_authority136 | Обычный тихий ход; разрешённый исход без Director permit. Качество инициативы с реальной моделью — #99 |
| R13 | Remote/CommunicationProfile · communication_cycle, group166, historical_correspondence130, call_continuity | J02–04, запрет маршрутизации к неизвестному ребёнку. Системное завершение невозможного звонка — #119 |
| R14 | Promotion/NPC review · npc_review, npc_review_revision, long_term_advance | J02 неподтверждённая карточка, следующий ход, телефон и Knowledge; J06 sibling без NPC |
| R15 | LTA/lifecycle · long_term_advance, reproduction | 5/15 лет в действующих регрессиях; J05 20 лет, следующий герой, обычный ход |
| R16 | Repository/History, epoch/revision · single_mode, runtime_v3_storage, runtime_handoff | J06, архивные payload и heads, повтор миграции; mixed WAL, backup, конкурирующее открытие в single_mode |
| R17 | React/Playwright · workshop192, npc-review, group152, phone163, genealogy156, relationship-motion, streaming72, narrative-skins | Полные desktop/mobile gates; рядом с итогом CI в PR указана граница локального запуска |
| R18 | ContextScope, запрос Milestones, genealogy, календарь, directory, LTA · runtime_properties46, long_term_advance, context_builder_v2 | Фактические размеры ниже; время — наблюдение, пороги CI используют размеры/бюджеты |

## Сквозные маршруты

| ID | Как повторить (pytest, подстрока для -k) | Что сравнивается |
|---|---|---|
| J01 | `generation_editor_start_turn_save_reload` | Генерация, JSON, экспортные MD и TXT → preview/reject/accept → восстановление двух версий → Start → два обычных хода с повторным открытием БД → новая авторская правка и второе прохождение. TXT/MD используют общий text-adapter. |
| J02 | `j02_pending` | Вход нового NPC, наблюдаемый отдельно Олег, pending review, ход, реальная отправка/ответ, до/после прочтения, календарь, источники и перезагрузка |
| J03 | `api_jobs_meeting_retry_variants_reload_and_cost` | Автономная серия в группе, вопрос, пауза при чтении, ответ, единый план, направленное доверие, повтор, SQLite, дальнейший ход |
| J04 | `j04_call`; дополнительно регрессия #119 ниже | Завершение принятого звонка собеседницей в сцене смерти, смена героя, reload/ход. Потеря сознания без авторского отбоя блокируется #109. |
| J05 | `j05_three_generations` и `hidden_birth_recipient` | Один мир #78 с действующими семейными связями и зачатием/рождением через Resolver; 20 лет → выросший ребёнок → смерть → сестра → ordinary turn. Проверены parent edges, возраст, способности, внешность, история беременности и личная Knowledge. |
| J06 | `j06_checkpoint`, `old_save_restore_regenerate_variant_rollback`, `retry_regenerate_variants_and_rollback` | На семейном checkpoint новый NPC, ошибочный Extraction, repair, ручной retry, исходный context, sibling без NPC, восстановление, rollback и сравнение архивных байтов; отдельный сохранённый legacy snapshot |

Для регрессии #109 без изменения рабочей ветки из корня репозитория:

```sh
git fetch origin pull/119/head
git show c48e9540fa0710e8d12913a4797bebdf1b5c8597:tests/test_remote_incapacitation.py > /tmp/test_remote_incapacitation.py
PYTHONPATH="$PWD:$PWD/tests" python -m pytest -q /tmp/test_remote_incapacitation.py::test_incapacitated_actor_is_not_trapped_in_call
```

На базе потеря сознания принята атомарно, capabilities запрещают действие/речь/восприятие, но в SQLite после reload звонок остаётся `answered` вместо `ended`. Нужна повторная приёмка после #119. PR #118 относится к созданию мира; его код здесь не используется.

## Бюджеты и границы

`python -m pytest -qs tests/test_runtime_properties46.py`. На мире из 112 персонажей, с синтетической нагрузкой в 96 архивных пакетов, запрос вернул 8 milestones, окно истории — 64 пакета, родословная — 24 узла с признаком усечения, адресная книга — 111 адресатов. Для обычного хода локальная оценка составила 24 617 токенов при окне 32 768 и резерве 2 000, для 15 лет LTA — 0 модельных вызовов. Отдельная генерируемая проверка использует до 163 персонажей и 2 751 исторического события. Бюджеты относятся к возвращённому результату: SQLite-запрос Milestones всё ещё может обходить всю ancestry выбранной ветки.

Новый формат сохранений и миграция истории не требуются. Доставка/семантика модели проверены на детерминированных ответах. Биллинг, полнота понимания произвольной прозы и широкая живая игра с DeepSeek относятся к #99.
