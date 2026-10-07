# Context Builder v2 in Runtime v3

The old builder serialized a broad world slice and discarded narrative continuity first when it overflowed. The new path selects a scene scope before serialization. Canonical WorldState remains authoritative, and the normal turn still uses Narrative + Extraction only.

## Scope and projections

`RelevanceResolver` constructs one `ContextScope` for a request. `CharacterContextClassifier`, both builders, HistorySelector and Director consume it. Extraction resolves the same policy against completed narrative as well as current player input, so newly affected entities can enter its slice. There is no LLM relevance call or recursive relationship-graph expansion.

- `FULL_PRESENT`: complete static card and active runtime for physical participants.
- `FULL_REMOTE`: complete personality for an active remote interaction; GM information does not authorize describing unobserved gestures or revealing private facts.
- `ACTIVE_REFERENCED`: absent author or acting NPC whose speech/action must be personalized now; identity, role, personality, communication style and bounded habits, plus topical runtime and directed relationships. No automatic biography or physical scenery.
- `COMPACT_REFERENCED`: identity/role and an ID-only runtime stub; no automatic emotion, situation, motivations, physical state or Knowledge.
- `INDEX`: identity/name/role, capped at 64 optional entries. Explicitly referenced names are resolved against the entire card catalog before this cap.

Mention weights decay across the last three visible turns. An old protagonist participation is not a permanent history-selection reason. Threads, facts and schedules are ranked before assembly. The director receives selected thread/event IDs, not all global unresolved/due records. Facts are not included simply because a present actor knows them; selected Knowledge retains its actual owner and status.

Structural relevance (scene, explicit names, motivations, causal links, recent history, selected threads and due events) combines with bounded local semantic candidates before deterministic ranking. Names/aliases or IDs resolve explicit references, including common Russian name/location forms. Semantic-only characters do not expand into their entire fact/Knowledge neighborhood. Extraction uses structural resolution against current input and completed narrative without running semantic search.

Classification priority is FULL_PRESENT > FULL_REMOTE > ACTIVE_REFERENCED > COMPACT_REFERENCED > INDEX. `participation.py` recognizes explicit authored-content requests such as «прочитать сообщение Юры», letters, voicemail, recordings, recalled dialogue and off-screen action. Without a name it uses a recent witnessed message Event's `author_id`; old saves can use an unambiguous named message in latest visible narrative. Authorship is optional additive Event metadata, validated against message participants. It is never guessed from all participants. Background actor metadata and structurally relevant due Director events also supply participation. A semantic-only overdue schedule cannot activate its actor or a Director due trigger.

The two-turn Yura regression resolves a message author on turn N and sends his personality/style on N+1, both with and without repeating his name. It leaves physical presence, remote interaction and canonical character state unchanged. Contrasting polite/verbose and dry/sarcastic authors retain different profiles.

### Local semantic service

`SemanticRetriever` is the only sentence-transformers integration. A lazy CPU process service indexes Facts, Threads, history Events, Locations, ScheduledEvents and compact character descriptions. Query text is bounded to 1,200 current-input characters, 600 latest-narrative characters and 400 current-motivation characters. It does not embed a concatenation of the entire story.

The default is `intfloat/multilingual-e5-small`; the requested baseline MiniLM remains configurable. Normalized vectors use cosine similarity, a minimum threshold and a maximum gap from the best candidate, per-type caps and deterministic type/ID tie-breaking. Caps: Facts 12, Threads 4, history Events 8, Locations 3, Characters 6, ScheduledEvents 4. The final hybrid scope further caps Facts at 24, Threads at 6, schedules at 12 and history at 16 / 2,400 estimated tokens. No vector DB, FAISS, extra LLM request or canonical embedding migration is added.

