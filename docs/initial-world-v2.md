# Initial World State v2 — implementation record (#44)

**Work in progress. This is not an acceptance-complete implementation of #44.**

Baseline: master `442c95b`, after merged PR #104. Read `AGENTS.md`, Epic #36,
and the complete #44 description including the pre-implementation clarifications.

## Boundary audit

The authoring document is a versioned `world_draft` in the existing document
journal. Its `world.version = 2` contract is different from `WorldStateV3`.
`draft_world.prepare()` creates compatibility projections; it is not proof that
the document can run. `DraftStorage.confirm_draft()` persists through
`migrate_snapshot()`, which calls `migrate_v2()` and the canonical invariants.

The old conversion omitted explicitly supplied personality/values and several
other Character fields, Knowledge lifecycle/provenance, Fact claims, some Thread
and ScheduledEvent fields, reproduction/process collections, and pacing/risk and
protagonist metadata. These fields could survive authoring export but disappear
at Start Game. The converter now copies applicable fields according to existing
Runtime models. No second Runtime or authoritative world schema is introduced.

The first implementation increment adds `services/initial_world_v2.py`:

- `normalize()` accepts explicit `creative_generate` / `normalize_existing`
  operations with identical deterministic canonical semantics. Neither operation
  performs LLM calls or invents missing story facts. Creative completion belongs
  upstream of this boundary.
- Explicit canonical fields of new authoring input are checked with the existing
  Pydantic models before migration, so malformed new fields cannot silently vanish
  through historical-load salvage. Errors include the field path and error type,
  without including raw field contents.
- `readiness()` delegates to the same Runtime migration/invariants. Existing
  draft validation and therefore confirmation include this check. Broken
  canonical references block Start Game rather than passing authoring checks.
- Structured Motivation records and retired Knowledge statuses survive draft
  prepare, readable export and Runtime conversion. An unknown scheduled date can
  remain `None`; no precise time is invented for a vague future plan.
- Advisory review no longer requires every NPC to have a private secret.

## Compatibility

The checkpoint foundation adds six SQLite tables (`preparation_runs`,
`preparation_units`, `preparation_resources`, `preparation_attempts`,
`preparation_submissions`, `preparation_field_locks`) through an
idempotent additive migration. No historical-snapshot rewrite, dependency
addition, or Tabletop change. The existing migration cache and immutable History DAG remain
the owners of saved migrations/history. Old saves continue to use the existing
conservative load path, not the stricter new-authoring boundary.

Keep the existing distinction between legacy name-only places and explicit #39
structured geography. Adding an empty `organizations` map to every old draft
changes its migration identity mapping and breaks legacy QA references. This
was caught by the full suite and removed. New structured plans must declare
their stable location/organization IDs explicitly; do not rewrite old IDs.

## Current acceptance status

The implementation below supersedes the initial incremental TODO lists. Quick
and Scenario hand-off now use the staged worker, canonical record forms support
paused editing, and prompt revision 5 reviews unbound/revised source semantics.
Final suite evidence and any remaining acceptance limitations are recorded at the
end of this document and in PR #105. Earlier increment notes describe historical
milestones, not the current feature inventory.

## Verification

`tests/test_initial_world_v2.py` covers generated/JSON/structured Markdown
equivalence; idempotency; preservation of personality, values, completed goals,
Knowledge revision/evidence, Fact claims and reproduction processes; unknown
birthdays/residences/deadlines; path-specific malformed-field/reference errors;
actual import/author/confirm APIs with idempotent confirmation; secret filtering;
ordinary turns, serialization/reload and sibling History branches.

All provider-related tests use mocks/fixtures; no paid provider calls were made.
Exact final suite/browser results are recorded in the PR description.

## Second implementation increment

- Canonical snapshots import into the existing editable envelope, without a
  retained second world state. IDs (including identically named places), observer
  camera, calendars, canonical metadata, portable History and structured
  Milestones survive author/confirm/save. Missing external History produces an
  author warning rather than invented history. Empty observer worlds stay empty.
