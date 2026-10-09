# Canonical life state and objective social relations (#38)

This extends `backend/runtime_v3`; there is no second runtime or persisted family tree.

## Ownership

- `Character`: `life_status` (default unknown), explicit capability overrides, coarse
  setting-dependent developmental stage, current `display_name`, immutable name phases.
- `WorldStateV3.objective_relations`: stable phase ID, typed endpoints, active/closed,
  since/until canonical minute/date, outcome, evidence, source turn, knowledge fact links.
- `WorldStateV3.conditions`: actor, narrative description, temporary/persistent/unknown
  duration, active/resolved/cancelled/unknown-outcome lifecycle, restrictive capabilities.
- Existing `WorldHistoryV3.state_changes`: accepted before/after transitions with date,
  minute, turn and source quote. Current truth never requires searching historical prose.
- Existing directed `relationships`, Knowledge and scheduled events retain their owners.

Missing is not dead; unknown is not false. Legacy unknown life/capability values do not
block ordinary play. Adult eligibility is conservative until a setting-aware adult stage
is established. There is no universal age-to-biography table: infant/child/adolescent/adult
are explicit canonical classifications; birth dates remain owned by #37.

## Transitions

Extraction emits `life_changes`, `condition_changes`, `social_relation_changes`.
Each needs `assertion: established` and a quote in accepted narrative/player input.
Schemas and assertions carry meaning; Python does not parse social prose with regex.
Optional bad transitions warn locally, preserve earlier accepted records and do not
abort an otherwise valid turn. A contradictory parentage graph is never silently repaired.

Controlled actor voluntary relation/name choices require explicit player evidence.
An NPC can end a relationship without the player's consent (`decision_actor_id`).
An NPC-only established adoption can be committed without player input. Validity of the
completed event in the fictional setting remains an extraction assertion, not a legal engine.

Symmetric links sort endpoints. `child` input is normalized to one `parent` record.
Creation of a duplicate active kind/pair is rejected; concurrent different ties and
multiple spouses/guardians/adoptive parents are supported. Closed phases cannot be
reactivated or rewritten. Reconnection/remarriage uses a new ID. Close engagements explicitly
when superseded; no automatic marriage, monogamy, custody or surname inference.

Chronology for runtime transitions comes from the existing calendar at acceptance.
Imports may supply known historical bounds or leave them unknown. Name changes preserve
previous names without rewriting old cards, narrative, variants or History.

Active and unknown-outcome conditions continue restricting capabilities. Partial effect
updates cannot clear another restriction. Resolve/cancel with evidence to release that
condition; overlapping conditions continue applying. Elapsed time alone never heals.

Death removes ordinary scene/remote participation but preserves character and control
identity. It closes only active romantic partnership phases (widowed for spouse). Existing
motivation and commitment owners consume canonical dead IDs idempotently: active motivations
are cancelled with provenance, pending commitments are cancelled, dependencies follow the
existing commitment resolver. Death never fulfills a commitment. Conditions/family parentage
remain historical truth, not a simulated recovery. Director excludes actors unable to act.
Player-authored ordinary actions are rejected before model calls when `can_act=false`;
empty continuation and explicit Time Skip remain available, with no action choices.

## Genealogy and access

`GET /api/saves/{sid}/genealogy?root_id=...&depth=3&limit=100` is read-only and uses the
currently controlled character, never a caller-supplied observer or truth flag. Bounds:
0–8 edges of depth, 1–200 nodes. Unknown and nonexistent roots return the same empty result.
There is no new full-truth endpoint or editor bypass.

Filter relations by their `fact_id` in existing Character Knowledge **before** traversal.
Facts must identify all affected endpoints; creating a fact does not grant Knowledge.
Existing witnessed information events are the only acquisition path. A separate
`closure_fact_id` prevents knowledge of a former tie disclosing a later divorce.
Known death can close a *known* partnership, but cannot disclose a secret partnership.
Suspected edges stay uncertain and do not derive factual ancestors/siblings. Names and
life status respect their own knowledge path; hidden provenance/closure dates/counts
never enter the genealogy response. UI uses the server projection.

Derive inverse parent/child, ancestors/descendants and siblings from known canonical edges.
Half-siblings require explicit complete-parentage facts known to the observer for both
characters. Otherwise output only the established sibling link; unknown parentage stays
unknown. Biological and adoptive lineages stay distinct; guardianship and step-links
never become parentage. Dead ancestors remain queryable.
Known revoked adoption remains a historical edge without deriving current legal kinship;
an observer unaware of the revocation still sees only their established knowledge.

Stdlib `graphlib.TopologicalSorter` handles directed parent/care cycle detection, `deque`
handles bounded traversal. NetworkX would add a dependency without reducing these small
algorithms; it is not needed. Context only sends bounded incident ties (64), not a dynasty.

## Compatibility / limits

Safe defaults are applied on read to v3 saves; the existing v2 import migration carries
explicit new fields and derives the original display name from the existing card. No SQL
schema rewrite or historical snapshot migration is needed. Individually malformed optional
fields warn on read; corrupt capability overrides fail closed. Malformed condition or graph
structure that cannot be safely interpreted raises a diagnostic instead of silently healing
or hiding a cycle. Import validation remains strict. Stored originals are not overwritten.

No age simulation, reproduction, life opportunities, future milestone service, residence
model, phone, character dossier redesign or new control-transition UX is implemented.
Existing Tabletop code is unchanged. The small current family/life panel is usable now;
#45/#83 may enrich it later. Current app-wide GM inspector surfaces remain existing behavior;
the new genealogy API has no GM bypass. No extra model calls or paid test calls are needed.
