# Significant possessions (#77)

`WorldStateV3.possessions` is a map of stable `SignificantPossession` identities.
It is a small continuity domain inside the existing Runtime, not Tabletop inventory.
Owner (title), holder (custody), location and status are independent nullable fields.
Unknown does not mean unowned. Nothing infers custody from ownership, residence,
Character movement, a mention, age or elapsed time. Destruction retains the identity
and historical ownership; it makes the object unavailable permanently.

## Mutation and evidence

`possession_deltas` enters the existing RawTurnResult → StateResolver → StatePatch
pipeline. Each optional record is separately validated, capped at 24 per extraction.
It requires a completed-outcome assertion, continuity significance, a current
accepted Event/Fact, a verbatim narrative source, known references and CAS revision.
Failed optional changes produce `possession_rejected` diagnostics and leave the
object untouched. No extra LLM call or second Resolver is introduced.

Operations: introduce, acquire, transfer, gift, sell, lose, recover, return,
destroy, relocate. `updates` is partial, and explicit null clears stale information.
A changed owner requires explicit holder/location; changed custody requires explicit
location, including null. Loss preserves ownership but clears custody; recovery
must establish a holder or place. A destroyed identity cannot be recovered.
Multiple changes of one object in one extraction require distinct ordered Events.

Voluntary sales/gifts require the current owner's decision. Changes involving an
EXTERNAL actor's voluntary disposal/custody/purchase require explicit player evidence;
background cannot manufacture authorization. An AUTONOMOUS actor may return a
borrowed object. Involuntary changes require completed action/observation/discovery
consequences, not a communication asserting a plan. Accepted evidence and semantic
assertions are a trust boundary: Python validates references, source, agency and
transition consistency, not the natural-language meaning of arbitrary quotations.

A per-object applied operation ledger binds immutable fact IDs and operations.
Repeated extraction cannot reapply an accepted operation, even with renamed event
IDs. Reusing an introduction fact cannot create a second ID. A new ID with the same
normalized name/type is rejected conservatively; explicitly distinct similar
objects need distinct identity descriptions. This is not fuzzy entity matching.

## History, persistence and compatibility

Changes append before/after records and provenance to existing WorldHistory.
Non-routine operations produce #40 Milestones; relocation alone does not.
Existing transactions, original regeneration snapshots, history heads, variants,
rollback and sibling snapshots own atomicity and isolation. No SQLite table or
parallel inventory schema is introduced. Read migration defaults missing maps to
empty and logs/drops malformed optional entries in the read projection only.
Old JSON/history remains untouched; old prose never generates objects.
Structured #78/import data can supply this same model, with validated references.
#39 remains authoritative for locations/residence; no implicit title to a residence.
#38 remains authoritative for capabilities. Future #43/#44/#45/#46 reuse this model.
No Tabletop models, equipment, rules or content packs are changed.

## Knowledge and bounded context

Creation `fact_id` identifies the object. `field_facts` identifies the immutable
source for each current field. Changing custody does not replace the source for
unchanged ownership. Knowledge is acquired only through existing #76 witnessed
paths. Neither being the owner nor being in the same scene grants knowledge.
Old beliefs stay unchanged until a grounded #76 correction. Use exclusive Fact
claims (`subject_id=item_id`, `predicate=possession.<field>`, `scope=ownership`)
when old/new assertions are mutually exclusive.

Context Builder uses the existing ContextScope: explicit names/IDs first, then
scene locations and related characters, at most 12 records and 6000 JSON characters.
Under model hard-limit pressure, lower-ranked incidental objects are omitted while
explicitly named objects are retained. Existing prompt schema compaction also uses
validation-equivalent JSON Schema forms; no model limits or narrative history limits
are raised. Shared social relation projections reuse only IDs present in the current
relation block, preserving full rows when their referenced relation is absent.
Narrative receives only fields its observer knows, with per-field `known_by` for
other actors. Hidden possession facts, history events and milestones are withheld.
Extraction receives scoped current truth/revisions and knowledge attribution;
full ledgers/history are never injected. Missing projected fields mean unknown,
not current access. A field's fact must establish that exact field; when audiences
differ, use separate facts/deltas. Current implementations rely on Extraction to
make this semantic distinction, as other evidence-bound Runtime domains do.

The feature is usable through normal narrative actions, the existing Fact/Knowledge
and Milestone views, and the deterministic QA checkpoint. A dedicated property
management UI is outside #77 and belongs to later UI work; there are no dead endpoints.

## Verification

`tests/test_possessions.py` covers lifecycle, owner/holder/location, source/CAS/agency,
replay/renamed extraction, no inferred items, bounded context and secret information,
ordered transitions, migration, atomic history/siblings, real engine jobs,
regeneration/variant selection/rollback and Hypothesis elapsed-time invariants.
See [manual QA](manual_qa/narrative_v4/possessions.md).
