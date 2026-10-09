# Temporal commitments (#66 / Epic #36)

`scheduled_events` remains the single canonical collection. No new tables, runtime,
clock, workflow engine or per-tick LLM calls. Calendar arithmetic stays in #37's
stdlib adapter; no additional temporal/FSM dependency is needed.

New optional fields have safe defaults: commitment, end_temporal, depends_on,
started_minute, outcome, evidence, source_turn. The status enum remains
pending/resolved/cancelled. An active interval is pending + started_minute;
resolved means evidence-confirmed completion, cancelled includes a missed plan.
Blocked is an outcome on a still-pending plan, not automatic cancellation.

Extraction supplies an assertion (agreed/rescheduled/cancelled/occurred/missed/
blocked/started/ended) and a current-turn quote. New/retimed plans supply a temporal
constraint, not an LLM-computed minute. Runtime checks evidence, references,
controlled-actor decisions and transitions. Player decisions require explicit_choice
and a quote from player_input. An NPC can cancel a joint plan via decision_actor_id.
Semantic truth of the assertion is the existing Extraction's responsibility;
Python does not attempt to understand agreement prose with regex.

A reschedule retains canonical ID and resets the relative anchor to the original
turn's minute. Repeated agreed claims do not move anchors. Terminal IDs cannot
reactivate. Exact duplicate description/participants/start is rejected; semantic
identity still belongs to Extraction, which receives recent/relevant terminal plans.
Legacy records remain loadable and can be closed by evidence even with unresolved
zero deadlines. Historical snapshots are never rewritten. Existing state_changes
now additionally preserve before_scheduled_events for lifecycle provenance.

Dates, weekdays and relative days resolve via #37. Exact times stay exact; periods
and date-only values are inclusive relevance windows, not invented appointments.
Conditions such as “after work” remain explicit constraints. Dependencies express
only necessary plans; cancellation cascades to pending dependents. Cycles/unknown
references in extraction are rejected locally. No relationship penalty is derived.

The existing ContextScope selects active/relevant intervals and recent or topical
terminal plans. Context labels distinguish PLAN, OVERDUE PLAN, CURRENT STATE,
FACT and CANCELLED PLAN. This is GM-only information, not Character Knowledge.
Director acts only on pending events. Time Skip stops at the start of relevant
controlled-actor plans or the end of active intervals, including a zero-minute
stop for already due unresolved items. Players can continue via an ordinary turn.
Bounded background simulation cannot change the protected actor's joint plan.

The existing calendar range response adds `scheduled: {items, truncated, limit}`.
Each item carries source_id/id, date/end_date, type/kind, character_ids, status,
outcome, interval_state and a window. The range is at most 400 days and 500 items;
unknown dates are omitted, not guessed. No persisted UI copies. A read-only section
in the existing World inspector exposes plans, windows, dependencies and evidence.
UI strings follow the existing Russian presentation convention; canonical labels
remain language neutral. The full calendar management UI remains #45's scope.

Automated tests cover pure transitions, property-based clock immutability and the
#78 import/start → ordinary turn → persistence/reload → next turn path, plus
Time Skip, regenerate, sibling variants and rollback. Manual QA:
[commitments.md](manual_qa/narrative_v4/commitments.md).