- `world_interpretation.py` validates typed entity/claim extraction, exact source
  quotes (uniquely recoverable offset errors are repaired deterministically),
  references, knowledge holders, explicit/inferred/open/prohibited/ambiguous
  classification and source time scope. Identity reuse is exact, never fuzzy.
  The existing generation API accepts `task=interpret`; immutable revisions use
  `document_versions`. Public reads expose no claim/entity/source text.
- A reserved existing Fact/Claim predicate `organization.parent` represents a
  direct parent company: subject_id is the subsidiary, value is the parent ID.
  The canonical residence/organization invariant validates references, conflicting
  current parents and cycles. Nonempty scope denotes a historical/qualified claim,
  not a current edge. No claim means unknown. Fact visibility/Knowledge remains
  responsible for disclosure; no new economy or organization graph store.
- `initial_world_stages.py` provides independently typed request payloads,
  application-owned roster identities, bounded character batches, deterministic
  canonical composition and input fingerprints/selective invalidation. It now feeds the staged worker; the default UI
  still uses the monolithic route pending hybrid editor integration. Canonical source facts still
  need complete semantic protection in the integrated orchestration path.
- `generation_checkpoints.py` adds a tested persistence foundation using existing
  Preparation IDs and the version journal: immutable payloads, input hashes,
  output references, attempts, expiring worker leases, transactional commit CAS,
  pause boundaries, cancellation and interrupted-request uncertainty. These
  methods now back the staged worker and application startup recovery. Existing
  legacy jobs continue to run via their previous lifecycle. UI editing and
  selective regeneration remain incomplete.

Additional deterministic tests cover canonical snapshot API import/confirm,
empty observer worlds, five subsidiaries, broken/cyclic organization references,
interpretation failure/cancel/revision/privacy, bounded batch composition,
selective input invalidation, durable journal reload, lease replacement, late
commits, pause/resume, cancellation, retry budget and uncertain billing outcomes.

## Third implementation increment

`world_generation.py` runs interpretation, setting/roster, places, bounded NPC
batches, life, lore, opening and deterministic assembly through existing
Preparation/model leases and tracked usage. It passes typed partial schemas,
curated contexts and saved prompt/config revisions; final assembly makes no LLM
call. Automatic retries are limited to malformed local stage output; provider
failures require explicit retry and cannot echo private request text into status.

Job creation and immutable brief/Scenario/settings/prompt capture now share one
SQLite transaction, before dispatch or model-lock acquisition. A shutdown between
submission and worker startup remains resumable. Stage execution owns an expiring
lease with heartbeat even while waiting for a local model. Pause commits the
in-flight validated result and schedules no next unit. Restart resumes safe
checkpoints using existing encrypted credentials, or waits visibly for access;
in-flight outcome uncertainty requires explicit retry. Cancellation preserves
prior checkpoints/drafts. Idempotency keys prevent duplicate HTTP submission.

The author inspection API never returns artifacts without author mode. Public
save projections exclude source provenance/settings text, secret Facts without
POV knowledge and other NPCs' Knowledge. Canonical data remains intact. Assembly
publishes through existing versioned world_draft only after current completed
checkpoints and canonical validation pass in a guarded transaction.

Creation settings validate stable genre IDs, optional geography/world type, cast
targets and expressiveness without generating life events. User-defined NPCs
remain above cast targets. Canonical expressiveness is presentation-only;
conservative legacy default is realistic, new generation default is expressive.
The existing game policy editor exposes it without creating a turn.

`tests/test_world_generation.py` covers the real HTTP/worker/SQLite path with free
deterministic provider fixtures: seven bounded requests in a two-person world,
atomic draft publication/Start Game, pause/reuse, encrypted recovery, missing
credentials, queued Scenario capture, submission idempotency, malformed stage
repair and private provider-error filtering. This is not yet the required full
seven-character/corporate-group brief fixture or hybrid editing acceptance.

The repository additionally supports atomic paused-checkpoint revisions and an
impact preview, with artifact/revision CAS, immutable prior journal versions,
transitive declared-input invalidation and accepted-field locks enforced on
later commits. Regeneration contexts receive those locks. This internal boundary
is tested, but is deliberately not an unrestricted HTTP editing endpoint:
source-constraint reconciliation and existing author-editor integration remain
required before exposing partial edits to users.

