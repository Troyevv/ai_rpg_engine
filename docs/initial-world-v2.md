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

The checkpoint foundation adds four SQLite tables (`preparation_runs`,
`preparation_units`, `preparation_resources`, `preparation_attempts`) through an
idempotent additive migration. No historical-snapshot rewrite, dependency
addition, or Tabletop change. The existing migration cache and immutable History DAG remain
the owners of saved migrations/history. Old saves continue to use the existing
conservative load path, not the stricter new-authoring boundary.

Keep the existing distinction between legacy name-only places and explicit #39
structured geography. Adding an empty `organizations` map to every old draft
changes its migration identity mapping and breaks legacy QA references. This
was caught by the full suite and removed. New structured plans must declare
their stable location/organization IDs explicitly; do not rewrite old IDs.

## Remaining required work

The following is **not implemented by this increment** and is required before
this PR can be marked ready or Issue #44 closed:

1. Extend the canonical/authoring equivalence matrix as each generation stage
   is integrated; canonical snapshot imports and portable History are implemented.
2. Integrate the typed interpretation into automatic generation, editable
   preview and structured-setting reconciliation. Backend extraction/provenance
   and numbered journal revisions are implemented.
3. Replace `draft_generation.run()`'s monolithic request with bounded typed
   stages and NPC batches; curated stage contexts and stage-local accounting.
4. Persist stage checkpoints, dependencies, attempts, leases and CAS revisions
   in existing Preparation storage. Current `Preparation.submit()` still uses a
   daemon thread, and application restart still stops its jobs. Durable
   pause/edit/resume/recovery is not implemented yet.
5. Selective invalidation and regeneration, protected accepted edits, stale
   response rejection, interruption/billing uncertainty and credential recovery.
6. Existing Workshop/Quick/Scenario UI integration: genre, scale, geography,
   expressiveness, interpretation/impact previews, progress and hybrid controls.
   Keep author-only artifacts out of public job status/Player View.
7. Extend final readiness with checkpoint currency and unresolved semantic
   contradictions; add deterministic integration tests and #78 manual scenarios.

The partial canonical readiness check must not be described as the completed
generation readiness gate: checkpoint currency cannot be verified until durable
generation artifacts exist.

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
  canonical composition and input fingerprints/selective invalidation. It does
  not yet replace the live monolithic generator. Canonical source facts still
  need complete semantic protection in the integrated orchestration path.
- `generation_checkpoints.py` adds a tested persistence foundation using existing
  Preparation IDs and the version journal: immutable payloads, input hashes,
  output references, attempts, expiring worker leases, transactional commit CAS,
  pause boundaries, cancellation and interrupted-request uncertainty. These
  methods are not yet wired into the application worker/startup/UI. Existing
  legacy jobs continue to run via their previous lifecycle. Do not describe this
  foundation as completed automatic recovery or complete hybrid generation.

Additional deterministic tests cover canonical snapshot API import/confirm,
empty observer worlds, five subsidiaries, broken/cyclic organization references,
interpretation failure/cancel/revision/privacy, bounded batch composition,
selective input invalidation, durable journal reload, lease replacement, late
commits, pause/resume, cancellation, retry budget and uncertain billing outcomes.
