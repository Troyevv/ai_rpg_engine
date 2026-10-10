# Milestones and long-term context (#40)

WorldState owns current truth; History owns chronology and provenance. Milestones
are an immutable compact index of **accepted structured transitions**, not another
Character/world snapshot. No new runtime, LLM call, event-sourcing framework,
calendar, biography inference or per-NPC simulation is introduced.

## Storage and identity

`backend/runtime_v3/milestones.py` indexes batches inside the existing
`append_history` transaction. `world_milestones_v3` stores compact records and
`world_milestone_actors_v3` indexes their actors. The History batch ID scopes each
record to its immutable branch. SQLite recursive CTEs walk ancestor IDs without
decoding old History JSON and use `UNION` to terminate corrupt cycles. Queries
deduplicate canonical transition identity, filter **before pagination**, and return
at most 100 records. No 64-batch cutoff applies to this index.

SQLite, hashlib and existing Pydantic cover indexing, validation and deterministic
identity; no new dependency is needed. IDs derive from accepted transition IDs
(birth additionally uses established actor/date identity), never fuzzy prose
matching. Replaying a batch or resolver retry cannot add duplicate results in its
lineage. Distinct transitions in the same minute remain distinguishable. Names
captured at the transition are not changed by later renames.

The index and History commit atomically with the save/variant. Rollback restores
the previous history head; sibling variants remain stored but are not ancestors.
Regeneration binds its reader to the recorded **before** head. No copied milestone
array is added to every WorldState or snapshot.

## Mapping

| Accepted transition | Index category |
|---|---|
| Established birthday from validated character change | `birth`, known date; minute remains unknown |
| Life status becomes dead | `death` |
| Explicit canonical display-name change | `name_change` |
| Engagement / completed marriage | `engagement` / `marriage` |
| Divorce / other partnership phase closure | `divorce` / `spouse_ended`, `engaged_ended` |
| Adoption, guardianship, foster care established/ended | Their relation kind / kind + `_ended` |
| Residence phase begins/ends | `relocation` / `residence_ended` |
| Significant role phase begins/ends | `role_started` / `role_ended` |
| Explicit Runtime `protagonist_transition` history record | `protagonist_transition` |

Employment, education, training, office, profession and retirement phase changes
are significant by default. `role_changes.significance=major` is the bounded
extension for significant setting-specific roles; `routine` suppresses indexing.
Both still require normal accepted role evidence and lifecycle validation. This
metadata never creates truth on its own. Attendance, movement, dialogue, emotion,
ordinary goals and routine scenes are not milestones. An engagement or wedding
plan never becomes a marriage milestone. A shared residence may produce residence
milestones; the index does not infer marriage or cohabitation from visits.

Birth-date discovery does not assert that a baby was born **now**. Initial imported
biography/birthdays are current truth but are not automatically fabricated as
played transitions. Birth/pregnancy mechanics remain #41. Protagonist records have
a narrow typed indexing boundary for #42; this PR adds no new protagonist command.
Existing actor/POV and observer switches do not change protagonist identity and
therefore do not produce that category. Long-term Advance remains #43 and can
reuse the same accepted-transition/batch writer.

## Causality

Existing transition History gains deterministic IDs and `source_record_id`.
Optional `source_event_id` resolves to an accepted event in the same extraction
involving an affected actor. Optional `source_process_id` references an existing
condition or commitment involving that actor. Invalid links produce a local
`causal_reference_invalid` diagnostic without dropping otherwise valid truth.
Conditions, role/residence/life/social changes and commitments can share these
references. History preserves all linked consequences; milestones retain links
only for the significant subset. There is no new universal causal graph.

## Query and knowledge boundaries

Internal `query(db, history_head, ...)` supports actors, category, inclusive world
minute/date ranges, causal event/process, limit and offset. Dates use the canonical
calendar representation. An unresolved minute is `null` and does not match minute
ranges; a known birth date can still match date queries. `latest_per_category`
provides bounded representative context even after many career changes.

`GET /api/saves/{sid}/milestones` exposes `actor_id`, `category`, `start_minute`,
`end_minute`, `start_date`, `end_date`, `limit` (1–100), `offset` (nonnegative).
The public projection uses only facts **known** to the controlled actor. Knowing
marriage does not disclose a later divorce. Unknown/suspected-only transitions
are omitted before pagination; causal IDs, hidden names and source metadata are
not serialized. The public summary comes from the authorized canonical fact,
not a broader evidence quotation. An observer camera with no controlled actor
has no implicit truth authorization. The API is read-only and never grants Knowledge.

The dedicated game-management biography UI belongs to #45; this issue exposes a
working read API and normal Narrative/Extraction context, without redesigning UI.

## Context and compatibility

The existing Context Builder/ContextScope selects at most eight already relevant
actors, two representative milestones each, with an aggregate 1600 estimated-token
budget. Topical overlap and deterministic category importance rank representatives.
Archived actors cannot promote themselves into the scene. Each GM-only record
has `known_by`; it is not automatically available to a character. Current age,
life state, active objective ties, residences and roles continue to come from
WorldState. Active objective ties rank ahead of closed phases. Optional older role
history is removed first under pressure, milestones next, before scene/action facts
or active commitments. Context diagnostics report selected/included counts. A dead
milestone contradicting a currently alive actor emits a diagnostic; canonical
state is never repaired from historical text.

Initialization performs a versioned, transactional, conservative backfill from
typed History before/after transitions only. Malformed sources are skipped with
logging; legacy prose is never sent to an LLM or reinterpreted. Original History
and saved snapshots remain byte-for-byte unchanged. Existing schema_version=3
and unknown defaults remain valid. Ordinary turns with no milestones keep working.
Missing ancestry is still reported by the existing History audit. Tabletop is unchanged.

Tests: `tests/test_milestones.py` plus existing Runtime/legacy/Time Skip/Tabletop
regressions. Manual checkpoint: [milestones](manual_qa/narrative_v4/milestones.md).
