# Issue 192 — implementation and acceptance ledger

## Reference and baseline

- Base: `master@eaf75a13e8b5e5cc1b9ed855a17b40be608fd3ec` (fresh checkout; matches the issue audit).
- Read the issue and all six appendix comments. Original reference: Issue 175 attachment `world-workshop-reference.zip`.
- Original `world-workshop.html`: **468501 bytes**, SHA-256 **4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1**. Verified before edits.
- `tests/fixtures/workshop175-reference.zip` contains only that byte-identical HTML. The preview JPG and README are excluded. No demo state or JavaScript is imported into production. The E2E server independently verifies the hash before serving it.
- **Pre-change browser baseline was blocked.** Local Chromium terminated with `socket() failed: Operation not permitted (1)` in `process_singleton_posix.cc`. The separate cloud browser could not reach the local server (`ERR_CONNECTION_REFUSED`). No new baseline PNGs were obtained before editing. A limited historical baseline was recovered later (see provenance below); it does not replace the missing complete baseline series. Source inspection, unit tests and build are not substitutes for baseline measurements.
- `00-workshop192.spec.ts` captures original/current pairs at 360×800, 390×844, 412×915, 430×932, 768×1024, 1024×768, 1280×800, 1440×1000 and 1920×1080 and records browser/font/overflow metadata. Those captures are post-change evidence, not the missing pre-change master baseline. The later Issue 190 prototype remains the reference for “По моей идее”.

## Status conventions

**Implemented** means code exists; it does not imply browser acceptance. **Preserved** means the existing implementation was retained. The initial 77 base-state pairs have been captured; every visual item still requires its complete interaction-state comparison; motion, keyboard, focus, physical mobile keyboard and theme acceptance are open until observed. There is no agreed design deviation beyond those already authorized by Issues 175/190 (real Runtime, projected canon, existing skins/portraits, separate Narrative, real presets and recovery).

