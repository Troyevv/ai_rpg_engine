# Issue 45 implementation and preservation plan

Base: master 318a8f1, includes merged #116 (ffddf3f) and completed #44.

## Navigation and ownership
Desktop: existing shell → current-save “Игра” → Time / Characters / Chronology / Settings.
Mobile: same entry → full-width sheet → one selected destination. Scene fixation stays above story.
Phone: one mounted edge device → expanded nonmodal device → same edge device. Incoming calls never open it automatically.
#45 owns controls/calendar/phone and initial genealogy. #83 will refine the same genealogy/dossier; #86 retains the single Inspector width; #87 reading surface and #72 streaming remain untouched.

| Existing feature | Integration boundary |
| --- | --- |
| Time Skip / LTA | Existing components and endpoints, distinct operations |
| permanent / temporary / observe | Existing protagonist and camera services, no dialogue commands |
| pacing / risk / outcomes | Existing NarrativePolicy and revision guards |
| portraits | Existing PortraitControl, shared authorized asset API |
| genealogy | Existing knowledge-filtered server projection |
| global provider / theme | Existing Settings unchanged |
| relationship notices | Existing local preference and key, one control in current-game settings |
| Tabletop | No changes to its screens or rules |

## Dependency audit
Existing Motion 12 (MIT), Radix Dialog 1 (MIT), Lucide and skin tokens are reused. No new design system.
FullCalendar React evaluated: capable event scheduler but its editing/resource features and Gregorian date model are unnecessary for a read-only arbitrary-calendar projection.
React DayPicker 9 (MIT) adopted behind Calendar adapter for Gregorian keyboard navigation/localized month grids. Custom profiles retain server day/weekday arithmetic; no JS Date interpretation of fictional dates. Year overview is bounded monthly navigation, not an event store.
React Flow 12 (MIT) and Dagre 1 (MIT) provide graph navigation and bounded layout; only authorized graph nodes enter them. No persisted graph state. Added libraries add frontend bundle cost; lazy loading is preferred for secondary views.

## Interaction policy / state matrix
Modal Current Game/calendar/protagonist/Inspector takes priority over nonmodal phone. Opening a modal collapses the device, preserving per-actor per-conversation drafts in component memory. Escape collapses phone and restores its trigger; modal Escape belongs to Radix. Incoming notifications never steal focus. Generation locks canonical commands, not browsing. No panel opening submits a turn. Phone is outside story flow; scroll and game input drafts survive.

| Surface | States to exercise |
| --- | --- |
| phone | peek, unread, ringing, answered, expanded, keyboard, reduced motion, actor change |
| calendar | unknown date, empty, birthday, pending/resolved/cancelled/rescheduled, custom calendar |
| protagonist | active, incapacitated, dead, observer, temporary control |
| portrait | missing, upload, crop, error, history, original viewer |

Use existing #78 isolated loader and checkpoints. Keep base unchanged. Start Game → ordinary turn → reload → next turn; then Time Skip, LTA, temporary/observe/permanent switch. Change pacing/risk/outcome, reload and verify only future policy changes. Toggle notices and reload. Exercise phone message drafts across chats/closing and channel focus. Compare genealogy before/after knowledge/control change. Calendar navigation must not change save revision/world_time. Test 360/393 px, tablet/desktop, two contrasting skins and reduced motion. Record actual executed checks separately; this itinerary is not a claim of passing QA.

## Delivered behavior and compatibility

`CurrentGame` composes separate `GameCalendar`, `Genealogy`, `WeatherSettings`, and chronology surfaces. Time Skip and LTA remain their original distinct services and now open as sibling dialogs, avoiding stacked focus traps. Shared eligibility covers send button, submit callback, choices and Ctrl/Cmd+Enter. Incapacitation permits observation; death uses the existing required protagonist transition.

The calendar filters the canonical state on the server **before** building events, markers or counts. An NPC birthday needs known structured birthday evidence; own commitments and explicitly known scheduled events are visible. Existing fixture checkpoints now record the knowledge they intended to exercise. The shared genealogy endpoint applies the same birthday restriction; graph limits are 80 nodes / depth 1–6. Portraits remain consumers of #74 authorized assets.

Weather is an optional versioned, reproducible daily projection of persisted profile + canonical region + world minute. Explicit configuration uses the existing revision-guarded history/rollback transaction. Old snapshots default to `weather: null`; no SQL migration or rewriting historical snapshots. Unsupported regions/calendars do not acquire invented terrestrial seasons. Configuration begins at the current minute; earlier weather remains unknown, and future weather is omitted. No LLM calls or live weather service. Calendar month requests remain bounded; multi-year skips compute only requested days. The same projection supplies scene, calendar and model context.

