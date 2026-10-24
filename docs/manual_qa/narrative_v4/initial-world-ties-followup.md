# PR #105 — ties output exhaustion

## Evidence and limits

The reported production error is `stage/ties: provider request failed
(OutputLimitReached)`. In `llm.chat_stream`, that exception requires
`finish_reason == "length"` with `require_complete=True`. The error string alone
does **not** establish the production request cap, exact usage or intended full
JSON size. That production request/database was not supplied in this workspace.
No exact production token counts are claimed.

Existing local real-provider records give these reference measurements (each cap
was **12,000**; all five finished with **stop**, not length):

| Historical request | Input tokens | Output tokens | Raw answer UTF-8 bytes | Objective / directed records |
| --- | ---: | ---: | ---: | ---: |
| 9 | 5,518 | 2,201 | 7,833 | 9 / 9 |
| 17 | 6,146 | 1,217 | 4,214 | 2 / 10 |
| 29 | 7,840 | 1,524 | 5,271 | 5 / 4 |
| 35 | 7,796 | 1,817 | 6,422 | 8 / 8 |
| 57 | 11,342 | 6,765 | 21,568 | 13 / 26 |

These are provider usage counts and actual raw answer lengths, not estimates.
Historical request 57 had seven characters. Its input fit the configured context;
its output was substantially larger than the smaller-world responses. Some earlier
answers were structurally invalid despite finishing; this table is not a quality
pass. The separate follow-up `life_ties` network interruption has null usage and
finish reason and is **not** an OutputLimitReached measurement.

The architectural defect is an unbounded whole-cast output request: TiesPart
exposes up to 400 records, and directed emotional pairs alone grow as N*(N-1).
Verbose full biographies/places in input and optional default fields in output
increase cost. The evidence does not establish which combination exhausted the
new production request; its configured cap and usage still need its request log.

## Change

- Six unordered pairs per durable checkpoint, both directions in the same batch.
- Pair-constrained request schema; concise output and sparse meaningful ties.
- Participant biographies only, no full places payload; original source notes kept.
- Deterministic aggregate through existing validators, no extra Runtime/state.
- Independent resume, author edit and dependency invalidation; failed unpublished
  legacy monolith can subdivide without repeating characters/places.
- Safe output-limit diagnostics; no automatic provider retry or global cap change.

As an **offline size experiment**, partitioning historical response 57 without
changing any record produces compact JSON batches of **4,926 / 8,161 / 2,432 /
1,340 bytes**, with 12 / 18 / 6 / 3 records. This is not a new model response or an
actual per-batch token measurement. Output length remains model-dependent.

## Verification

Deterministic regressions cover 2/7/30/100-character pair coverage, duplicate and
out-of-batch rejection, directed adoption and asymmetric feelings, unchanged
chronology, truncation with actual mocked usage/finish callbacks, no automatic
retry, accepted checkpoint reuse, legacy failed-stage subdivision, fresh repository
reads, canonical confirmation/reload, and paused batch edits reaching the final
world while preserving other batches. The rich fixture retains seven characters,
six organizations and restricted Knowledge. Browser fixtures now honor assigned
pairs; existing assertions and timeouts remain unchanged.

Final checks:
- Full `python -m pytest tests -q`: **1628 passed in 200.15s**, after the final
  batch editor-schema regression/fix.
- Frontend `npm run build`: **passed in 3.08s**, existing bundle-size advisory.
- Full `npm run test:e2e`: **204 passed / 10 existing skips in 11.4m**.
- Fresh-backend `npm run test:e2e -- world-generation.spec.ts` after the final
  editor-schema change: **18 passed in 39.2s** (desktop/mobile).
- `git diff --check` and changed-file credential-pattern scan: passed.

The first focused browser run failed because its provider fixture still emitted
all pairs; the fixture was corrected to obey batch ownership, without weakening
assertions or timeouts. A temporary exec-server transport disconnection interrupted
log access, then recovered; the final Python and browser logs above were read after
reconnection. These are local results, not a GitHub Actions claim.

**New paid DeepSeek calls: 0; new API spend: $0.** No credential was read, recovered
from chat/logs, or persisted. The current environment has no DEEPSEEK_API_KEY. No new real-provider completion is claimed. The prior
network-policy block and unresolved usage remain as documented in
[the previous follow-up](initial-world-live-followup.md). PR #105 remains Draft;
Issue #44's live-quality acceptance criteria are not closed by these fixtures.
