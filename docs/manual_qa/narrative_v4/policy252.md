# #252 — Narrative authority: bounded semantic input and recovery

Implementation baseline: PR #248 `cbc4f4118755b4ca0e716f9f0b542f16f3a1d538`.
Product policy: master `ee343deee65f627932c5a4f13aedbb41fa06be8f/AGENTS.md`.
No merge, paid provider call, new Runtime, migration or mandatory model stage.
Final-HEAD CI/browser receipts belong in the PR description/checks. This report does
not certify new DeepSeek behavior: the paid semantic/playability gate remains **NOT RUN**.

## Contract and consumer map

New jobs record server-owned `_extraction_contract=5`. `contract_options()` supplies
Resolver policy for ordinary, hidden background and LTA; their producers receive the
same recorded version. Legacy jobs keep their recorded version (missing means v1).
The root context wrapper also uses the common default. QA C/D adapters explicitly
retain their historical v1/v2 profiles. Dedicated remote-message Extraction/1 keeps
its restricted source-bound schema/adapter; it cannot emit physical moves or ordinary
perceptions. Calls inside Narrative use the ordinary job contract. NPC card review
uses domain handlers directly, without an LLM Extraction contract.

| Semantic decision | Authority and necessary source | Deterministic derivatives / consumer |
|---|---|---|
| End membership | Extraction `final_scene` | Camera; membership grants no arrival/contact |
| Arrival / departure / intent / attempt | Extraction Movement; canonical actor and geography; player authority only where necessary | Existing Movement owner; intent/attempt never relocate; optional Event cannot contradict route |
| Statement, observation, rumor | `information_events`: source actor or explicit unknown, medium, content/claims | Existing Event, immutable Fact IDs, exact local alias map; no name matching |
| Who actually perceived each claim | Per-claim `perceived_by` and belief status | Event witnesses/fact links and Knowledge acquisitions; normal presence/capability/read guards |
| Player speaking | Verified PlayerAction, separately declared actual targets | Existing agency/delivery/coverage validation; listeners are not inferred targets |
| NPC contact and feelings | Accepted actor/targets or source/perceiver contact, existing directed proposal | Current/prior canonical event receipt, same step cap and override fences; no mutuality/consent |
| Experience / personality / values | Accepted event or milestone, existing owned experience/revisions | Existing profiles and History; no biography from time, no separate psychology store |
| Significant chronology claim | Extraction binds narrator/belief/lie/quotation to known event time | Calendar day arithmetic; never recorded-time substitution or prose keyword matching |
| Pregnancy, birth, age, life/role/possession | Existing domain assertions and agency/source requirements | Existing deterministic owners, identity and single SQLite transaction |

`raw.compile_semantic()` is a small input expansion, not a generic graph/DSL. Its
output is validated by the same Resolver/domain handlers. The raw provider response
is retained. Generated IDs include turn, narrative and LTA namespace and are stable
for the same candidate. A private in-memory marker prevents LTA from expanding twice;
model-supplied derived-source markers are removed. No state is committed by expansion.

New model-facing perceptions use `information_events`; legacy `knowledge_gained`
remains readable and is restored in the repair schema when an existing proposal
requires it. Explicit duplicate outcomes are rejected, not applied twice. Optional
local fact IDs support other unchanged domains. The schema/example is executable:
[`compact.json`](../../../tests/fixtures/policy252/compact.json), checked by JSON Schema
and real Resolver in `tests/test_policy252.py`.

## Error policy

| Failure | Outcome |
|---|---|
| Repeated technical perception links | Construct once deterministically; retain raw/provenance |
| Intent/attempt, malformed optional contact/beat without a dependent outcome | No domain authority; warning; keep independent Event/outcomes |
| Missing perception source, wrong revision/order, invalid meaningful Fact | Existing one bounded Extraction repair; no partial Knowledge |
| Declared completed significant possession / NPC experience with broken source | Repairable error; never silent `saved` with lost outcome |
| Unsupported subjective proposal / insufficient sustained experience / excessive feeling step | Reject proposal with diagnostic; retain existing profile and caps |
| Chronology narrator conflict | No commit, sticky reauthor; explicit targeted recovery |
| Independent background rejection | Discard that candidate, preserve foreground once; report rejection |
| Cancel, stale revision, critical boundary, SQLite failure | No partial canonical publication |

Source consumers were checked in Knowledge, commitments, life/social, residence/roles,
relationships, personality/values, possessions and communications. Existing essential
life/commitment/remote failures retain their owners. Optional metadata does not grant
new authority. Contact targets may be actual validated witnesses rather than duplicated
participants; the original Social response exposed this distinction during replay.

## Chronology correction

The bounded existing History selection supplies known event dates/minutes and computed
day distance. Only significant retrospective assertions need `chronology_claims`.
The Runtime checks their typed relation, not whether arbitrary prose contains a keyword.
Belief, lie and quotation do not become objective errors. Unknown time stays unknown.

