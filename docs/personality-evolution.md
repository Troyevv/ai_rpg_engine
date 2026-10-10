# Character development (#67 / Epic #36)

This extends Runtime v3's Character, RawTurnResult, Resolver, History and ContextScope.
There is no second character-card store, psychiatric model, numerical trait score,
per-turn psychologist call or per-NPC/year simulation. Tabletop is unchanged.

## Current truth and compatibility

`Character.personality` owns current established traits, communication tendencies,
habits, strengths, weaknesses, fears, preferences and early temperament. Item IDs
are stable within the Character. Each item has language-neutral field, prose text,
revision and source IDs; witness/fact authorization survives evidence-cache eviction.
Values/goals lifecycle remains in its existing layer, with #75 owning its expansion.

Old cards initialize this profile once, verbatim and without LLM interpretation.
An unmigrated profile is `null`; an intentionally sparse profile is an empty
`PersonalityProfile`. The static card retains the import baseline, but UI, Narrative
and semantic retrieval project current canonical personality onto the same card.
Refinement does not replace appearance, biography, identity, goals or unrelated items.
Historical snapshots are not rewritten. Optional malformed profile data is logged
and falls back locally on migration; valid records are not retrospectively reinterpreted.
No SQLite schema migration or new dependency is needed. Schema version stays 3.

## Semantic input and deterministic acceptance

Two optional extraction sections use the existing extraction request:

- `development_evidence`: completed meaningful behavior/experience, actor ID, exact
  supporting quote, accepted event ID, semantic meaning and kind. One event per actor
  yields one deterministic evidence ID. Multiple labels cannot manufacture a pattern.
- `personality_deltas`: evidence IDs, causal rationale, developmental capability
  assertion and at most three establish/refine/retire operations. Exact expected
  text/revision supplies compare-and-set. Whole-card replacements are not accepted.

Ordinary evidence needs three distinct accepted source turns. Multiple events in one
scene do not meet this floor. Semantic relevance is still required; three arbitrary
experiences are not permission to change arbitrary traits. A single genuinely
exceptional, explicitly established turning point can qualify. This is an extraction
semantic assertion, not a deterministic psychology law; Runtime does not infer it
from prose keywords. Unsuitable age/capability claims must be omitted by extraction;
Runtime additionally blocks mature fields for canonical infants.

EXTERNAL evidence requires an exact player quote, `completed_voluntary_behavior`,
and an event confirmed in completed Narrative. Narration alone, plans, hypothetical
wishes and things happening to the actor do not supply voluntary behavioral evidence.
An EXTERNAL delta needs repeated player-owned sources or an exceptional player-owned
turning point; NPC-era experience remains available as context. Background resolution
cannot change the protected actor. Selected choices and free text use the same
player-input → completed event → evidence path; choice indexes never enter development.

Milestones may supply accepted, lineage-checked source context for AUTONOMOUS actors.
They do not deterministically prescribe an outcome; the completed narrative must
explicitly establish the interpretation. EXTERNAL actors still need their own responses.
No relation or Knowledge record changes merely because personality changed.

Conflicting/invalid optional claims produce local diagnostics. Related operations are
atomic: one stale field rejects that delta; unrelated accepted records survive.
Retirement needs evidence just like establishment/refinement. Replay guards derive
from actor, affected dimension and canonical sources, not replacement prose. Changing
an item name/text cannot spend the identical sources again on that dimension.

## Provenance, bounded context and archive

Existing `WorldHistoryV3.state_changes` stores compact evidence and accepted partial
before/after deltas, source records, source turns/minutes/dates and causal rationale.
Normal save/variant transactions persist them atomically. Rollback restores the prior
profile/head, sibling branches diverge, regeneration uses original before lineage.

Current profiles retain at most 32 recent meaningful evidence records. Compact seen-source
and applied-operation identities are replay guards, never prompt content. They grow only
with accepted relevant evidence/changes; full quotations/old profiles are not duplicated
into a new current-state biography. `history_query`/`history_reader` provide bounded,
on-demand archive access for up to eight actors and 32 records. Exact old evidence IDs
can be validated through the original History lineage even after working-set eviction.
There is no 64-batch limit on this explicit archive query, nor an automatic history scan
for every actor every turn. #43 can use this reader with its own relevance/budget, then
propose the same partial deltas; #43 itself is not implemented here.

Context Builder uses the existing scope. FULL_PRESENT/FULL_REMOTE get current card
fields; active references get the existing compact behavior view; mere referenced/index
actors never gain full personality prose. Extraction gets bounded item/evidence views
for at most eight already relevant actors. Historical personality is attached only when
its causal event was selected by the existing History selector (two records/2000 chars),
and is dropped first under budget pressure. `personality_known_by` and historical
`known_by` distinguish GM truth from character knowledge. UI exposes current authorized
fields, not raw evidence, source IDs, replay ledgers or hidden psychological changes.

## Children and future consumers

#41 must create a sparse child using the same Character ID and an empty/minimal profile.
Do not copy parental traits or generate a hidden adult profile. Supported temperament
is separate from mature traits. Later experience can establish/refine/retire card items
progressively; age only gates plausibility. Nothing happens merely on a birthday or when
years pass. Switching NPC → controlled → NPC never resets the profile or provenance.
#42 protagonist transitions and #43 Long-term Advance remain future consumers; tests use
existing actor switches and deterministic time advancement, not premature implementations.

Manual QA: [personality](manual_qa/narrative_v4/personality.md).
