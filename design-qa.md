# Inspector #86 — design acceptance

final result: passed

Final recapture and side-by-side review completed. No actionable P0/P1/P2 findings remain within the explicit Skin System, real-data and unchanged #83 constraints recorded below.

## Source, baseline and comparison method

- Source of truth: supplied `issue86_interactive_mockups.zip`, extracted `issue86_prototype/index.html`. HTML SHA-256: `538a864e8ef320c8d10740bc832f25859f30d4c9357870d976a6f48f043b7ab0`. The HTML, its seven sections, theme/width switches and interactions were opened before implementation. Source capture does not modify its content or styling.
- Implementation baseline: master `cd91e1b80b28ab0b74971889032341b20a385637`, including the final changes of #120 and #121. Issue #86, its comments/additions, Epic #36 and AGENTS.md were read first.
- [Preservation inventory and architectural boundaries](docs/manual_qa/narrative_v4/issue86-inspector.md).
- [112 side-by-side comparisons, full-resolution originals and videos](docs/manual_qa/narrative_v4/issue86-evidence/README.md). `before-*` images document the original application. `reference-*` and `after-*` document the approved HTML and browser-rendered implementation.
- Actual application at `http://127.0.0.1:8011`, production frontend build, real FastAPI/SQLite APIs, supported import/confirm flow and `ui-inspector` test world. No frontend API replacement is used for the matrix. The error/retry test deliberately fails one scene request, then continues to the real endpoint.
- Each source/application image is **1440×900, 768×900, 393×900 or 360×900 physical pixels**, with the same CSS viewport and **deviceScaleFactor 1**. Both Graphite and Parchment, all seven sections, expanded and compact at every size. On phones the width switch is hidden; each preference is selected at 768 px and then resized to the target viewport before capture. Both remain single-column. This gives 112 pairs. Separate Pixel 7 runs test touch/mobile interaction behavior.
- Source has a 32 px demo-only bar. It is preserved in source screenshots and absent from the real application. Compare content after that offset, not a raw whole-image pixel error. Desktop contact sheets are scaled equally to 720 px per image; the originals remain unscaled. Phones remain at native CSS resolution in the pair files.
- Default section/filter states match. The source's fictional Apex records and the application's canonical Two Shores records differ in text, length, counts, available weather, calls and portraits. Content-dependent height differences are called out rather than filled with invented records.
- [Focused Graphite dossier comparison](docs/manual_qa/narrative_v4/issue86-evidence/detail-dossier-graphite.png) and [Parchment comparison](docs/manual_qa/narrative_v4/issue86-evidence/detail-dossier-parchment.png) use unscaled 900×380 crops from both originals. The mobile pairs are also readable at 1:1 for controls, text wrapping and spacing.

## Findings and correction history

| Priority | Earlier finding | Fix and post-fix evidence |
| --- | --- | --- |
| P1 | Modal Inspector and large metadata/search shell obscured the dossier; only three top-level entry points | Replaced by adjacent workspace and one grouped seven-section sidebar, shared mobile sheet, compact searchable character picker; all seven final desktop/mobile pairs |
| P1 | A single grid made unrelated cards stretch together and changed the source's density | Independent stacks, 1.4:1 overview/scene columns, dedicated relation/secret/thread/timeline cards, 1160/680 px content limits; World, Scene and Memory pairs |
| P2 | Avatar selectors stretched shared avatar internals | Excluded `.character-avatar` from flex text rules; shared #83 avatar rendering retained; focused dossier crops and portrait regression suite |
| P2 | Broad styling could override dossier pills/disclosures | Scoped new card styles to Inspector section cards; removed only the obsolete dossier modal shell CSS; five dossier tabs and portrait/editor suites |
| P2 | Public facts were collapsed and memory kind controls lacked the source's pill treatment | Visible fact prose, full-text disclosure only for long bodies, pill filters and timeline time/dot/line; World and Memory pairs |
| P2 | Scene edit action occupied a redundant sidebar card; tablet brand split across lines | Moved the action to the heading with the source's pencil/label; the real form appears only while editing. Made the narrow brand non-wrapping; Scene 360/1440 and all 768 pairs |
| P2 | Memory scope used a dropdown instead of the approved two-option control | Segmented player/controlled-character scope, same witness/knowledge predicates, disabled actor option when no actor; Memory pairs and scope persistence test |
| P2 | Search could shrink to an icon at tablet width; compact desktop relationships stacked metrics unlike the reference | Added a minimum usable search width and wrap behavior, plus a matrix assertion for visible input width. Relation metrics now stack at the source's viewport breakpoint rather than at the compact content width; 768 Memory and 1440 compact Relationships pairs |
| P1 | Escape from a dossier over genealogy could also close its origin | Top dialog → dossier origin → workspace ownership, family remains mounted/inert; desktop/mobile family-return and browser-back videos |
| P1 | Re-saving the displayed relative time during a location-only edit could change the canonical minute | Unchanged time uses the existing API's keep-current-time contract; real failed request/retry/save test checks location and unchanged minute; scene-save videos |

