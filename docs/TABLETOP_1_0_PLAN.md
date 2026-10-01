# Tabletop RPG 1.0: последовательные PR

База: PR #24, `8b6fc85`. Цель — одиночная кампания с обязательным AI-ведущим,
развитием 1–20, магией и динамическим миром. Это общий план; готовность одного
этапа не означает готовность версии 1.0.

| Этап | Ветка | Содержание | Статус |
|---|---|---|---|
| A | codex/tabletop-dm-protocol | DM protocol, typed commands, pending choices, services | Реализован; 496 backend / 6 tabletop E2E / build |
| B | codex/tabletop-character-creator | Creator, point buy, live sheet, species/classes/backgrounds/skills, roleplay generation, feature catalog | Реализован; 550 backend / 8 tabletop E2E / build |
| C | — | Features/resources, actions, conditions, advantage, reactions, GameAI, combat HUD | Ожидает |
| D | — | Spell catalog/slots, attacks/saves/AoE/concentration, spell UI | Ожидает |
| E | — | XP/milestones, levels 1–20, subclasses/ASI/feats, level-up UI | Ожидает |
| F | — | Campaign/world generation, travel, factions/quests/secrets, evolving world | Ожидает |
| G | — | Final desktop/mobile UX, sheets, spellbook, journal/map/party, DM settings | Ожидает |

Каждый следующий PR основан на предыдущем. Merge/deploy отдельны от реализации.
Нельзя вводить generic state patches, доверять LLM RNG/HP/damage/resources, repair
canonical state, обходить compiler или ломать старые сохранения.

## A: протокол и границы

- `commands.py`: discriminated union; посторонние поля отклоняются. Старый Python
  `Command(...)` — только фабрика, возвращающая конкретную модель, а не мешок optional fields.
- Runtime координирует Exploration/Dialogue/Check/Inventory/Encounter/Rest/Character/
  Choice services. ContentService владеет authoring expansion. Spell/Progression
  services появятся вместе с реализацией D/E, без пустых production-заглушек.
- DM интерпретирует ввод в typed command. `check/save` создаёт настоящий PendingRoll.
  `request_choice` создаёт сохраняемый PendingChoice с 2–6 typed action/target options.
  `resolve_choice` принимает ID, проверяет контроллер и заново проверяет выбранное
  действие по текущему состоянию. Команда не уходит в публичную проекцию вариантов.
- Пока есть pending roll/choice/reaction/initiative, `mechanical_resolution_complete`
  ложно и result narration вообще не вызывается. UI показывает механическую карточку
  и блокирует composer. Бросок завершает механику до narration; цепочка attack→damage
  не объявляет итог раньше времени.
- NarrationProjection содержит публичные сведения, подтверждённые события и roleplay
  героя. DMProjection отдельно добавляет релевантные скрытые сведения. Контекст включает
  последние шесть записей истории с лимитом 20 событий, а не весь GameState.
- Prompt запрещает создавать/требовать механику в прозе. Консервативный текстовый guard
  отклоняет явные инструкции бросков, DC/HP/урона/ресурсов/кнопок, пишет diagnostic usage,
  не запускает repair и не меняет состояние. Это дополнительный детектор известных
  формулировок, не доказательство понимания произвольного естественного языка.
- Обычные HTTP start/action/roll требуют конфигурацию AI-DM. Серверный `TABLETOP_DEBUG=1`
  разрешает автономные механические тесты; клиент не может включить его запросом.
  Пользовательского LLM on/off больше нет. Ошибка narration сохраняет уже подтверждённую
  механику и не открывает повторный бросок.
- Новые поля snapshot имеют безопасные defaults; v1→v2 миграция и старые v2 snapshots
  сохраняются. CAS/idempotency/rollback/replay используют те же атомарные операции.

Проверки A: invalid command payloads; pending/guard regressions; choice ownership,
unknown option, duplicate request, restart/replay/rollback; roleplay context без бонусов;
production/debug boundary; desktop/mobile freeform check→roll и choice→check→roll.
LLM stream в автоматических тестах подменён; реальная модель здесь не проверена.

## Итоговая сквозная проверка после G

Generate → point buy → roleplay generation → freeform check/manual roll → dialogue/
social check → quest/travel → initiative/combat/feature/damage/healing/loot/rest →
spells → quest reward/progression/level-up → dynamic expansion → save/restart/continue.
На каждом этапе тестировать невалидные цели, ресурсные ограничения, stale revisions,
повтор запроса, скрытые данные и незавершённую механику, а не только happy path.

## B: создание персонажа и фундамент правил

- Новый `d20-fantasy-v1` — собственный набор D20, шесть основных классов и видов,
  семь происхождений, 18 навыков. Старый `d20-basic-v2` остаётся для сохранений.
- Creator: 11 шагов, карточки с реальными эффектами, стандартный массив и point buy
  с серверной проверкой стоимости, диапазона и бюджета. Live sheet рассчитывается
  тем же RulesEngine, что и канонический герой; preview ничего не сохраняет.
- Каталог FeatureDefinition/FeatureEffect применяет пассивные эффекты вида, класса
  и выбранного стиля; владение оружием влияет на proficiency, броня проверяется.
- AI-портрет и отдельные roleplay-поля — предложения с принятием/отклонением/повтором.
  Строгая схема не допускает механических полей; контекст не содержит секретов мира.
- Активные классовые способности, магия и развитие относятся к следующим C–E.
  Это готовность этапа B, а не готовность всей версии 1.0.
- Проверки: 36 сочетаний классов/видов, эффекты, стоимость характеристик, совместимость,
  preview/compiler equality, roleplay boundary, desktop/mobile AI portrait→point buy→start.
