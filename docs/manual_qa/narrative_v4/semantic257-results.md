# #257: A/B/C live comparison — no production candidate selected

Subsequent separately authorized D experiment: [results and remaining blockers](semantic257-d-results.md). The proposal at the end of this historical A/B/C report has now been executed; D also did not qualify for production.

2026-11-15, code `b7f96d8202f77f548f51739f868241d184886b44`. The approved maximum was 90 new calls / $6.00. The independent first series completed **27 candidates / 44 actual calls** (reservations 700–743), all with real usage receipts and zero reasoning tokens. Model-specific cold/peak conservative expense: **$0.90545616**. The existing Budget deliberately accounted every call at Pro rates: **$1.5916824**, below its $6 ceiling. All 699 historical reservation rows are unchanged; no unknown new outcome remains.

**Neither B nor C qualifies for production.** The porch failure and unauthorized-refusal failure remain in every arm. Therefore the conditional confirmation series, six holdouts, sequential recovery, gameplay and production integration are **NOT RUN**. The unused allowance is not permission for D or gameplay. No original Narrative was regenerated and no successful or failed candidate was rerolled. One permitted repair was the only second chance.

A = current Flash/off v7; B = same Flash/off and schema, earlier lossless choice-context compaction; C = Pro/off with exactly A context/schema. Responses transport, temperature 0.1 and 8192 output limit were equal. See [frozen plan](semantic257.md) for source hashes and independent authored predecessor setup. These are compiler/Resolver comparisons, not committed campaign saves or production UI gameplay. “False acceptance” below means a structured candidate accepted by the real Resolver with the wrong semantic outcome; campaign SQLite was not advanced.

## Per-case evidence

| Case | A | B | C |
|---|---|---|---|
| Original porch | **FAIL**: first and repair use Lenin Street; accepted after repair | **FAIL**: same wrong street; repair leaves inconsistent action targets | **FAIL**: same wrong street; both responses fenced, rejected |
| Original river walk | **FAIL**: both remain at the porch despite a declared arrival | **FAIL**: generic city endpoint loses the shore; action targets remain invalid | **PARTIAL / FAIL**: creates the actual shore and two knowledge acquisitions, but moves en-route conversation after arrival; repair fixes invalid absolute minutes |
| Original river conversation | **PASS** first: correct shore and two disclosures; omits player's reply from Event coverage | **PASS** first: preserves player's interactions and two disclosures | **PASS** after format repair: shore and disclosures preserved |
| Original Olga background | **PASS** after one source repair: local exit, address retained, no hero/clock/Knowledge change | **FAIL**: local exit understood, but fake player input source remains | **FAIL**: autonomous Olga departure labelled unauthorized; format then agency/source rejection |
| Original cafe | **PARTIAL / FAIL** after repair: both at cafe, entry choice open, but information about Tamara's after-closing work not acquired | **PARTIAL / FAIL** after repair: same lost Knowledge | **FAIL**: content includes arrival and information during the route, but both replies fenced and unusable |
| Partial secret | **FAIL** first: whole secret stays hidden but disclosed conversation is lost | **PASS** first: acquires only the disclosed conversation, Galina source | **PASS** after format repair: selective disclosure retained |
| Unrequested refusal | **FAIL** first: unauthorized refusal accepted under photo-viewing input | **FAIL** after repair: removes action source, keeps refusal, becomes accepted | **FAIL**: no violation recognized; only fenced-JSON rejection |
| Authorized refusal (Pro smoke) | **PASS** first | **PASS** first | **PASS** after format repair |
| Narrator calendar contradiction | **PASS** first: exact date claim yields appropriate chronology refusal | **FAIL** first: date claim omitted, contradictory prose accepted | **PASS** after format repair: date claim yields appropriate chronology refusal |

PASS means the predeclared substantial outcome is correct and usable (including the appropriate refusal for contradictory prose). Minor scene colouring is not a failure. The river-conversation A coverage omission is recorded as a limitation, not treated as loss of the newly disclosed facts. PARTIAL is counted as FAIL in the aggregate: matching a location label alone cannot establish acceptance.

For cafe A/B, the before-state was checked: Alexey did not already have the reported fact that Tamara works on papers/dough after closing. A leaves it only in movement prose; B has even less detail. Neither produces its Fact/Knowledge source. This is a concrete lost information outcome, not a demand to extract every gesture. For river C, the information Event has no `during_step_id` and occurs after arrival at the new shore, despite being spoken along the path. Geography and acquisitions work, but the route-time consequence is not fully correct.

A correct rejection is not inferred from any arbitrary error: C's unrequested refusal fails on formatting, so it does not pass agency recognition. B's missing date claim is not repaired because it is structurally accepted: no test-oracle feedback or hidden retry was supplied.

## Measured first responses and repair

| Metric | A | B | C |
|---|---:|---:|---:|
| Semantically usable first outcome | 3/9 | 3/9 | 0/9 |
| Semantically usable final outcome | 4/9 | 3/9 | 4/9 |
| First response conforms to actual provider schema | 9/9 | 9/9 | 1/9 |
| Repair required | 3/9 | 5/9 | 9/9 |
| Correct final outcome among repaired cases | 1/3 | 0/5 | 4/9 |
| Resolver accepted final candidate | 8/9 | 6/9 | 4/9 |
| False acceptances | 5 | 3 | 1 |
| Paid calls | 12 | 14 | 18 |
| Input tokens | 287502 | 322468 | 452477 |
| Output tokens | 10303 | 12906 | 24582 |
| Mean full candidate latency, seconds | 7.113 | 8.366 | 19.546 |
| Median full candidate latency, seconds | 7.083 | 9.155 | 19.518 |
| Mean provider-stream total, seconds | 6.783 | 7.983 | 19.314 |
| Median provider-stream total, seconds | 6.638 | 8.888 | 19.336 |
| Conservative expense, USD | 0.09861420 | 0.11222760 | 0.69461436 |
| Mean USD per provider call | 0.00821785 | 0.00801626 | 0.03858969 |
| Mean USD per case including repair | 0.01095713 | 0.01246973 | 0.07717937 |

