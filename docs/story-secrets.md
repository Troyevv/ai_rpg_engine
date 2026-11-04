# Story secrets and private information (#178)

`Fact.visibility` remains privacy (`public` / `secret`). It is **not** plot classification.

## Canonical contract

- `story_secret: bool = false`: explicit author/Extraction classification of meaningful concealed plot information. Ordinary messages, technical receipts, sensitive conditions and family facts do not imply this flag.
- `secret_subject_ids: list[str] = []`: the people the secret concerns, independently of `character_ids`, witnesses, senders and Knowledge holders. Empty means a world secret.
- `secret_existence: hidden | discoverable = hidden`: explicit permission for anonymous placeholders, never permission to reveal content.
- `origin_remote_event_id: str | null`: Runtime-owned provenance for new facts originating in private communication. Extraction cannot supply it. An unread private-origin fact cannot advertise itself through a placeholder, even if classified discoverable.
- `Knowledge.confirmed_once`: branch-owned transition metadata preventing a later re-establishment of a retired belief from becoming a second first discovery. Initial `known` is also treated as already confirmed.

Facts retain existing IDs and immutability. References are checked by Runtime. No text classifier, keyword heuristic, separate secret database, or additional model call is introduced.

## Written disclosure

Existing Narrative / phone Extraction accepts `secret_disclosures` entries:

```json
{"source_event_id":"accepted-message-id","fact_id":"original-secret-id","assertion":"confirmed","evidence":"accepted source explanation"}
```

`assertion` is `confirmed` or `rumor`. A newly authored letter may reference its accepted artifact ID; Narrative Remote resolves that ID to the canonical event. An existing letter uses its canonical ID. Sources must belong to the current accepted semantic batch or an explicitly accepted Narrative remote record. The semantic interpretation is immutable per message/fact; a later correction requires a new source and the existing belief lifecycle.

Runtime stores links on `RemoteEvent.secret_disclosures`. Delivery grants nothing. Actual `read_by` **and** `delivered_to` permit consumption of an accepted link. Already-read messages are handled in the same Extraction transaction; future readers consume the saved link without a provider request. Group membership is not perception. `confirmed` may establish `known`; `rumor` gives `suspected`, never downgrades existing `known`, and does not revive retired beliefs.

All acquisitions use the existing Knowledge transition machinery, claim-conflict handling, revisions and History. Exact message testimony remains a separate private, non-story fact. Calls retain their existing Event/Knowledge contract. Reading never converts arbitrary Remote `fact_ids` into truth.

## Gameplay projection / #168

`ui_view(...).story_secrets` is relative to **controlled_actor_id**, never camera/inspected NPC:

- `personal[subject_id]`: rows for this subject only.
- `world`: subjectless rows.
- `revealed`: deduplicated known secret facts for the existing inspector. Its character links point to secret subjects.

Unknown rows contain only `{id, status: "hidden"}`. IDs are stable opaque observer/fact identities; no canonical fact ID, text, evidence, importance or title is supplied. Known rows contain `fact_id`, `text`, and the observer's available acquisition evidence as `source`. No controlled actor yields no rows. Hidden existence, protected conditions/reproduction/possessions, hidden births and unread private origins override discoverability.

`first_confirmations(before, after, accepted_history)` returns provenance-checked first confirmations (`new` / `revealed`) for the same controlled actor. It consumes accepted acquisition/event records, ignores migration rows, suspects, replays and control switches. #168 must call it **after successful commit** and scope presentation deduplication by save/actor/branch. It must not infer discovery merely from loading a snapshot. Notification rendering, fog, and seen-animation state remain #168.

Gameplay fact aliases and Knowledge are filtered server-side. Other minds' Knowledge, unknown private facts, raw knowledge sections, legacy secret-card fields, and omniscient Extraction/StatePatch diagnostics are excluded. History event visibility is witness-based. Explicit `GET /api/saves/{sid}/author-state` returns the original snapshot for author inspection; it is never embedded in ordinary save responses. This is an explicit view boundary in the existing single-user application, not a new authentication/role system.

## Authoring and compatibility

Draft schemas, field editing, creative generation, legacy handoff, Extraction and snapshot persistence carry classification and subjects. New generation uses `secret_subject_ids`; the old editor `owner_id` is accepted for compatibility. Existing schema factoring is shared by initial and creative generation to preserve context headroom without dropping constraints/content.

A legacy draft's explicit private `owner_id` can recover personal classification/subject. A lone private flag, participant list or message text cannot. Ambiguous v3 facts default to non-story with original fact, Knowledge and author access intact. Exact communicated-text facts are identified by their canonical remote-event identity, not their wording. No SQL schema migration or bulk rewriting of historical snapshots is required. New fields have neutral defaults. Before/after snapshots, independent variants, read receipts and rollback stay in existing repository transactions.

## Verification boundaries

Tests use real Runtime, APIs, SQLite, History and browser, with controlled provider responses. They do not establish live DeepSeek interpretation quality. No provider credentials or paid calls were used. A false semantic `confirmed` supplied by a model remains a model error; Runtime verifies source/reading/references rather than adjudicating prose. Legacy free-form text cannot be semantically reclassified without author input; arbitrary hidden information placed inside an otherwise public biography cannot be identified by structural validation.