| ID | Implementation / retained contract | Acceptance evidence or remaining work |
|---|---|---|
| W01 | Search indexes projected characters, locations, organizations, threads and facts, including text/aliases. | Unit indexing tests and desktop/mobile SQLite navigation passed. At `6d6fa2eb`, all five types open through Tab/Enter, Escape closes the record and player search/API exclude a hidden marker. |
| W02 | Empty search suggests objects; nonempty misses show a distinct state. | Unit test and real desktop/mobile empty-query suggestions versus no-results status passed at `6d6fa2eb`. |
| W03 | Overview diagnostics retain source paths and object links. | Review browser links including incomplete candidates. |
| W04 | Overview opens atomic campaign editor and stays in overview. | Atomic write test and overview title edit/return passed on desktop/mobile at `6d6fa2eb`; separate record-editor conflict regression also passed. |
| W05 | Public lead precedes expandable full author description. | Reader projection tests; visual pending. |
| W06 | Last three actual version reasons and timestamps. | API source retained; timezone/visual check pending. |
| W07 | Overview seeds AI example without overwriting stored instruction. Example replacement requires a decision. | Browser buffer/return pending. |
| W08 | Stats, compact first four cards and start-scene panel retained. | Base overview compared at desktop/mobile/tablet; compact hero and four mobile stats inspected. Full interactive-state acceptance remains open. |
| W09 | Mobile breadcrumb shows current section; generic prefix hidden. | Current section is visible in reviewed mobile captures at required widths; navigation regressions passed. |
| W10 | AI sidebar action has separate visual surface. | Visual/theme acceptance pending. |
| W11 | Navigation focuses content without scrolling; per-world/section scroll retained. The mobile menu defers focus until its portal closes; section changes from overview CTAs also transfer focus. | Real-frame E2E passed at `1a0e3766`: content focus after desktop/mobile navigation, Escape and normal/reduced movement. Complete nested-return/scroll comparisons remain open. |
| W12 | Read/action/revision states separated; field dirty/saving state reflects actual state. | Review failed/pending requests and child-dialog status propagation. |
| W13 | Existing theme typography retained. | At `1a0e3766`, all 55 desktop base pairs report Workshop Sans/Workshop Book with fonts ready. Portal computed fonts: Graphite Workshop Sans, Parchment Georgia, Cyberpunk Consolas. All six skin portal pairs inspected. Complete weight/width comparisons outside these states remain open. |
| W14 | Overview panel surfaces differentiated using skin tokens. | Visual/theme acceptance pending. |
| W15 | Existing modal backdrop retained. | Compared actual Graphite/Parchment/Cyberpunk portals: the global UI override removed blur. Restored the exact #175 scrim `#070a09ba` / `blur(9px)` only in the workshop; #190 atelier remains separate. Computed-style assertion passed in all three skins on both projects at `1a0e3766`; refreshed portal captures inspected. |
| W16 | Local create form before mutation; nonempty name required, description editable; cancel does not write. | Backend + component tests; E2E added. |
| W17 | Explicit ordered source/target; backend rejects self/missing/duplicate pair. | SQLite test verifies exact edge and no extra revision. |
| W18 | Full cards show personality; overview stays compact; portrait contract retained. | Grid/list artwork geometry and full-SVG pixel comparison passed in `workshop188-age-choice`; fuller cards inspected in historical/current pairs. All long-copy combinations are not claimed. |
| W19 | Family/organization filters use projected objective relations and roles. | Fixture/browser filter verification pending. |
| W20 | Pagination controls omitted for one page; existing bounded 12-card pages retained. | `workshop175.spec.ts` passed on both projects at `f0fbfa0`: 240 characters, 12 visible, search for the last record and retained scoped search after return. |
| W21 | Dossier hero/current-location context and character-name label. Empty motives collapse into one disclosure. Compatibility card projections do not duplicate canonical Runtime fields; every real editable contract remains available. | Added real SQLite/browser case for empty legacy/canonical intentions. Six fresh skin portal pairs inspected at `235b00a3`; compact actions, identity rows and footer geometry passed at `1a0e3766`. |
| W22 | Mobile horizontal portrait strip and searchable all-person select. | Browser touch/keyboard and 240+ people pending. |
| W23 | Isolated per-world multi-field buffers; one patch_fields transaction; explicit discard. | Backend/component tests and real SQLite/browser regression passed at `1a0e3766`: HTTP 409, buffer surviving reload, explicit discard and two fields committed in one version on both projects. |
| W24 | Existing field/card generator can produce a scoped preview; apply/reject is separate. | SQLite controlled-provider test: one call, unchanged canon before decision, stale rejection. Controlled-provider browser case passed in `workshop188-editing.spec.ts` at `3d8ac38`; paid-provider calls are not an acceptance requirement. |
| W25 | Existing procedural/photo/manual-age behavior retained; hover scaling is outside crop. | Portrait upload/crop, manual visual age, neutral fallback, descriptor persistence, Runtime handoff and reload suites passed at `f0fbfa0`; reviewed Anna historical/current frame pairs. |
| W26 | Collection search includes description/text/context/aliases. | Browser localized search pending. |
| W27 | Place/org metadata, starting-place badge, projected participants and organization locations. | Browser hierarchy and long-content check pending. |
| W28 | Parent dropdown excludes self/descendants; backend rejects cycles and unknown parent. | SQLite parent-cycle test. |
| W29 | Residence grouping and separate Runtime editors retained. | Existing regressions retained; browser pending. |
| W30 | Directed relation row uses stretched native action; inner controls remain separate. | Browser hit-target/keyboard check pending. |
| W31 | Seven named feeling sliders; unknown legacy keys stay visible/removable and unset stays absent. The existing Runtime whitelist is preserved. | Component unknown-value test. Browser keyboard/endpoints/two-field save/reverse-edge/restore regression passed on both projects at `6d6fa2eb`. Arbitrary custom keys are not accepted by the current canonical Runtime contract; see explicit scope conflict below. |
| W32 | Family duplicate shortcut opens actual server merge plans; zero-count text is structural only. | Existing merge contract retained; browser duplicate fixture pending. |
| W33 | Dossier tabs use tablist/tab/tabpanel and roving keyboard behavior. | Semantic tab selectors, retained dossier context and nested field-editor return passed in existing workshop suites. New long-name/tab-preservation case passed on both projects at `1a0e3766`. |
| W34 | Thread/fact/scene/event creation forms use single atomic add. | Six-type SQLite add tests; real browser cancel-without-write and thread creation with exactly one revision/version passed on desktop/mobile at `f0fbfa0`. |
| W35 | Story-secret slice uses projected story_secret, distinct from private facts. | Player-view suite retained; browser slice/POV pending. |
| W36 | Short thread heading + expandable original description; badge from server projection. | Server badge/projection test; long-copy visual pending. |
| W37 | Separate desktop date column, timeline axis, card surface, ending and server-projected today/past/future labels. | Runtime day classification unit test; rendered spacing still needs acceptance. |
| W38 | Scene time uses calendar presenter; scene text distinguishes same-location cards. | Calendar presenter retained; browser fixture pending. |
| W39 | Private facts and story secrets have distinct labels and slices. | Existing canonical flags unchanged; browser pending. |
| W40 | Quick fact-text edit opens existing scoped editor; full record retains knowledge context. | Scoped field tests; browser pending. |
| W41 | Multi-field record editor uses one version and existing server validation. | Atomic transaction/conflict tests. |
| W42 | Start scene is first tab; world/narrative and calendar/communication are separate. | Communication E2E navigation updated; browser pending. |
| W43 | Date/time editor previews via Runtime calendar arithmetic, including custom profiles. | Calendar unit tests added; browser invalid-date/save timing pending. |
| W44 | Communication screen links to existing contact section. | Browser navigation pending. |
| W45 | Distinguishes absent/stale/completed review; merges severity and paths; category counts/filter; pins checked revision. | Priority/duplicate unit test and revision/no-op/stale SQLite test. The author-only decision history now reuses accepted re-audit issue IDs, reasons and basis, distinguishes disproved/replaced, and marks changed-candidate history. SQLite and render tests verify privacy, no-write behavior and stale-address suppression. Structural fixes now require a previously observed typed defect and a completed report for the exact new candidate. Stable entity IDs survive array reordering and changed wording; semantic disappearance, deleted subjects, failed/stale reviews and initially false-positive findings never become fixes. Seven focused tracking tests and render tests passed. Full recovery browser acceptance remains open. |
| W46 | Scene diagnostics route to exact scene in chronology. | Browser diagnostic fixture pending. |
| W47 | No fabricated repair action: real recovery or existing field navigation. | Existing server recovery unchanged; browser pending. |
| W48 | AI examples, world/version context, three steps and empty proposal area. | Desktop/mobile base AI composition compared; three-step context/example panel inspected. Full example-overwrite interaction acceptance remains open. |
| W49 | Skeleton shown only for actual active editor job, old diff hidden during generation. | `world-ai-editor.spec.ts` passed controlled-provider running/reload/completion/error/retry/reject cases on desktop/mobile. Full paired loading-state motion comparison remains open. |
| W50 | First changed diff expanded and before/after surfaces distinct. | `world-ai-editor.spec.ts` passed first-diff-open, before/after, cancel/no-write, apply/reconnect idempotency and subsequent Narrative reload checks in Graphite/Parchment. |
| W51 | Applied proposal links to available object and immutable base version. | Browser object/base-version navigation pending. |
| W52 | Author-only owned snapshot read, timestamp, preview, explicit restore; stale head blocked. | SQLite ownership/no-write/conflict tests and desktop/mobile historical preview, explicit restore, new immutable version and real Runtime continuation passed at `f0fbfa0`. |
| W53 | Separate readable TXT omits headings/payload; legacy TXT/MD/JSON round trips retained. | Backend export test and existing portrait round-trip tests. |
| W54 | Draft rows expose revision and current-world marker. | `draft-world.spec.ts` draft-trash and complete workspace identity lifecycle passed at `f0fbfa0`; current revision/correct world shown in reviewed history screen. |
| W55 | Active draft uses current revision; opening list refreshes it; conflict refresh requires second confirmation. | Desktop/mobile same-name workspace regression passed at `6d6fa2eb`: fresh metadata via history entry, concurrent HTTP 409, cancellation without deletion, new explicit confirmation, restore and unchanged other workspace. |
| W56 | Removed duplicate style editor; links point to specialized editors/recovery. | Browser return paths pending. |
| W57 | Issue 190 generator retained. | Six #190 mobile reference/production pairs inspected: idea, genre, review, running, error, result. Existing Idea 190 suite passed; no replacement of the later approved design. |
| W58 | Existing generator panels/presets and validation retained. | Existing Idea 190 tests retained. |
| W59 | Existing progress and recovery remain server-driven. | Controlled-provider draft recovery, reload, malformed/empty response and generation suites passed in full CI at `f0fbfa0`. |
| W60 | Existing import/generation transitions retained. | Import, generation and workspace lifecycle E2E passed at `f0fbfa0`; six later-reference generator states inspected. |
| W61 | Scenario editor receives explicit wid, isolated keyed instance, common workshop shell. | Desktop/mobile two-world identity and isolated input-buffer E2E passed at `f0fbfa0`; reload recovery and deliberately held late DELETE regression passed. |
| W62 | Scenario input buffer per wid; Radix summary-deletion confirmation. | Separate per-world input retention and scenario trash late-response regression passed at `f0fbfa0`; physical keyboard not tested. |
| W63 | Imported JSON remains editable in text buffer. | Build; browser invalid-file correction pending. |
| W64 | Pasted valid JSON array rejected; bracket-prefixed Markdown retained as text. | Unit array-vs-Markdown distinction and real pasted-state/wrapper/Markdown/broken-input E2E passed. |
| W65 | No scenario checkbox in import; empty input cannot submit. | File/paste import and empty-input paths passed in `draft-world.spec.ts`; no paid provider used. |
| W66 | Import continues to use existing path without LLM request. | Existing controlled-provider import/lifecycle tests passed; deterministic import path retained. |
| W67 | Launch pins wid/revision/version; warnings/stale/stop require separate choices; changed conditions invalidate. | Component invalidation tests and updated real launch E2E passed at `f0fbfa0`; all interactive confirmation combinations are not visually accepted. |
| W68 | Summary separates protagonist, control, camera, scene/place/time; scene edit preserves camera fields. | Found and fixed migration dropping explicit POV/subject. Server launch projection keeps subject separate from POV and hides inaccessible names. SQLite handoff covers different protagonist/control/POV and observer without protagonist; E2E added. 158 related backend tests passed. |
| W69 | Full launch summary and real API handoff; existing-save continuation retained. | Real launch, Narrative turn, save/reload, portraits and AI-version isolation E2E passed at `f0fbfa0`; full paired launch-dialog interaction acceptance remains open. |

