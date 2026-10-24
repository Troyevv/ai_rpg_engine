# World authoring contract 1

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
then zero-provider compilation. Larger world: analysis + bounded record-plan pages + bounded
assigned-record batches, then zero-provider aggregation/compilation. Relations
are explicit planned records, never a generated Cartesian product of actors.
The request estimator is conservative UTF-8 accounting, not tokenizer telemetry.

## Planning revision 2 and explicit limits

New jobs capture `prompt.planning_version=2`; captured revision-1 author jobs keep
one-plan execution and numeric batch identities. This is a scheduler revision of
the approved source/compiler architecture, not a replacement Runtime contract.

- Input: at most 100,000 characters at the API boundary and 120,000 UTF-8 bytes.
  Admission checks schema/context/answer reserves before provider work. Ordinary
  ideas stay whole. Larger inputs use lossless saved source sections.
- Planning responses: at most `min(32, max(1, (max_tokens-1200)//400))`
  records, summaries at most 200 characters. The source schema has a hard ceiling
  of 32 records; the executor validates the smaller assigned response bound.
  References can cross pages; the combined Plan checks the entire registry.
  Aggregate limit: 3,000 records. No pair enumeration or dropped mandatory edges.
  Each source section has at most 3,001 page attempts, with ordinary job usage and
  failure accounting; duplicate/no-progress records fail instead of looping.
- Every original section is passed to analysis and creative expansion. Each
  creative batch processes the sections in order, receiving its accepted partial
  and only its related accepted batches. It must preserve earlier substantive
  details. All intermediate versions are checkpointed. A later section can refine
  the world/opening; this produces a visible interpretation warning.
- All requests retain the conservative input + schema + full answer preflight.
  Oversized registry, related context or a single substantive record produces an
  actionable error before that request, never silent truncation. The 3,000-record
  bound is an aggregate ceiling, **not a guarantee that every density/profile fits
  every selected context**. Provider adherence remains a live-test question.
- Batch identities derive from their assigned records. Upstream edits reconcile
  the leased unit graph, preserve retired versions and attempts, and revalidate
  unchanged batches only if header and other dependency hashes still match.
  A changed batch with index-based field locks blocks with an explicit conflict;
  the author must restore the plan or explicitly unlock it. Locks never move to
  another entity merely because its array index happens to match.

Small world: analysis + one document request. Large world: section analyses +
bounded plan pages + expansion batches × source sections. Compilation and
aggregation make no provider calls. This strategy favors source coverage and
recoverability; long densely connected inputs can require many paid requests if
later authorized. It does not claim a fixed price or literary-quality guarantee.

## Additional lifecycle conversion matrix

| Source | Target / conversion | Absent, ambiguous or unsupported | Regression |
|---|---|---|---|
| character capabilities | Character/capabilities, nullable booleans | unknown stays null | lifecycle fields |
| developmental stage, reproductive capability, biological sex, identity components | corresponding Character fields | no inference from name, age prose or relationships | lifecycle fields |
| historical name changes | portable History/legacy identity_change, actor reference + exact original date/description | no invented minute or turn; not executable past transitions | lifecycle fields |
| relation since/until dates and outcome | ObjectiveRelation date/outcome fields | existing canonical chronological validation | compiler gate |
| residence/role status, dates, outcome | existing social phase fields | empty remains absent | source/compiler models |
| condition status, duration, effects, evidence | Condition + Capabilities | effects may restrict, not grant abilities | lifecycle fields |
| contact owner/character, label/address, kind, flags, provenance | Contact with stable ID and reference resolution; created_at is initialization registration | no contact inferred from acquaintance; no historical acquisition date invented | lifecycle fields |
| pregnancy gestational/impregnating actors, parents | Pregnancy and linked ReproductiveEvent | only explicitly present records; no random conception | pregnancy regression |
| conception earliest/latest dates | inclusive calendar-day interval; shift initial minute anchor to retain nonnegative historical minutes | no exact conception minute invented | pregnancy regression |
| due date/clock/description | ScheduledEvent pregnancy_due + existing boundary | missing exact executable boundary requires clarification | pregnancy regression |
| unborn child local key and sex | stable child slot; no Character before birth | unknown Runtime-required outcome diagnosed, never rolled | pregnancy regression |
| pregnancy fact/count_fact and child sex_fact references; description / count / sex | reuse explicitly named author Facts, or create linked secret Facts when absent | explicit Knowledge can reference the same Fact; no automatic Knowledge | pregnancy regression |

