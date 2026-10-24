# Договорённости и личные интервалы — #66

Используется тот же QA-мир #78 и календарь #37. Каждый reset создаёт новое
прохождение; существующие saves/история не изменяются.

```bash
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --db /tmp/narrative-qa.sqlite3 --checkpoint commitments
RPG_DB_PATH=/tmp/narrative-qa.sqlite3 python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

Для запуска UI/backend используйте штатную команду проекта с той же изолированной
БД (см. README сценариев). Загрузчик возвращает ID созданного прохождения.
Исходный `base` и checkpoints `calendar-evening`/`calendar-leap` сохранены.

## Исходное состояние

Четверг, 2026-10-08 20:42. Кирилл, Вера, Тимур дома.

| Canonical ID | Состояние | Срок / связь |
|---|---|---|
| qa_friday_trip | pending | Пятница вечером, после работы; Кирилл и Елена |
| qa_sunday_return | pending | Воскресенье вечером; зависит от qa_friday_trip |
| qa_school_break | pending, planned | Каникулы Аси 10–17 октября |

В справочнике «Мир» открыт раздел «Договорённости и периоды». Окно вечера
показывается диапазоном, не обещанным выездом ровно в 18:00. Это GM-информация,
не автоматическое знание каждого персонажа. Ася сохраняет школьную роль.

## T1 — срок, выполнение и отсутствие повторной встречи

1. Начните игру; выполните обычный ход о карте. Reload; ещё обычный ход.
2. Явно договоритесь с Тимуром о встрече у карты сегодня в 21:00. Extraction:
   один новый pending ID, temporal(day_offset=0,time=21:00), evidence/player_evidence.
3. Time Skip на два часа должен остановиться в 21:00, не в конце запроса.
   pending не становится resolved от продвижения часов. Повторный skip при
   неразрешённой due-встрече останавливается сейчас; можно обычным ходом
   выполнить, перенести или отменить план.
4. Встретьтесь, поговорите, завершите встречу. У того же ID — resolved,
   outcome=fulfilled, evidence завершения. Поездка в сад всё ещё pending.
5. Обычный следующий ход, reload: встреча не инициируется повторно; исторический
   факт договорённости остаётся истинным, но Context классифицирует план как FACT.
6. Regenerate завершения, выбор первоначального варианта, rollback: восстанавливается
   соответствующий pending/resolved snapshot. Новая ветвь вариантов не загрязняет старую.

Автоматический эквивалент: `test_qa_start_turn_reload_next_turn_skip_variants_and_meeting_regression`.
Отдельная unit-регрессия воспроизводит «Гвоздь + независимая поездка в коттедж».

## T2 — перенос, препятствие, отмена и срыв

Reset. «Переносим поездку на субботу утром» с явным решением Кирилла:
тот же qa_friday_trip, окно субботы; второго pending дубля нет. API диапазона
пятницы больше не содержит поездку, субботы — содержит.

Поломка машины: blocked, всё ещё pending; возвращение тоже pending, без штрафа
отношениям. «Поездку отменяем»: cancelled, зависимое возвращение — cancelled /
dependency_cancelled. Отказ Елены также может отменить совместный план без согласия
Кирилла: Extraction указывает decision_actor_id Елены, не подделывает player_input.

На отдельном reset подтвердите неявку участника: missed / cancelled, не fulfilled,
автоматических relationship penalties нет. Последствия отношений возможны только
через обычное evidence-bound изменение, не из таймера.

## T3 — интервалы

Reset. До 10 октября каникулы planned. Наступление 10 октября не активирует их
автоматически, не перемещает Асю, не удаляет образование. После подтверждённого
«каникулы начались» — active (status=pending + started_minute).

Для текущего отпуска можно установить интервал фразой «Я уже в отпуске до ...»:
Extraction передаёт supported started, start/end. Сам отпуск не означает отъезд.
Reload сохраняет границы/фазу. По окончании срока интервал остаётся текущим с
overdue temporal relevance, пока evidence не подтвердит ended/cancelled. Для
controlled actor Time Skip прерывается у конца активного интервала.

## T4 — отрицательные сценарии и связанные приготовления

«Может быть съездим», мечта, неподтверждённое предложение и рассказ о прошлогодней
поездке не создают новый commitment. Старый факт сам по себе также не создаёт план.

Явно установленные свадьба, встреча по месту проведения и приглашение могут иметь
отдельные IDs/dependencies. Не создаётся обязательный checklist. Наступление даты
не устанавливает брак, приглашение не устанавливает присутствие гостя.

## Проекция и ограничения проверки

`GET /api/saves/{id}/calendar?start_date=2026-10-01&end_date=2026-10-31`:
`scheduled.items` содержит source_id, участников, тип, статус, outcome, window,
interval_state. Week/month/year — тот же range API; максимум 400 дней/500 items,
truncated явно сообщает об усечении. Чтение не меняет revision, время или историю.

CI использует детерминированные ответы провайдера. Семантическое различение
«договорились»/«может быть» выполняет существующая Extraction, а не regex. Живую
модель проверяйте отдельно по последовательностям выше; платные вызовы не нужны CI.

## T5 — QA-01: ordinary turn cannot skip a temporal boundary (#106)

Reset `commitments` using the isolated database command above. Use controlled
provider responses (automated: `tests/test_temporal_guard.py`); live DeepSeek is
not required and does not establish the frequency of the model error.

1. Start with a one-minute scene: `world_time=5563`, Friday trip boundary `6840`.
2. Input `Рассматриваю карту.`; supply narrative `Прошла неделя спокойной работы.`
   and `final_scene.elapsed_minutes=10080`, without `compression`.
   Before the fix this committed `15643`. Now the job is rejected with
   `ordinary_temporal_boundary`; snapshot, History head and accepted variants
   remain unchanged. The rejected prose must not become an accepted turn.
3. Repeat with `compression=null`, `{}`, a string, or a supported compression
   claim. None may bypass the boundary. No extraction-only retry silently
   changes elapsed time beneath the same prose.
4. Reload, make a short ordinary turn, then attempt the invalid jump via
   regenerate. The accepted variant remains selected. Generate a valid variant,
   select the original, rollback, and make another ordinary turn: each restores
   its own canonical time and History lineage.
5. Reaching exactly `6840` is allowed; advancing past a future relevant boundary
   is not. Once due/overdue, advancement requires an accepted resolution,
   cancellation, reschedule or interval transition moving its boundary forward.
   Zero-minute interaction remains possible; time alone never fulfills a plan.
6. An unresolved external response forbids advancement even without compression
   metadata. An explicitly linked, accepted response with current player evidence
   unlocks time; unrelated input does not answer every pending question.
7. Explicit Time Skip retains its Runtime-planned target and interruption;
   background and LTA retain their own clock ownership. Metadata from Extraction
   cannot opt an ordinary turn into those modes.

Shared QA-03 contract: `commitment_ready(state, event)` is a read-only predicate
used by ordinary/compression boundaries, Time Skip and LTA. The event must be
pending and each direct prerequisite resolved with no blocked/missed/cancelled
outcome. No automatic rescheduling or completion occurs. Legacy resolved
prerequisites without an outcome remain supported. This PR only shares this
existing LTA criterion; further QA-03 scenarios remain in #108.

## T6 — QA-03: prerequisite readiness after rescheduling (#108)

Reset `commitments` in the isolated database using the command above. Automated
coverage: `tests/test_commitment_readiness.py` uses real Repository, engine jobs,
Resolver and SQLite persistence with controlled provider responses; no paid calls.

1. Start with one minute: `world_time=5563`. Explicitly reschedule
   `qa_friday_trip` with `assertion=rescheduled` and
   `temporal={day_offset:6,time:"18:00"}`, current evidence and player evidence.
   Use zero elapsed minutes for the reproducible setup. The same canonical ID
   now has boundary `14040`; `qa_sunday_return` stays pending at `9720`, dependent
   on the trip. Do not move the return or invent a completed departure.
2. Request a five-day Time Skip (`7200` minutes). Expected: `12763`, no
   interruption by `qa_sunday_return`. Both plans keep their IDs, dates, statuses
   and evidence. Independent NPC background attempts may update their existing
   `last_attempt_minute` metadata, without inventing outcomes.
3. Reload, regenerate the skip, select its original variant, then rollback.
   Each restores its own time and snapshot; rollback returns to `5563`. Make two
   short ordinary turns with reload between them to exercise the new branch.
4. After rollback, submit a rejected ordinary jump across the rescheduled trip,
   including a proposed cancellation. The entire operation must leave snapshot,
   History and accepted turns unchanged, including after reload.
5. On separate resets, establish `blocked`, `cancelled`, or `occurred` for the
   parent through accepted current evidence. Pending/blocked never unlock the
   dependent; cancellation uses the existing dependency-cancellation lifecycle.
   Only accepted fulfillment makes the pending return actionable. The five-day
   skip then stops at `9720`; reaching that date still does not resolve the return.
   Rollback of the outcome restores the pending prerequisite and readiness.
6. From the rescheduled setup, a two-week LTA with `max_llm_calls=0` stops at the
   parent at `14040`, never the unready return at `9720`. Reload/regenerate and
   rollback preserve the same boundaries. Compression shares the same predicate
   (near-boundary status matrix: `test_shared_readiness_for_skip_compression_and_lta`).

The root-cause correction landed with QA-01 / PR #112: the read-only
`commitment_ready` from `runtime_v3/commitments.py` is already consumed by Time
Skip, LTA and ordinary/compression boundaries. #108 adds integration coverage,
not a competing policy or a new persisted contract. Direct prerequisites must be
resolved with no failed/blocked/cancelled outcome; legacy resolved records without
an outcome retain compatibility. UI remains a projection; no new actor knowledge
or player decisions are inferred from the clock.

Before/after reproduction: on pre-QA-01 master `442c95b`,
`test_dependency_does_not_interrupt_skip` fails with `9720 != 12763`; on master
containing PR #112 it passes. Controlled responses prove deterministic Runtime
behavior, not the frequency of a live model's mistakes.
