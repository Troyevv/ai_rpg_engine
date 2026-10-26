# PR #123 — color and typography finishing pass

Baseline and checked PR HEAD: `72a5bf3f184e1134792acd0b964de92ab558f1b1`. No intervening commits were present. The previous acceptance of a darker, flatter Graphite as an intentional skin difference was incorrect and is superseded by this report.

Reference: unchanged approved Issue #86 HTML, SHA-256 `538a864e8ef320c8d10740bc832f25859f30d4c9357870d976a6f48f043b7ab0`. Browser-rendered production app uses real `ui-inspector` saves, FastAPI/SQLite and the existing deterministic provider. All captures use identical CSS/pixel sizes: 1440/768/393/360 × 900, DPR 1, Graphite/Parchment, expanded/compact. Phone width preference is set at 768 before returning to its target viewport. Reference demo bar is retained; it accounts for a 32 px vertical offset. Full-resolution reference and baseline images remain in [the original evidence folder](../issue86-evidence/README.md).

## Color roles

| Role | Approved Graphite | New scoped Graphite |
| --- | --- | --- |
| Workspace | #1c1e21 | #1c1e21 |
| Navigation | #17191c | #17191c |
| Card | #202226 | #202226 |
| Hero / raised surface | #25272b | #25272b |
| Hover | #303237 | #303237 |
| Border | #3a3c40 | #3a3c40 |
| Primary prose | #eeede9 | #eeede9 |
| Secondary labels | #aaadb2 | #aaadb2 |
| Accent / selected fill | #dfb979 / #3b3429 | #dfb979 / #3b3429 |

Browser assertions verify computed background, navigation, hero, card, border, prose, secondary text and selected navigation. They also verify the document root palette is unchanged. Semantic tokens are scoped to Inspector, its settings/mobile navigation, and the active desktop sidebar. Game, Phone and Tabletop retain their own skin values. Parchment retains warm paper surfaces and serif identity, with primary prose restored and quieter borders; contrasting skins inherit their existing palettes.

## Corrections

- P1: dark/flat workspace and grey active selection → approved layered surfaces, warm gold selection and primary text.
- P2: conspicuous outlines and muted substantive copy → lower border prominence, brighter narrative/fact prose and warm disclosure links.
- P2: metric colors depended on field order → stable meaning-based blue trust, rose affection/attraction, green respect, purple fear/jealousy and amber irritation. No dimensions or values fabricated.
- P2: repeated short card heading/body → one copy when the heading already contains the complete record; long bodies remain available.
- P2: technical relationship fact titles → localized relationship type and actual character names only for a canonical `fact_id` link or an exact legacy generated relationship string corroborated by an authorized projected relation and its two character IDs. Raw text remains in the source disclosure. Missing links retain original prose; arbitrary narrative is never used to infer relations or change privacy.

Dossier #83 layout/editors and portrait tools remain intact. No Runtime, permission, persistence or Tabletop changes. Different names, record counts, portraits and available weather are real-data differences, not copied demo content. Source mock has no separate real-data title contract; summaries are derived excerpts, not invented narratives.

## Validation

Final result: **passed**. `npm run build --prefix frontend` passed. `npm run test:e2e --prefix frontend -- e2e/inspector86.spec.ts e2e/presentation.spec.ts e2e/runtime-handoff.spec.ts e2e/completion-matrix.spec.ts`: **39 passed, 5 skipped** (four duplicate mobile screenshot matrices and the duplicate computed-palette test). [Build log](logs/build.log), [Playwright log](logs/playwright.log). [Desktop editor/filter recording](editors-desktop.webm), [mobile recording](editors-mobile.webm). Matrix covers all seven sections, both width preferences and both requested skins; existing tests cover keyboard/touch, editor retry, contextual return, public family/birthdays, all skin presets, reduced motion, enlarged text and Start Game → ordinary turn → save/reload → next ordinary turn on desktop/mobile. External paid LLM and physical Android hardware are not exercised.

## Screenshot matrix