A's 4/9 and C's 4/9 do not imply equal quality or establish superiority: failure types differ. B has three additional false refusals of valid scenes (porch, river, Olga); C has three (porch, Olga, cafe), plus failure to recognize the unrequested-refusal violation. Correct initial chronology rejection counts as a successful outcome. C sometimes describes the right meaning in a fenced response; that content is noted above, but it cannot count as a usable first Extraction. Removing fences manually for a second execution was not allowed or performed.

Eight of nine C first replies contain Markdown fences despite the Responses JSON Schema request; all nine need repair. This demonstrates actual output nonconformance for this profile/transport, not an unsupported claim that the API request failed. Official support and model-list availability did not guarantee compliance. Every receipt reports reasoning_tokens=0.

Full latency includes the existing bounded repair and local validation/journaling. Provider-stream timing includes transport and recording overhead, not an invented server-only duration. All tokens include failed initial replies and repair. Prices used: Flash $0.30/$1.20 and Pro $1.32/$3.96 per million input/output tokens; no cache discount deducted. Pro costs about seven times A per case here, with about 2.75 times full latency and substantially more output tokens. This is one bounded sample, not a general model ranking.

B reduces original foreground message bytes about 5–6% and preserves all source values/schema. Its first-input token reductions are measurable in `assessments.json`; repair frequency still rises from 3/9 to 5/9. Olga A/B inputs are identical: differing outcomes are sampling variation, not a context-compaction effect. The modest B experiment does not establish that every possible context simplification is ineffective, nor prove overload as the root cause.

## Confirmed findings, limits and decision

The supplied original/current state is available to the model. First answers can correctly describe a porch/shore while assigning the wrong existing ID. Partial disclosure may be omitted altogether; an unrelated input quote or removed input source can accompany an unchosen decision; a calendar contradiction may disappear from structured claims. These are extraction interpretation/coverage failures. The reasons the model makes them (ID preference, instructions load, model limitations) remain hypotheses. A deterministic prose parser or additional mandatory critic was not added.

One QA helper was accidentally named `inspect.py`, shadowing Python's standard library for the next subprocess. This stopped execution before that candidate's provider dispatch; the helper was renamed and the batch resumed only unsubmitted schedule entries. The completed porch calls were not repeated. There was no database-sharing incident or extra paid attempt. Inputs, outputs, scopes, schemas, usage and timings remain recorded.

No production defaults, Runtime rules, server contract, database schema or old snapshots changed during the experiment. Full CI is not rerun for a nonexistent production change. Issue #257 is **not accepted**, and the earlier #255/#256 campaign acceptance remains blocked. The six holdouts remain unseen by the provider and available for an eligible candidate's independent confirmation.

## Free next candidate, not a selected solution

The observed failures justify a narrow experiment with the destination representation described conditionally in #257. `devtools/issue257/destination_prototype.py` is an **unselected QA-only adapter**, with no production import. It replaces movement endpoint with one destination: exact `existing_id`, or a new `{name, anchor_id, relation}`. The model still determines the place and relation. The adapter creates an ordinary Location and stable technical ID; it does not infer an address/parent, read prose, change Knowledge, or add a geography store. Locations unrelated to that trip remain expressible through the original domain schema.

The current SceneCandidate patch protocol retains the original experimental source and repairs its fields; the unchanged v7 compiler/Resolver receive ordinary records. The prototype's binding differs explicitly from v7. Tests cover known destinations, null departure/local exit, shared arrival, stable repeated compilation, an addressed anchor repair retaining an independent event, and actual projected schema. Five **authored** controls run through the adapter/compiler/Resolver; these are not genuine model successes or production persistence acceptance.

Free profile after preparation: **60 tests passed**, 11.97 s. The D input freezer validates the projected schemas/budgets for all 15 cases. No paid D call occurred. Prototype limitations: only already canonical anchors are supported in the inline branch; it has not yet been tested for all cross-domain references, production log lineage, saved variants or SQLite integration. Those must be addressed only if comparison demonstrates benefit. It deliberately does not claim to fix unauthorized refusals or missing calendar findings.

Proposed **separate** next permission: up to **54 new Flash/off calls / $1.50 conservative**. D gets one first reply on the same nine primary cases, compared with the already recorded unchanged A inputs/results (at most 18 calls with repair). Only if critical outcomes qualify, confirmation uses fresh A/D on the three fixed originals plus six holdouts (18 first + at most 18 repairs = 36 calls). No Pro, Narrative generation, campaign recovery, gameplay, or production default switch in that allowance. Expected expense roughly $0.25–$0.70; the full Flash unknown-outcome reserve remains $0.3244032. Existing ledger limits must be configured from reservation 743 or the actual later baseline; old allowance is not reused. The destination experiment may itself fail agency/coverage or place selection, in which case production remains unchanged and the exact blocker must be reported.
