# #256: spatial consequences and explicit suffix recovery

PR #248; base `a47072d6e1477f66278e770c84b4c46c58dc82dd`. This is free implementation/replay, **not real-model acceptance**. No paid calls, new world, merge, or issue closure. The original provider archive is `issue255-claim-live-evidence-20261115.tar.gz`, 95,557,322 bytes, SHA256 `6736c9c23e8751190c0b693a519cf2fa3ba0ac0f8d3bdf4aa45281817b095b30`.

## Confirmed causes and ownership

| Original evidence | Cause | Change |
|---|---|---|
| River turn 10, `b3afc7fcd79a45acb520d7a9518989db` | Extraction omitted travel; clearing an invalid camera field left both people at home. Per-person routes duplicated one shared outcome. | New recorded Extraction/7 represents a trip once with explicit `actor_ids`; compiler produces per-person Movement and one Event. It never infers travellers from final visibility or prose. |
| Cafe turn 12, `a23601e9e1374583a476e5141fedc9bc`, epochs 0/1 | Declaration failure prevented Resolver from finding missing Galina route before the only repair. | Structurally readable proposals carry pending diagnostics into the existing Resolver. Geography, agency and camera are collected together, with publication prohibited while substantive errors remain. Malformed prerequisites still prevent dependent checks, not checks on unrelated declarations. |
| Same cafe outputs | Rejected final cast synthesized Galina's arrival in diagnostic scratch state, invalidating earlier real encounters. | No synthetic movement or address update after `scene_arrival_unproven`. Earlier encounters stay valid; genuinely impossible later contact still fails. |
| Olga background in turn 11 | Leaving a room was represented as canonical departure to an unknown place. | `local_exit` records the event and removes local visibility without changing canonical address. Actual departure still clears address; arrival into a canonical child room still uses that room ID. No Knowledge is derived from address, shared parent, visibility, or local exit. |
| Actor-camera provider/repair schema | Model was offered a field that this camera rejects. | v7 actor projection omits `observer_location_id` in first and repair schemas. Observer projection retains it. Legacy redundant annotation matching a fully validated route becomes a warning; conflicting annotation still needs repair. |
| River scope with zero step IDs | Camera-only repair could not add any missing route/location. | A conflicting structured camera declaration opens the connected actor/step dependencies. Model may add the missing shared route and referenced place. Unrelated keyed records remain unchanged; candidate hash, one-repair cap and claim-specific restrictions remain. |

A conversation **during** a shared trip may reference its preceding movement with `during_step_id`. Runtime checks explicit travellers and a common known origin/endpoint, without inventing an intermediate location. The accepted History Event retains `during_event_id`; Knowledge still requires actual per-claim perceivers. Before/after conversations remain ordinary ordered steps. This is a relation between existing Events, not a second spatial state or route graph.

Structural facts, claims, agency/consent, secrecy, chronology and identity retain their existing owners. No regex/NLP prose interpretation, automatic missing Events, extra critic, mandatory provider call or additional repair was introduced. Semantic warnings still do not block world launch.

## Production path and compatibility

`ContextBuilder → provider schema → SceneCandidate → compiler → StateResolver → existing atomic commit` uses the recorded version in ordinary, optional background and LTA. New turns record v7. Recorded v1–v6 Retry/regeneration retain their wire contract and hashes. v6 `actor_id` movement is not silently converted into v7. Old direct v1–v5 agency failures retain their existing behavior. There is no SQLite migration.

The transport stays the existing Responses JSON Schema path (its historical format label `extraction_v6` is just a name); actual schema and request metadata carry v7. Tight 32K first/repair contexts retain the original Narrative and mandatory reproductive identity/Knowledge. No model/context/output cap was raised.

Compilation collects readable declarations without granting authority. Rejected player actions do not manufacture secondary unknown-action errors; geography continues to be checked independently. Irrecoverable identity/type dependencies cannot safely be evaluated as if they were valid, and are reported as such. This is not a guarantee that all possible future semantic errors can be known before a model changes its interpretation.

## Repairing the original chain

The earliest affected accepted turn is 9 (porch), before the river omission in 10. Recovering only blocked turn 12 would preserve false history. Original turns 9–12 and Olga's background remain immutable evidence.

A minimal explicit production option on `POST /api/saves/{id}/turns` is `recovery_source_job_id`, with `kind=turn`, current revision and ordinary provider config, no replacement input. Storage requires a completed original Narrative in the same save and the original chronological position after rollback. It copies original input/prose, records source job/revision/version/Narrative digest, chooses the current server contract, and freezes context against corrected current before-state. Ordinary Retry itself is unchanged.

