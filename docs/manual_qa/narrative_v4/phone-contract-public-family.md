# PR #120: phone contract and public family directory

This report supersedes the DOB/family visibility statements in the earlier UI acceptance report. Base: `da3f0dba80c7e2c6d8c6e3edea4fcef151e50feb`; same PR branch, no merge. The newer product specification explicitly makes canonical birthdays and family structure public UI reference information. It does not grant this knowledge to NPCs or disclose unrelated secrets.

## Cause and implementation

The old prompt requested a wrapper but published the inner proposal schema. Consumers could pass a string operation into Runtime, then finalize a failed communication as a successful turn/missed call. No original DeepSeek response was supplied; the reproduction uses controlled responses through production services.

`remote_decision.py` now owns the required wrapper schema and strict parser (`remote-decision/1`). Both ordinary `remote_initiative.stage` and communication continuation consume it. Only a complete valid legacy flat proposal is wrapped; IDs, unknown fields and malformed JSON are never repaired. Runtime `accept` remains the authority for permissions/options and effects. Duplicate JSON keys are rejected.

Communication raises on parse/schema/Runtime failure before finalization. The durable outgoing command remains; staged read/reply changes, time, turn and success receipt are not committed. Frames distinguish raw responses from accepted checkpoints. Retry replays accepted source-bound work and makes a fresh attempt for rejected frames, preserving the old prompt/raw/error under `previous_attempt`. Current technical instructions are used with original user context. Existing revision, worker epoch, source/receipt lineage and shared four-decision budget remain in force. Retry is explicit, not a background repair loop. The same-job SSE subscription now follows `attempt_epoch`, fixing a reproduced UI hang after successful Retry.

The phone distinguishes technical failure from refusal/silence, retains Retry and end/cancel, and exposes full save-scoped diagnostics on demand. Normal toasts do not contain private prompt/raw data. Existing usage instrumentation records actual provider attempts. No API key is added to diagnostics.

Calendar endpoint and nearby-date projection include canonical DOB independently of Knowledge/control. Genealogy roots include all Characters; graph edges are an allowlist of objective family relations with canonical statuses. Names/DOB/life status are public; raw facts, reasons, provenance and unrelated social relations are not. Existing portrait authorization is unchanged. Full calendar queries retain all birthdays within their bounded date range; nearby dates remain a compact preview. Graph windows retain depth/node limits and truncation indication; global root search and recenter reach other branches.

No production dependencies, DB migrations, historical snapshot rewrites or new persisted family world are introduced. The existing #78 loader gains `ui-public-directory`, with no contacts/Knowledge and a canonical DOB for Zoya.

## Legacy recovery

For an old already-saved communication with a rejected report, the turn shows a recovery explanation beside the existing **Ещё вариант** action. It regenerates from the recorded source boundary, without resending the command. Existing confirmation warns that later turns will be archived. The original erroneous variant remains selectable; historical snapshots are not rewritten. This path is tested with a later ordinary turn and selection of the original variant. It is intentionally an explicit user action, not silent migration.

## Requirement map

| Requirement | Implementation / evidence |
|---|---|
| R01 | `remote_decision.py`; production prompt schema equality and negative schema tests; [actual fixture prompt/schema/raw→validated](pr120-contract-evidence/production-contract.json) |
| R02 | Both remote consumers use shared parser; strict flat compatibility followed by unchanged `accept` |
| R03 | Failed call and staged read tests compare entire durable snapshot, turn count and job error; no success commit |
| R04 | Accepted checkpoints, fresh rejected attempts, legacy flat replay, concurrent retry, epoch/lineage and legacy saved recovery tests |
| R05 | Phone error/retry/details, save-scoped diagnostics endpoint; desktop/mobile two-skin recordings |
| R06 | Calendar endpoint + save preview; public DOB tests including 510 birthdays, leap day and birth boundary |
| R07 | All roots + canonical family allowlist; separate/empty/dense families and no-Knowledge UI |
| R08 | Private calendar, social Knowledge, phone/asset/save guards retained; privacy regression suites |
| R09 | Existing loader, projections and legacy variants; no migrations; documentation and regression |

Test paths below are relative to `tests/`, or `frontend/e2e/` for browser suites. Browser/provider fixtures replace only external model output, not canonical responses or final state.