The process-local LRU cache (30,000 rows) keys embeddings by type, ID and content hash, within one model instance. Unchanged rows are reused; edits encode only changed rows. Deleted/rolled-back records are immediately absent from active search even if reusable cached vectors remain. Restart rebuilds the cache. Model/cache access is locked. Model/encoding failure falls back to structural resolution with a diagnostic error class and a 60-second retry cooldown.

Provision weights once, explicitly, before running offline:

```sh
python scripts/benchmark_semantic_v2.py --download
```

Runtime itself uses `local_files_only=True`, CPU and `trust_remote_code=False`; it never downloads weights during a turn. If weights are absent, gameplay still works through fallback. Dependency compatibility is Python 3.10+ (project baseline); this run and CI use Python 3.12. sentence-transformers brings PyTorch; the dependency file prefers the CPU wheel index. First model load/index build is slower than warm queries.

| Environment setting | Default |
|---|---|
| `RPG_SEMANTIC_ENABLED` | `1`; `0` disables retrieval |
| `RPG_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` |
| `RPG_EMBEDDING_THREADS` | `2` CPU threads |
| `RPG_SEMANTIC_THRESHOLD` | `0.785` for E5, `0.30` otherwise |
| `RPG_SEMANTIC_MAX_GAP` | `0.06` for E5, `0.20` otherwise |
| `RPG_EMBEDDING_QUERY_PREFIX` | `query: ` for E5, empty otherwise |
| `RPG_EMBEDDING_DOCUMENT_PREFIX` | `passage: ` for E5, empty otherwise |

Set model/cache settings before starting the process; changing model requires a restart. Thresholds are model-specific and based on a small fixture, not universal quality guarantees.

### Truth and ownership invariants

- semantic similarity != canonical truth
- semantic similarity != Character Knowledge
- relevance != physical presence
- narrative participation != physical presence
- mere reference != behavioral participation

Canonical Facts appear once. POV Knowledge and acting-actor Knowledge are separate ownership blocks containing actor_id, fact_id and canonical status (including unknown/suspected); Narrative's `current.knowledge` is empty to avoid duplication. Mentioned/index actors do not dump Knowledge. Retrieval never creates or changes these records. The GM-only contract forbids treating absent Knowledge as permission to reveal a fact.

Narrative keeps up to six visible assistant scenes and their player inputs (respecting an explicitly smaller `recent_turns` setting). Extraction includes current canonical runtime, affected entity IDs, current input, completed narrative and schema. It omits old narrative, static cards, tone, global index and history. Schema descriptions are stated once in the extraction contract; shared `$defs` preserve validation constraints.

## Budgets and diagnostics

The default soft target is 18,000 estimated input tokens; `target_context_budget` is also a builder argument. The hard input ceiling is model context minus output reserve and existing framing margin. Under soft pressure, weak semantic-only actor cards, low-scoring supporting Facts (and their Knowledge rows), distant history and optional legacy prose are trimmed first. The compact identity index survives soft overflow and is dropped only near the hard ceiling. Full participant cards, ACTIVE_REFERENCED personality/style, six-scene continuity, core relationships and highest-scoring topical facts remain protected. If mandatory context exceeds the hard ceiling, the request fails before calling the provider.

Selection diagnostics are recorded outside the LLM messages for Narrative, Extraction and both World Simulation stages. They include classified characters, selected/total section counts, continuity, previous input count and budgets. Diagnostics distinguish scope-selected and prompt-included counts for each character mode and entity type. Knowledge counts separate POV, FULL_PRESENT, FULL_REMOTE and ACTIVE_REFERENCED owners. Per-entity diagnostics include similarity, reasons and selected/included flags. Semantic statistics include model, effective threshold, duration, active document count, cache hits/misses/rebuilt rows and candidate counts by type. Classified INDEX count includes omitted index entries; it is not the number of cards sent. Per-message token estimates complement existing actual input/output/cache/cost accounting. Exact context reuse preserves selection metadata in job configuration, including regeneration, without changing the stored message array.

## State changes and compatibility

