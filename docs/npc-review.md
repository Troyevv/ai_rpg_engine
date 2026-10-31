# Narrative NPC review (#167)

## Identity, canon and review

The Resolver registers the canonical Character before validating same-turn scene,
event and Knowledge references. `promotion.character` carries explicit initial
attributes; `promotion.fields` still requests all eleven CARD_FIELDS. Missing
text keys normalize to empty strings. Invalid types, provenance imports, canonical
ID collisions and impossible dates remain structural errors and use normal repair.
No sex, birthday, knowledge or reproductive ability is inferred from prose in Python.

`publish_cards` is the single materialization boundary for the engine, transactional
helper, simulation and LTA. It publishes identity cards and snapshot-owned
`pending_reviews` together. Only identity enters the unconfirmed descriptive card;
its proposed descriptions never enter Narrator/Extraction through that card.
Canonical, evidence-backed initial attributes and accepted deltas are independent
of the descriptive proposal. The existing limited LTA promotion policy is retained.

The same current snapshot, before/after snapshots and immutable History DAG own the
queue. No SQL table, independent character model, cross-branch queue, or rewrite of
historical saves is introduced. Old saves without the optional key have an empty
queue. A random review creation ID scopes local recovery to a specific variant;
canonical character IDs remain the extractor's validated IDs.

## Structure matrix

| Data | Startup source | Promotion/review behavior |
| --- | --- | --- |
| Eleven descriptive fields | shared `CARD_FIELDS` / draft schema | Same keys and card shape; partial input retained, all nonblank on confirmation |
| `biological_sex` | `ACTOR_FIELDS` → `Character` | Explicit male/female/null; unknown accepted as null; typed control |
| `birth_date`, development, life status, reproductive capability | Same canonical Character fields | Explicit values or canonical unknown defaults; date/calendar/stage and life validation |
| `capabilities` | `Capabilities` | Same five nullable booleans, typed three-state controls; never inferred from sex/age prose |
| `identity_components` | Character identity dictionary | Typed key/value editor; Runtime birth/name lifecycle constraints retained |
| physical state, situation, emotion | Startup `world.characters` / Character | Separate canonical inputs; field-level CAS and edit provenance |
| goals, intentions, obligations | Character Motivation / startup normalizer | Initial strings use the same model normalization; editor changes active text through lifecycle services, preserving inactive records |
| appearance, personality, values | Character profile models; initial card initialization | Optional initial structured profiles validated against existing models without imported provenance; accepted dynamic profiles shown via existing projections and preserved on confirmation |
| relationships, objective relations, roles, residences, conditions, Knowledge | Separate canonical stores | Existing deltas own creation/validation; editor displays available relationship/role/condition projections, never converts related records to card text |
| location, portraits, name history | Separate movement/portrait/name domains | Not arbitrary card-editor inputs; continue to use existing domain UI/pipelines |
| IDs, source/revision fields, birth/name provenance, fact references | Runtime-owned metadata | Never required manual fields and cannot be imported as a Character replacement |

The editor schema derives from Character using the same startup `runtime_schema`.
The generation schema omits technical profile histories; under soft context-budget
pressure optional *structured* initial profile enrichment is omitted from the wire
schema, while all eleven descriptions, identity/life attributes, capabilities and
motivation fields remain. Canonical data and Runtime validation are never omitted.
Nullable enum unions and unreachable schema definitions are compacted equivalently;
repair JSON is not double-encoded. This preserves the existing model budget.

## Edits, concurrency and provenance

Review edits are save-revision and review-revision guarded under `BEGIN IMMEDIATE`.
An operation receipt makes retries idempotent within the same snapshot lineage.
Drafts and proposals are durable but do not mutate canonical descriptions. Generation
uses existing providers, model leases, credentials and request/usage accounting;
its one-field output is a proposal, never a world mutation. Duplicate concurrent
field requests are rejected.

Confirmation updates the existing card, not Character wholesale. Canonical edits
compare changed fields with their creation baseline and current values. Concurrent
game changes cause a named conflict; keeping the current value resolves it. Life
changes use the existing life-domain; motivations use `replace_active`; the full
world, dates and references are validated before commit. A reviewer cannot use the
card to undo death, replace controlled-actor choices, rewrite recorded birth data,
or disable the capabilities of a participant in an active conversation.

History records canonical before/after values and the review operation. Initial
profile text fills only previously unset fields, never overwrites accumulated
personality/appearance or resurrects retired traits. Pending data is restricted to
the originating review audience; it is not a knowledge broadcast or phone contact.

## User flow

After successful publication: queue → descriptive sections → typed canonical state
→ existing connections → save/defer/confirm. Deferring dismisses the visible queue
without deleting identities. Selecting another card first saves edits. A local
recovery copy protects unsent edits and generated proposals, scoped by save,
review creation ID and revision. Confirmation remains disabled until eleven fields
are nonblank; unknown canonical attributes do not require fictional values.

Desktop has a persistent queue and editor pane; mobile uses a full-height surface,
horizontal queue/section navigation, independent content scrolling, safe-area
footer and fixed actions. It uses existing skin tokens, focus trapping and reduced
motion. Browser QA checks empty/long text, multiple NPCs, errors, proposal comparison,
canonical controls, defer/play/reopen/reload and confirmation on both viewports.