The existing Workshop now renders staged job progress and cooperative controls,
including explicit acknowledgement of uncertain provider billing and a separate
opt-in author checkpoint inspection. No raw artifacts appear in progress. A
browser fixture verifies paused-state reload, secret visibility and cancellation
on desktop/mobile. Quick Creation still defaults to the legacy request until the
required edit/constraint reconciliation path is complete; this is a WIP rollout,
not the final architecture promised by #44.


## Fourth implementation increment

The versioned draft record now carries its generation job/revision reference.
Publication and Start Game share a transactional check of required stages,
completed checkpoint versions, complete input manifests, current input hashes,
resource ownership/output hashes and unresolved blocking interpretation IDs.
Publication additionally requires the supplied draft to equal the committed
assembly. Existing author patches/restores and targeted draft generation preserve
this reference; fresh imports and replacement legacy generation remain independent.
An already-confirmed immutable draft version still returns its original save,
even if later preparation dependencies change. Historical saves are not rewritten.
This verifies checkpoint currency, not yet full semantic source-fact protection.

The additive `preparation_units.retry_attempts` migration preserves consumed
budgets from existing jobs. Explicit upstream changes permit a fresh bounded
budget for invalidated units; pause/resume, failure and process restart do not
reset it. Total attempt numbers and the attempt journal remain monotonically
increasing. Later-stage character projections now include current canonical
personality items/revisions, active values and active/blocked motivations instead
of relying solely on compatibility card prose. Development evidence/history is
not copied wholesale into these contexts.

Deterministic regressions exercise stale/missing stages and manifests, changed
resource versions/hashes, changed run revisions after an author edit, confirmation
idempotency, retry exhaustion across author revisions/reload, and canonical
personality/value/motivation context selection. Full verification results are
recorded in PR #105. Paused semantic edits, creation UI/default routing and the
rich-brief acceptance fixture remain required work.


## Fifth implementation increment — paused personality edits

The existing draft PATCH API now accepts a generation job/unit and artifact
version for author-only personality text edits on a stable paused checkpoint.
The existing Workshop checkpoint dialog exposes current canonical personality
items and missing categories, dependency impact preview, and explicit save.
The server validates canonical Character/Personality DTOs, workspace ownership,
character identity, run/artifact CAS and the stable-pause boundary. It preserves
other character fields/cards and independent batches. Accepted items are locked
against provider replacement; revisions use the existing checkpoint journal.
Resume rebuilds declared dependent outputs and retains the accepted character.

Explicit personality source constraints are conservatively protected: the editor
rejects conflicting-scope edits and identifies the source claim requiring a
constraint revision. This is not the still-required source-revision editor.
Directly represented explicit Character facts (birth date, biological sex, life
status, display name and developmental stage, without historical time scopes)
are checked before stage commit and again at assembly. Unsupported semantic
claims are not claimed to be verified by these exact checks.

Deterministic API tests cover preview without mutation, foreign workspace/stale
CAS rejection, source protection, resume without repeated character generation,
unchanged peers, Start Game and a contradictory provider output rejected before
checkpoint commit. Browser tests exercise the edit/impact/save/reload path on
desktop and mobile. No new DB tables or Runtime model were introduced.

Still required: edits to other checkpoint types, explicit source/constraint
revision and ambiguity resolution, targeted regeneration controls with finer
semantic dependencies, full free-form fact/chronology protection, creation
settings UI, Quick/Scenario default staged routing, and the rich #78 fixture.
The existing default creation routes remain unchanged during this incomplete
integration; this PR is not acceptance-complete.

## Current continuation — hybrid editor and default staged creation

This section supersedes the historical increment notes above about default UI
routing. Quick Creation and the existing Scenario hand-off now submit
`world_staged`. Imports retain the conservative zero-provider path.

- Workshop creation controls expose primary/secondary/custom genres, cast
  presets/custom counts, world type/geography, NPC expressiveness and existing
  canonical pacing/risk presets. Settings travel through immutable input capture
  and canonical assembly. They do not manufacture historical consequences.
