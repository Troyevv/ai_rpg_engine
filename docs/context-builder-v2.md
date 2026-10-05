# Context Builder v2 in Runtime v3

The old builder serialized a broad world slice and discarded narrative continuity first when it overflowed. The new path selects a scene scope before serialization. Canonical WorldState remains authoritative, and the normal turn still uses Narrative + Extraction only.

## Scope and projections

`RelevanceResolver` constructs one `ContextScope` for a request. `CharacterContextClassifier`, both builders, HistorySelector and Director consume it. Extraction resolves the same policy against completed narrative as well as current player input, so newly affected entities can enter its slice. There is no LLM relevance call or recursive relationship-graph expansion.

- `FULL_PRESENT`: complete static card and active runtime for physical participants.
- `FULL_REMOTE`: complete personality for an active remote interaction; GM information does not authorize describing unobserved gestures or revealing private facts.
- `COMPACT_REFERENCED`: identity/role, current situation, topical motivations and selected relationships/facts; no biography, appearance or off-camera emotional exposition.
- `INDEX`: identity/name/role, capped at 64 optional entries. Explicitly referenced names are resolved against the entire card catalog before this cap.

Mention weights decay across the last three visible turns. An old protagonist participation is not a permanent history-selection reason. Threads, facts and schedules are ranked before assembly. The director receives selected thread/event IDs, not all global unresolved/due records. Facts are not included simply because a present actor knows them; selected Knowledge retains its actual owner and status.

The implementation uses deterministic lexical relevance and common Russian name forms, not semantic search. Names/aliases or IDs resolve explicit references; implicit pronouns and unusual inflections rely on current participants, recent narrative, motivations and events. This is a quality boundary worth checking with representative live play.

Narrative keeps up to six visible assistant scenes and their player inputs (respecting an explicitly smaller `recent_turns` setting). Extraction includes current canonical runtime, affected entity IDs, current input, completed narrative and schema. It omits old narrative, static cards, tone, global index and history. Schema descriptions are stated once in the extraction contract; shared `$defs` preserve validation constraints.

## Budgets and diagnostics

The default soft target is 18,000 estimated input tokens; `target_context_budget` is also a builder argument. The hard input ceiling is model context minus output reserve and existing framing margin. Optional index entries and lower-relevance supporting facts go first. Full participant cards, six-scene continuity, active motivations, current relationships, topical/causal facts and immediate events are never silently removed to meet a target. If mandatory context exceeds the hard ceiling, the request fails before calling the provider.

Selection diagnostics are recorded outside the LLM messages for Narrative, Extraction and both World Simulation stages. They include classified characters, selected/total section counts, continuity, previous input count and budgets. Classified INDEX count includes omitted index entries; it is not the number of cards sent. Per-message token estimates complement existing actual input/output/cache/cost accounting. Exact context reuse preserves selection metadata in job configuration, including regeneration, without changing the stored message array.

## State changes and compatibility

`Camera.remote_interactions` is an additive list of `{actor_id, channel, last_active_turn}`. Extraction must renew active interactions with current evidence in `final_scene.remote_interactions`; omission clears them. Physical entry wins over remote classification. Camera/POV changes reset the scene's interactions. A simple explicit current call/message action can activate the initial request; discussing a person or rereading an old message cannot. Existing saves default to an empty list. Transient character modes are never persisted.

Motivations gain the additive terminal status `expired`. Existing active IDs can transition to completed/cancelled/failed/superseded/expired with a current-turn quote. Unknown IDs cannot mutate existing motivations, and terminal entries cannot reactivate. New controlled-actor desires still require explicit player input. Completion semantics belong to the existing Extraction call; the old completion-verb and reply-name whitelists are removed.

Emotion has no allowed-emotion dictionary. Extraction supplies `player_evidence.emotion` and, for a semantic paraphrase, `emotion_assertion: "explicit_internal_state"`. A literal state excerpt is also supported. Runtime verifies a whole current-player declaration, excluding quoted speech, questions and conditional statements. Gestures do not automatically generate state. As specified, semantic truth of the model's assertion is the model's responsibility; this is not a second hidden NLP detector. The assertion is not persisted.

Extraction refreshes `physical_state` with current evidence, including the empty string when a condition clears; omitted fields still mean no change. There is no new evaluator call or physical-state vocabulary.

Relationships continue through the same directed mechanism for NPC→NPC, NPC→controlled and controlled→NPC. They are independent of emotion agency gates. Values are absolute canonical baselines, not deltas; the prompt asks for inertial updates and usually none after neutral conversation. Manual editing remains an override, with subsequent automatic evolution from the edited baseline. No direction is mirrored automatically.

Canonical initial Facts/Knowledge replace matching imported knowledge lines in prompts. Relevant unconverted prose remains a bounded, explicitly GM-only compatibility block; no holder is guessed and no Knowledge is granted. Legacy provenance warnings/history are not repaired or rewritten by this change.

## Validation and benchmark

- `python -m pytest -q`: 739 passed.
- `cd frontend && npm run build`: passed (existing bundle-size warning).
- New deterministic fixtures exercise selection/decay/remote entry, six-turn conversations and callbacks, emotional scenes, POV isolation, scene changes, lifecycle, emotion provenance, physical-state clearing, all relationship directions and manual baselines. Existing API/storage tests cover rollback, regenerate, variants, imports, time skip and background simulation.
- Some prior tests assumed that every known fact must enter a prompt or that Python determines semantic completion. They now supply an explicit topic or assert current-source validation. Existing positive emotion fixtures emit the new extraction assertion; negative provenance/gesture cases remain covered.
- These are deterministic tests and mocked LLM transport scenarios. They do not prove natural-language quality or semantic extraction accuracy for a live model. No paid provider call was made.

Reproduce the same-world comparison:

```sh
python scripts/benchmark_context_v2.py --baseline-ref 663c2e82c0a37b566b5c7ba2f1059915c2b1f92f
```

The fixture has 35 characters, 56 locations, 141 directed relationships, 221 facts, 442 knowledge records, 36 threads, 56 scheduled events and 551 history events. Both versions use a 128,000 context limit and 4,000 output reserve. Values below are the conservative UTF-8 heuristic, not actual API usage or a universal savings claim.

| Measurement | Before Narrative | After Narrative | Before Extraction | After Extraction |
|---|---:|---:|---:|---:|
| Estimated input tokens | 123,329 | 10,523 | 123,710 | 7,852 |
| Locations / 56 | 56 | 1 | 56 | 1 |
| Facts / 221 | 167 | 1 | 149 | 1 |
| Knowledge / 442 | 168 | 2 | 150 | 2 |
| Relationships / 141 | 16 | 4 | 16 | 4 |
| Threads / 36 | 36 | 1 | 36 | 1 |
| Scheduled events / 56 | 56 | 1 | 56 | 1 |
| History events / 551 | 31 | 1 | 31 | 0 |
| Assistant continuity | 0 | 6 | 0 | 0 |

After selection: 2 FULL_PRESENT, 0 FULL_REMOTE, 1 COMPACT_REFERENCED, 32 INDEX. The baseline had no character modes. Its overflow handling removed all six scenes, illustrating why optimizing the order of selection matters. Extraction's fixed schema cost can dominate a very small scene; the goal is to avoid repeating narrative material, not to guarantee a fixed savings percentage.
