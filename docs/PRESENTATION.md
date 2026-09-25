# Оформление миров

Визуальный слой остаётся поверх Runtime v2. Темы не меняют WorldState, secrecy,
player agency, стоимость и порядок LLM-вызовов.

## Тема мира

В «О мире» / «Мир», а также в настройках, раскройте «Тема мира».
Доступны Graphite, Gothic, Parchment, Noir, Neon и «Автоматически».
Настройка сохраняется сразу, отдельно от кнопки сохранения настроек моделей.
Она общая для всех прохождений выбранного мира и устройств, подключённых к этой БД.
У другого экземпляра сервера своя БД и свои настройки.

Legacy-мир без настройки открывается в Graphite. Выбор Auto один раз определяет
тему по фиксированным жанровым ключевым словам названия/исходного описания и
сохраняет результат. Возврат в Auto после ручного выбора возвращает первоначальную
автотему. Она не меняется во время игры. CSS и дополнительные запросы LLM не генерируются.
Новые миры также начинают с Graphite, пока пользователь не выберет тему или Auto.

SQLite `world_presentation` хранит только presentation-метаданные отдельно от
канонических snapshots. Старые сейвы не переписываются. API:

- `GET /api/worlds/{id}` дополнительно возвращает `presentation`.
- `GET /api/worlds/{id}/presentation` возвращает `{theme_id, mode}`.
- `PUT /api/worlds/{id}/presentation` принимает `{theme_id}` из закрытого enum,
  включая `auto`, и возвращает разрешённую тему.

## Frontend

`ThemeProvider` выставляет `data-theme` на `document.documentElement`: Radix
portals и Sonner получают те же токены, что и основное приложение. Временные swatches
локально используют те же пять палитр. Неизвестный/отсутствующий theme id безопасно
отображается как Graphite. При смене мира берётся его собственная настройка.

`index.css` только собирает слои:

- `tokens.css`: семантический контракт, шрифты, радиусы, тени, скорости;
- `themes.css`: пять палитр, без компонентных переопределений;
- `base.css`, `shell.css`, `ui.css`: основа, навигация и общие controls;
- `game.css`, `inspector.css`, `diagnostics.css`, `workshop.css`: экраны;
- `mobile.css`: responsive, sheets и safe-area;
- `motion.css`: CSS-анимации Radix/disclosure/loading и reduced motion.

`motion.ts` содержит Framer Motion primitives и стандартные длительности
140/240/480 ms. `MotionConfig reducedMotion="user"` и `useMotionPreset` заменяют
translate/scale/stagger простым fade. Существующая история не анимируется после
refresh; streaming chunks не запускают layout-анимацию всего журнала.

`SectionTabs` переиспользуется Inspector, WorldCamera, Workshop и Diagnostics.
Клавиши Left/Right/Home/End перемещают выбор и focus. Diagnostics использует
связанные tab/tablist/tabpanel, остальные группы сохраняют button navigation.
Dialogs сохраняют Radix focus trap, Escape и возврат фокуса.

## Проверка

`npm run build`, `python -m pytest -q`, `npm run test:e2e`.
Новые browser tests проверяют пять тем, persistence между browser contexts, старые
миры, auto, portal inheritance, действия/POV/наблюдение, reduced motion и длинный
контент на 1920×1080, 1366×768, 360×800, 430×932. Скриншоты game/inspector/diagnostics
попадают в Playwright test-results; они дополняют функциональные assertions.