## Initial validation (historical; superseded by completed runs below)

- Production TypeScript/Vite build succeeded (existing large-chunk warning remains).
- Final frontend suite: **134 passed** (20 files).
- Historical preview also handles malformed/incomplete saved candidates without mutation: frontend regression and real SQLite regression passed. Final focused backend: **18 passed**, plus the new incomplete-history case **1 passed**.
- Latest review/timeline/recovery verification: **34 passed**, plus **1 passed** for checked-revision/no-duplicate-version/stale projection.
- Focused backend suites: 64 passed after fixing the new-card removal/manual-path regression.
- Full backend run: **3203 passed, 1 skipped** in 917.64 s. Final targeted calendar/projection/Runtime handoff suite: **60 passed**.
- Playwright discovery: **644 tests / 92 files**. CI at `3cfacfc`: all four selected smoke jobs passed (desktop/mobile). Full E2E remains in progress; subsequent changes still require a fresh run. No full E2E success, visual acceptance, physical phone testing or paid-provider result is claimed.

## Browser evidence reviewed

Run [42069720818](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818) at `3cfacfc` produced **77 original/current pairs** (11 sections × 7 widths). The screenshot tests completed in both projects and detected no document-level horizontal overflow. This does not establish local-panel overflow, motion or full acceptance.

