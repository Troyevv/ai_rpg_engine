> The strict optional-projection behavior described below is superseded by the [P0 recovery report](../issue133-recovery/README.md). This document retains the earlier run evidence.

# PR #133 — единый мир телефонной и физической сцен

## Причина и исправление

Ранее committed_route выводил краткий Event.text, а не художественное продолжение;
physical_choice_source инвалидировал старые варианты, но текущий звонок не предоставлял
физических. Extraction не имел контракта фактического отбоя. Проверка голосового
согласия использовала текущий ввод, теряя предложение из предыдущего хода.

Теперь обычный Narrative/Extraction ход создаёт проверенные physical_projections
для принятых Events, отдельные physical/call choices, evidence-bound call lifecycle
и голосовые scheduled_event_changes с исходными History source IDs. Resolver
проверяет ссылки, точные источники, порядок, временные границы, отсутствие пересечений,
согласие участников и agency. Ошибка → один существующий extraction repair; удалить
кандидата из repair ради успешного commit нельзя. Все последствия фиксируются атомарно.
Проекции и открытие журнала не продвигают время. Второго Runtime/History/календаря нет.

CallScene использует прежний renderer/streaming/scroll. Основная лента получает
только подтверждённые физические фрагменты. Отбой NPC снимает блокировку ввода;
явное чтение завершённого разговора раскрывает журнал даже после сохранённого collapse.
Свободный ввод и ручной отбой сохранены.

## Видимая последовательность

Это screenshots настоящего React UI с API/SQLite/jobs/Resolver и контролируемым
провайдером, не live LLM. JSON рядом — фактические API-проекции снимков.
`before` означает сцену **до звонка в исправленной версии**, не изображение старого дефекта.

| Этап | Desktop graphite | Mobile parchment (393 px) |
|---|---|---|
| До звонка: Виктория пока ждёт | [PNG](desktop-graphite-before.png) | [PNG](mobile-parchment-before.png) |
| Телефонный разговор | [PNG](desktop-graphite-during-call.png) | [PNG](mobile-parchment-during-call.png) |
| Звонок активен, стук уже в основной истории | [PNG](desktop-graphite-during-physical.png) | [PNG](mobile-parchment-during-physical.png) |
| После отбоя: требование и актуальные варианты | [PNG](desktop-graphite-after.png) | [PNG](mobile-parchment-after.png) |

Также сохранены desktop parchment и mobile graphite (360 px), те же четыре этапа.
Порядок: 09:00 исходная сцена → соединение 09:01 → стук 09:03 → требование 09:05 →
отбой 09:07. Встреча на 10:01: исходное предложение +60 минут, а не отбой +60.
Старое ожидание остаётся исторической карточкой; новые события последовательно
продолжают её. Реплики Кати не скопированы в физическую историю.

## Регрессии

- `python -m pytest tests/test_call_continuity.py tests/test_phone122.py -q`
  **32 passed** плюс отдельный passed API case NPC-first proposal → player assent → reschedule → cancel; проверяет настоящий API/job pipeline, календарь, отбой, reload, следующий Narrative
  context, no-event, прощание без отбоя, неподтверждённое предложение, ручной отбой,
  failure/Retry, варианты, rollback/новую ветку, чужие источники, agency и legacy cards.
- `python -m pytest tests/test_narrative_test_world.py tests/test_call_continuity.py -q`:
  22 passed на этапе до последнего дополнительного отрицательного case.
- `npm test`: 34 passed. `npm run build`: passed (существующее предупреждение о chunk size).
- `npx playwright test call-continuity --reporter=line`: 4 passed, desktop/mobile,
  graphite/parchment, reload → реальный журнал → следующий физический ход.
- Полный backend: 2216 passed, один Hypothesis deadline failure (см. ниже);
  прогон начат до последних дополнительных tests/guards. CI проверяет конечный commit.
- Существующие browser phone regressions: первый запуск 8 passed, 26 не стартовали
  из-за отсутствующего Playwright ffmpeg. Исправлена локальная среда, тесты не изменены.
  Повторный прогон: **33 passed, 1 failed** (mobile group membership: панель телефона
  не осталась открытой после смены героя). Изолированный повтор того же теста:
  **1 passed**. Причина нестабильности окончательно не установлена; нужны CI и
  повторная интеграционная проверка. Результат всего прогона не объявляется зелёным.

Первые browser запуски выявили неверные test locators и реальное сохранение collapsed
состояния при открытии журнала; исправлены, успешный прогон выполнен без retries/skips.
При параллельной локальной нагрузке property-test possessions превысил Hypothesis
200ms deadline (365ms, затем 31ms); тест/лимит не ослаблялись.
После завершения параллельной нагрузки `python -m pytest tests/test_possessions.py -q`: **27 passed**.

## Совместимость и границы

Новые поля ScheduledEvent опциональны, SQL-миграций нет. Исторические snapshots не
переписываются. Старые явно физические Event cards остаются читаемыми; отсутствующие
художественные span/choices не придумываются задним числом. Смена actor не раскрывает
чужие телефонные реплики; физическая проекция ограничена свидетелями.

Semantic classification остаётся обязанностью Extraction: детерминированные проверки
доказывают происхождение и целостность, но не понимание произвольной фразы моделью.
Live DeepSeek и реальная пользовательская приёмка не подтверждены. Оплачиваемые вызовы
не выполнялись; фиктивные usage/cost не заявляются. Issue #122 не закрывается и PR
не мёрджится. Для ручной проверки использовать существующий #78 checkpoint
`phone-office` и [сценарий](../phone.md#pr-133--единый-мир-во-время-звонка).


## Доставка

После явного разрешения пользователя изменения опубликованы в существующей ветке
PR #133 через подключённый GitHub API. Прямой git push недоступен из-за отсутствия
credentials. Дерево файлов коммита `f429dd3a3ed8a204f1e7db80559bc71966377177`
точно совпадает с разрешённым локальным `a4cda3a`:
`234cd6425b262031a8357361c0c184448b003fc1`.

Новый PR не создавался, force-push не применялся. Запущены Verify RPG Engine и
Streaming continuity evidence. Актуальные результаты CI приведены в описании
[PR #133](https://github.com/Troyevv/ai_rpg_engine/pull/133); этот отчёт отдельно
фиксирует локальные результаты и ограничения, не заменяя проверку нового HEAD.