- Author checkpoint inspection includes a grouped interpretation preview with
  named entity links, source quotes, temporal scope, knowledge holders and
  blocking ambiguities. The checkpoint editor supports typed scalar and advanced
  JSON-record patches for setting, places, characters, life, lore and opening;
  source revisions require explicit acknowledgement. Complex records currently
  use the advanced JSON editor, not complete domain-specific forms.
- Explicit source revisions preserve the original brief/spans and append numbered
  author amendments. Whole-claim revisions allow ambiguity classification and
  blocking status to change atomically. Creation settings can also be revised.
- Changes use existing draft PATCH, stable-pause/artifact/run CAS, immutable
  document history, impact preview and field locks. Unlock and targeted stage
  regeneration are available. Overlapping accepted locks remain consistent;
  provider lock violations enter bounded repair and cannot publish.
- New prompt revision 2 fingerprints stage-specific and source-character-specific
  constraints. A Knowledge revision reuses setting/places/character checkpoints;
  a personality constraint revision reuses unrelated character batches. Existing
  prompt revision 1 jobs retain their recorded dependency contracts. These are
  derived authoring dependencies, not another world state or relationship graph.
- Interpretation can bind source claims to canonical stage predicates (equals,
  record-subset contains/absent, exact filtered holder sets). These run before
  checkpoint commit, during assembly and again against the canonical snapshot at
  Start Game after author edits. Explicit entity identities are also rechecked.
  Unbound free-form claims are **not** claimed to have complete semantic coverage.
- When all parts exist, paused patches also compose through Runtime validation
  before publication, catching cross-stage reference/invariant errors. Earlier
  partial stages still require final assembly validation.

No new SQLite tables or destructive migration in this continuation. Reuses the
existing preparation resources/units/locks and document_versions; old snapshots,
Tabletop, legacy imports and prior prompt definitions are preserved.

Deterministic evidence includes source amendments/acknowledgement, unchanged
upstream artifacts, unlock/regenerate impact, family/prohibition/Knowledge/time
binding conflicts, post-edit Start Game rejection, and a seven-character,
five-subsidiary rich brief through the real worker/Start Game/History branches.
The latter verifies adoption versus marriage, known holders after discovery,
Friday 06:00 activity and unchanged player intentions. Fixtures do not establish
real-provider semantic reliability; no paid calls are used.

### Current paused editor and roster revisions

The canonical record editor uses the existing Pydantic JSON schemas for nested
records, optional values, typed enums and named entity/Fact references. Source
claim records also have a form; anchored source spans and identity remain
immutable and revisions require explicit acknowledgement. Advanced JSON remains
available for complex predicates. Server validation remains authoritative.

Prompt revision 4 atomically reconciles invalidated character batch definitions
when the author changes the roster or its tiers. Accepted character/card locks
move with canonical character IDs. Generated characters with accepted edits must
remain in the revised roster. Previously completed units cannot be redefined
without invalidation; obsolete units are retired while their artifacts, attempt
history and document versions remain intact. The existing journal stores the
revised plan. Older prompt revisions retain their recorded planning contracts.

Quality-review warnings shown in player mode are limited to those reproducible
from the player projection. Hidden-NPC details stay in author mode; ordinary
import validation retains its actionable diagnostics.

Deterministic regression coverage now includes moving a locked character between
core/secondary batches, resuming and starting the resulting world, rejection of
missing protected identities and transaction rollback on invalid replans. Browser
coverage includes the Scenario hand-off and closing the browser context plus
restarting the backend with the same SQLite database before resume/Start Game.

### Semantic review and retry contract (prompt revision 5)

Source claims without executable predicates, explicitly amended claims and
structured setting claims receive bounded semantic review in groups of at most
eight. Each request sees the relevant canonical sections and source constraints,
not a full-world generation schema. Existing provider/model lease, request budget
and usage accounting apply. Reports must cover every requested claim exactly once
and cite existing canonical paths. Negative/unresolved reports pause generation
before publication; their detailed explanations stay author-only. They do not
silently repair user facts or repeatedly retry a valid negative judgment.