Library choices: DayPicker 9.14 (MIT), React Flow 12.12 (MIT), Dagre 1.1.8 (MIT). Calendar and graph are lazy chunks (~86 kB / ~228 kB minified); the existing main bundle still triggers Vite's >500 kB advisory. DayPicker retains its keyboard-aware DayButton; Radix handles modal semantics, React Flow provides pan/zoom and an accessible text list, and existing skin/motion tokens and reduced-motion preferences apply. Phone uses transform-based continuity without a second dialog or state store.

## Executed validation (2026-10-26)

- `python -m pytest -q`: **2111 passed** (391.61 s).
- `python -m pytest -q tests/test_current_game_ui.py tests/test_narrative_pacing.py`: **97 passed**, after transaction cleanup.
- `npm --prefix frontend run build`: TypeScript and production build passed; bundle-size advisory above.
- Focused Playwright `current-game`, `calendar`, `long-term`, `narrative-skins`: **20 passed**. Includes all shipped skins; mobile widths 360/390/412/430; Time Skip and rollback; LTA preview/commit/reload; calendar browsing without revision/time mutations.
- Focused Playwright `current-game`, `phone`, `protagonist`, `narrative-pacing`, `portraits`, `runtime-handoff`: **32 passed** on desktop/mobile. Includes Start Game → ordinary turn → persisted reload → next turn, PR #116 original-export/rejected-opening recovery, explicit climate/reload, temporary control ownership, calls/emergency/group contacts, per-chat drafts, portrait upload/crop/history/delete, manual and death-triggered protagonist transitions.

Browser command prefix used in this environment:

```sh
PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell npx playwright test
```

An isolated temporary config selected port 8012 and a separate results directory for focused runs. Normal checked-in `playwright.config.ts` remains unchanged. Fixtures use temporary databases and deterministic fake providers; this is not a live-model quality assessment.

## Evidence

All images below are browser captures, not design mockups. Before images are from untouched master `318a8f1`; after images use the same phone checkpoint.

| Surface | Desktop | Narrow mobile |
| --- | --- | --- |
| Before: phone entry | [desktop](issue45-evidence/desktop-before-phone-resting.png) | [393px](issue45-evidence/mobile-before-phone-resting.png) |
| Before: generic phone dialog | [desktop](issue45-evidence/desktop-before-phone-expanded.png) | [393px](issue45-evidence/mobile-before-phone-expanded.png) |
| After: same device at rest | [desktop](issue45-evidence/desktop-phone-resting.png) | [393px](issue45-evidence/mobile-phone-resting.png) |
| After: messenger + incoming call | [desktop](issue45-evidence/desktop-phone-expanded.png) | [393px](issue45-evidence/mobile-phone-expanded.png) |
| Calendar, Parchment | [desktop](issue45-evidence/desktop-calendar.png) | [360px](issue45-evidence/mobile-calendar.png) |
| Genealogy, Graphite | [desktop](issue45-evidence/desktop-family-graphite.png) | [360px](issue45-evidence/mobile-family-graphite.png) |
| Genealogy, Parchment | [desktop](issue45-evidence/desktop-family-parchment.png) | [360px](issue45-evidence/mobile-family-parchment.png) |

## Remaining limits

Browser mobile emulation does not certify a physical Android keyboard, OS Back gesture, GPU animation timing or pinch interaction. Escape, modal dismissal, reduced motion and short-viewport behavior are tested; no new OS navigation interception was introduced. Phone drafts live only in component memory and intentionally disappear on full reload. Weather is a simple deterministic daily climate model, without hourly fronts, external forecasts or custom-world season inference. Genealogy exposes bounded depth/recentering; the later #83 visual redesign remains out of scope. No Tabletop domain changes, provider-setting changes, merges or follow-on issues.

Final responsive pass after focus/date/keyboard refinements: `current-game` + `calendar`, **16 passed** (45.1 s). Added composer non-overlap assertions at 393×500, Escape focus restoration, 820px tablet and 125% root text sizing. Evidence: [short viewport](issue45-evidence/mobile-phone-short-viewport.png), [tablet enlarged text](issue45-evidence/desktop-calendar-tablet-large-text.png). This simulates reduced available height; it does not emulate a real OS keyboard.

Full exploratory browser run (started before the UI fixes): **226 passed, 10 failed, 10 skipped**. Five failures were #45 graph layout/modal lifecycle/test-fixture defects, fixed and covered by the passing focused runs above. Five were existing generator waits (`draft-v4` structured motivations on both projects; `draft-world` creation at desktop 1280/1440 and mobile 412). An independent untouched-master worktree reproduces the same failure classes: **10 passed, 8 failed** across 18 baseline/creation checks, with failing viewport cases varying between runs. Both fail waiting for the generator to leave `generating` / open its result within the existing 12 s assertion budget. No timeout inflation or out-of-scope generator change was made; the full suite is **not reported green**.

