# Protagonist role and onboarding

Issue #42 extends Runtime v3, without a second runtime or PlayerCharacter.
`WorldStateV3.meta` owns current protagonist ID, required-succession flag and
chronological periods. Camera subject, POV and EXTERNAL controlled actor are
separate fields. A null control value is valid observation. The existing Character,
Life State capability projection, personality, Appearance, Knowledge and possessions
remain authoritative, with unchanged stable identities.

`runtime_v3.protagonist.transition` is the sole permanent/temporary/observation/
resume boundary. Permanent changes close/open periods and emit the existing
`protagonist_transition` Milestone source; temporary and camera operations do not.
Death goes through the normal Life State resolver, including its social/lifecycle
consequences. Reconciliation requires succession without deleting the dead actor.
Incapacity never changes protagonist identity; an infant can be protagonist with
null control. No adult-age selection gate is added.

`DeathPolicy` is the narrow #68 seam; the current default rejects autonomous death
of the current protagonist and the EXTERNAL controlled actor. Explicit established input/system truth can enter the
normal death flow. A test policy exercises eligible autonomous death. No risk
profile, pacing preset, Director replacement or simulation was added.

Creation uses the existing Character model and shared card field definitions.
`CharacterDraft` is a review envelope, not a persisted alternate actor schema.
Optional typed proposals use Location, Organization, ObjectiveRelation, Relationship,
Residence, NarrativeRole, Fact and Knowledge contracts. Existing identities cannot
be overwritten. A relation involving a new character is an explicit authored initial
condition; feelings cannot be assigned to existing NPCs. Secret acquisition requires
a known source plus explicit authorization at the current POV. Own biographical
secrets have separate factual identity, holders and acquisition provenance. Approved
social proposals likewise create canonical facts with separately selected knowledge
holders; establishing a relation does not broadcast it. Existing event references
are checked against the branch history and the current POV.

The HTTP adapter delegates to the repository: `BEGIN IMMEDIATE`, idle/revision
check, whole-candidate validation, append History, project, save and increment
revision. The character and transition are one commit. Operation receipts are
queried only along the current History DAG, isolating branches and idempotent
retries. No SQLite schema addition is needed. Historical variant JSON is not
rewritten. Legacy role defaults are initialized on read and persisted by normal
future writes. Older unknown period beginnings are recorded as a marked legacy
baseline at migration time rather than fabricated historical transitions.

Draft generation calls the existing provider/usage instrumentation once per
explicit request. The creation context is bounded to public setting facts and
identity/location/organization indexes; it never includes hidden NPC biography or
prior protagonist memory. Individual-field output replaces only that path and
cannot approve its own proposals. No generation runs on selection, preview, manual
creation or confirmation. API keys never enter snapshots or request diagnostics.

The editor follows existing Russian Narrative UI conventions and shared controls;
canonical identifiers remain language-neutral. Generated prose follows campaign
language. Portrait uploads continue through the existing #74 card surface after
confirmation; initial birth/development history and portrait asset references cannot
be imported into a new identity through the draft.

Semantic truth of authored biography, whether prose describes voluntary action,
and a generated scene's literary accuracy still require user review and the existing
Narrative/Extraction contracts. Runtime validates structure, identity/reference,
chronology, agency and transition boundaries; it is not a second semantic LLM.