The recovery button explains that model calls may cost money. It creates a new job with
original context/effective config, source job ID, original text/hash and canonical grounds.
It asks for exact local edits of the rejected spans, preserves every other byte and
rejects missing, duplicate, overlapping or unchanged edits. A fresh ordinary Extraction
must explicitly recheck the corrected assertions before domain validation/commit.
The original rejected response and accepted earlier turns remain intact. Correction
and its Extraction have normal request/usage records; no hidden automatic reroll.
Independent LTA/background candidates retain their existing rejection/report path;
this UI action is only exposed for ordinary engine job kinds it can execute safely.

## Evidence and measurements

Available original archive:
`live248-final.tar.gz`, SHA256
`4306f22a7d9ffd01b45f066afbd5e740d21e9e1b5963ae1706ba6dc2ac509b17`.
Full original SQLite copies were restored via production rollback to exact checkpoints,
replayed through jobs, reloaded, rolled back and integrity-checked. Archive manifest
hashes remained unchanged. The later full Berezovsk #251 archive was not available in
this workspace; repository fixtures were used and are not claimed as that full replay.
Semantic retrieval used the existing structural fallback in this environment.

- Baseline A1: the same production background and LTA controls both failed with
  `movement_source_invalid`. New v4/v5 paths accept the genuine arrivals without a
  duplicate arrival Event; necessary LTA cause attribution remains.
- Legacy archive replay: 12 original/control runs; original Crisis and authored
  violation controls rejected atomically. Knowledge retained four acquisitions;
  birth retained ten. This is persistence/structure, not new model understanding.
- v4/v5 comparison uses identical original raw, not fabricated new model responses.
  An old Campaign answer lacks required `target_mode` in both; the archive has no
  subsequent response to the requested repair. This is recorded as missing corpus
  response, never as a successful repair or a new v5 regression.
- The known old Phone false-arrival answer still passes structural validation.
  **Semantic failure remains**, even when job status is `saved`. Returning the old
  duplicate Event gate would not make two model claims independent proof.
- Authored controls on unchanged Knowledge prose prove four per-claim acquisitions,
  excluded listeners, no unread-message Knowledge, stable IDs, commit/reload and
  atomic persistence failure. They do not prove DeepSeek will emit the right claims.

Reproducible free commands:

```bash
python tests/measure_policy252.py /tmp/policy252-measurements.json
python tests/replay_live248_sqlite.py EXTRACTED_ARCHIVE NEW_OUTPUT --final
python tests/replay_live248_sqlite.py EXTRACTED_ARCHIVE NEW_OUTPUT_V4 --final --contract 4
python tests/replay_live248_sqlite.py EXTRACTED_ARCHIVE NEW_OUTPUT_V5 --final --contract 5
python -m pytest -q tests/test_policy252.py
python -m pytest -q --junitxml=/tmp/pytest252.xml
cd frontend
npm test
npm run build
npm run test:e2e -- policy252.spec.ts playability251.spec.ts
```

`measure_policy252.py` reports full actual serialized prompt/schema/output bytes,
conservative estimates and exact structural error codes on six fixed archived scenes.
No Narrative, input or substantial state is shortened for these figures. Repeated
contract instructions were compacted; optional Director schema annotations yield to
the existing soft budget. The same legacy repair representation remains available.
Exact final measurements and final-HEAD test totals are recorded in the PR receipt.
Bytes/estimates are **not** billed tokens, latency, repair quality or paid cost metrics.

## Acceptance ledger and remaining gate

| #252 criterion | Evidence / limit |
|---|---|
| A1 aligned producer/consumer | Baseline failures and production v4/v5 background/LTA regressions |
| Narrow semantic slice, less repeated linkage | Executable compact example, four perceptions, independent recipients, source/agency checks, size measurements |
| No insignificant scene gates / no silent substantial loss | Optional annotation controls; Knowledge/revision, possession, experience and atomicity negatives |
| Targeted chronology and lineage | Production API/job correction + new Extraction; exact edits, stale/cancel/reload/rollback/SQLite tests |
| NPC development and objective processes | Current NPC contact, LTA shared information/relationship source; personality, pregnancy/birth/aging and calendar regressions |
| Fixed corpus false outcomes exposed | Original negative cases explicitly characterized; no semantic PASS from commit |
| Backend and actual browser/CI | Focused checks performed; final-HEAD receipts are PR checks/body. Local Chromium launch blocked by environment socket policy, not counted as browser PASS |
| No additional mandatory ordinary call | Successful controls still Narrative + Extraction; only existing repair or explicit correction adds calls |
| Saves/History/agency/Knowledge/atomicity | Recorded contracts, original context, variant lineage and rollback retained; no migration |
| Fresh Extraction and same-Berezovsk gameplay | **NOT RUN: separately approved paid budget required** |

Before semantic acceptance: freeze old/new contracts, same model/temperature and fixed
Narrative corpus; measure false rejections/acceptances, missed outcomes, first response
versus one repair, manual recoveries, actual tokens/calls/latency/cost. Then continue the
same Berezovsk with natural compound actions and bounded background/LTA. Evaluate literary
interest and NPC initiative separately; rare unobserved events are NOT OBSERVED. No reroll
to PASS and no claim of universal correctness from a small corpus. Issue #252 remains open
until these limits are accepted or its remaining gate is completed. #205 retains model/
auto-budget work; no additional model router is introduced here.
