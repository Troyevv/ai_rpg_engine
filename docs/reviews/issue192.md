# Issue 192 — implementation and acceptance ledger

## Reference and baseline

- Base: `master@eaf75a13e8b5e5cc1b9ed855a17b40be608fd3ec` (fresh checkout; matches the issue audit).
- Read the issue and all six appendix comments. Original reference: Issue 175 attachment `world-workshop-reference.zip`.
- Original `world-workshop.html`: **468501 bytes**, SHA-256 **4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1**. Verified before edits.
- `tests/fixtures/workshop175-reference.zip` contains only that byte-identical HTML. The preview JPG and README are excluded. No demo state or JavaScript is imported into production. The E2E server independently verifies the hash before serving it.
- **Pre-change browser baseline was blocked.** Local Chromium terminated with `socket() failed: Operation not permitted (1)` in `process_singleton_posix.cc`. The separate cloud browser could not reach the local server (`ERR_CONNECTION_REFUSED`). No baseline PNGs were obtained. Source inspection, unit tests and build are not substitutes for baseline measurements.
- `00-workshop192.spec.ts` captures original/current pairs at 360/390/412/430/1280/1440/1920 px and records browser/font/overflow metadata. Those captures are post-change evidence, not the missing pre-change master baseline. The later Issue 190 prototype remains the reference for “По моей идее”.

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
| W11 | Navigation focuses content without scrolling; per-world/section scroll retained. | Keyboard browser verification pending. |
| W12 | Read/action/revision states separated; field dirty/saving state reflects actual state. | Review failed/pending requests and child-dialog status propagation. |
| W13 | Existing theme typography retained. | OPEN: measure font families, weight, widths in all required themes. |
| W14 | Overview panel surfaces differentiated using skin tokens. | Visual/theme acceptance pending. |
| W15 | Existing modal backdrop retained. | OPEN: compare opacity/blur against original in real browser. |
| W16 | Local create form before mutation; name/description required; cancel does not write. | Backend + component tests; E2E added. |
| W17 | Explicit ordered source/target; backend rejects self/missing/duplicate pair. | SQLite test verifies exact edge and no extra revision. |
| W18 | Full cards show personality; overview stays compact; portrait contract retained. | Crop and card density need browser review. |
| W19 | Family/organization filters use projected objective relations and roles. | Fixture/browser filter verification pending. |
| W20 | Pagination controls omitted for one page; existing bounded 12-card pages retained. | Existing 240-character E2E retained; rerun required. |
| W21 | Dossier hero/current-location context and character-name label. | Motive layout and browser comparison pending. |
| W22 | Mobile horizontal portrait strip and searchable all-person select. | Browser touch/keyboard and 240+ people pending. |
| W23 | Isolated per-world multi-field buffers; one patch_fields transaction; explicit discard. | Backend/component tests cover atomic fields, conflict and buffers. |
| W24 | Existing field/card generator can produce a scoped preview; apply/reject is separate. | SQLite controlled-provider test: one call, unchanged canon before decision, stale rejection. Real-provider browser acceptance pending. |
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
| W45 | Distinguishes absent/stale/completed review; merges severity and paths; category counts/filter; pins checked revision. | Priority/duplicate unit test and revision/no-op/stale SQLite test. OPEN: confirmed-resolution history and full recovery browser acceptance. |
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
| W68 | Summary separates protagonist, control, camera, scene/place/time; scene edit preserves camera fields. | Runtime handoff suite in full run; observer/no-protagonist browser pending. |
| W69 | Full launch summary and real API handoff; existing-save continuation retained. | Existing post-start save/portrait/AI tests retained; browser acceptance open. |

## Validation

- Production TypeScript/Vite build succeeded (existing large-chunk warning remains).
- Final frontend suite: **132 passed** (19 files).
- Latest review/timeline/recovery verification: **34 passed**, plus **1 passed** for checked-revision/no-duplicate-version/stale projection.
- Focused backend suites: 64 passed after fixing the new-card removal/manual-path regression.
- Full backend run: **3203 passed, 1 skipped** in 917.64 s. Final targeted calendar/projection/Runtime handoff suite: **60 passed**.
- Playwright discovery: **644 tests / 92 files**. CI at `3cfacfc`: all four selected smoke jobs passed (desktop/mobile). Full E2E remains in progress; subsequent changes still require a fresh run. No full E2E success, visual acceptance, physical phone testing or real DeepSeek result is claimed.

## Browser evidence reviewed

Run [42069720818](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818) at `3cfacfc` produced **77 original/current pairs** (11 sections × 7 widths). The screenshot tests completed in both projects and detected no document-level horizontal overflow. This does not establish local-panel overflow, motion or full acceptance.

- Desktop artifact: [13435284825](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818/artifacts/13435284825).
- Mobile artifact: [13437102576](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42069720818/artifacts/13437102576).
- Inspected all eleven desktop sections at 1440, plus mobile overview/cards/start/AI at 360. Original data is the prototype's demo; current data is `workshop188.json`. Different counts, names and portrait content are not pixel regressions. Location artwork remains excluded by the issue.
- Confirmed composition defects: an overlong overview lead/geography pushed cards below the fold, mobile collection controls occupied an extra row, start settings were below the context, AI composition lacked a panel and heading hierarchy. Follow-up changes shorten expandable previews, group collection controls, place start controls beside the textual preview, and restore the AI panel. Their final screenshots must still be reviewed.
- Fixed test defects without suppressing checks: mobile search opens from the mobile menu; snapshot title is selected by accessible name; dossier tabs use `tab` semantics. The full jobs were cancelled by the newer commit, so their overall result is **not passed**.
- Extended the next evidence run with geometry/font/DPR/focus metadata and real Graphite/Parchment/Cyberpunk dossier portals, focus restoration and unchanged-canon assertions.

## Remaining acceptance gate

Keep the PR as draft until browser evidence is generated and reviewed, the pinned-master baseline is reproduced in an authorized browser environment, long-copy/crowded-world/skins/motion/keyboard cases pass, and all rows above have actual acceptance evidence. Do not close Issue 192 based on this ledger, a green build or an implementation report alone.
