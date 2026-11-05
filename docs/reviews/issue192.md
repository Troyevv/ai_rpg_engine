# Issue 192 — implementation and acceptance ledger

## Reference and baseline

- Base: `master@eaf75a13e8b5e5cc1b9ed855a17b40be608fd3ec` (fresh checkout; matches the issue audit).
- Read the issue and all six appendix comments. Original reference: Issue 175 attachment `world-workshop-reference.zip`.
- Original `world-workshop.html`: **468501 bytes**, SHA-256 **4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1**. Verified before edits.
- `tests/fixtures/workshop175-reference.zip` contains only that byte-identical HTML. The preview JPG and README are excluded. No demo state or JavaScript is imported into production. The E2E server independently verifies the hash before serving it.
- **Pre-change browser baseline was blocked.** Local Chromium terminated with `socket() failed: Operation not permitted (1)` in `process_singleton_posix.cc`. The separate cloud browser could not reach the local server (`ERR_CONNECTION_REFUSED`). No baseline PNGs were obtained. Source inspection, unit tests and build are not substitutes for baseline measurements.
- `00-workshop192.spec.ts` captures original/current pairs at 360×800, 390×844, 412×915, 430×932, 768×1024, 1024×768, 1280×800, 1440×1000 and 1920×1080 and records browser/font/overflow metadata. Those captures are post-change evidence, not the missing pre-change master baseline. The later Issue 190 prototype remains the reference for “По моей идее”.

## Status conventions

**Implemented** means code exists; it does not imply browser acceptance. **Preserved** means the existing implementation was retained. The initial 77 base-state pairs have been captured; every visual item still requires its complete interaction-state comparison; motion, keyboard, focus, physical mobile keyboard and theme acceptance are open until observed. There is no agreed design deviation beyond those already authorized by Issues 175/190 (real Runtime, projected canon, existing skins/portraits, separate Narrative, real presets and recovery).

