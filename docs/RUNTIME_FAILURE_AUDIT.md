# Runtime failure audit — before implementation, 2026-09-27

Scope: RawExtraction → deterministic normalization/salvage → final resolver → canonical copy → commit.
The rows below cover every field of the current extraction models. This document was written before the implementation changes in this revision.

## Policy

DROP removes an independent claim/field and its dependent claims, with a structured warning. DERIVE is ordinary deterministic processing, never a warning or repair. FATAL rejects the entire candidate copy; the engine may request one repair. Unknown required actor/fact IDs, malformed types/core arrays and conflicting canonical IDs remain structural. Knowledge with a missing Event is deliberately DROP: it cannot create knowledge and has no dependent mutation; an existing corrupt persisted knowledge reference is FATAL. This distinction preserves the earlier graceful-degradation contract.

## Field inventory

`R` = required raw field; `O` = optional. Required evidence can be missing only through explicit record salvage. LLM FACT errors in independent claims are DROP; an invalid mandatory identity/type is structural, irrespective of the semantic field category.

| Field | Category | Owner / source | Required | Derivation / recovery | Fatal rationale |
|---|---|---|---|---|---|
| scene.location | STRUCTURAL | final camera snapshot | R | no guessed location; resolver distributes it to final members | empty/wrong type cannot define camera |
| scene.present_ids | STRUCTURAL | final camera snapshot | R | deduplicate known IDs | unknown actor / absent controlled actor |
| scene.text | LLM FACT | extraction summary | R | retain as display text | malformed required text |
| scene.time | REDUNDANT | clock label derived from elapsed + Before; legacy absolute time fallback | O | DERIVE label; elapsed owns clock if supplied | backwards legacy clock |
| scene.elapsed_minutes | LLM FACT | extraction duration | O | Before + elapsed; legacy time then minimum policy if absent | invalid type/range |
| choices | STRUCTURAL | action proposals, not canonical decisions | R | six normal / zero background | malformed/missing/duplicate choices |
| choices[].action | LLM FACT | proposed action | R | no WorldState mutation | malformed required text |
| choices[].speech | OPTIONAL METADATA | proposed speech | O | default empty | invalid type |
| WorldDelta arrays | STRUCTURAL | typed raw container | O | missing array → [] | non-array/wrong record types |
| *.evidence | LLM FACT | literal current player_input or completed narrative | R | DROP independent unsupported/missing record, cascade dependencies | Promotion identity definition cannot safely be guessed |
| Character.id | STRUCTURAL | existing/promoted canonical ID | R | reference lookup | unknown ID / duplicate patch |
| Character.location | REDUNDANT | final resolver only | O legacy | ignore; scene/Movement/Before owns position; remove from advertised schema | never competes with owner |
| Character.situation | LLM FACT | objective sourced description | O | absent = unchanged; DROP unsupported record | no independent fatal |
| Character.goals | LLM FACT | player_input for controlled actor; sourced NPC state otherwise | O | DROP unsupported field; absent = unchanged | invalid list/type remains structural |
| Character.intentions | LLM FACT | same as goals | O | same as goals | same |
| Character.emotion | LLM FACT | explicit player_input only for controlled actor | O | DROP unsupported field; never infer psychology | invalid type |
| Character.obligations | LLM FACT | explicit promise/action for controlled actor | O | DROP unsupported field | invalid list/type |
| Character.player_evidence | OPTIONAL METADATA | quotes from current player_input | O | fallback record evidence; not persisted as state | malformed container |
| Character.player_evidence.goals/intentions/obligations | LLM FACT | one explicit quote per new item | O | player-agency validator, DROP corresponding field | wrong mandatory types |
| Character.player_evidence.emotion | LLM FACT | explicit emotion quote | O | same | wrong type |
| Event.id | STRUCTURAL | canonical unique occurrence ID | R | no overwrite history | duplicate/existing ID |
| Event.text | LLM FACT | sourced occurrence | R | DROP unsupported record | malformed required type |
| Event.participants | LLM FACT | actors involved in this event | R | independent of final/intermediate geometry | unknown actor |
| Event.witnesses | LLM FACT | actual information recipients | R | not inferred from scene membership | unknown actor |
| Event.fact_ids | LLM FACT | facts conveyed by event | O | remove dependency on dropped new Fact | unknown non-dropped Fact |
| Event.medium | LLM FACT | information channel/action | R | action cannot authorize Knowledge | invalid enum/type |
| Event.location | OPTIONAL METADATA | event source, not final scene | O | unknown remains null | malformed type |
| Event.minute | OPTIONAL METADATA | explicitly known event time | O | unknown remains null; recorded_minute separately derived | explicit time outside turn interval |
| Event.order | OPTIONAL METADATA | known relative order | O | unknown remains absent | malformed type |
| Movement.actor_id | STRUCTURAL | canonical actor ID | R | lookup | unknown actor |
| Movement.to_location | LLM FACT | sourced destination | R | off-camera endpoint owner after Before | malformed destination |
| Movement.from_location | REDUNDANT | Before / previous resolved movement | O legacy | ignore; DERIVE origin, hidden in schema | none |
| Movement.minute | OPTIONAL METADATA | legacy known time | O | not required to build route | explicit impossible interval |
| Movement.order | OPTIONAL METADATA | relative route order | O | needed only for distinct off-camera destinations; final scene owns final members | ambiguous off-camera endpoint |
| Fact.id | STRUCTURAL | canonical Fact identity | R | upsert | duplicate patch ID |
| Fact.text | LLM FACT | sourced proposition | R | updating text invalidates old knowledge status | malformed required type |
| Fact.secret | LLM FACT | visibility classification | O | false default | wrong type |
| Fact.character_ids | LLM FACT | relevant actors | O | [] default | unknown actor |
| Knowledge.actor_id/fact_id | STRUCTURAL | existing actor/Fact | R | reference lookup | unknown mandatory reference |
| Knowledge.status | LLM FACT | known/suspected/unknown | R | accept only with complete path | invalid enum/type |
| Knowledge.source_event_id | LLM FACT | Event of this delta | R | DROP if no Event→fact_ids→witness→medium path | persisted dangling source is fatal |
| Relationship.source_id/target_id | STRUCTURAL | directed canonical actor pair | R | key derived as source:target | unknown actor / self relation |
| Relationship.dimensions | LLM FACT | canonical RELATION_DIMENSIONS | O | DROP unknown individual key; no semantic mapping | malformed number/range |
| Relationship.context | LLM FACT | sourced subjective relationship | R | retained independently of dropped dimension | malformed text |
| Thread.id | STRUCTURAL | canonical thread identity | R | upsert | duplicate patch |
| Thread.description/state | LLM FACT | sourced thread development | R | DROP unsupported record | malformed text |
| Thread.character_ids | STRUCTURAL | canonical actors | R | lookup | unknown actor |
| Thread.status/relevance | LLM FACT | sourced status/rank | R | typed enum / 0..1 | malformed value |
| Thread.last_event_id | STRUCTURAL | supporting current event | R | DROP when supporting new Event was dropped | unknown non-dropped reference |
| Scheduled.id | STRUCTURAL | canonical obligation occurrence | R | upsert | duplicate / nonexistent resolution |
| Scheduled.due_minute | LLM FACT | explicit deadline | R | world clock comparison | pending in past / premature resolution |
| Scheduled.type/description | LLM FACT | sourced obligation | R | DROP unsupported record | malformed text |
| Scheduled.participants | STRUCTURAL | canonical actors | R | lookup | unknown actor |
| Scheduled.status | LLM FACT | pending/resolved/cancelled | O | pending default | impossible transition |
| Scheduled.resolved_event_id | STRUCTURAL | resolution event this turn | O | required for resolution; cascade DROP | unknown reference / unrelated participants |
| Promotion.id/name | STRUCTURAL | new canonical identity | R | identity registry | existing ID/name conflict |
| Promotion.fields | STRUCTURAL | complete permanent CARD_FIELDS | R | typed complete card | incomplete identity definition |
| Promotion.goals/intentions/obligations | LLM FACT | sourced new NPC state | O | [] default | wrong types |
| Promotion.situation/emotion | LLM FACT | sourced new NPC state | O | empty default | wrong types |

