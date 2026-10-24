# Issue #44 — live acceptance, 2026-10-24

**NOT ACCEPTED. Keep PR #105 Draft. No live scenario reached Start Game.**

Baseline: `b7f11f80dbc419f86c3ab7c57869b133dbb82643`. Existing author-document/compiler architecture and Runtime invariants are retained.

## Fixes grounded in observed failures

- Extraction's JSON Schema previously allowed/defaulted `origin=generated`, while the DTO's validator prohibited it. Extracted entities now require explicit origin in the schema.
- Remove arbitrary 200/3000-character plan-summary ceilings without truncation. Record counts, input/context/output ceilings and the 3000-record aggregate limit remain enforced.
- Live A returned an empty, supposedly complete creative plan with no exact opening time. Planning now explicitly owns creative expansion and receives cast targets; empty completion and unusable opening anchors are rejected before accepting the page.
- The advertised page schema now uses the scheduler's actual record allowance. Real responses still exceeded that allowance. Python now validates and retains the entire bounded response, checkpoints surplus records, and materializes subsequent bounded pages without another provider call. Tests cover preservation, duplicate/aggregate rejection and resume after interruption without re-querying the plan.
- Opening time gets a request schema distinct from vague historical time: exact clock, date/weekday anchor, no period/day offset, ISO date shape and explicit zero-based weekday mapping. The historical DTO and canonical compiler are unchanged. Unused historical schema definitions are removed from planning requests to preserve 8192-token compatibility.
- Live B used unqualified plan references. Only an exact unique registered key is qualified to `section/key`; unknown and ambiguous references remain blocking.
- Live C used exact character names in analysis observations instead of registry keys. Only exact unique extracted names are normalized; ambiguous names, inflections and unregistered references remain errors. No fuzzy identity merge or invented entities.

The internal page `continuation` is excluded from provider schemas. Existing pages without it remain readable. No database/save migration or Runtime validator change is introduced. New creative output quality is not proven by these deterministic fixes.

## Actual DeepSeek results

Model: `deepseek-flash`, non-thinking; effective user context 32768, output ceiling 12000. The provider SDK was used through the real Preparation/API/SQLite path, with a serial budget guard. Missing local `socksio` was installed before successful generation dispatch. Credentials were transient and are absent from committed files and the checkpoint archive.

| Scenario | Evidence | Unverified/blocker |
| --- | --- | --- |
| A: short Moscow/НИИ idea | Real analysis; three paid planning responses across debugging. First plan was empty; subsequent plans exceeded page size. Accepted analysis retained. | Planning paid-retry allowance exhausted before lossless pagination was implemented. No compiler, canonical world, editor, Start Game or ordinary live turn. |
| B: full Volkov/Apex source | Entire original source retained; all eight named characters extracted. The full source is `tests/fixtures/world_authoring/volkov_user_brief.txt`. Three paid planning attempts. The last real response had 32 records and Friday index 4, 08:00. Revalidation of this saved response after fixes required no additional paid planning request. Both plan pages and aggregate plan are completed in SQLite. | First expansion request was interrupted after automatic approval review rejected continuation as an exhausted planning retry. Its outcome/usage is unknown and reserved in full. No further B calls were made. Full traits, subsidiaries, family/Knowledge semantics, canonical state and gameplay are NOT accepted. |
| C: fictional dystopia with humans/androids | Two real analysis responses reproduced display-name/key mismatch. The second saved response validates after exact-name normalization, without another API request. | Next document request was blocked BEFORE dispatch because its worst-case reservation exceeded the remaining token allowance. Species semantics, world compilation and gameplay remain unverified. |

Saved-response replay means revalidating bytes actually returned by DeepSeek, not fabricating a successful response. It is not proof of fresh end-to-end generation. SQLite attempt counters include local revalidation; no failing paid planning stage was sent more than three times.

## Spending and stop conditions

See `issue44-live-usage.json` for the sanitized per-attempt ledger.

- 13 actual HTTP requests: 2 model-list access probes and 11 generation calls.
- 10 generation calls returned usage: 32,766 input + 29,734 output = **62,500 tokens**.
- 1 interrupted expansion call has no usage: **53,335 tokens** remain conservatively reserved.
- Accounted total: **115,835 / 150,000 tokens**. Remaining allowance: 34,165; insufficient for the next C document's reservation.
- Estimated known charge: **$0.020817252** using published Saturday/off-peak Flash cache-hit/miss/output tariffs. This is usage-based estimation, not a billing statement.
- Conservative accounting ceiling, including uncertainty: **$0.46334 / $3**, using $4/M tokens for reservation. Actual total spend is unknown until the interrupted request is reconciled. Software checks are not a guaranteed financial cap.
- The ledger request counter is 14 because it also counts one local `ImportError` before SDK construction/network dispatch; that attempt was proven not sent and its token reservation released.
- No simultaneous paid generation, no provider automatic retries, no increased user spending/token/request limits. Budget is checked before each dispatch; unknown outcomes retain their reservation.

Tariff source: https://api-docs.deepseek.com/quick_start/pricing/ (checked 2026-10-24).

## Verification

- Focused author/contract/budget tests: 93 passed before the final defensive malformed-input guards; current dedicated regression file: 13 passed, including durable overflow resume.
- Full Python suite: `python -m pytest -q` — 1811 passed in 239.07s (0:03:59).
- Frontend `npm run build`: passed; existing bundle-size warning only.
- Full Playwright rerun: **206 passed, 10 skipped**, 11.2 minutes (desktop/mobile). Final-code generation/recovery rerun: **  20 passed (58.7s)**.
- Existing fixtures cover canonical compilation, directed feelings/Knowledge, chronology, author editing, confirmation, start, ordinary turn, save/reload and legacy job contracts. These are offline checks, not substitutes for the live acceptance gate.
- `git diff --check` and secret-pattern scan: passed.
- GitHub Actions must be inspected on the pushed SHA; a previous green run does not certify these changes.

## Remaining acceptance work

Resume only after reviewing the interrupted B request/remaining budget and obtaining a fresh authorized test allocation if needed. Keep accepted analysis/plans, not fresh whole-world reruns. Re-test A against current code, complete B and C through canonical compilation and the real editor/Start Game/ordinary turn/save-reload path, and inspect every explicit user fact and executable Runtime bridge. Do not mark Ready or merge based on the current report.
