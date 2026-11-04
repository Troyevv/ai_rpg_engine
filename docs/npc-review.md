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

## Review hardening (#169)

Field proposals use a bounded NPC-specific context, not protagonist creation's
public directory. Narrative's `visible_views` and accepted surface reconciliation
supply the introduction and up to four recent relevant scenes; at most sixteen
witnessed events and twenty-four observer-known/suspected facts supplement them.
Personality/appearance, roles, residences and objective links use their existing
visibility projections. Another actor's Knowledge, unwitnessed source events,
unread remote motivations and hidden profile items never enter this context.
Directed feelings are restricted to the observer's own outgoing relationship.
No GM-only Narrative block or complete WorldState is sent. Character attributes
require observed source changes; old prose is explicitly subordinate to current
canonical profiles. The provider's actual token budget remains a hard guard.
Generation checks save revision both before the request and after its response.
A late response from an outdated world is rejected without applying any text.

DOB establishment now shares one domain procedure with Extraction and records
DOB provenance plus a History transition. Established game birth data stays
protected. Values already equal to current canon are no-ops: acknowledging a
later life change cannot clear its fact reference or repeat its lifecycle cascade.
Existing Life transitions and motivation lifecycle still own their side effects;
manual scalar edits get a separate canonical audit transition.

A pending card cannot silently disagree with an established appearance/personality
profile. The editor shows the visible current text beside the description and
requires an explicit “keep current profile” acknowledgement. Its opaque signature
is bound to the actual profile revision and stored with the draft. Later changes
invalidate that acknowledgement. Retirement stays retirement, and hidden traits
are not exposed by the comparison. Descriptive baseline text may be retained,
but all existing canonical projections continue to prefer the dynamic profile.
These are optional snapshot fields; old pending records remain readable.
