# Residence, location hierarchy and narrative roles (#39)

Extends Runtime v3 in place after #38, under Epic #36. WorldStateV3 remains the
single source of truth. SQLite/history schema and `schema_version=3` stay unchanged:
additive Pydantic defaults are applied at the read boundary, never written into old snapshots.

## State and transitions

- `Location.parent_id`, generic `kind`, `aliases`: optional geography. No mandatory
  country or setting-specific levels. Existing #37 CalendarProfile remains authoritative;
  geography does not change calendar configuration, language or nationality.
- `residences`: stable phase IDs, actor/location, active/closed, nullable since/until
  world minutes and canonical dates, opening fact/context/evidence and closure fact.
- `roles`: same chronology with generic kind/title, optional organization and field/program.
  Concurrent education, jobs, membership, office and setting-specific roles are permitted.
- `organizations`: stable identity/name/kind, active/closed/unknown, optional known
  locations, creation/closure provenance and rename history. References never mean presence.

Extraction proposes `location_changes`, `residence_changes`, `role_changes`,
`organization_changes`. `assertion=established` and a source quote are mandatory.
The resolver owns dates/timestamps; extraction cannot rewrite arbitrary persisted fields.
Roles/residences close by ID; changing institution/program/location means a new phase.
`replaces` explicitly and atomically closes only the named active phases of the same actor.
Without it phases coexist. Opening evidence is retained, closure evidence goes to History.
Organization closure closes its active linked roles with `organization_closed`; it never
chooses a next job, moves people or informs them automatically. Closed phases cannot reopen.

Voluntary controlled-actor changes require a player quote and `explicit_choice`.
An external consequence requires `transition=external` and the responsible other
Character's ID. Background changes to protected residence/roles, including indirect
organization-closure cascades, are rejected. Established NPC decisions remain possible.
Semantic interpretation of the source is the LLM's task; Runtime checks grounding,
references, phase identity, agency assertions, duplicates, chronology and graph structure.
Age/time alone creates no role and ends no role. No commute, scheduling, salary or economy.

## Identity, validation and context

Stdlib `graphlib.TopologicalSorter`, already used by #38, validates the single-parent DAG.
NetworkX was evaluated: no additional graph algorithm is needed, so no new dependency.
New dynamic locations support forward parent references. Cycles and missing parents
reject only affected optional records; a mandatory final scene referring to a rejected
place still uses the existing repair path. Known explicit aliases reuse the canonical
place ID (including final-scene/movement references); ambiguous names require an ID.
Organization name/alias duplicates are rejected with diagnostics; reuse the existing ID.
No fuzzy identity merges. Explicit distinct places may share a name under distinct parents.

#64 final_scene remains authoritative for scene endpoints. An off-camera entrant from
another place in structured geography requires a grounded movement or situation_evidence;
residence/role alone never teleports them. Locations/roles do not create scene participants.

Context Builder v2 supplies relevant active phases and organizations plus linked geographic
ancestors in the existing GM-only canonical block. Targeted old phases are bounded to eight
and are dropped before current truth under token pressure. Closed full records and detailed
before/after transitions remain in canonical state and History for save/branch continuity.
The compact social_status projection explicitly retains empty active sets after the last
phase closes; old card prose cannot silently reactivate that role. Empty active sets do not
imply unemployment or homelessness. Existing static role/card prose is historical when it
conflicts with a newer canonical role.

`residence_role_knowledge` and the read-only UI use explicit Fact/Knowledge authorization.
Creation knowledge never discloses a later closure or rename. A role fact can identify its
organization, but does not expose its locations or private organization history. No global
Knowledge broadcast, including to the controlled actor. Extraction must use the normal
witnessed informational event path. An observer with no authorized facts sees no rows.
UI labels follow the existing `lib/social.ts` presentation boundary, not persisted labels.

## Imports, compatibility and limits

Initial JSON draft imports may explicitly provide `world.residences`, `world.roles`,
`world.organizations`, and hierarchy fields on the existing `locations` list. These imports
preserve declared place IDs and validate all references before confirmation. Name-based
physical locations resolve to declared IDs; ambiguous names require IDs. Legacy name-only
imports keep their historical deterministic location IDs. Neither current location, card
biography, age, family relations nor organization membership is converted into residence.
Missing fields become empty/unknown; migration is deterministic and idempotent.

Malformed optional extraction changes produce local diagnostics and do not lose unrelated
valid changes. Malformed persisted chronology/references are integrity errors requiring
explicit repair, not silently erased history. Existing imported chronology may stay unknown.
No new authoring editor or organization management screen is added (#45); JSON import and
ordinary evidence-bound Narrative turns expose this issue's usable authoring surface.
Tabletop schemas, dice/rules, UI and persistence are unchanged.

Automated coverage: `tests/test_residence_roles.py`, existing Runtime/calendar/commitment/life
and Tabletop suites, `frontend/e2e/residence.spec.ts` on desktop/mobile. Reproducible manual
scenarios: [QA #39](manual_qa/narrative_v4/residence-roles.md).