## Derived state and mutation ownership

| State | Owner after refactor | Input / rule | Recovery |
|---|---|---|---|
| character.location | Final State Resolver → scene_sync | Before → sourced movements → authoritative final camera override | DERIVE; no inference for absent NPC |
| character.scene_id | scene_sync | resolved position + camera membership | DERIVE |
| live scene.location/participants | scene_sync | final snapshot; off-camera resolved positions | DERIVE; no writes from apply_delta/record_scene |
| camera.scene_id | scene_sync | final scene identity | DERIVE |
| event.scene_id | events.apply_events | unique immutable event snapshot | DERIVE, never reused as live scene |
| world_clock.minute | timeline.advance | Before + elapsed, legacy absolute fallback | DERIVE; no backwards time |
| scene.time / clock label | timeline.label | canonical minute | DERIVE |
| character.minute / last_event_id | spatial/character apply; event apply respectively | committed update time / event | DERIVE |
| event.recorded_minute/source_sequence/player_observed | event apply | runtime turn metadata | DERIVE |
| relationship key/change/provenance | relationship apply | canonical pair, numeric difference, source quote | DERIVE |
| knowledge key | knowledge apply | actor:fact | DERIVE |
| scene IDs / start/end/status | scene_sync | runtime identity and clock | DERIVE |
| historical snapshot | event apply once | exact sourced event members, witnesses, optional metadata | immutable; FATAL if modified |
| diagnostics derivations/warnings | resolver / salvage | actions actually performed | never trusted from raw input |

## Mutation-path findings and decisions

Before this refactor, `record_scene`, `scene_sync` and `apply_delta(Character.location)` all wrote positions. `derive_movements` then treated a redundant final location as a competing truth. Replace this with one spatial publisher. `record_scene` remains a compatibility facade delegating to that publisher. Runtime v2 must use a dedicated scene/choice parser, not the legacy patch mutator. Legacy helpers for historical callers are not a fallback in the active pipeline.

RawExtraction owns source claims; CanonicalTurnDelta owns resolved positions and final membership. Build on a copy; isolated salvage retries discard the entire provisional copy. Every successful apply checks canonical invariants. Scene-derived positions are diagnostics, never warnings. Off-camera movements with distinct unordered destinations are genuinely ambiguous and remain FATAL. Redundant Character.location can never introduce such a conflict.

Final-scene actors do not need complete routes. For them unordered movements cannot determine a unique historical route; do not invent it or make it block the authoritative endpoint. Preserve source records and report only derivations that are deterministic.

## Verification plan

15 named reconstructed failure fixtures (not production captures), 100 deterministic payload mutations, structural-negative cases, and 25 successive saved turns. Verify real request count, repair_rate=0 for tolerable variations, warnings vs derivations, immutable historical snapshots, complete knowledge paths, off-camera preservation and canonical graph invariants after each commit. Update obsolete fatal expectations instead of preserving the old architecture through tests.