- Desktop artifact: [13435284825](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818/artifacts/13435284825).
- Mobile artifact: [13437102576](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818/artifacts/13437102576).
- Inspected all eleven desktop sections at 1440, plus mobile overview/cards/start/AI at 360. Original data is the prototype's demo; current data is `workshop188.json`. Different counts, names and portrait content are not pixel regressions. Location artwork remains excluded by the issue.
- Confirmed composition defects: an overlong overview lead/geography pushed cards below the fold, mobile collection controls occupied an extra row, start settings were below the context, AI composition lacked a panel and heading hierarchy. Follow-up changes shorten expandable previews, group collection controls, place start controls beside the textual preview, and restore the AI panel. Reviewed the follow-up desktop overview/start/cards/AI captures from `2060d80`: the start controls precede the context, the overview lead is bounded, and the AI composer has its own panel. Mobile and complete interaction-state acceptance remain open.
- Fixed test defects without suppressing checks: mobile search opens from the mobile menu; snapshot title is selected by accessible name; dossier tabs use `tab` semantics. The full jobs were cancelled by the newer commit, so their overall result is **not passed**.
- Extended the next evidence run with geometry/font/DPR/focus metadata and real Graphite/Parchment/Cyberpunk dossier portals, focus restoration and unchanged-canon assertions.

