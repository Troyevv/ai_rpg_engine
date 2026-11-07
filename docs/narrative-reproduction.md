# Minimal conception, pregnancy and birth (#41)

This is an extension of Runtime v3. `reproduction.py` runs inside StateResolver;
StatePatch, committed snapshots, the History DAG, #76 Knowledge and #38 genealogy
remain the owners of persistence, lineage and projections.

## Authoritative data

`Character.reproductive_capability` defaults to `unknown`. Explicit initialization
or an evidenced `life_changes` proposal can establish `can_become_pregnant`,
`can_impregnate`, or `neither`. Names, sex, marriage and card prose do not establish
capability. Both actors must be alive, independently established adults, conscious
and capable of acting. A known birth date can veto an inconsistent adult stage.

`reproductive_events` retains each accepted encounter and its outcome, including
unsuccessful attempts. Extraction supplies a stable encounter label, completed
current Event, both consent IDs, protection and explicitly established parents.
Runtime requires narrative evidence and explicit player consent for an EXTERNAL
participant; background cannot supply that consent. Malformed optional proposals
produce diagnostics without rejecting the otherwise valid turn.

Runtime hashes the encounter identity, participant IDs and independent purpose
salts. It samples conception, child count, each child's sex and early temperament;
no global random generator or LLM call participates. Replaying the same encounter
uses its stored result. A continuous open encounter cannot produce another attempt,
even under a new label; `encounter_ended` closes the existing canonical ID. A new
encounter needs a new identity. The semantic determination of completion, consent
and encounter continuity belongs to Extraction; Runtime verifies its structured
assertions, evidence provenance and state constraints, not natural-language meaning.

The canonical `reproduction_policy` is world configuration, with defaults in the
Pydantic `ReproductionPolicy` model. Initial-world JSON may specify it under `world`.
It contains protected/unprotected/unknown conception probabilities (defaults
0.01/0.20/0), child-count weights (0.98/0.019/0.001), gestation days (280), minimum
adult age (18), and `shared_family_name`. These are configurable **game rules**, not
medical probabilities. Each accepted encounter retains its policy. Changing the
policy cannot reroll an already stored outcome. No medical or genetic dependencies.

## Time and birth

A pregnancy stores an interval for conception. Exact minutes remain null unless
established by the current Event. The due boundary uses the existing calendar's
world minutes and day length; dates are projected by #37 for Gregorian/custom
calendars. The due estimate is not an actual birthday. A Runtime-owned scheduled
entry integrates the process with the existing Time Skip/background selector.
Ordinary extraction cannot rewrite this schedule. Passage of time marks a process
due but does not fabricate a completed birth.

An accepted `births` claim must reference the pregnancy and an actual completed
birth Event at/after the configured due boundary. Premature/complicated birth is
outside this minimal game rule. Birth creates the previously allocated child IDs,
ordinary Characters and sparse cards, individual parent edges, birth facts and
History/Milestones, then closes the pregnancy/schedule atomically. An unknown
calendar anchor leaves birth_date unknown and retains the actual world minute.
Retry cannot create a second set of children. Rollback and variants use ordinary
before/after snapshots; there is no separate child database or family tree.

## Identity, development and knowledge

`naming_decisions` binds a decision to pregnancy + child ID, including after birth.
Proposed, agreed, cancelled and replaced remain distinct; replacements retain prior
records and History provenance. Agreement requires all established decision-makers;
EXTERNAL agreement/delegation requires explicit player evidence. A recorded explicit
delegation allows the autonomous decision-maker to choose. Delegation need not
include a proposed name. No runtime parsing of names or universal name concatenation.

An agreed name applies at birth without a second confirmation. Otherwise the
canonical display_name stays null; “Без имени” is a Russian UI label only. Identity
components are open setting-owned string components. Matching known parental
family_name values are applied when configured; differing/missing names remain
unresolved. Marriage supplies neither parents nor surname rules.

Newborns get no mature profile, habits, communication style, values, goals,
intentions, obligations or parental Knowledge. Their existing #67 profile contains
only one stable early-temperament item (bounded activity/adaptability/sensitivity/
intensity/sociability tendencies). It does not predetermine future personality.
#38 capability projection blocks infant voluntary action; an evidenced later stage
transition and #67 experience can enrich the same Character, preserving birth IDs.
Age remains a #37 projection; elapsed years alone do not invent biography.