| Test | Executed coverage / result |
|---|---|
| T01 | `test_remote_decision_contract.py`: production `planning_context` schema equals parser model; valid wrapper/null/flat. Actual fixture contract attached. |
| T02 | `test_communication_cycle.py`: answer/decline/read/send through `run`; contract test identifies endpoint through parser + `accept`. |
| T03 | Cycle silent/read-only outcomes and ordinary stage null tests. |
| T04 | Strict flat equivalence, canonical identify, legacy flat checkpoint replay with provider forbidden. |
| T05 | Parameterized missing/wrong root/enum/type/basis/extra fields. |
| T06 | Empty/truncated/multiple objects/duplicate keys rejected. |
| T07 | Contract invalid actor/event; existing `test_remote_communication.py` guards for basis/path/knowledge/membership. |
| T08 | Whole snapshot equality after failed call; job error and unchanged turns; real browser call remains ringing. |
| T09 | Schema failure after accepted staged read: no commit; retry makes only one additional provider call. |
| T10 | Legacy flat checkpoint replays unchanged raw with normalization metadata; malformed frame replaced with preserved previous attempt. |
| T11 | Cycle provider outage/retry; phone E2E provider error/reload and original source; existing job recovery tests. |
| T12 | Duplicate request tests and concurrent retry (only one claimant); one outgoing event after completion. |
| T13 | Cycle cancellation/owner/stale revision tests; UI end/cancel. |
| T14 | Cycle regenerate/variants/stale retry; original variant restoration in legacy recovery test. |
| T15 | Old saved rejected report + later ordinary turn → explicit regenerate → answered; original erroneous variant preserved. |
| T16 | Phone E2E real API/jobs read→reply; cycle one-way contact test does not synthesize reverse contact. |
| T17 | Phone E2E outgoing answer → Narrative channel → end; physical camera/location unchanged. |
| T18 | Cycle/E2E decline, null, read-only, unavailable; group shared budget and timeout tests. |
| T19 | Ordinary stage uses same parser; null vs rejected metadata and unchanged remote world. |
| T20 | Technical failure/retry E2E desktop/mobile, Graphite/Parchment, reduced motion; existing draft/keyboard/reload E2E. |
| T21 | Public directory API + browser month/year with no Knowledge; all canonical DOB test. |
| T22 | Public character roster and birth-boundary tests; existing birth-identity/reproduction regression. |
| T23 | Leap-day/birth boundary tests; custom-calendar year-boundary browser test and calendar regression. |
| T24 | Public roots without contacts/Knowledge; separate-family and empty-family E2E. |
| T25 | `test_life_social.py` canonical hidden adoption/closed relation/name assertions; public family allowlist test. |
| T26 | Observerless projection and read-only snapshot tests; existing control/rollback/variant regression. |
| T27 | 510 birthdays beyond preview/page limit; dense graph E2E truncation and recenter; root search includes all Characters. |
| T28 | Private observance/scheduled-event tests retained; family excludes private facts; scoped diagnostic rejects another save; full phone/assets regression. |
| T29 | Existing snapshot fixtures require no new fields; views compare unchanged state/revision and have no model call path. |
| T30 | `runtime-handoff.spec.ts`: Start Game → ordinary turn → persisted save/reload → next ordinary turn, desktop/mobile; Tabletop regression and production build. |

| Gate | Result |
|---|---|
| G1 | Shared production schema/parser and both consumers verified. |
| G2 | Atomic technical errors, full diagnostics and working same-source Retry verified. |
| G3 | API/job message and call paths, including autonomous null/refusal verified. |
| G4 | Public DOB API/month/year and existing recurrence verified. |
| G5 | Public canonical roots/relations, separate families and bounded traversal verified. |
| G6 | Privacy, lineage, budgets, skins, localized UI and Tabletop regression verified. |
| G7 | Matrix and evidence attached to existing PR; environment limits below are explicit. |

## Commands and results

- `python -m pytest -q`: **2150 passed in 301.16 s** ([log](pr120-contract-evidence/backend-full.log)). This run collected before the last five compatibility/schema cases and the deceased-DOB case; the final focused run below covers those additions and the diagnostic usage projection.
- `python -m pytest -q tests/test_remote_decision_contract.py tests/test_public_family_directory.py`: **33 passed**, including final strict-field, legacy-flat checkpoint and deceased-DOB tests.
- Focused integration/privacy/calendar/communication run: **120 passed** (attached log); these overlap the full suite and are not added together.
- `npm --prefix frontend run build`: passed TypeScript/Vite; existing main-bundle size advisory remains.
- From `frontend`: `PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell npx playwright test e2e/phone-completion.spec.ts e2e/completion-matrix.spec.ts e2e/runtime-handoff.spec.ts e2e/tabletop.spec.ts --output=/tmp/pr120-public-ui-final`: **38 passed**, including mandatory smoke on both projects.
- Final phone error/details/Retry refinement: same environment, `npx playwright test e2e/phone-completion.spec.ts --grep 'technical call failure' --output=/tmp/pr120-public-error-ui`: **2 passed**, each loops both skins (mobile 360×800; desktop 1440×1000).

An initial UI run exposed old four-node expectations after public family disclosure and a real same-ID Retry SSE bug. Expectations and subscription were fixed; the subsequent 38-test run passed. Initial backend failures were six superseded hidden-DOB/family expectations; private-event/authorization tests were retained.

## Evidence and limits

[Evidence index](pr120-contract-evidence/README.md) contains real screenshots, videos, production prompt/schema/raw examples and logs. Prior UI before/after evidence remains in `pr120-final-evidence`; the new recordings show failure → Retry → answered without a duplicate call. Screens were visually reviewed, including mobile Retry/cancel reachability and public family layout.

No live paid DeepSeek call or original user save/raw log was available. Deterministic provider tests are not live-provider tests. Mobile is Chromium touch/viewport emulation, not physical Android/OS keyboard/Back or GPU instrumentation. The entire repository E2E suite is not claimed green: previously reproduced generator timeouts on master remain documented in the earlier report and were not changed in this scope. No new failing targeted checks remain.