## Remaining acceptance gate

Keep the PR as draft until browser evidence is generated and reviewed, the pinned-master baseline is reproduced in an authorized browser environment, long-copy/crowded-world/skins/motion/keyboard cases pass, and all rows above have actual acceptance evidence. Do not close Issue 192 based on this ledger, a green build or an implementation report alone.

- Added explicit accepted re-audit decisions without inferring fixes from disappearing messages. Backend ownership/privacy/no-write/staleness regression passed; frontend outcome/stale-link regression added. The decision list does not claim that an opined or reformulated warning is a fixed world defect.

## Completed CI run and follow-up

At `43e991a`, run [42075038214](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42075038214) completed: backend **3209 passed, 1 skipped**, frontend passed, all four smoke jobs passed. Full E2E: desktop **162/163** and **152/159**, mobile **151 passed / 1 failed / 11 skipped** and **141 passed / 5 failed / 13 skipped**. Existing project skips are unchanged.

Confirmed defects fixed in follow-up: list portraits were vertically centered after the added personality text increased row height; reload during a scenario job hid the path back to its editor. Updated obsolete assertions for the explicitly requested AI action surface, version-number success message and rejection of pasted JSON arrays. No assertions were disabled or made optional. The separate POV migration defect was found by inspection and covered by real SQLite handoff tests. These follow-ups require a new complete CI result.

- W68 launch modal now shows the complete selected scene text; the browser fixture contains two distinct scenes at the same place.

- Mobile Graphite dossier capture exposed overlapping age/location/search rows caused by several children sharing hard-coded grid rows. Replaced that layout with explicit identity and switcher groups; added browser geometry assertions in all three skins.

- Mobile overview still hid cards below an oversized hero. Moved full setting/genre into an accessible disclosure, restored the corner edit action and four-column mobile statistics, and retained expandable untruncated source text.


## Continuation — completed 3d8ac389 CI and deterministic race regressions

Run [42080709704](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42080709704) completed: backend **3213 passed, 1 skipped**, frontend **134 passed**, all four selected smoke jobs passed, and both full mobile shards passed. Full desktop shards had **164 passed / 1 failed** and **160 passed / 1 failed**. No complete CI success is inferred from the mobile result.

The retained traces identify two timing defects. Search mounted its destination record while the outgoing Radix search layer still owned Escape/focus; navigation now waits for the search portal's close lifecycle. Deleting a scenario remounted its editor after a trash query had started, losing the open state and fetched rows; trash state now belongs to the persistent Preparation wrapper, and a late delete response cannot clear a newly selected workspace. The browser regression deliberately holds the DELETE response while opening/loading trash, then checks its state after the workspace changes. Tests remain strict, without extra timeouts or forced clicks.

The start-settings summary now uses the same server-projected five roles as the launch dialog. Its browser test checks POV before opening the launch dialog as well as the real handoff.

Reviewed the latest 360px overview and 390px places captures: the hero is bounded, four stats remain on one row, and the locations Add button is present. Source-content differences remain explicit. The evidence driver now uses the exact required viewport heights and adds 768×1024 / 1024×768 tablet boundaries; the previous seven-width, 900px-height series is historical evidence, not proof of those required dimensions. Fresh captures and full CI are required for these follow-ups.

## Latest continuation — verified fixes and remaining browser checks

The branch includes `master@cc326ce9f0377a1f305f9baa1dc37d82f62e4de7` (relationship-meter animations). This synchronizes the working branch; PR 195 is not merged.

