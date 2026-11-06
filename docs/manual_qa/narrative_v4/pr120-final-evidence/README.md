# PR #120 — реальные экраны и переходы

[Поэлементная приёмка R01–R11 / T01–T26 / G1–G7](../current-game-ui.md#pr120-final-acceptance). Все изображения — Chromium captures, не макеты.

## Сопоставимые before/after

Before: нетронутый HEAD `3bc9e4a970a51d2585770bf33bfb782b8e813472`. After: текущая доработка. Для каждой пары совпадают fixture, skin и viewport: desktop 1440×1000 DPR 1, mobile 360×800 DPR 2.625 с touch emulation. `family-seed` для месяца/года/родословной; `phone-seed?unread=true` для входящего звонка, контактов и чата. В чате одинаковый неотправленный текст; входящий текст прочитан при открытии беседы. В старой версии contacts/call объединялись в одном экране — одинаковые before captures этой комбинации намеренны.

| Экран | Desktop before → after | Mobile before → after |
| --- | --- | --- |
| Месяц, graphite | [до](desktop/calendar-graphite-before.png) → [после](desktop/calendar-graphite-after.png) | [до](mobile/calendar-graphite-before.png) → [после](mobile/calendar-graphite-after.png) |
| Год, graphite | [до](desktop/year-graphite-before.png) → [после](desktop/year-graphite-after.png) | [до](mobile/year-graphite-before.png) → [после](mobile/year-graphite-after.png) |
| Родословная, graphite | [до](desktop/family-graphite-before.png) → [после](desktop/family-graphite-after.png) | [до](mobile/family-graphite-before.png) → [после](mobile/family-graphite-after.png) |
| Входящий, graphite | [до](desktop/phone-incoming-graphite-before.png) → [после](desktop/phone-incoming-graphite-after.png) | [до](mobile/phone-incoming-graphite-before.png) → [после](mobile/phone-incoming-graphite-after.png) |
| Контакты, graphite | [до](desktop/phone-contacts-graphite-before.png) → [после](desktop/phone-contacts-graphite-after.png) | [до](mobile/phone-contacts-graphite-before.png) → [после](mobile/phone-contacts-graphite-after.png) |
| Чат, graphite | [до](desktop/phone-chat-graphite-before.png) → [после](desktop/phone-chat-graphite-after.png) | [до](mobile/phone-chat-graphite-before.png) → [после](mobile/phone-chat-graphite-after.png) |
| Месяц, parchment | [до](desktop/calendar-parchment-before.png) → [после](desktop/calendar-parchment-after.png) | [до](mobile/calendar-parchment-before.png) → [после](mobile/calendar-parchment-after.png) |
| Год, parchment | [до](desktop/year-parchment-before.png) → [после](desktop/year-parchment-after.png) | [до](mobile/year-parchment-before.png) → [после](mobile/year-parchment-after.png) |
| Родословная, parchment | [до](desktop/family-parchment-before.png) → [после](desktop/family-parchment-after.png) | [до](mobile/family-parchment-before.png) → [после](mobile/family-parchment-after.png) |
| Входящий, parchment | [до](desktop/phone-incoming-parchment-before.png) → [после](desktop/phone-incoming-parchment-after.png) | [до](mobile/phone-incoming-parchment-before.png) → [после](mobile/phone-incoming-parchment-after.png) |
| Контакты, parchment | [до](desktop/phone-contacts-parchment-before.png) → [после](desktop/phone-contacts-parchment-after.png) | [до](mobile/phone-contacts-parchment-before.png) → [после](mobile/phone-contacts-parchment-after.png) |
| Чат, parchment | [до](desktop/phone-chat-parchment-before.png) → [после](desktop/phone-chat-parchment-after.png) | [до](mobile/phone-chat-parchment-before.png) → [после](mobile/phone-chat-parchment-after.png) |

## Дополнительные сценарии

Эти насыщенные fixtures добавлены в существующий #78 loader, поэтому не смешаны с идентичными before/after. Calendar/phone mobile — 360 CSS px; отдельная семья — 393×852; dense family — Pixel 7 viewport 412×839; keyboard simulation — 393×500, tablet — 820 px и увеличенный текст.

| Сценарий | Desktop | Mobile |
| --- | --- | --- |
| Календарь: несколько событий, Graphite | [снимок](desktop/calendar-events-graphite.png) | [снимок](mobile/calendar-events-graphite.png) |
| Календарь: несколько событий, Parchment | [снимок](desktop/calendar-events-parchment.png) | [снимок](mobile/calendar-events-parchment.png) |
| Пустой месяц | [снимок](desktop/calendar-empty-parchment.png) | [снимок](mobile/calendar-empty-parchment.png) |
| Годовой обзор | [снимок](desktop/calendar-year-parchment.png) | [снимок](mobile/calendar-year-parchment.png) |
| Custom CalendarProfile | [снимок](desktop/custom-year-after.png) | [снимок](mobile/custom-year-after.png) |
| Другая семья, Graphite | [снимок](desktop/family-other-graphite.png) | [снимок](mobile/family-other-graphite.png) |
| Другая семья, Parchment | [снимок](desktop/family-other-parchment.png) | [снимок](mobile/family-other-parchment.png) |
| Нет известных родственников | [снимок](desktop/family-empty-parchment.png) | [снимок](mobile/family-empty-parchment.png) |
| Ограниченный большой граф | [снимок](desktop/family-dense-after.png) | [снимок](mobile/family-dense-after.png) |
| Контекстный вход из пустого досье | [снимок](desktop/empty-card-context-after.png) | [снимок](mobile/empty-card-context-after.png) |
| Телефон у края viewport | [снимок](desktop/phone-resting-after.png) | [снимок](mobile/phone-resting-after.png) |
| Отдельные детали контакта | [снимок](desktop/contact-after.png) | [снимок](mobile/contact-after.png) |
| Исходящий: соединение | [снимок](desktop/call-active-after.png) | [снимок](mobile/call-active-after.png) |
| Исходящий: отказ | [снимок](desktop/call-decline-after.png) | [снимок](mobile/call-decline-after.png) |
| Исходящий: нет ответа | [снимок](desktop/call-silent-after.png) | [снимок](mobile/call-silent-after.png) |
| Реальный read → reply через job | [снимок](desktop/chat-reply-after.png) | [снимок](mobile/chat-reply-after.png) |
| 393×500, composer и send | [снимок](desktop/phone-keyboard-after.png) | [снимок](mobile/phone-keyboard-after.png) |
| Tablet, текст 125% | [снимок](desktop/tablet-large-text-after.png) | [снимок](mobile/tablet-large-text-after.png) |

## Записи взаимодействий

| Переходы | Desktop | Mobile |
| --- | --- | --- |
| Контакт → дозвон → реплика/ответ → завершение → send/read/reply → reload | [WebM](desktop/outgoing-call-and-reply.webm) | [WebM](mobile/outgoing-call-and-reply.webm) |
| Открытие/сворачивание, две темы, входящий/физическое действие/answer, каналы и draft | [WebM](desktop/incoming-call-and-draft.webm) | [WebM](mobile/incoming-call-and-draft.webm) |
| События → пустой месяц → назад → год | [WebM](desktop/calendar-navigation.webm) | [WebM](mobile/calendar-navigation.webm) |
| Другая семья → доступный список → пустая семья → возврат | [WebM](desktop/family-selection.webm) | [WebM](mobile/family-selection.webm) |
| Календарь/год → Narrative с draft → семья | [WebM](desktop/workspace-return.webm) | [WebM](mobile/workspace-return.webm) |
| Дата сцены → календарь → пустое досье → общая родословная | [WebM](desktop/contextual-entries.webm) | [WebM](mobile/contextual-entries.webm) |

В коротких записях автоматизация выполняет действия быстрее обычного пользователя. Модель детерминирована для воспроизводимости; решения проходят реальные APIs, jobs и Runtime. Никакого заранее готового исходящего answer/reply в UI fixture.

## Наблюдения при визуальной проверке

- Сетка месяца занимает рабочую область, детали справа/ниже. Длинные названия и участники не сливаются; пустой день не придумывает события. Год прокручивается целиком, содержит разрешённые маркеры.
- В отдельной семье видны развод, партнёрство, усыновление и подозреваемая опека; партнёрская дуга проходит над карточками. На узком экране toolbar компактен; fit/zoom и доступный список остаются достижимы.
- В чате сообщения прокручиваются отдельно от composer. На 393×500 send больше не скрывается нижней навигацией. После read высота текста не сбивает позицию. Разговор переносится в основной Narrative по явному действию без потери текста.
- Dense graph: [desktop metrics](desktop/graph-metrics.json), [mobile metrics](mobile/graph-metrics.json), измерение от выбора корня до 80 DOM nodes. Это время браузерного теста, а не GPU/fps benchmark. Для 100+ родственников используются depth/recenter, не одновременная читаемость всех узлов.

Физический Android, настоящая OS keyboard/Back, live платный LLM и инструментальные GPU timing не проверялись. Эмуляция viewport/touch и уменьшенной высоты указана отдельно; полный E2E репозитория не объявляется зелёным.

## Логи проверок

- [Backend: 2123 passed](backend-tests.txt)
- [Применимый UI acceptance: 74 passed](ui-acceptance.txt)
- [Контекстные входы и повтор smoke: 12 passed](context-tests.txt)
- [Финальные телефонные сценарии/снимки: 12 passed](phone-tests.txt)
- [TypeScript + Vite build](build.txt)

Прогоны пересекаются; результаты не суммируются в уникальное количество тестов.
