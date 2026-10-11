# Character Knowledge lifecycle (#76)

This extends Runtime v3 `Fact`, `Knowledge`, `StateResolver`, `WorldHistoryV3`,
ContextScope and the existing transactional snapshots. There is no second world,
memory store, gossip agent, background refresh or mandatory model call.

## Truth and belief

Facts are immutable assertions with stable IDs; a changed assertion gets another
ID. Canonical life/social/role state still owns objective truth. Character Knowledge
references the assertion the actor believes, not a mutable field of that state.
An actor may therefore still **know** "Oleg works in the workshop" after Oleg's
canonical role moved to the academy. No status or knowledge changes merely because
world truth or time changed. Relative staleness is not secretly written into a mind.

`Fact.claim` is optional: `{subject_id, predicate, value, scope: ""}`. Its subject,
predicate and scope identify an **exclusive single-valued slot**; value is the
asserted value. Extraction reuses exact IDs. Use `primary_employment`, for example,
not a many-valued "jobs" or "friends" slot. Scope distinguishes concurrent roles or
historical periods. Omit the metadata if exclusivity/identity is not established.
Text similarity, regex and translated words are never identity or truth classifiers.
Legacy facts remain unstructured; migration does not infer missing claim semantics.

| Knowledge status | Meaning |
|---|---|
| `known` | Current confident belief; not proof that the objective assertion remains true |
| `suspected` | Current uncertain belief; alternative suspicions may coexist |
| `unknown` | Explicit absence/loss of knowledge, preserved in context as a boundary |
| `outdated` | Evidence established the old belief is no longer usable, without requiring a replacement |
| `refuted` | Evidence explicitly disproved the old belief |
| `superseded` | Old belief retired in favour of a correction; `replaced_by` identifies it |

A corrected belief is `known` plus the old record's `superseded` transition, not an
extra certainty level. Retired records are historical, never current permissions
for kinship, roles, milestones, personality or values. A character who has not
received an update keeps the old `known` record unchanged.

## Acquisition and chronology

Use the existing `knowledge_gained` array. Every transition requires an accepted
Event in that extraction, the actor in witnesses, the fact in fact_ids and one of
the existing information media: observation, conversation, message, testimony or
discovery. Both acquisition and event evidence must occur in completed narrative;
a player's intended future conversation alone does not qualify. Message/call/public
information reuse existing grounded media; this does not implement #70 or add a
new inference mechanism. Perception capabilities and foreground/background ownership
are checked. Semantic entailment is still Extraction's responsibility; Runtime
validates structure and provenance rather than pretending a quote match proves it.

New known belief supersedes conflicting known values for that actor's exact slot.
An explicit `supersedes: [old_fact_id]` can also correct legacy assertions, but both
old and new IDs must be in the same accepted event and belong to that actor.
Unrelated characters are never changed. Suspected alternatives do not automatically
retire confident knowledge. Same-value assertions are not contradictory.

Each record has revision, source_event_id, evidence, source_turn and replaced_by.
Optional expected_revision is compare-and-set against the exact prior record;
reviving a retired record requires it. Unchanged replays do not create history.
Multiple acquisitions for one record/known slot need distinct Event.order; without
it the ambiguous group is rejected with diagnostics. Ordered application rechecks
revisions. Invalid optional records are dropped locally before retiring anything.

`knowledge_acquisitions` retains before/after, source and trigger_fact_id; the latter
links automatic retirement to the correction event, without pretending the actor
heard the old assertion again. `state_changes` records `knowledge_transition` for
chronological History. Previous provenance remains in before snapshots and the
append-only lineage. Current state does not require historical events to be loaded.

## Context, UI and performance

The existing selector includes up to 48 relevant belief records for participating
actors, with an extra single hop to the matching slot's older/current assertion.
Narrative receives current known/suspected/unknown; Extraction may additionally see
bounded retired records/revisions for explicit revival. Neither receives the whole
belief history. Immutable assertion text accompanies selected IDs. The Narrative
contract explicitly requires behaviour from beliefs even when GM truth differs.

The existing dossier and Memory surfaces distinguish current and former beliefs,
show correction evidence and the replacement. Labels follow the existing Russian
Inspector convention; stored statuses/slots remain language-neutral. No new UI
ownership policy or future dossier redesign is introduced.

Acquisition is capped at 64 proposals/turn. The resolver indexes existing knowledge
once for the actors actually receiving valid evidence, then visits conflicting slot
entries. No fact × NPC refresh, per-NPC LLM calls, deterministic decay or automatic
propagation. Context selection and ordinary state validation retain their existing
linear passes. History remains in the existing archive, not a growing prompt field.

## Compatibility and limits

Old v3 rows get safe defaults (revision 0, unknown provenance); v2 migration retains
its original History provenance. Historical snapshots are not rewritten. Malformed
optional new metadata is salvaged locally; broken core actor/fact references remain
errors. No SQL migration or schema_version bump is needed. Existing StatePatch CAS,
atomic jobs and history ancestry own reload, regenerate, rollback and branch isolation.

Structural contradiction handling only works where the claim slot is explicitly
established. It does not infer arbitrary free-text contradictions, truth, forgetting
or a person's access to public information. Live-model semantic recall needs manual
QA. Later epic issues (#43/#44/#46) may reuse this path; they are not implemented here.

Verification: `tests/test_knowledge_lifecycle.py`, existing Runtime/Knowledge suites,
`frontend/e2e/knowledge.spec.ts`, and [manual checkpoint](manual_qa/narrative_v4/knowledge.md).