Use `rollback_last` to archive the incorrect suffix, then recover original jobs sequentially. The first corrected turn is a selectable sibling only when source parent and full before-state match. Later corrected suffix turns have new parents and explicit source-job lineage; they must not share an incompatible old node. Old variants, History, snapshots and request records are never rewritten. Background recovery reuses the original completed Narrative for the same explicit camera subject; an ambiguous source is rejected, not regenerated silently.

Free preparation:

```sh
RPG_SEMANTIC_ENABLED=0 python devtools/issue256/prepare.py EVIDENCE_DIR NEW_OUTPUT_DIR
```

In this workspace, `/workspace/work/issue256-ready/recovery-ready.sqlite` is at the last correct state before turn 9. Its manifest is **READY_NOT_REPAIRED**: all 52 original variants and 57 History rows remain unchanged, original jobs and source SQLite are preserved. No provider dispatch occurs. This is the input for separately authorized real recovery, not a repaired Live save.

Free authored control:

```sh
RPG_SEMANTIC_ENABLED=0 python devtools/issue256/replay.py EVIDENCE_DIR NEW_OUTPUT_DIR
```

`/workspace/work/issue256-free/control-final/` recovered all four unchanged original Narrative texts through production jobs on another SQLite copy, using explicitly labelled authored Extraction controls. Both characters reach porch → shore → cafe; Olga keeps `loc_home_sokolov`. Five mock Extraction calls (four foreground, one background), no Narrative generation, no repair. Each commit/reload matches, SQLite integrity is OK, original jobs remain unchanged. This proves the mechanism, **not DeepSeek semantic accuracy**. The authored places and answers are not installed into the real campaign.

## Free validation

- Original river/room replies still characterize their incorrect saved outcomes; both cafe epochs reproduce the missing route without fake earlier presence failures. Original hashes/bindings are retained.
- New tests cover shared arrival/return, independent NPC departure, unfinished intentions, co-traveller information and outsider rejection, local exit, all independent route/agency/camera errors before one repair, actor/observer schema, nested diagnostics, LTA NPC arrival and private Knowledge.
- Production recovery test: same prose, one Extraction, new contract/current before, unchanged source records, stale/duplicate rejection, commit/reload, original/corrected sibling selection and rollback.
- Existing suites exercise cancellation, stale epoch/revision, publication failure, one bounded repair, fact/provenance, Crisis/agency, old contracts, background and LTA.
- Desktop/mobile Chromium: **4 passed**, v6/v7 Retry → reload → continued turn; v7 additionally rolls back and recovers original Narrative through the production API without a Narrative call.
- Frontend unit: **153 passed**; TypeScript and production build PASS.
- Initial broader profile: **250 passed**; final expanded profile/full CI results are recorded in the PR conversation for the actual commit. A full run started before final compatibility changes is diagnostic, not a claim of final-HEAD success.

During free checks, two old-contract tests exposed changed first-error behavior; accumulation is now restricted to scene contracts. Three legacy camera tests expected needless repair for a correct route; their assertions now require saved outcome plus the specific warning and unchanged independent Fact, rather than merely loosening status checks. Two new authored controls initially used an invalid claim enum/missing LTA cause and an incorrect History field assertion; those test fixtures were corrected to the existing contracts, with no Runtime weakening.

## Remaining acceptance and proposed paid stage

Static validation cannot detect every movement that the model omits entirely from structured output. v7 removes duplicate route bookkeeping and misleading camera projection; whether DeepSeek actually extracts the original shared walk correctly remains **NOT TESTED live**. No claim that #255/#256 is finished or PR ready to merge follows from these tests.

Proposed first paid stage, requiring separate approval: **at most 10 new DeepSeek Flash calls / $0.60 conservative**, thinking off. Four original foreground Narratives plus Olga's original background each get one Extraction and at most one existing repair. No fresh Narrative or successful-call repetitions. Stop the dependent chain on failure; preserve all responses and usage. Real continuation through UI follows only after successful recovery and separately bounded gameplay authorization.

Baseline ledger inspected read-only: reservation 697, 697 total calls, no open unknown outcomes. Old 665 remains conservatively settled at its full $0.3244032, without fabricated usage. Last actual stage: 30 calls, 627,780 input / 23,856 output, $0.2169612 cold/peak conservative. Expected short recovery is roughly $0.04–$0.12; this is an estimate, not authorization or a price guarantee. Existing Budget reserves the full 1,048,576-input window plus 8,192 output ($0.3244032) before each dispatch, then settles actual receipts. $0.60 accommodates that reserve and expected earlier receipts; it may stop early. Unknown usage retains the reserve and stops further calls. Only existing cumulative limit configuration will change after approval; no new budget mechanism and no reuse of old permission.