`Camera.remote_interactions` is an additive list of `{actor_id, channel, last_active_turn}`. Extraction must renew active interactions with current evidence in `final_scene.remote_interactions`; omission clears them. Physical entry wins over remote classification. Camera/POV changes reset the scene's interactions. A simple explicit current call/message action can activate the initial request; discussing a person or rereading an old message cannot. Existing saves default to an empty list. Transient character modes are never persisted.

Motivations gain the additive terminal status `expired`. Existing active IDs can transition to completed/cancelled/failed/superseded/expired with a current-turn quote. Unknown IDs cannot mutate existing motivations, and terminal entries cannot reactivate. New controlled-actor desires still require explicit player input. Completion semantics belong to the existing Extraction call; the old completion-verb and reply-name whitelists are removed.

Emotion has no allowed-emotion dictionary. Extraction supplies `player_evidence.emotion` and, for a semantic paraphrase, `emotion_assertion: "explicit_internal_state"`. A literal state excerpt is also supported. Runtime verifies a whole current-player declaration, excluding quoted speech, questions and conditional statements. Gestures do not automatically generate state. As specified, semantic truth of the model's assertion is the model's responsibility; this is not a second hidden NLP detector. The assertion is not persisted.

Extraction refreshes `physical_state` with current evidence, including the empty string when a condition clears; omitted fields still mean no change. There is no new evaluator call or physical-state vocabulary.

Relationships continue through the same directed mechanism for NPC→NPC, NPC→controlled and controlled→NPC. They are independent of emotion agency gates. Values are absolute canonical baselines, not deltas; the prompt asks for inertial updates and usually none after neutral conversation. Manual editing remains an override, with subsequent automatic evolution from the edited baseline. No direction is mirrored automatically.

Canonical initial Facts/Knowledge replace matching imported knowledge lines in prompts. Relevant unconverted prose remains a bounded, explicitly GM-only compatibility block; no holder is guessed and no Knowledge is granted. Legacy provenance warnings/history are not repaired or rewritten by this change.

## Validation and benchmark

- `python -m pytest -q`: 766 passed.
- `cd frontend && npm run build`: passed (existing bundle-size warning).
- New deterministic fixtures exercise selection/decay/remote entry, six-turn conversations and callbacks, emotional scenes, POV isolation, scene changes, lifecycle, emotion provenance, physical-state clearing, all relationship directions and manual baselines. Existing API/storage tests cover rollback, regenerate, variants, imports, time skip and background simulation.
- Some prior tests assumed that every known fact must enter a prompt or that Python determines semantic completion. They now supply an explicit topic or assert current-source validation. Existing positive emotion fixtures emit the new extraction assertion; negative provenance/gesture cases remain covered.
- These are deterministic tests and mocked LLM transport scenarios. They do not prove natural-language quality or semantic extraction accuracy for a live model. No paid provider call was made.

Reproduce the same-world comparison:

```sh
python scripts/benchmark_context_v2.py --baseline-ref 663c2e82c0a37b566b5c7ba2f1059915c2b1f92f
```

The fixture has 35 characters, 56 locations, 141 directed relationships, 221 facts, 442 knowledge records, 36 threads, 56 scheduled events and 551 history events. Both versions use a 128,000 context limit and 4,000 output reserve. See [context-builder-v2-results.md](context-builder-v2-results.md) for the real-model comparison, prompt-part breakdown, selected/included counts, semantic quality/performance and limitations. These are conservative UTF-8 estimates, not actual API usage or a universal savings claim.

Reproduce the Russian model comparison (omit `--download` once weights are cached):

```sh
python scripts/benchmark_semantic_v2.py --download
python scripts/benchmark_semantic_v2.py --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --download
```

Tests use controlled encoders and disable default retrieval so CI is reproducible without downloading model weights. The separate benchmark uses real local weights. Neither benchmark generates live Narrative prose. PR #47 remains draft for repeat live QA; no automatic merge and no Epic #36 follow-on work are part of this change.