- W45 stores observed structural fix history in author-only draft metadata, outside world canon. The original typed review predicates remain the single verifier. Same-job manual versions retain history; a new generation resets it. Repeated identical completed reports do not create versions or duplicate fixes. No migration or extra LLM call is introduced.
- Section entry animation now also wraps review and AI screens. A new browser test records actual opacity/translation/animation frames for original/current section and dossier transitions, reduced motion and mobile menu movement. It also verifies Escape, portal removal and restored focus. The test is added, not yet claimed passed.
- Inspected Graphite/Parchment/Cyberpunk dossier pairs on desktop and mobile from `3d8ac38`. The repaired mobile identity rows no longer overlap. Search and the three text actions still made the mobile header unnecessarily tall; mobile actions now share the avatar row as 44px icon buttons with accessible names. The original full text remains on desktop. A geometry assertion checks that the strip and actions do not overlap and the header leaves room for content. Fresh screenshots are required.
- Added W21/W22 browser coverage at 360×800 / 390×844 / 430×932 for empty motives, the canonical editor without a duplicate compatibility field, a long-name search, preserving the active tab while changing characters, avatar navigation and focus return.

Local validation for this continuation: the tracking/completeness/recovery/initial-draft/workshop backend selection passed **78 tests**; frontend passed **137 tests**; production build succeeded. Local browser execution remains blocked before any page assertion by Chromium's Unix-socket sandbox error. GitHub Actions is the browser execution environment; no physical Android/IME acceptance is inferred from it. Appendix 6 explicitly uses controlled provider responses and forbids paid API calls for this audit.

Run [42106147109](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42106147109) at `f0fbfa0` completed successfully: backend **3213 passed, 1 skipped**, frontend and all four smoke jobs passed, **all four Full E2E shards passed**. This verifies the two modal/trash timing regressions and the exact-viewport capture driver. The newer W11/W21/W45, motion and atomic-editor tests described above require their own fresh CI run; this success is not attributed to those later changes.

The new atomic-editor browser test uses a real concurrent API write, expects HTTP 409 without partial mutation, reloads the stored buffer, explicitly discards it, then verifies that changing two fields creates exactly one revision/version.

### Exact viewport evidence and tablet follow-up

The `f0fbfa0` capture jobs produced 99 base-state pairs (11 sections × 9 sizes, including the extra 412×915 device width), plus six skin dossier pairs. Reviewed all 11 base sections at 390×844 and tablet overview/cards/start/AI at 768×1024 plus overview/review/history at 1024×768. Required 768px captures exposed overly narrow side-by-side start panels and a wrapping “Персонаж” button. Start panels now stack through 960px; primary heading actions do not shrink or split their label. Browser geometry assertions cover both defects. Thread headings now use the book face with a bounded three-line preview; the complete text remains below.

The unknown feelings value also has explicit accessible value text: screen readers distinguish “Не задано” from an actual zero. Stored dimensions remain unchanged until an edit. These final visual/a11y adjustments require a new browser run after the in-flight `235b00a3` suite.

### Recovered historical baseline (limited)

Recovered and inspected the retained browser artifacts from successful run [42051309940](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42051309940), created **2026-11-05 15:04:56 UTC**, before Issue 192 implementation. Both its PR head `66674050b81047fdd7c9d11dd94d202f014ed923` and the actual Actions checkout `4b99436faa893ea8c65a10e9b0ea1c9caac8cbf7` have tree `6ea82456e75463227622346bf00cafa6d7ca30cf`, identical to the original `master@eaf75a1` tree. This is original-master evidence, not a reconstruction from changed code.

- Sources: desktop shard 2 artifact [13426729578](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42051309940/artifacts/13426729578), mobile shard 2 artifact [13428018461](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42051309940/artifacts/13428018461).
- Compared matching `anna-cards`, `field-error-graphite` and `ai-empty-graphite` captures against `f0fbfa0`. The two source fixtures are unchanged; the Anna test setup and capture are unchanged before/after. Changes preceding the field-error capture are navigation semantics and the requested persistent AI action surface, not fixture data.
- The desktop AI comparison confirms the restored composed panel and hierarchy; cards show the fuller personality/details and compact mobile toolbar; the field-error state retains its source text/diagnostics and gains explicit discard.
- **Excluded mobile AI captures from settled-layout acceptance:** both historical/current captures caught the menu closing. They are transient evidence, not a valid finished-page comparison. The new motion test samples actual frames separately.
- This recovery covers only existing historical scenarios at their original Desktop Chrome / Pixel 7 settings. It does not supply all 11 sections, required viewports, every interactive state or the missing pre-edit measurement manifest. It was recovered after implementation and is not presented as a newly captured pre-edit baseline.

### Completed `235b00a3` run