Pregnancy existence, count, each child's sex, parent edges, birth and naming have
separate fact IDs. Conception grants **no Knowledge**, even to participants. Existing
#76 Event/witness paths handle later examinations, communication and discovery.
Birth witnesses acquire outcomes and observable gestational parentage through that
same pipeline. Other parentage requires explicit `disclosed_parent_ids`; prior names
require their own grounded Knowledge path. Protected
background observers do not. Character and choice projections omit hidden outcome
fields; unknown off-camera newborns do not appear in their card/index/genealogy.
Extraction receives bounded canonical process records for validation. Atomic
assertions already represented there are not repeated as fact prose in its prompt.
Missing assertions are not permission to reveal them. No unconditional extra call.

### Birth sex disclosure (#231)

At an observable due birth, Narrative receives a separate **Birth authoring
constraints / GM-only** block with stable child IDs and canonical sex. It is absent
before the due boundary, for an absent/unperceiving POV, and for remote processes
outside the current camera. Private background authoring uses its own camera.
This block constrains an actual delivery; it is neither proof of delivery nor
character Knowledge. The author may omit sex and must not reveal it before a
grounded observation/announcement. Ordinary POV/character Knowledge stays filtered.

Every new `BirthClaim.sex_observations` must assess **every canonical child once**:

- `child_id` identifies the existing pregnancy slot, never a new outcome.
- `narrative_sex` records what the authored prose actually establishes; `event_sex`
  independently records the Event summary. Neither is a proposed canonical value.
- `basis=not_disclosed` uses explicit null values and no recipients. Guesses,
  hopes and player assumptions do not establish sex.
- `observation` identifies the specific perceivers; `announcement` also identifies
  its participant/speaker and `direct_observation` or established `prior_knowledge`.
- `perceived_by` is a subset of accepted Event witnesses with perception capability,
  not the entire birth audience. The existing sex Fact and canonical Event own each
  Knowledge acquisition. Generic `knowledge_gained` cannot bypass this assessment.

Runtime compares the semantic assessment against the pregnancy's canonical sex;
it never searches prose for sex words, rewrites biological sex, or creates a second
sex Fact. The persisted sex Fact is checked against the pregnancy outcome on load.

A contradictory `narrative_sex` raises **birth_narrative_sex_conflict**. The whole
provisional scene is rejected before commit, with a durable `reauthor_narrative`
diagnostic. Extraction-only retry is blocked even after reload, and the UI removes
that retry action. The player can abandon the failed scene and author a new turn;
accepted History and sibling variants remain untouched. No automatic reauthor loop
or extra reviewer request is added. This conservatively rejects the scene even if
the underlying cause was a mistaken semantic assessment of otherwise correct prose.

A missing/malformed assessment or divergent Event summary is eligible for the
existing **one** Extraction repair. The repair must reinterpret the same prose,
not silently correct it to canon. Persistent failure leaves no child/Event/Knowledge
changes. Standard delivery remains Narrative + Extraction (two calls); only failed
structural/summary validation adds at most one automatic call per attempt.

Existing saves/History need no migration. Legacy in-flight birth payloads missing
the new assessment must be reinterpreted before acceptance; they are not given a
fabricated `not_disclosed` default. Regeneration uses its recorded author context.

The semantic trust boundary remains Extraction: a model that falsely labels both
prose and summary as canonical can evade any structural validator. These changes
do not claim to prove arbitrary prose correct with deterministic code or mocked
provider tests. A paid live-model retest was not run as part of #231.

The optional wire contract is included when reproductive capability, pregnancy or
birth identity is relevant. Legacy worlds still expose the normal life_changes
capability field, so an explicit establishment enables subsequent service events.
Existing saves load with conservative defaults. Read normalization does not rewrite
historical snapshots; corrupt process identities fail integrity validation rather
than silently deleting outcomes and enabling a reroll.

## Appearance boundary for #74

Only an explicit appearance quote is stored in the existing ordinary card's
`fields['Внешность']`, with canonical birth event provenance. No temporary appearance
schema and no parent-derived phenotype. `appearance_adapter(snapshot, child_id)`
returns the unchanged Character ID, optional accepted text and birth provenance.
This is #74's lossless input boundary; #74 itself is intentionally not implemented.
Round-trip and branch tests preserve this input without modifying old snapshots.

## Limits

As elsewhere in Runtime v3, validating evidence quotes cannot prove that an LLM
interpreted their meaning correctly. Prompt/context tests do not certify literary
quality. Hidden state is filtered from new POV projections, not protected by a
second LLM verifier. No forced intimacy pacing, romantic side effects, health
simulation, genetics, appearance evolution, or future epic implementation.

See [manual QA](manual_qa/narrative_v4/reproduction.md).
