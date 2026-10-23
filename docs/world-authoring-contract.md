# World authoring contract 1 (implementation in progress)

This contract supersedes revision 6's direct Runtime DTO generation, exhaustive
pair planning, mandatory semantic review and mechanical 6,000-character splitting
for new jobs only. Captured older jobs retain their contracts. Runtime, imports,
History persistence, leases, accounting, CAS and field locks remain unchanged.

The author document is preparation source, never a second running WorldState.
Compilation is pure: document + ID map + explicit settings produce a canonical
initial package, diagnostics and a field transformation map. No clock, randomness,
network, database writes or inference of prose is permitted in the compiler.

## Transformation matrix (before implementation)

| Author field | Target | Conversion / absent or ambiguous | Tests |
|---|---|---|---|
| version, record key | contract / ID table | version checked; identity(kind,key), reuse supplied IDs; collision blocks | deterministic, IDs |
| origin, field origins | transformation map | explicit/generated/unknown retained; no semantic claim of extraction accuracy | provenance |
| world title, setting, era, genre, tone, description, public description, rules | campaign | exact copy; no invented metadata | prose |
| character name, aliases | Character/display_name, card | exact copy | prose |
| age, role, biography | card fields | prose, no inferred birth date or occupation | prose, agency |
| appearance | AppearanceProfile/legacy_text | exact prose, never guessed feature kinds | prose |
| personality, communication, habits, strengths, weaknesses, fears | PersonalityProfile/items and card projection | exact text; omitted remains absent | prose |
| location, situation, physical state, life status, birth date | Character | explicit references and scalar values, no residence inference | references |
| goals, intentions, obligations | Motivation | stable IDs; controlled actor requires explicit origin | agency |
| location name, description, kind, parent | Location | explicit hierarchy; cycle blocks | cycles |
| organization name, kind, description, sites | Organization | description in context; references checked | references |
| organization parent | Fact/Claim organization.parent | explicit structural claim, no Knowledge broadcast | references |
| objective relation kind, endpoints, status, context | ObjectiveRelation | supported kinds only; symmetric normalization owned by Runtime | directed |
| feelings source, target, levels, context | Relationship | known dimensions only; very_low=-80, low=-40, neutral=0, high=40, very_high=80; unknown omitted | levels |
| fact text, secrecy, participants | Fact | exact copy; no holder inference | knowledge |
| past event text, participants, time description | portable History/legacy | preserve original temporal precision, no invented minute | time |
| knowledge holder, fact, status, evidence | Knowledge | explicit actor/fact key; prior knowledge kept in history, current knowledge only in WorldState | knowledge |
| residence actor/place, context | Residence | explicit only | references |
| occupation actor, kind, title, organization, context | NarrativeRole | explicit only | references |
| possession name, kind, owner, holder, place, status | SignificantPossession | explicit only; description retained as linked Fact | references |
| condition actor, description | Condition | no invented capability effects | references |
| commitment description, participants, place, time | ScheduledEvent | explicit temporal basis via existing Calendar; no precise deadline for vague prose | time, agency |
| opening actors, place, situation | Camera | exact copy; protagonist/control separate from POV | agency |
| opening date, weekday, clock, calendar profile | Meta/calendar and world_time | supplied reference; no minutes-from-Monday rule; missing exact clock requires author clarification | time |
| unsupported details | supported descriptive text or diagnostic | never silently discarded or coerced to another enum | diagnostics |
| uncertainties | author diagnostics | semantic warnings; never bypass invalid Runtime | diagnostics |

Each significant source field must be represented in the transformation map.
No field is deferred to a mandatory third LLM parsing pass. JSON schemas are
generated from the Pydantic author models. Fixtures test code, not live quality.

Live-проверка не выполнена.

## Implemented request plan and storage

- `world_authoring.py`: Pydantic source models and generated provider schemas.
- `world_authoring_pipeline.py`: captured contract, output estimate, source
  analysis, registered record planning, bounded disclosure batches, source edits.
- `world_authoring_compiler.py`: pure deterministic compiler, stable ID map,
  transformation map, canonical gate, portable initial History.
- Existing Preparation worker owns provider calls/usage, leases, retries and CAS.
  A format failure gets at most one automatic correction. Truncation and uncertain
  provider failure do not replay automatically. Compiler failure pauses for editing.
- Existing Workshop checkpoint forms and full initial editor show the author
  document. Compiled edits cannot be overwritten without explicit acknowledgement.
  Publication still uses the existing versioned draft and confirmation transaction.

Small world: analysis + document (two paid requests if eventually authorized),
then zero-provider compilation. Larger world: analysis + record plan + bounded
assigned-record batches, then zero-provider aggregation/compilation. Relations
are explicit planned records, never a generated Cartesian product of actors.
The request estimator is conservative UTF-8 accounting, not tokenizer telemetry.

## Explicit remaining limitations — not acceptance-complete

1. Source admission is at most 120,000 UTF-8 bytes and must fit the selected
   planning context with schema, answer and analysis reserves. The analysis helper
   supports lossless sections, but **creative planning across source sections that
   exceed context is not implemented**. Admission rejects this before paid work.
2. The registry plan is currently one response, with at most 3,000 planned records.
   Output-bounded expansion is implemented; output-bounded *planning* of a dense
   graph is not. A truncated plan requires explicit recovery, never a blind retry.
3. Existing plan/batch definitions remain immutable. Content edits and dependent
   recompilation work; changing a plan's batch topology needs reconciliation work.
   Do not claim arbitrary selective replanning is implemented.
4. The compact source format covers the fields in the matrix. It does not yet
   express every optional prior Runtime lifecycle feature (e.g. full pregnancy,
   contacts and name-change lifecycle records). Import/legacy generation still
   support their existing canonical representations. Do not claim complete parity.
5. Transformation entries identify every top-level record field and its canonical
   destination section. Fine-grained nested transformation locations still need
   expansion. Analysis accuracy and creative preservation of arbitrary prose
   remain author-review concerns; deterministic tests are not semantic proof.
6. No paid provider was called. Literary quality, real response-size planning and
   provider schema adherence are unverified. Browser execution requires a working
   Chromium installation; build success alone does not verify browser behavior.

## Reproducible checks

Offline documents: `tests/fixtures/world_authoring/{institute,family,orbital}.json`.
They are independent, manually inspectable author inputs, not Runtime snapshots.

```sh
python scripts/check_author_world.py --document tests/fixtures/world_authoring/family.json
python -m pytest tests/test_world_authoring.py -q
python -m pytest tests -q
cd frontend
npm run build
CI=true npm run test:e2e
```

Only after a **new explicit paid-test authorization**, in an isolated directory:

```sh
python scripts/check_author_world.py --live-source idea.txt --allow-paid \
  --database /tmp/author-live-new.sqlite3 --max-requests 12 --max-total-tokens 150000
```

The live command asks for a temporary key without storing it, caps request count
and conservative token reservations, records actual requests through existing
instrumentation, and never resumes a failed or uncertain job automatically. The
command has been prepared but **has not been run**. Its token reservation bound
is not a dollar-price guarantee.
