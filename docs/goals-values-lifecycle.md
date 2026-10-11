# Goals, intentions and durable values (#75)

This extends Runtime v3, not a separate motivation engine. `Character.goals` and
`intentions` retain their existing Motivation records/IDs. `obligations` remains the
legacy obligation list; timed agreements still belong to ScheduledEvent/#66.
`Character.values` stores sparse durable principles, independent of personality items
and Emotion. No schema/database migration or additional model stage is required.

## Transitions and provenance

Extraction receives a bounded current slice with IDs, status, revision and explicit
semantic dependencies. It proposes `*_updates`; Resolver validates current evidence,
optional accepted Event ownership, compare-and-set and player agency. A completed
result must be evidenced in completed narrative, not just proposed in player input.
Terminal states do not reopen; replay does not add chronology. A new desire gets a
new ID. New semantic assertions and explicit player quotes allow arbitrary game
languages; no regex/text-equality completion classifier exists.

Active and blocked are open states. Completed, cancelled, failed, superseded and
expired are historical. Due time does not change any of these states. Abandonment
and replacement of an EXTERNAL motivation require explicit player input. Background
work cannot change the protected actor. Legacy NPC Extraction string lists only add; omitted entries no longer cancel.
Validated explicit player declarations retain their existing replacement semantics. Explicit UI list edits still express replacement
and have their existing transactional History record. Blocked entries appear in
history/constraint UI and never drive choices until an evidenced unblock.

Each accepted partial transition has a History entry with before/after, source,
turn/date/minute and revision. Existing immutable snapshots/lineage own rollback,
regeneration, response variants and branch isolation. Initial strings migrate to
stable IDs without retroactive semantic guesses. Optional damaged values/metadata
are diagnosed and salvaged locally; old text/status/IDs are retained.

## Cross-domain review

Extraction may attach IDs of necessary target Characters, roles or organizations.
A deterministic linear pass detects dead targets and closed/missing dependencies.
It marks the existing record `review_required` and suspends its actionability without
inventing a changed desire or claiming achievement. Relevant Extraction batches then
resolve it semantically (including an achieved graduation goal after canonical role
closure). A dependency signature avoids requeuing an acknowledged condition. No
universal workflow engine or per-NPC/day call loop is introduced.

Legacy records without semantic links cannot be mechanically associated with an
organization/person by parsing their text. They are still reviewed when selected by
ContextScope; Extraction can attach links. Unsupported or omitted semantic updates
remain pending/current rather than being automatically guessed as completed.

## Values

`value_deltas` uses establish/refine/retire with expected text and revision. Retirement
retains the entry and History. Initial explicit `Ценности`/`Приоритеты` prose migrates
verbatim; biography/personality is not reinterpreted as a value. Unrelated values are
never overwritten. UI projects current values and permitted value history.

Explicit durable statements require an accepted event (and player quote for EXTERNAL).
Gradual evolution reuses #67's **development evidence cache and branch-scoped History
archive**, requiring three distinct source turns; EXTERNAL needs player-owned completed
voluntary behavior. It does not change personality items. One event happening to an
actor, a transient feeling, a birthday, marriage or a standalone turning point cannot
satisfy the sustained route. Evidence thresholds are validation guards, not psychological
scores; semantic appropriateness remains Extraction's responsibility.

## Context, Knowledge and bounds

Current motivations: at most eight records/1,800 characters per field, relevant actors
only. Extraction prioritizes review and rotates other entries using the canonical turn,
so replay is deterministic. Values: at most eight/1,200 characters per actor; evolution
profiles only for the eight highest-priority relevant actors. Optional development/value
sections have a 24-record cap. Completed items are excluded from current motivation,
Director, and stale initial card fields. Already-selected causal History can supply a
small historical lifecycle projection. Values have explicit known-by projections;
changes do not broadcast Knowledge. UI value chronology follows the same witness rules.

No new generation-choice feature (#73), Long-term Advance (#43), dossier redesign,
or Tabletop behavior is implemented. Semantic model quality is not guaranteed by
mocked CI: real-model manual checks remain relevant. No paid calls are required by tests.
