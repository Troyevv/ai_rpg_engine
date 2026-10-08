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

Автотесты: `tests/test_calendar_v2.py`, `tests/test_narrative_test_world.py`;
UI desktop/mobile: `frontend/e2e/calendar.spec.ts`.
