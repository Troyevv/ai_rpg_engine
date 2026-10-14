# Narrative continuity (#71)

Parent: #36. Extends Runtime v3, #68 pacing and #69 initiative; no second Director,
context selector, quest planner, per-NPC agent or mandatory model request.

## Ownership and bounded work

`continuity.project` is a disposable ContextScope projection. The existing Director
receives a small continuity policy alongside its pacing and initiative permits.
Accepted History turns contain a reconstructable scene/progress signal; accepted
Events contain structured interaction receipts. There is no second canonical store.
The normal Narrative + Extraction pair remains responsible for prose and semantic
classification; Resolver validates references, evidence, agency and effects.

Six recent observed turns are compared by camera location, participants and controlled
actor. Changes in Knowledge, relationships, threads, plans, motivations, life state,
roles, residences, conditions, scene and accepted interaction evidence count as progress.
Repeated unchanged interaction state produces at most 0.25 additional relevance for
existing grounded pacing sources and a priority hint for eligible NPC initiative.
Existing risk, quiet periods, candidate budgets and agency remain binding. No event is
required, and quiet turns need neither events nor canonical mutations.

The normal History tail is bounded. Repetition projection considers at most 128 tail
Events and 16 recent receipts. A targeted, request-cached SQL query of the immutable
History DAG retrieves up to 64 older receipt Events for at most 48 ContextScope basis
IDs. Thus an unchanged rejection can survive many ordinary turns without copying the
whole archive into Python or creating persistent secondary memory. Branch membership
is determined by the recorded before-head, not globally by an Event ID.

## Repetition and shared experience

`continuity_beats` identify question/proposal/information/decision/opportunity receipts
using canonical basis IDs, actor, targets and kind. They have open/resolved/rejected
status, an accepted source Event and quoted evidence. A deterministic digest of their
canonical basis allows changed evidence to invalidate stale receipts. Canonical IDs
and statuses, never fuzzy text similarity, own identity. Reopening a resolved thread
requires a new accepted participant-linked Event. A returned open beat against an
unchanged terminal receipt fails atomically. The prompt also sees terminal receipts.

Choices may carry kind/basis_ids. Equivalent identified purposes are collapsed;
terminal/answered/rejected purposes are suppressed. Legacy action/speech-only choices
remain valid and exact duplicates are removed. Internal metadata does not reach the
choice UI or mutate player state. EXTERNAL decisions in receipts require player proof.

HistorySelector gives bounded, decaying weight to shared experiences among current
participants. POV visibility still filters events. NPC fact-based claims require their
own current Knowledge. Milestone candidates expose known_by and decay both with world
time and subsequently established progress. Transitions need no synthetic Thread and
never automatically disclose facts or cause off-camera scenes.

## Meeting regression

`scene_transitions` annotate an accepted Event with started/advanced/ended, actors and
related thread IDs. Ordinary character_changes/thread_changes supply evidenced final
summaries. If an affected situation or thread state was simply carried forward unchanged,
Resolver invalidates that stale summary to the empty/unknown value; immutable History
retains its original content. Structural movement/presence changes also invalidate
unchanged character situations. No location or off-camera arrival is invented.

A transition never closes the relationship thread itself. Completed intentions remain
owned by #75, commitments by #66. The integration test exercises Ilya/Sonya: agreed →
met → talked → departed → next turn, with commitment fulfilment, intention completion,
ongoing relationship thread, reload, regenerate, variant selection, rollback and branch.

## Natural time compression

Ordinary Narrative may summarize waiting, travel, work or routine with an evidenced
`final_scene.compression` claim and explicit elapsed_minutes. Director grants at most
30 minutes, capped at the nearest relevant scheduled/commitment boundary (including
active interval ends, overdue boundaries and interruptions). Resolver rechecks the
original permit and canonical boundaries before advancing the existing Calendar.
An outstanding meaningful response blocks compression unless the actual player response
is supplied; multiple outstanding responses cannot be silently consumed. Invalid
compression fails the turn instead of keeping prose that contradicts a clamped clock.
Detailed Time Skip keeps its existing ownership and disables this optional permit.
No daily NPC simulation or #43 implementation is introduced.

## Compatibility and limits

Thread gains only optional source_event_id. Existing snapshot migrations/defaults and
History lineage handle legacy saves; no database schema migration or historical snapshot
rewrite. Tabletop code is unchanged. Original Director policy is replayed for regenerate.
Malformed legacy event metadata is ignored conservatively during projection.

Under tight context limits, already-elided optional personality/value evaluation schemas
are also removed if their corresponding baselines are absent. Current scene, canonical
state, Knowledge and continuity guards are retained.

The existing model still classifies semantic equivalence, scene completion and routine
intervals. Runtime cannot prove that arbitrary prose was classified completely or
correctly. Untagged semantic paraphrases are governed by the prompt; tests do not claim
to establish literary quality. Coarse basis IDs should not be reused for unrelated
questions; use the smallest relevant canonical basis. No live-provider evaluation or
paid DeepSeek requests are required in CI.