Run [42109622727](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42109622727) completed: backend **3220 passed, 1 skipped**, frontend **137 passed**, four smoke jobs passed. Full desktop shard 1: **165 passed**; shard 2: **163 passed / 2 failed**. Full mobile shard 1: **154 passed / 11 skipped**; shard 2: **151 passed / 1 failed / 13 skipped**.

All three failures were in the newly added assertions, diagnosed from logs and retained traces. The empty-motives locator also matched a nested “Сведения” summary; it now selects the direct disclosure heading. The desktop reduced-motion assertion incorrectly required `transform:none`, rejecting the fixed centering matrix `matrix(1, 0, 0, 1, -520, -425)`. Captured frames show a constant position, opacity 1 and no animations. The corrected assertion requires no animations/animated translate, constant transform, constant X/Y and full opacity; desktop centering is preserved. No production behavior or assertion is disabled to obtain a pass.

The real 409 / retained buffer / explicit discard / two-fields-one-version case passed in both projects. Normal section/dossier motion and mobile normal/reduced menu motion passed. Reviewed the fresh mobile Graphite/Parchment/Cyberpunk dossier captures: compact actions, separate identity/search rows and reachable footer are visible; all geometry assertions passed. The selector and stationary-layout corrections, plus tablet layout changes, require the next CI run.

### Additional critical interaction coverage

The history-page “Мои черновики и корзина” shortcut did not refresh list metadata, unlike the sidebar entry. Both now use one refresh handler. New real SQLite/browser tests cover this entry with two same-name workspaces, an overview edit, a concurrent revision, HTTP 409, cancellation without deletion, a fresh explicit decision, trash restore and preservation of the other workspace.

Additional browser cases exercise all five search result types with Tab/Enter, hidden-canon exclusion in the player projection, no-results versus empty-query states; feeling sliders with Home/End/ArrowLeft, −100/0/100, unset distinct from zero, two values in one version, unchanged reverse edge and restore; and a custom 30-day calendar with invalid day rejection, a month/midnight boundary and unchanged camera/agency. These are added tests, not yet claimed passed. Fixture validation and production build pass locally.

**W31 scope conflict:** the issue asks to support custom dimension keys. The existing canonical contract in `backend/services/relation_dimensions.py`, `draft_initial.py` and `runtime_v3/models.py` explicitly accepts only seven named dimensions. A real validation probe with `custom:23` returns a structural error. The editor does not discard an existing unknown key and permits removing it, but this is not custom-dimension support in a playable world. This PR does not silently relax the shared generation/Runtime contract. Arbitrary canonical dimensions remain an unresolved requirement and must not be marked accepted.


The final code review also found that replacing an instruction with an example after a lost submission response retained the old idempotency key. Instruction changes now share one reset path; retrying unchanged text retains its key. A focused component regression passed: cancel/accept example emits no request, unchanged retry reuses the key, accepted replacement submits a different key and the new text. Nullable protagonist/controlled/POV types now match the observer API contract; this changes no runtime behavior.


### Final tablet review

Reviewed the `1a0e3766` reference/current pairs for places, relationships, stories, chronology, knowledge, review, AI and history at both 768×1024 and 1024×768. The history export row was clipped by the inner scroll surface at tablet width; document overflow alone did not detect it. Export buttons now wrap within their parent and retain readable labels. The comparison test checks the bounds and text overflow of all four controls at every required viewport. Production build passed; final browser verification is pending.


### Completed `6d6fa2eb` run and final corrections

Run [42117776408](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42117776408): backend **3220 passed / 1 skipped**, frontend **138 passed**, production build and four smoke jobs passed. Full E2E: desktop **168 + 165 passed**, mobile **157 + 152 passed / 24 existing skips**; one failure per project, both in the new W43 test. The test used the old frontend fallback label rather than the actual Runtime label “Минута мира”; the captured accessibility tree and desktop trace identify the mismatch. Exact accessible-name selectors are corrected; no checks are removed. The remaining three new critical scenarios passed on both projects. A real FastAPI/SQLite probe separately verified invalid custom date rejection, month-boundary arithmetic and saving minute 1450 without changing the calendar contract.

The final browser correction also records CSS timing functions, keyframe easing and animation delay alongside effect timing: effect-level `easing` alone can report linear while CSS keyframes use another curve. These new measurements, export button wrapping/bounds and corrected calendar selectors still require the next run.