| Viewport / skin / section / width | Comparison | Application |
| --- | --- | --- |
| 1440-graphite-Мир-compact | [Reference / before / after](compare-1440-graphite-Мир-compact.jpg) | [Full resolution](after-1440-graphite-Мир-compact.png) |
| 1440-graphite-Мир-expanded | [Reference / before / after](compare-1440-graphite-Мир-expanded.jpg) | [Full resolution](after-1440-graphite-Мир-expanded.png) |
| 1440-graphite-Отношения-compact | [Reference / before / after](compare-1440-graphite-Отношения-compact.jpg) | [Full resolution](after-1440-graphite-Отношения-compact.png) |
| 1440-graphite-Отношения-expanded | [Reference / before / after](compare-1440-graphite-Отношения-expanded.jpg) | [Full resolution](after-1440-graphite-Отношения-expanded.png) |
| 1440-graphite-Память-compact | [Reference / before / after](compare-1440-graphite-Память-compact.jpg) | [Full resolution](after-1440-graphite-Память-compact.png) |
| 1440-graphite-Память-expanded | [Reference / before / after](compare-1440-graphite-Память-expanded.jpg) | [Full resolution](after-1440-graphite-Память-expanded.png) |
| 1440-graphite-Персонажи-compact | [Reference / before / after](compare-1440-graphite-Персонажи-compact.jpg) | [Full resolution](after-1440-graphite-Персонажи-compact.png) |
| 1440-graphite-Персонажи-expanded | [Reference / before / after](compare-1440-graphite-Персонажи-expanded.jpg) | [Full resolution](after-1440-graphite-Персонажи-expanded.png) |
| 1440-graphite-Сцена-compact | [Reference / before / after](compare-1440-graphite-Сцена-compact.jpg) | [Full resolution](after-1440-graphite-Сцена-compact.png) |
| 1440-graphite-Сцена-expanded | [Reference / before / after](compare-1440-graphite-Сцена-expanded.jpg) | [Full resolution](after-1440-graphite-Сцена-expanded.png) |
| 1440-graphite-Сюжет-compact | [Reference / before / after](compare-1440-graphite-Сюжет-compact.jpg) | [Full resolution](after-1440-graphite-Сюжет-compact.png) |
| 1440-graphite-Сюжет-expanded | [Reference / before / after](compare-1440-graphite-Сюжет-expanded.jpg) | [Full resolution](after-1440-graphite-Сюжет-expanded.png) |
| 1440-graphite-Тайны-compact | [Reference / before / after](compare-1440-graphite-Тайны-compact.jpg) | [Full resolution](after-1440-graphite-Тайны-compact.png) |
| 1440-graphite-Тайны-expanded | [Reference / before / after](compare-1440-graphite-Тайны-expanded.jpg) | [Full resolution](after-1440-graphite-Тайны-expanded.png) |
| 1440-parchment-Мир-compact | [Reference / before / after](compare-1440-parchment-Мир-compact.jpg) | [Full resolution](after-1440-parchment-Мир-compact.png) |
| 1440-parchment-Мир-expanded | [Reference / before / after](compare-1440-parchment-Мир-expanded.jpg) | [Full resolution](after-1440-parchment-Мир-expanded.png) |
| 1440-parchment-Отношения-compact | [Reference / before / after](compare-1440-parchment-Отношения-compact.jpg) | [Full resolution](after-1440-parchment-Отношения-compact.png) |
| 1440-parchment-Отношения-expanded | [Reference / before / after](compare-1440-parchment-Отношения-expanded.jpg) | [Full resolution](after-1440-parchment-Отношения-expanded.png) |
| 1440-parchment-Память-compact | [Reference / before / after](compare-1440-parchment-Память-compact.jpg) | [Full resolution](after-1440-parchment-Память-compact.png) |
| 1440-parchment-Память-expanded | [Reference / before / after](compare-1440-parchment-Память-expanded.jpg) | [Full resolution](after-1440-parchment-Память-expanded.png) |
| 1440-parchment-Персонажи-compact | [Reference / before / after](compare-1440-parchment-Персонажи-compact.jpg) | [Full resolution](after-1440-parchment-Персонажи-compact.png) |
| 1440-parchment-Персонажи-expanded | [Reference / before / after](compare-1440-parchment-Персонажи-expanded.jpg) | [Full resolution](after-1440-parchment-Персонажи-expanded.png) |
| 1440-parchment-Сцена-compact | [Reference / before / after](compare-1440-parchment-Сцена-compact.jpg) | [Full resolution](after-1440-parchment-Сцена-compact.png) |
| 1440-parchment-Сцена-expanded | [Reference / before / after](compare-1440-parchment-Сцена-expanded.jpg) | [Full resolution](after-1440-parchment-Сцена-expanded.png) |
| 1440-parchment-Сюжет-compact | [Reference / before / after](compare-1440-parchment-Сюжет-compact.jpg) | [Full resolution](after-1440-parchment-Сюжет-compact.png) |
| 1440-parchment-Сюжет-expanded | [Reference / before / after](compare-1440-parchment-Сюжет-expanded.jpg) | [Full resolution](after-1440-parchment-Сюжет-expanded.png) |
| 1440-parchment-Тайны-compact | [Reference / before / after](compare-1440-parchment-Тайны-compact.jpg) | [Full resolution](after-1440-parchment-Тайны-compact.png) |
| 1440-parchment-Тайны-expanded | [Reference / before / after](compare-1440-parchment-Тайны-expanded.jpg) | [Full resolution](after-1440-parchment-Тайны-expanded.png) |
| 360-graphite-Мир-compact | [Reference / before / after](compare-360-graphite-Мир-compact.jpg) | [Full resolution](after-360-graphite-Мир-compact.png) |
| 360-graphite-Мир-expanded | [Reference / before / after](compare-360-graphite-Мир-expanded.jpg) | [Full resolution](after-360-graphite-Мир-expanded.png) |
| 360-graphite-Отношения-compact | [Reference / before / after](compare-360-graphite-Отношения-compact.jpg) | [Full resolution](after-360-graphite-Отношения-compact.png) |
| 360-graphite-Отношения-expanded | [Reference / before / after](compare-360-graphite-Отношения-expanded.jpg) | [Full resolution](after-360-graphite-Отношения-expanded.png) |
| 360-graphite-Память-compact | [Reference / before / after](compare-360-graphite-Память-compact.jpg) | [Full resolution](after-360-graphite-Память-compact.png) |
| 360-graphite-Память-expanded | [Reference / before / after](compare-360-graphite-Память-expanded.jpg) | [Full resolution](after-360-graphite-Память-expanded.png) |
| 360-graphite-Персонажи-compact | [Reference / before / after](compare-360-graphite-Персонажи-compact.jpg) | [Full resolution](after-360-graphite-Персонажи-compact.png) |
| 360-graphite-Персонажи-expanded | [Reference / before / after](compare-360-graphite-Персонажи-expanded.jpg) | [Full resolution](after-360-graphite-Персонажи-expanded.png) |
| 360-graphite-Сцена-compact | [Reference / before / after](compare-360-graphite-Сцена-compact.jpg) | [Full resolution](after-360-graphite-Сцена-compact.png) |
| 360-graphite-Сцена-expanded | [Reference / before / after](compare-360-graphite-Сцена-expanded.jpg) | [Full resolution](after-360-graphite-Сцена-expanded.png) |
| 360-graphite-Сюжет-compact | [Reference / before / after](compare-360-graphite-Сюжет-compact.jpg) | [Full resolution](after-360-graphite-Сюжет-compact.png) |
| 360-graphite-Сюжет-expanded | [Reference / before / after](compare-360-graphite-Сюжет-expanded.jpg) | [Full resolution](after-360-graphite-Сюжет-expanded.png) |
| 360-graphite-Тайны-compact | [Reference / before / after](compare-360-graphite-Тайны-compact.jpg) | [Full resolution](after-360-graphite-Тайны-compact.png) |
| 360-graphite-Тайны-expanded | [Reference / before / after](compare-360-graphite-Тайны-expanded.jpg) | [Full resolution](after-360-graphite-Тайны-expanded.png) |
| 360-parchment-Мир-compact | [Reference / before / after](compare-360-parchment-Мир-compact.jpg) | [Full resolution](after-360-parchment-Мир-compact.png) |
| 360-parchment-Мир-expanded | [Reference / before / after](compare-360-parchment-Мир-expanded.jpg) | [Full resolution](after-360-parchment-Мир-expanded.png) |
| 360-parchment-Отношения-compact | [Reference / before / after](compare-360-parchment-Отношения-compact.jpg) | [Full resolution](after-360-parchment-Отношения-compact.png) |
| 360-parchment-Отношения-expanded | [Reference / before / after](compare-360-parchment-Отношения-expanded.jpg) | [Full resolution](after-360-parchment-Отношения-expanded.png) |
| 360-parchment-Память-compact | [Reference / before / after](compare-360-parchment-Память-compact.jpg) | [Full resolution](after-360-parchment-Память-compact.png) |
| 360-parchment-Память-expanded | [Reference / before / after](compare-360-parchment-Память-expanded.jpg) | [Full resolution](after-360-parchment-Память-expanded.png) |
| 360-parchment-Персонажи-compact | [Reference / before / after](compare-360-parchment-Персонажи-compact.jpg) | [Full resolution](after-360-parchment-Персонажи-compact.png) |
| 360-parchment-Персонажи-expanded | [Reference / before / after](compare-360-parchment-Персонажи-expanded.jpg) | [Full resolution](after-360-parchment-Персонажи-expanded.png) |
| 360-parchment-Сцена-compact | [Reference / before / after](compare-360-parchment-Сцена-compact.jpg) | [Full resolution](after-360-parchment-Сцена-compact.png) |
| 360-parchment-Сцена-expanded | [Reference / before / after](compare-360-parchment-Сцена-expanded.jpg) | [Full resolution](after-360-parchment-Сцена-expanded.png) |
| 360-parchment-Сюжет-compact | [Reference / before / after](compare-360-parchment-Сюжет-compact.jpg) | [Full resolution](after-360-parchment-Сюжет-compact.png) |
| 360-parchment-Сюжет-expanded | [Reference / before / after](compare-360-parchment-Сюжет-expanded.jpg) | [Full resolution](after-360-parchment-Сюжет-expanded.png) |
| 360-parchment-Тайны-compact | [Reference / before / after](compare-360-parchment-Тайны-compact.jpg) | [Full resolution](after-360-parchment-Тайны-compact.png) |
| 360-parchment-Тайны-expanded | [Reference / before / after](compare-360-parchment-Тайны-expanded.jpg) | [Full resolution](after-360-parchment-Тайны-expanded.png) |
| 393-graphite-Мир-compact | [Reference / before / after](compare-393-graphite-Мир-compact.jpg) | [Full resolution](after-393-graphite-Мир-compact.png) |
| 393-graphite-Мир-expanded | [Reference / before / after](compare-393-graphite-Мир-expanded.jpg) | [Full resolution](after-393-graphite-Мир-expanded.png) |
| 393-graphite-Отношения-compact | [Reference / before / after](compare-393-graphite-Отношения-compact.jpg) | [Full resolution](after-393-graphite-Отношения-compact.png) |
| 393-graphite-Отношения-expanded | [Reference / before / after](compare-393-graphite-Отношения-expanded.jpg) | [Full resolution](after-393-graphite-Отношения-expanded.png) |
| 393-graphite-Память-compact | [Reference / before / after](compare-393-graphite-Память-compact.jpg) | [Full resolution](after-393-graphite-Память-compact.png) |
| 393-graphite-Память-expanded | [Reference / before / after](compare-393-graphite-Память-expanded.jpg) | [Full resolution](after-393-graphite-Память-expanded.png) |
| 393-graphite-Персонажи-compact | [Reference / before / after](compare-393-graphite-Персонажи-compact.jpg) | [Full resolution](after-393-graphite-Персонажи-compact.png) |
| 393-graphite-Персонажи-expanded | [Reference / before / after](compare-393-graphite-Персонажи-expanded.jpg) | [Full resolution](after-393-graphite-Персонажи-expanded.png) |
| 393-graphite-Сцена-compact | [Reference / before / after](compare-393-graphite-Сцена-compact.jpg) | [Full resolution](after-393-graphite-Сцена-compact.png) |
| 393-graphite-Сцена-expanded | [Reference / before / after](compare-393-graphite-Сцена-expanded.jpg) | [Full resolution](after-393-graphite-Сцена-expanded.png) |
| 393-graphite-Сюжет-compact | [Reference / before / after](compare-393-graphite-Сюжет-compact.jpg) | [Full resolution](after-393-graphite-Сюжет-compact.png) |
| 393-graphite-Сюжет-expanded | [Reference / before / after](compare-393-graphite-Сюжет-expanded.jpg) | [Full resolution](after-393-graphite-Сюжет-expanded.png) |
| 393-graphite-Тайны-compact | [Reference / before / after](compare-393-graphite-Тайны-compact.jpg) | [Full resolution](after-393-graphite-Тайны-compact.png) |
| 393-graphite-Тайны-expanded | [Reference / before / after](compare-393-graphite-Тайны-expanded.jpg) | [Full resolution](after-393-graphite-Тайны-expanded.png) |
| 393-parchment-Мир-compact | [Reference / before / after](compare-393-parchment-Мир-compact.jpg) | [Full resolution](after-393-parchment-Мир-compact.png) |
| 393-parchment-Мир-expanded | [Reference / before / after](compare-393-parchment-Мир-expanded.jpg) | [Full resolution](after-393-parchment-Мир-expanded.png) |
| 393-parchment-Отношения-compact | [Reference / before / after](compare-393-parchment-Отношения-compact.jpg) | [Full resolution](after-393-parchment-Отношения-compact.png) |
| 393-parchment-Отношения-expanded | [Reference / before / after](compare-393-parchment-Отношения-expanded.jpg) | [Full resolution](after-393-parchment-Отношения-expanded.png) |
| 393-parchment-Память-compact | [Reference / before / after](compare-393-parchment-Память-compact.jpg) | [Full resolution](after-393-parchment-Память-compact.png) |
| 393-parchment-Память-expanded | [Reference / before / after](compare-393-parchment-Память-expanded.jpg) | [Full resolution](after-393-parchment-Память-expanded.png) |
| 393-parchment-Персонажи-compact | [Reference / before / after](compare-393-parchment-Персонажи-compact.jpg) | [Full resolution](after-393-parchment-Персонажи-compact.png) |
| 393-parchment-Персонажи-expanded | [Reference / before / after](compare-393-parchment-Персонажи-expanded.jpg) | [Full resolution](after-393-parchment-Персонажи-expanded.png) |
| 393-parchment-Сцена-compact | [Reference / before / after](compare-393-parchment-Сцена-compact.jpg) | [Full resolution](after-393-parchment-Сцена-compact.png) |
| 393-parchment-Сцена-expanded | [Reference / before / after](compare-393-parchment-Сцена-expanded.jpg) | [Full resolution](after-393-parchment-Сцена-expanded.png) |
| 393-parchment-Сюжет-compact | [Reference / before / after](compare-393-parchment-Сюжет-compact.jpg) | [Full resolution](after-393-parchment-Сюжет-compact.png) |
| 393-parchment-Сюжет-expanded | [Reference / before / after](compare-393-parchment-Сюжет-expanded.jpg) | [Full resolution](after-393-parchment-Сюжет-expanded.png) |
| 393-parchment-Тайны-compact | [Reference / before / after](compare-393-parchment-Тайны-compact.jpg) | [Full resolution](after-393-parchment-Тайны-compact.png) |
| 393-parchment-Тайны-expanded | [Reference / before / after](compare-393-parchment-Тайны-expanded.jpg) | [Full resolution](after-393-parchment-Тайны-expanded.png) |
| 768-graphite-Мир-compact | [Reference / before / after](compare-768-graphite-Мир-compact.jpg) | [Full resolution](after-768-graphite-Мир-compact.png) |
| 768-graphite-Мир-expanded | [Reference / before / after](compare-768-graphite-Мир-expanded.jpg) | [Full resolution](after-768-graphite-Мир-expanded.png) |
| 768-graphite-Отношения-compact | [Reference / before / after](compare-768-graphite-Отношения-compact.jpg) | [Full resolution](after-768-graphite-Отношения-compact.png) |
| 768-graphite-Отношения-expanded | [Reference / before / after](compare-768-graphite-Отношения-expanded.jpg) | [Full resolution](after-768-graphite-Отношения-expanded.png) |
| 768-graphite-Память-compact | [Reference / before / after](compare-768-graphite-Память-compact.jpg) | [Full resolution](after-768-graphite-Память-compact.png) |
| 768-graphite-Память-expanded | [Reference / before / after](compare-768-graphite-Память-expanded.jpg) | [Full resolution](after-768-graphite-Память-expanded.png) |
| 768-graphite-Персонажи-compact | [Reference / before / after](compare-768-graphite-Персонажи-compact.jpg) | [Full resolution](after-768-graphite-Персонажи-compact.png) |
| 768-graphite-Персонажи-expanded | [Reference / before / after](compare-768-graphite-Персонажи-expanded.jpg) | [Full resolution](after-768-graphite-Персонажи-expanded.png) |
| 768-graphite-Сцена-compact | [Reference / before / after](compare-768-graphite-Сцена-compact.jpg) | [Full resolution](after-768-graphite-Сцена-compact.png) |
| 768-graphite-Сцена-expanded | [Reference / before / after](compare-768-graphite-Сцена-expanded.jpg) | [Full resolution](after-768-graphite-Сцена-expanded.png) |
| 768-graphite-Сюжет-compact | [Reference / before / after](compare-768-graphite-Сюжет-compact.jpg) | [Full resolution](after-768-graphite-Сюжет-compact.png) |
| 768-graphite-Сюжет-expanded | [Reference / before / after](compare-768-graphite-Сюжет-expanded.jpg) | [Full resolution](after-768-graphite-Сюжет-expanded.png) |
| 768-graphite-Тайны-compact | [Reference / before / after](compare-768-graphite-Тайны-compact.jpg) | [Full resolution](after-768-graphite-Тайны-compact.png) |
| 768-graphite-Тайны-expanded | [Reference / before / after](compare-768-graphite-Тайны-expanded.jpg) | [Full resolution](after-768-graphite-Тайны-expanded.png) |
| 768-parchment-Мир-compact | [Reference / before / after](compare-768-parchment-Мир-compact.jpg) | [Full resolution](after-768-parchment-Мир-compact.png) |
| 768-parchment-Мир-expanded | [Reference / before / after](compare-768-parchment-Мир-expanded.jpg) | [Full resolution](after-768-parchment-Мир-expanded.png) |
| 768-parchment-Отношения-compact | [Reference / before / after](compare-768-parchment-Отношения-compact.jpg) | [Full resolution](after-768-parchment-Отношения-compact.png) |
| 768-parchment-Отношения-expanded | [Reference / before / after](compare-768-parchment-Отношения-expanded.jpg) | [Full resolution](after-768-parchment-Отношения-expanded.png) |
| 768-parchment-Память-compact | [Reference / before / after](compare-768-parchment-Память-compact.jpg) | [Full resolution](after-768-parchment-Память-compact.png) |
| 768-parchment-Память-expanded | [Reference / before / after](compare-768-parchment-Память-expanded.jpg) | [Full resolution](after-768-parchment-Память-expanded.png) |
| 768-parchment-Персонажи-compact | [Reference / before / after](compare-768-parchment-Персонажи-compact.jpg) | [Full resolution](after-768-parchment-Персонажи-compact.png) |
| 768-parchment-Персонажи-expanded | [Reference / before / after](compare-768-parchment-Персонажи-expanded.jpg) | [Full resolution](after-768-parchment-Персонажи-expanded.png) |
| 768-parchment-Сцена-compact | [Reference / before / after](compare-768-parchment-Сцена-compact.jpg) | [Full resolution](after-768-parchment-Сцена-compact.png) |
| 768-parchment-Сцена-expanded | [Reference / before / after](compare-768-parchment-Сцена-expanded.jpg) | [Full resolution](after-768-parchment-Сцена-expanded.png) |
| 768-parchment-Сюжет-compact | [Reference / before / after](compare-768-parchment-Сюжет-compact.jpg) | [Full resolution](after-768-parchment-Сюжет-compact.png) |
| 768-parchment-Сюжет-expanded | [Reference / before / after](compare-768-parchment-Сюжет-expanded.jpg) | [Full resolution](after-768-parchment-Сюжет-expanded.png) |
| 768-parchment-Тайны-compact | [Reference / before / after](compare-768-parchment-Тайны-compact.jpg) | [Full resolution](after-768-parchment-Тайны-compact.png) |
| 768-parchment-Тайны-expanded | [Reference / before / after](compare-768-parchment-Тайны-expanded.jpg) | [Full resolution](after-768-parchment-Тайны-expanded.png) |