Reviews are existing checkpoint/journal records under the assembly/validation
stage. Scoped source inputs and accepted artifacts invalidate their dependents.
A server-computed basis hash is rechecked against the actual normalized draft at
Start Game, preventing author edits from silently reusing obsolete semantic
approval. Imports, old saves and previously captured prompt versions do not gain
new provider calls. No new Runtime model or database table is introduced.

Definite HTTP 429/503 rejection before any streamed output gets one bounded retry
with backoff. Lost responses, partial streams and other provider errors require
explicit retry; no claim of exactly-once billing is made.

The author preview includes filtered family/business/relationship edges and
source-scoped chronology/Knowledge holders without inventing exact timestamps.
It warns when explicit NPCs exceed target counts. Canonical record forms now
include source-claim revisions, named references and editable dynamic map keys;
advanced JSON remains available for unusual predicate values.

### Paused record revisions and stale locks

Paused record tests now exercise relationships, residences, roles, possessions,
contacts, Facts, Threads and scheduled commitments through edit, invalidation,
resume and canonical confirmation. Existing cases cover characters, places,
Knowledge/source revisions and roster changes. Unbound family constraints do not
block unrelated possession/role edits; canonical bindings still validate the
entire stage and dependent semantic reviews must run before publication.

When an explicit source revision invalidates a locked checkpoint, the author may
inspect the stale artifact and explicitly unlock its fields before regenerating.
Unlock changes only the lock journal/run revision, never validates stale data or
changes artifact version/status. Stable pause, workspace ownership, lease and CAS
checks still apply. The next generation must pass current source/canonical checks.
Genre/settings controls precede the premise field in the shared creation form.

Structured geography conflicts and material jurisdiction uncertainty have
real-worker deterministic tests: negative semantic findings pause with the source
brief/quotes intact, preserve accepted work and cannot publish a playable draft.
Nonmaterial missing jurisdiction remains a warning in the rich-brief fixture.

### Verification and limits

Final full-suite results for this increment are pending; see PR #105 for the
published tree and observed results. The preceding published tree passed 1528
Python tests and 198 Playwright tests (10 existing project-matrix skips).

All automated provider responses are deterministic fixtures, with no paid
DeepSeek calls. Semantic review is model-assisted; it cannot guarantee exhaustive
extraction of arbitrary prose or infallible judgment. Canonical bindings, cited
review evidence, revision hashes and author inspection complement that review.
Real-provider narrative-quality evaluation has not been executed. The #78 manual
recipe is `docs/manual_qa/narrative_v4/initial-world.md`; automation covers its
creation/recovery/ordinary-turn/save/branch/legacy/Tabletop paths. Do not represent
the recipe itself as a completed manual evaluation.

### Integration with #112 and author revalidation

Merged master `105833d` (PR #112) into the existing #44 branch through a merge
commit, without rebase or force push. No merge conflicts; the e2e provider keeps
both staged generation and the explicit pending-response evidence required by
the temporal guard. Runtime guard code is unchanged by #44.

A generated-world integration case now runs actual engine jobs after Start Game:
Friday 06:00, a pending commitment at 06:05, accepted short turns, rejected weekly
regeneration, successful variant selection, reload, rollback and a sibling turn
reaching exactly 06:05. Advancing beyond the unresolved boundary fails without
changing the snapshot. Initial calendar and private Knowledge survive.

The existing Author World editor now offers "Проверить изменённый мир". It submits
an existing durable Preparation job with immutable current author snapshot and
copies validated checkpoints into a new versioned review journal with source
links. Only reviews whose canonical context changed call the provider; unchanged
reviews and creative stages are reused. Assembly consumes the captured author
snapshot, never regenerates characters or silently discards edits. Source
bindings/canonical validation run before submission and confirmation. A negative
review preserves the edited draft; cancel returns to ordinary author editing.
Inherited generation artifacts are read-only in this review job. Existing lease,
CAS, idempotency, credential, recovery and billing-uncertainty behavior apply.
No new database tables, Runtime schemas or historical snapshot rewrites.

Tests cover successful edit/review/confirm, zero-call repeated validation,
negative review/cancel, duplicate submission, read-only inherited checkpoints,
original checkpoint preservation and desktop/mobile editor integration.
