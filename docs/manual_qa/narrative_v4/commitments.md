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
