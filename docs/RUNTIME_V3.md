# Runtime v3

Status: v3 runtime implemented; review candidate, not yet validated on real user saves.
The local backend suite has 339 passing tests and the frontend production build passes.
Browser CI and the real-save acceptance gate must pass before release.

## Ownership

WorldStateV3 describes the present. WorldHistoryV3 records how it happened. A
GameSnapshot stores current state, immutable character cards, campaign metadata,
memory and a history cursor. History batches are separate SQLite records whose
parent cursor forms a branch/variant DAG. Neither history nor read projections
are embedded in canonical WorldState.

| Field | Owner | Source | Persisted | LLM sets | Derived | Fatal if absent |
|---|---|---|---|---|---|---|
| meta.schema_version | runtime | constant 3 | yes | no | yes | yes |
| meta.turn_id/world_time | runtime | prior state + elapsed | yes | elapsed only | yes | yes |
| camera | resolver | final_scene or explicit POV command | yes | final observation | yes | yes |
| character.location_id | resolver | final camera / off-camera movement | yes | movement target only | yes | no: null is unknown |
| character.situation | extractor | supported narrative | yes | yes | no | no |
| goals/intentions/emotion/obligations | extractor + agency validator | player input for controlled actor | yes | source-bound | no | no |
| static character card | creation/promotion | generation or supported promotion | separately | promotion only | no | yes for existing actor |
| facts | resolver | supported claims | yes | claims only | IDs scoped | no |
| knowledge | resolver | validated new acquisition | yes | acquisition only | actor/fact/status | no |
| relationships | resolver/manual editor | canonical dimensions and context | yes | supported changes | no | no |
| threads/scheduled_events | resolver | supported changes | yes | yes | no | no |
| locations | resolver | creation / existing ID | yes | new description | IDs canonical | yes when referenced |
| events/movements/provenance | history writer | accepted raw claims | history only | claims only | IDs/origins | no |
| scene cards and UI timeline | selector | current state + bounded history | no | no | yes | no |

## Mutation pipeline

RawTurnResult is a tolerant extraction envelope, never a writable state model.
Malformed optional records are dropped with paths and reasons. A malformed root,
unknown required camera actor/location or ambiguous required movement is fatal
and permits one repair. Unsupported optional claims never cause repair.
StateResolver produces a runtime-owned StatePatch on a copy. The patch applies
once, then assert_world_state_v3_invariants validates current state, without
walking history. State, history cursor and response variant commit atomically.

The final camera controls participant positions. A participant does not need a
redundant movement record. Off-camera actors retain their previous position
unless an explicit supported movement changes it. Event chronology is descriptive;
it does not reconstruct a second spatial world.

New Knowledge requires a current extraction Event, a fact referenced by that
Event, actor membership in witnesses, an information-bearing medium and supported
evidence. Committed Knowledge contains only actor_id/fact_id/status. Deleting an
old Event cannot revoke it. audit_world_history reports incomplete provenance
without preventing subsequent turns.

## Migration

Migration is a versioned storage boundary, not a runtime fallback. It returns
(state, history, report), preserves legacy history as unmodified payloads, and
preserves known Knowledge whenever actor and fact exist. Incomplete provenance
is reported, never used to erase valid current knowledge.

Location priority: explicit Character location, unique active-scene membership,
current camera participant snapshot, otherwise null. Locations receive stable
IDs derived from legacy names. Camera participants are reconciled to the camera
location, with an explicit migration report when a stale character position
conflicts. Legacy scenes and source_event pointers are removed from current state.
The migrated snapshot and migration report are persisted once. Historical variant
snapshots use the same boundary and independent immutable history cursors.

## Read surfaces and compatibility

UI selectors may derive scene cards from current locations. These are disposable
views, not writable scene entities. Context separates current truth from bounded
recent/relevant history; POV knowledge never joins historical provenance.
Generation/draft import can retain its old schema at the migration boundary.
Runtime, background simulation, regeneration and POV use only v3 mutation code.

## Acceptance gates

Domain tests cover strict current-state references, field-level agency, new
acquisitions, old damaged history, optional-record mutation and spatial derivation.
Integration gates cover atomic rollback, immutable sibling variants, branches,
migration/save/reload/play, background and 100 consecutive persisted turns.
Actual production saves must be added to the migration corpus when supplied;
reconstructed fixtures are explicitly labelled and are not real-save evidence.

## Regression migration

V2 temporal test modules were replaced, not disabled: their source JSON corpus
is replayed by `test_runtime_v3_corpus.py`. Expectations about historical Scene
membership, required source_event_id in current Knowledge and last_event_id in
current Thread deliberately no longer apply. Their replacement gates are:

| Old concern | V3 gate |
|---|---|
| intermediate geometry / inferred origin | domain movement tests + both historical JSON corpora |
| optional extraction schema and evidence | 100 seeded mutations + mixed local drops |
| old Knowledge chain breaking future turns | history corruption, malformed audit records, real next job |
| final-state accumulated consistency | 100 persisted domain turns and 100 actual engine jobs |
| player agency | source-specific acceptance, negation, quoted speakers, omissions and per-field warnings |
| repair | one structural retry, request snapshots, restart/variant association, unsafe errors never retried |
| v2 saves | persisted reconstructed corpus, migration, two commits and reloads |
| request usage | actual tokens/cache/cost/duration snapshots and active-variant association |

The full suite remains the release gate; failures are not skipped or marked xfail.


## Runtime cutover and review limits

The production v2 WorldDelta apply path, temporal resolver, Scene mutators,
legacy state_updates and background implementation have been removed. V1/v2
normalization remains solely for generation/import migration and read-only draft
preview. UI scene IDs are projections and cannot be persisted in WorldStateV3.

A StatePatch is based on the prepared snapshot saved as memory_before_json (after
POV/camera preparation and optional memory compaction). before_json remains the
rollback point before that preparation. Response variants preserve both; selecting
a sibling restores its own state and immutable history cursor. Background updates
are combined into the final patch, while separate history records retain the
main and background narratives. Event.source_record_id targets that exact record;
UI sequence numbers remain zero-based independently of meta.turn_id.

Context keeps the current camera, participant cards, current player input and
rules. Old conversation pairs and low-relevance optional facts/relationships,
threads, schedules and remote locations are removed deterministically if needed.
Removing a fact from the request removes its context-only knowledge rows too;
no persisted knowledge is erased. Provider requests remain saved verbatim.

No production SQLite save was supplied. The checked-in persisted corpus is
reconstructed, explicitly labelled in its README. A real affected save still needs
`load → migrate → play → save → reload → play` before release approval. The PR
must remain a draft until that gate is addressed; this is not proof of compatibility
with every existing player database.
