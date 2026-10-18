# Long-term Advance (#43)

## Architecture

`long_term.plan` produces a disposable deterministic projection over canonical
v3 state and ContextScope. `long_term.run` resolves a bounded number of groups,
then publishes through the existing job/variant/History transaction. There is no
second runtime, scheduler, NPC agent, Knowledge store or daily simulation.

The request specifies weeks/months/years and a hard cap of 0–8 provider attempts.
One uncertain group uses at most two calls: Narrative and existing Extraction.
There is no automatic repair call. Groups contain at most three causes; new
identity proposals are capped at two and require an accepted role or relation.
Structured due and known-date age transitions execute independently of this cap.
A pregnancy becoming due is not a completed birth. Unsupported outcomes stay
unresolved and receive diagnostics. Cancellation does not publish partial state.

Ranking is stable: due cause/process priority, controlled involvement, current
ContextScope, established ties, dormancy and canonical ID tie breaking. Selected
groups run in chronological order. NPC relevance is derived, not life status;
canonical Characters are never deleted or recreated on dormancy/reactivation.
Pacing/risk continues to be owned by #68. Opportunity domains identify possible
work, education, contacts, relationships and moves; they are not completed events.
Player opportunities are returned for an explicit ordinary player decision.

Annual dates use first/last/count rather than expanding days or years. Gregorian
and custom profiles use #37 arithmetic. Detailed Time Skip remains unchanged.
Actual outcomes reuse #38/#39/#40/#41/#66/#67/#76 resolver/provenance rules.
Opportunity receipts are queried from the existing branch History DAG.

## Persistence and presentation

The dedicated endpoint creates a normal durable job with before/after snapshots,
revision checks and immutable variants. A provider attempt uses existing usage
instrumentation. Regeneration preserves the original request and recorded
Narrative messages keyed by canonical candidate group (independent of skipped
Extraction calls). No SQL schema change or historical snapshot rewrite is used.
Optional result metadata lives in the snapshot and History report.

The shared responsive dialog previews the date and interruption before starting.
Results distinguish player decisions and off-camera observer summaries. Observer
information never grants Character Knowledge. Event evidence and fact-level
knowledge transitions remain required; public-looking state is not broadcast.

## Acceptance coverage

Primary tests: `tests/test_long_term_advance.py`; existing owner tests continue
to validate their resolver contracts.

| Criterion | Implementation / automated coverage |
| --- | --- |
| 5/15 years without day loops | Interval adapter; `test_long_advance_no_calls_or_invented_biography` |
| Hard cap with 100+ NPC | `test_hard_cap_100_npcs_and_deterministic_transitions` (120 NPC, caps 0–8) |
| Deterministic transitions survive exhausted budget | Same test; `test_due_process_survives_zero_budget_without_invented_birth` |
| Unselected outcomes remain unresolved | Canonical sources unchanged; per-source report reasons |
| Stable ordering | Hypothesis mapping-order regression |
| Holidays/birthdays do not create scenes | Coalesced annual dates regression |
| Due commitment is pending; cancellations/rescheduling/dependencies | Commitment interruption and dependency tests |
| Pregnancy and birth use #41 | Accepted birth regression and existing reproduction suite |
| Invalid protagonist / incapacity | Accepted illness/death at a scheduled boundary enters #42; denied-risk, existing-death and incapacity regressions |
| Dormant identity/history retained | Derived relevance/reactivation regression |
| Personality needs canonical experience | Accepted course/turning-point regression; zero-budget no-trait regression |
| Child growth without adult personality generation | Born child → 15-year advance regression |
| Education/work chronology | Accepted role and course completion regressions; existing residence/role suite |
| Contextual opportunities; no silent player acceptance | Role opportunity regression, bounded #68 selection and branch-specific receipt deduplication |
| Accepted outcomes carry provenance | Source-linked events, owner resolver tests |
| New characters require accepted continuing identity | Accepted friendship creates one minimal canonical identity; incidental/duplicate preparation regressions |
| Secret relocation / independent knowledge facets | Secret residence and work-message regressions |
| Significant remote communication | Read/answered evidence required; delivered-only message is not a response cause or knowledge broadcast |
| Extraction cannot advance the clock | Rejected nonzero elapsed time; deterministic target survives without repair calls |
| Told facts and suspected beliefs | Explicit message evidence, unchanged suspicion and JSON round-trip test |
| No global Knowledge broadcast / per-fact model loop | Group pipeline and 120-NPC hard-cap regression |
| Save/reload/rollback/branch/regenerate | Real job/variant regression on extended #78 world; replay after a changed number of Extraction calls |
| Ordinary Narrative and Time Skip | Existing full Python suite and ordinary follow-up smoke |
| Tabletop isolated | Dedicated Narrative job guard; existing Tabletop suite |
| Desktop/mobile | `frontend/e2e/long-term.spec.ts` in both configured projects |

Browser execution and complete final CI are required before merge. Deterministic
fakes validate Runtime semantics, not the literary quality of arbitrary providers.

## Deliberate bounds

At most four uncertain groups can be resolved per request. Pending outcomes may
remain unresolved even after the target date. Player commitments stop progression
for an ordinary decision; off-camera groups cannot act for the controlled actor.
Risk-permitted death of an observed/uncontrolled protagonist uses the existing
consequence policy and stops at the accepted event. No aging-to-death rule exists.

Relevance is projected once per interval; dormant records remain canonical.
Registry traversal for deterministic projection is linear, while semantic calls
and new identity proposals are capped independently of registry size and interval.
Provider/transport failure retains the existing atomic failed-job behavior; it
does not publish a partial world. Exhausted semantic budget still advances certain
transitions. No live paid-provider validation is performed.
