# Calendar v2 — #37 / #65

Исходник: base v2, обычный JSON import/confirm. Сценарии не требуют ручной правки БД.
Команда загрузки (новое изолированное прохождение при каждом запуске):

```bash
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --db /tmp/narrative-qa.sqlite3 --checkpoint calendar-evening
```

## C1. Вечер, полночь, будущая поездка

- Checkpoint `calendar-evening`: Day 1, четверг 2026-10-08, 20:42;
  world_time=5562, у камеры Кирилл/Вера/Тимур. Вера: birth_date=1993-10-09.
  На 9 октября настроен «День моста». `qa_friday_trip`: Кирилл/Елена,
  pending, due_minute=0, condition «В пятницу вечером».
- Начните игру, выполните обычный ход о карте. Проверьте диагностику обоих LLM
  запросов: одинаковый current_time (до перехода), evening, правильная дата/weekday.
  Choices не должны предлагать ожидать наступления сегодняшнего вечера.
- Посмотрите «Ближайшие даты»: день рождения и праздник существуют; партия,
  подарки, выходной, приезд Елены не считаются состоявшимися.
- Откройте Time Skip, выберите «До полуночи». Предпросмотр — следующий день,
  пятница, 00:00. Закройте: время/revision/история не должны измениться.
- Выполните пропуск. После сохранения время соответствует actual_target,
  возраст Веры вырос с 32 до 33. Последующий обычный ход получает новую дату.
- В четверг поездка future (due_minute projection=6840), Елена не становится
  ACTIVE_REFERENCED/ACTIVE_NARRATIVE только из-за поездки. Достижение срока
  не переводит pending в resolved без подтверждённого события.
- Reload сохраняет дату/возраст/план. Regenerate использует исходный recorded
  context; выбор старого варианта и rollback возвращают прежний календарный
  anchor/world_time. День рождения не добавляет canonical Event автоматически.

## C2. Високосная дата

Загрузите `--checkpoint calendar-leap`: 2024-02-28 23:59, Day 1;
birth_date Веры=1992-02-29, age=31, будущих поездок нет.
Выполните Time Skip на одну минуту: 2024-02-29 00:00, Day 2, age=32.
Ещё сутки: 2024-03-01. Reload/rollback должны сохранять/восстанавливать точную
дату и возраст. Для 29 февраля в невисокосном году birthday не создаётся;
возраст увеличивается 1 марта. Неизвестные birthdays остальных остаются null.

## C3. Просмотр диапазона без хода

Запросите `GET /api/saves/{id}/calendar?start_date=2027-10-01&end_date=2027-10-31`.
Проверьте days (weekday, month_length, month_start/end, year_start, day_number),
configured observances и birthdays. Чтение не изменяет world_time, save revision,
историю, Knowledge или участников. Повторный запрос возвращает тот же результат;
диапазон больше 400 дней отклоняется. Наличие события календаря — не факт участия.

## C4. Старый/неизвестный календарь

Импортируйте fixture без world_clock.calendar и без birth_date (автотест делает
это через production import/confirm). Date остаётся null; Day N/weekday/HH:MM
работают. Никакая дата не выводится из названия города, возраста или wall clock.
Обычный ход → save → reload → следующий ход обязаны работать.

## Время Event в History (#220)

| Источник | Что означает `minute` |
|---|---|
| Обычная сцена | Абсолютная минута события между началом и концом хода включительно. При `elapsed_minutes=0` границы совпадают. |
| Рассказ о прошлом или воспоминание | Event фиксирует текущий разговор, чтение или воспоминание. Содержание прошлого относится к Fact/Knowledge по обычным правилам восприятия. Авторские события предыстории и импортированные записи сохраняют свои даты. |
| Time Skip | Границы задают начало пропуска и фактическая остановка `actual_target`. Последующая фоновая сцена обрабатывается при фиксированных часах. |
| Long-term Advance | Группа обрабатывается в выбранную Runtime минуту кандидата. Если Extraction опустил минуту, LTA передаёт эту известную точку. |

Для обычного Event неизвестную точную минуту Extraction опускает. В этой записи History
остается `recorded_minute` конца хода. Timeline использует его для сортировки.
При известной минуте Runtime проецирует `calendar_date` по календарю мира на момент события.
`order` различает последовательность событий, `source_sequence` и `source_record_id`
относят их к исходному ходу. Локальные ID Extraction разрешаются в канонические Event ID.

Replay Campaign/014: при начале 2105840 и длительности 2 значение 2 вызывает
`event_minute_invalid` с путём `events[0].minute`. Обычный job допускает один
Extraction repair. Повторная ошибка сохраняет диагностику и оставляет прежнюю
вершину History. Проверки SQLite и вариантов — `tests/test_event_chronology.py`.

## C5. Time Skip и фоновая активность NPC

- Загрузите `calendar-evening`, начните игру и запишите текущее время.
  Выполните Time Skip на четыре часа: фоновая сверка карты Олегом должна
  обрабатываться при времени, установленном Time Skip. Итоговое время равно
  `actual_target`, без дополнительной длительности фонового ответа.
- В диагностике проверьте этапы `world_simulation` и `world_simulation_delta`.
  Если Extraction предлагает допустимое ненулевое `elapsed_minutes`, Runtime
  игнорирует его с диагностикой `background_elapsed_ignored` (предложенная
  длительность и применённый ноль), без дополнительного repair-вызова.
  Временные метки фоновых событий и истории соответствуют итоговому времени.
- Изменения NPC сохраняются; фоновый ответ не изменяет состояние Кирилла
  и не выдаёт ему Knowledge. Недопустимые изменения по-прежнему проходят
  validation/repair и при неудаче отклоняются.
- Reload сохраняет точное время. Regenerate и выбор исходного варианта
  не добавляют часы; rollback возвращает время до пропуска. Повторный
  пропуск из этого состояния даёт тот же целевой момент.
- Обычный Narrative-ход продолжает увеличивать время на свою длительность.
  Ответы фоновой LLM с длительностью 0 и 15 минут воспроизводятся
  детерминированно в `tests/test_background_time.py` на этом же QA-мире;
  случайный живой ответ LLM не гарантирует появления ненулевой длительности.

Автотесты: `tests/test_calendar_v2.py`, `tests/test_narrative_test_world.py`,
`tests/test_background_time.py`;
UI desktop/mobile: `frontend/e2e/calendar.spec.ts`.

## C3. Regional presets and optional review (#44, 2026-10-26)

Reset the existing checkpoint into a fresh isolated save (does not overwrite saves):

```bash
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --db /tmp/narrative-calendar-policy.sqlite3 --checkpoint calendar-evening
```

Follow [the calendar/start-policy checklist](calendar-start-policy-v2.md). Import the
existing fixture's export as an author draft, apply RU/north, then switch only
holidays to US. The fixture's own Bridge Day, Vera's DOB, calendar anchor and pending
Friday trip remain unchanged. Preview remains read-only. Confirm, ordinary turn,
reload and rollback preserve the regional profile and author overrides. Automated
`test_existing_78_calendar_checkpoint_preserves_presets_through_turn_reload_rollback`
uses the same `calendar-evening` source and real repository/engine paths.