Final server confidentiality check also removes private observance definitions from `world_clock.calendar`, not only its event markers. The final targeted backend command, `python -m pytest -q tests/test_current_game_ui.py tests/test_narrative_pacing.py tests/test_calendar_v2.py tests/test_commitments.py`, passed **152 tests** (13.14 s).

## PR120 completion specification — intermediate update, not acceptance

Audit base and latest remote HEAD were both `8a6c181`; master remains `318a8f1` with #44/#116 integrated. No later changes were discarded. Existing seven Inspector views, Game, Phone and canonical APIs retain ownership. Calendar/family now share a direct desktop rail/mobile-menu workspace, preserving mounted Game; character-card entry uses that same workspace. Global settings remain separate. No new dependencies or SQL migration.

Implemented in this update: direct navigation, month/agenda composition, miniature year grids, selected-date/range consistency, server-side authorized family root choices, permanent card entry, B02 direct reply path, B05 filtered calendar labels, and B06 valid Observance regression. Calendar/profile remain canonical. The year view requests one bounded month per configured month; no History loading.

Validation: production build passed; `pytest -q tests/test_current_game_ui.py tests/test_remote_communication.py tests/test_life_social.py` **77 passed**. Browser `phone`, `runtime-handoff`, `pr120-completion` **12 passed** including Start → ordinary turn → reload → next ordinary turn on desktop/mobile. Updated `current-game` + `pr120-completion`: **16 passed**. Final visual/navigation rerun: **2 passed**. These are targeted runs, not a full-suite claim.

Visual inspection caught unequal calendar columns (percentage day width); fixed with equal fixed-layout columns and recaptured. [Desktop month](pr120-completion-evidence/desktop-calendar-after.png), [mobile month](pr120-completion-evidence/mobile-calendar-after.png), [desktop year](pr120-completion-evidence/desktop-year-after.png), [mobile family](pr120-completion-evidence/mobile-family-after.png). [Desktop transitions](pr120-completion-evidence/desktop-video.webm), [mobile transitions](pr120-completion-evidence/mobile-video.webm). Before captures remain in issue45-evidence above. Videos cover navigation/month/year/family/return, **not** a completed outgoing phone conversation. Chromium emulation, no physical Android check.

| Requirement | Status in this update |
|---|---|
| R01 | Direct desktop/mobile entrances and shared workspace implemented; draft/return verified |
| R02 | Partial: calendar composition improved; complete visual system/phone review remains |
| R03 | Month/agenda and real year grids implemented; custom-year acceptance still pending |
| R04 | B04–B06 fixed, valid canonical fixture and projection checks pass |
| R05 | Authorized roots/search and permanent card entry implemented; independent-family and large-graph acceptance pending |
| R06 | Not complete: phone screen redesign remains |
| R07–R08 | Not complete: automatic bounded dial/read→optional-reply job cycle remains |
| R09 | Direct-conversation reply without reverse contact fixed and tested through planner/accept/delivery |
| R10 | Not complete: new continuation orchestration/idempotency/lineage acceptance remains |
| R11 | Targeted preservation tests pass; complete requested matrix remains |

| Tests | Evidence / remaining work |
|---|---|
| T01–T03 | Passed runtime-handoff and direct-navigation E2E |
| T04 | Partial: calendar screenshot; dense multi-event/long-title review remains |
| T05 | Passed selected day follows browsed month, revision unchanged |
| T06 | Gregorian year passed; custom-year/boundary checks pending |
| T07 | Existing backend lifecycle tests retained; full UI status matrix pending |
| T08 | Valid private Observance canonical fixture and filtered UI projection pass |
| T09 | Existing weather/reload tests pass; full switch/rollback matrix pending |
| T10–T12 | Not fully verified: independent family, known isolated NPC, complex large graph |
| T13 | Hidden root name regression caught and fixed; full matrix pending |
| T14 | Existing phone draft/read/reload tests pass; redesign/motion acceptance pending |
| T15–T16 | Not implemented end-to-end automatic continuation |
| T17 | Existing phone routing tests pass; new complete interaction video pending |
| T18–T19 | Not implemented end-to-end automatic read/reply cycle |
| T20 | Planner candidate → accepted direct reply → original conversation delivery passes without reciprocal contact |
| T21 | Existing remote communication tests pass |
| T22–T23 | New continuation retry/reconnect/lineage checks pending |
| T24 | Existing protagonist/incapacitation/death E2E retained and passing |
| T25 | Narrow viewport/draft/focus tests pass; full physical keyboard and visual matrix pending |
| T26 | Full requested preservation rerun pending; no Tabletop code changes |

G1 is implemented; G2/G3/G6/G7 are partial. G4/G5 are **not met**. This update does not complete the attached specification and must not be treated as merge-ready or as closing #45.