The last two findings are interaction/data-preservation regressions, not reasons to change Narrative Runtime. Their fixes are entirely in the UI.

## Required fidelity surfaces

| Surface | Review and deliberate application constraints |
| --- | --- |
| Fonts and typography | Hierarchy, compact uppercase eyebrows, restrained sans UI, serif narrative prose, title weights, wrapping and tab density compared in full images and focused crops. Existing `--ui-font`, narrative and Skin heading fonts remain authoritative. Parchment retains its established serif UI rather than copying the standalone prototype's sans UI. Long-name, enlarged-text and reduced-motion regressions are included. |
| Spacing and layout | Desktop 214 px navigation, compact topbar, bounded centered content, independent card stacks, horizontal directions/filters, single-column phones and scrollable dossier tabs. Compact/expanded use one persisted preference. No whole-document horizontal overflow at the matrix sizes; long content stays within its scroll surface. Extra original application destinations remain reachable in the scrolling navigation. |
| Colors and tokens | Semantic Skin tokens drive background, card surfaces, border, accent, text, relationship meters and knowledge states. Graphite is darker and Parchment warmer/textured than the standalone HTML: preserving the existing Skin System is an explicit requirement. No global palette or skin replacement. |
| Image quality and assets | Existing #83 uploaded portraits, circular crop, fallback silhouettes and portrait editor are retained. No copied demo character photograph, generated substitute or handwritten icon set. Existing Lucide icons replace the prototype's standard icon-font glyphs with the same meanings. Dedicated portrait regressions cover 36–144 px, uploaded/cropped/original/history/error states and hidden senders. |
| Copy and content | Section titles/actions and RU/EN labels use the localization helper. Real canonical descriptions, names, evidence, directed dimensions and timestamps populate cards. Where the API supplies only prose, the heading is a shortened excerpt, so short records can repeat it. No invented separate title, chronology, numeric feeling, weather or demonstration role switch. |

## Intentional adaptations and limits

- The character dossier remains the #83 implementation, including all five tabs, portrait tools, biography/appearance, goals, motivations, relationships, life conditions and public birthday/family entry points. Its content and internal layout were not redesigned to imitate the sample person.
- The prototype's fake editor/toasts are replaced by revision-protected APIs and real permission/busy/error states. The scene editor remains an inline form when open. Relationship overrides use the existing authorized editor. Relationship meters represent the actual -100…100 range.
- No weather or location parent chain is manufactured when absent. Remote calls use the real actor-owned phone projection and are separate from physical presence. Opening the phone returns to the mounted existing device.
- Calendar, genealogy, library/workshop, settings, reading mode and game navigation remain available. Their presence adds destinations beyond the seven-section prototype.
- Secret/knowledge classification comes from the existing projection. The public birthday and family directory remains accessible without Knowledge or phone-contact membership; UI tests verify this. No inference from prose changes authorization.
- Cloud browser inspection opened both reference and application; later remote automation calls timed out. Final evidence and all viewport comparisons use local Chromium screenshots, not a claim of continued cloud inspection. Physical Android hardware, OS font settings and an external paid LLM provider were not tested; Pixel 7 emulation, browser Back, enlarged text and the existing deterministic test provider were tested.