`author_transformations.py` now expands records, lists, dictionaries, capabilities,
qualitative dimensions, motives, calendar and temporal structures to leaf-level
source and target paths. Provenance points to retained source metadata; unknown
levels have an explicit omitted disposition. Paths identify source local keys and
canonical record IDs; they are an audit map, not executable LLM-generated rules.

## Scope exclusions and validation boundary

- Executable pending naming decisions and already active remote sessions are
  optional initial-state bridges, tracked in [#114](https://github.com/Troyevv/ai_rpg_engine/issues/114).
  They are not prerequisites for the mandatory creation path. `source_notes`
  preserves their full text with a visible diagnostic; an opening requiring their
  execution blocks compilation rather than pretending that prose is executable.
- Changed-batch field locks require explicit conflict resolution. This is the
  intended protection against lost edits, not an unfinished auto-migration feature.
- No paid provider was called. **Live-проверка не выполнена.** Literary quality,
  actual DeepSeek response-size behavior and source-preservation quality remain
  unverified. Fixtures verify transport, compilation and persistence, not LLM truth.
- Current Python/build/browser results and the exact commit are recorded in PR #105.
  Build success and the existence of browser tests alone are never browser evidence.

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

## Final scope classification (#44)

The completion criterion is a valid initial playable world, not exhaustive
serialization of every possible intermediate Runtime process.

| Capability | Initial-world obligation | Scope decision |
|---|---|---|
| Identity, prose, current location/state, objectives, relations, explicit Knowledge, chronology, opening/calendar | Required; invalid references/invariants block confirmation | Implemented; keep existing canonical gate |
| Existing residence/work, possessions, conditions, contacts, explicitly specified ongoing pregnancy | Required when supplied and supported | Implemented; never create absent circumstances |
| Historical name changes and other past transitions without executable time | Preserve precision and text | Portable History; no synthetic turn/minute |
| Pending naming decisions, pre-existing remote conversations/in-flight messages, specialized historical process internals | Rare optional initial scenarios | Preserve as source_notes with a visible diagnostic; no executable process is implied |
| Future births/naming, phone activity, progression of motives/personality, background lifecycle | Runtime simulation after Start Game | Existing Runtime owns progression; no parallel authoring simulator |

For an optional scenario that is indispensable to the opening, source_notes must
set requires_execution=true. Compilation then blocks with an actionable error;
accepting a warning never fabricates an executable state. The author may change
the opening or explicitly choose descriptive preservation. Source, source notes,
private descriptive Facts, and versions remain intact. Unknown schema fields are
still rejected rather than discarded. Model extraction/coverage accuracy remains
a live-review responsibility, not a claim of deterministic NLP verification.

| New author field | Destination | Conversion / missing behavior | Test |
|---|---|---|---|
| source_notes key/origin/field_origins | ID map / provenance | existing stable identity and metadata rules | source note compiler |
| capability, text | private Fact.text | exact labeled text, no inferred mechanics | source note compiler |
| participants | Fact.character_ids | explicit references only; no automatic Knowledge | source note privacy |
| requires_execution | diagnostics / compilation gate | true blocks; false retains prose with warning; no note means no generated record | source note gate |

## CI cancellation investigation

Run 40042668121 reached Playwright after Python (1772 passed on its merge ref),
build and browser installation succeeded. Setup/Python/build/install occupied
about 11m44s; the serial 216-test browser matrix then had only ~8m left in the
20-minute job. The log ends with cancellation at ~20m14s, consistent with the
configured job deadline; the API does not identify an external cancelling actor.
The job allowance is now 35 minutes, preserving every assertion and per-test
limit. Line reporting exposes individual progress. Browser fixture servers use
the existing structural retrieval path explicitly, avoiding attempts to load an
unavailable optional encoder; semantic retrieval retains its Python tests.

In this executor the Playwright CDN returned an HTML page instead of a ZIP. The
same Chrome-for-Testing 153.0.8010.12 headless ZIP from Google's official storage
installed successfully. Local runs use the existing PLAYWRIGHT_EXECUTABLE_PATH
option. CI keeps the normal Playwright installation, which already worked there.