| ID | Implementation / retained contract | Acceptance evidence or remaining work |
|---|---|---|
| W01 | Search indexes projected characters, locations, organizations, threads and facts, including text/aliases. | Unit test; SQLite/browser navigation test added, not yet accepted. |
| W02 | Empty search suggests objects; nonempty misses show a distinct state. | Unit test; render pending. |
| W03 | Overview diagnostics retain source paths and object links. | Review browser links including incomplete candidates. |
| W04 | Overview opens atomic campaign editor and stays in overview. | Atomic write test; browser return pending. |
| W05 | Public lead precedes expandable full author description. | Reader projection tests; visual pending. |
| W06 | Last three actual version reasons and timestamps. | API source retained; timezone/visual check pending. |
| W07 | Overview seeds AI example without overwriting stored instruction. Example replacement requires a decision. | Browser buffer/return pending. |
| W08 | Stats, compact first four cards and start-scene panel retained. | Reference comparison pending. |
| W09 | Mobile breadcrumb shows current section; generic prefix hidden. | Browser widths pending. |
| W10 | AI sidebar action has separate visual surface. | Visual/theme acceptance pending. |
| W11 | Navigation focuses content without scrolling; per-world/section scroll retained. The mobile menu defers focus until its portal closes; section changes from overview CTAs also transfer focus. | Real-frame E2E checks focus after desktop/mobile navigation; new check awaits CI. |
| W12 | Read/action/revision states separated; field dirty/saving state reflects actual state. | Review failed/pending requests and child-dialog status propagation. |
| W13 | Existing theme typography retained. | OPEN: measure font families, weight, widths in all required themes. |
| W14 | Overview panel surfaces differentiated using skin tokens. | Visual/theme acceptance pending. |
| W15 | Existing modal backdrop retained. | Compared actual Graphite/Parchment/Cyberpunk portals: the global UI override removed blur. Restored the exact #175 scrim `#070a09ba` / `blur(9px)` only in the workshop; #190 atelier remains separate. Computed-style E2E assertion added; final capture pending. |
| W16 | Local create form before mutation; nonempty name required, description editable; cancel does not write. | Backend + component tests; E2E added. |
| W17 | Explicit ordered source/target; backend rejects self/missing/duplicate pair. | SQLite test verifies exact edge and no extra revision. |
| W18 | Full cards show personality; overview stays compact; portrait contract retained. | Crop and card density need browser review. |
| W19 | Family/organization filters use projected objective relations and roles. | Fixture/browser filter verification pending. |
| W20 | Pagination controls omitted for one page; existing bounded 12-card pages retained. | Existing 240-character E2E retained; rerun required. |
| W21 | Dossier hero/current-location context and character-name label. Empty motives collapse into one disclosure. Compatibility card projections do not duplicate canonical Runtime fields; every real editable contract remains available. | Added real SQLite/browser case for empty legacy/canonical intentions. Existing six skin portal pairs inspected; compact mobile actions need fresh captures. |
| W22 | Mobile horizontal portrait strip and searchable all-person select. | Browser touch/keyboard and 240+ people pending. |
| W23 | Isolated per-world multi-field buffers; one patch_fields transaction; explicit discard. | Backend/component tests cover atomic fields, conflict and buffers. |
| W24 | Existing field/card generator can produce a scoped preview; apply/reject is separate. | SQLite controlled-provider test: one call, unchanged canon before decision, stale rejection. Controlled-provider browser case passed in `workshop188-editing.spec.ts` at `3d8ac38`; paid-provider calls are not an acceptance requirement. |
| W25 | Existing procedural/photo/manual-age behavior retained; hover scaling is outside crop. | Existing portrait suites retained; browser recheck pending. |
| W26 | Collection search includes description/text/context/aliases. | Browser localized search pending. |
| W27 | Place/org metadata, starting-place badge, projected participants and organization locations. | Browser hierarchy and long-content check pending. |
| W28 | Parent dropdown excludes self/descendants; backend rejects cycles and unknown parent. | SQLite parent-cycle test. |
| W29 | Residence grouping and separate Runtime editors retained. | Existing regressions retained; browser pending. |
| W30 | Directed relation row uses stretched native action; inner controls remain separate. | Browser hit-target/keyboard check pending. |
| W31 | Seven feeling sliders plus custom dimensions; unset stays absent. | Component unknown-value test; browser endpoints pending. |
| W32 | Family duplicate shortcut opens actual server merge plans; zero-count text is structural only. | Existing merge contract retained; browser duplicate fixture pending. |
| W33 | Dossier tabs use tablist/tab/tabpanel and roving keyboard behavior. | Existing E2E selectors updated to semantic roles; execution pending. |
| W34 | Thread/fact/scene/event creation forms use single atomic add. | Six-type SQLite tests; browser cancel/create added. |
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
| W48 | AI examples, world/version context, three steps and empty proposal area. | Component/build checks; visual pending. |
| W49 | Skeleton shown only for actual active editor job, old diff hidden during generation. | Controlled-provider E2E retained; browser pending. |
| W50 | First changed diff expanded and before/after surfaces distinct. | Existing diff tests updated for expanded default; browser pending. |
| W51 | Applied proposal links to available object and immutable base version. | Browser object/base-version navigation pending. |
| W52 | Author-only owned snapshot read, timestamp, preview, explicit restore; stale head blocked. | SQLite ownership/no-write/restore/conflict tests; E2E added. |
| W53 | Separate readable TXT omits headings/payload; legacy TXT/MD/JSON round trips retained. | Backend export test and existing portrait round-trip tests. |
| W54 | Draft rows expose revision and current-world marker. | Browser identical-name/delete/restore pending. |
| W55 | Active draft uses current revision; opening list refreshes it; conflict refresh requires second confirmation. | Browser concurrent deletion check pending. |
| W56 | Removed duplicate style editor; links point to specialized editors/recovery. | Browser return paths pending. |
| W57 | Issue 190 generator retained. | Existing unit/build checks; all later-reference screenshots pending. |
| W58 | Existing generator panels/presets and validation retained. | Existing Idea 190 tests retained. |
| W59 | Existing progress and recovery remain server-driven. | Existing backend recovery tests in full suite; E2E pending. |
| W60 | Existing import/generation transitions retained. | Full related E2E pending; no visual acceptance inferred. |
| W61 | Scenario editor receives explicit wid, isolated keyed instance, common workshop shell. | Two-world browser identity/buffer test added; late-response acceptance pending. |
| W62 | Scenario input buffer per wid; Radix summary-deletion confirmation. | Browser cancel/reload/isolation pending. |
| W63 | Imported JSON remains editable in text buffer. | Build; browser invalid-file correction pending. |
| W64 | Pasted valid JSON array rejected; bracket-prefixed Markdown retained as text. | Unit test. |
| W65 | No scenario checkbox in import; empty input cannot submit. | Existing import API remains deterministic; browser pending. |
| W66 | Import continues to use existing path without LLM request. | Existing import tests retained. |
| W67 | Launch pins wid/revision/version; warnings/stale/stop require separate choices; changed conditions invalidate. | Component test; existing real launch E2E updated for explicit choices. |
| W68 | Summary separates protagonist, control, camera, scene/place/time; scene edit preserves camera fields. | Found and fixed migration dropping explicit POV/subject. Server launch projection keeps subject separate from POV and hides inaccessible names. SQLite handoff covers different protagonist/control/POV and observer without protagonist; E2E added. 158 related backend tests passed. |
| W69 | Full launch summary and real API handoff; existing-save continuation retained. | Existing post-start save/portrait/AI tests retained; browser acceptance open. |

## Validation

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