## Interaction and regression verification

Primary interactions: all section entries; theme and width switching; character name/alias search, empty results, nearby, previous/next and keyboard selection; contextual dossier return; filter and scroll preservation; scene draft/cancel/error/retry/save; directed relations, thread states and memory filters; metadata/export; phone return; genealogy/calendar links; Escape and browser Back; focus return and preserved composer draft.

Browser `pageerror` is collected in the matrix and critical flows and asserted empty. API failure states are explicitly exercised. Console/backend output includes the existing semantic-retrieval structural fallback when optional local models are unavailable, and the build reports its existing large-bundle warning; neither is hidden as a successful provider call.

| Command / run | Result |
| --- | --- |
| `python -m pytest -q` | Passed, exit 0 (full backend suite) |
| `python -m pytest -q tests/test_narrative_test_world.py tests/test_character_dossier.py` | 15 passed |
| `npm run build --prefix frontend` | Passed (TypeScript + production Vite build) |
| Earlier dossier/editor/theme/knowledge/runtime regression run, 11 specs | 62 passed, 8 skipped |
| `npm run test:e2e --prefix frontend -- e2e/inspector86.spec.ts e2e/dossier-portraits.spec.ts e2e/portrait-polish.spec.ts e2e/portraits.spec.ts e2e/phone-completion.spec.ts e2e/pr120-completion.spec.ts e2e/completion-matrix.spec.ts e2e/inspector-ux.spec.ts e2e/current-game.spec.ts e2e/tabletop.spec.ts --max-failures=3` | 89 passed, 13 skipped; skips are duplicate viewport captures in the mobile project |
| `npm run test:e2e --prefix frontend -- e2e/inspector86.spec.ts e2e/presentation.spec.ts e2e/knowledge.spec.ts e2e/runtime-handoff.spec.ts --max-failures=2` | 28 passed, 4 duplicate viewport captures skipped |
| `npm run test:e2e --prefix frontend -- e2e/inspector86.spec.ts --grep "seven sections" --project=desktop` after responsive polish | 4 passed; all 112 pairs captured and dimension-verified |

[Saved final build, browser and focused backend logs](docs/manual_qa/narrative_v4/issue86-evidence/logs).

All browser commands use `PLAYWRIGHT_EXECUTABLE_PATH` pointing to the installed Chromium headless shell. An earlier simultaneous-run attempt produced a Playwright output-directory ENOENT; subsequent suites ran sequentially and the affected current-game cases passed. Early assertion failures and the scene-time bug were fixed before the passing runs above.

Mandatory smoke: **Start Game → ordinary turn → save/reload → next ordinary turn**, desktop and mobile, through real APIs and SQLite persistence with the existing deterministic provider. [Desktop recording](docs/manual_qa/narrative_v4/issue86-evidence/smoke-desktop.webm), [mobile recording](docs/manual_qa/narrative_v4/issue86-evidence/smoke-mobile.webm). Runtime handoff also verifies rejected opening recovery and canonical time progression. Tabletop end-to-end tests passed; no Tabletop production files were changed.

## Implementation checklist

- [x] Inventory and preserve original fields/actions/API boundaries.
- [x] Integrate all seven sections and unchanged #83 dossier.
- [x] Correct composition, typography, scope controls, navigation and return ownership.
- [x] Verify public birthdays/genealogy and canonical state preservation.
- [x] Run backend, frontend build, relevant browser regressions and mandatory smoke.
- [x] Complete post-polish recapture and final side-by-side review.

Delivery: a separate PR to master; no merge and no work on #72/#87.
