# Structured world preparation

## Existing architecture and reuse

The old Scenario → Markdown summary → parser → immutable world flow remains available under “Со Сценаристом”. `world_parser.py` knows legacy headings, character markers and explicit knowledge-holder markers; it cannot reliably infer knowledge holders or all free-prose facts. Imported source is retained in full, and the editor reports that limitation instead of inventing holders.

The new preparation flow uses the same `preparation_workspaces`, cancellable preparation jobs/SSE, provider/model settings, tracked usage, prompt revisions, `document_versions`/heads, runtime World State v2, save snapshots and `world_entities` projection. No parallel character, relationship, knowledge or scene tables were introduced. The new prompt is seeded by the existing idempotent prompt migration. Existing saves and response-variant snapshots are never rewritten.

A draft is a versioned existing World State aggregate in the document journal (`kind=world_draft`, owner=workspace ID). The workspace revision is the concurrency token; document ID identifies an immutable state version. Each patch, entity operation, generation and restore appends a version. Restoring creates a new head; it does not erase later alternatives. A reload reads the backend head. Confirm records an idempotency receipt (`draft_save`, owner=workspace:version) in the same transaction as the immutable world, save and world-entity projection.

## Lifecycle

Free idea, optional Scenario output, and legacy Markdown/text import converge in the editor. Structured generation asks for one complete JSON aggregate using the existing streamed provider pipeline and continuation handling. Raw JSON is accumulated on the server, excluded from public job snapshots, decoded and checked before recording a version. Invalid JSON leaves the previous version intact. Structurally incomplete worlds can be repaired as drafts but cannot start a game. Targeted generation applies only the returned `value` to an allowlisted field; extra top-level operations are rejected. Character regeneration changes its card only, retaining identity and world links.

Validation checks identities, directed relationship references, knowledge/fact/source links, scene participants and intervals, actor state, world-clock consistency, events and threads. Semantic checks are intentionally limited heuristics (for example age/profession); they are warnings, not a claim of exhaustive literary consistency. Explicit/creative/unknown semantics are instructions to the model; the runtime has no provenance enum and this change does not add a competing provenance system.

Confirm does **not** call an LLM or parse Markdown. It copies the selected validated aggregate into the existing save. Opening that game uses the existing Start action, GM, State Delta, transaction, choices and branch/regeneration flow. Campaign metadata is included in the existing GM-only context section; actor knowledge remains separately represented.

## API

All routes are under `/api/workspaces/{id}/draft`:

- GET: safe Player projection by default; `?author=true` explicitly requests complete author data.
- POST `/import`: revision and complete legacy/export text.
- PATCH: revision plus patch/add/remove/restore operation. Structural IDs cannot be patched. Deletion returns a dependency error instead of cascading.
- GET `/dependencies`: entity references for deletion/whole-character review.
- POST `/generate`: world/field/character task, provider config, instruction, expected revision; returns the existing job contract.
- POST `/confirm`: expected revision and immutable version ID; returns world/save IDs idempotently.
- GET `/export`: expected version ID and `format=md|txt`.

Player View is projected server-side, excluding hidden world facts, other actors' intentions and arbitrary legacy root blobs. Author View requires an explicit spoiler warning in the UI. This is a presentation boundary in the existing local single-user app, not a replacement authentication system.

Exports contain readable Markdown plus a versioned integrity-checked payload preserving existing IDs, directionality and knowledge. Importing the unmodified export reconstructs exactly that state. If the readable part was edited externally, import refuses the inconsistent payload and asks to edit the original export in the editor; it never silently treats stale embedded state as authoritative.

## Verification

Backend tests cover import/export roundtrip, default projection, patch isolation, immutable references, dependency deletion, stale revisions, restore, duplicate-confirm protection, save isolation, semantic warning acknowledgement, streamed world/field generation and first-context fidelity. Existing backend tests cover old saves, branches, cancellation and provider behavior. Browser tests cover creation, Author/Player views, field editing, export, reload, confirmed save and first GM turn at 360/390/412/430 and desktop widths, with screenshots. Browser/model fixtures test the integration contract, not the quality of an actual paid LLM response.
