# Narrative pacing, risk and outcome policy (#68)

Parent: [Epic #36](https://github.com/Troyevv/ai_rpg_engine/issues/36).
This extends Runtime v3 and the existing Director/ContextScope. It adds neither a
second Director nor a health simulator, catastrophe table, NPC scheduler or #69 initiative engine.

## Canonical settings

`WorldStateV3.meta` owns `narrative_pacing`, `narrative_risk`, `outcome_preference`
and at most twelve `pacing_recent` records. Presets expand to validated structured
values; `custom` exposes independent bounded fields. Default: moderate, realistic,
natural. `narrative_policy_models.py` is the source of preset values and ranges.

Pacing controls intensity, quiet minutes, recent-pressure threshold, disruption,
escalation, active-thread cap, candidate budget and minimum relevance. Hard limits
are twelve active threads, six selected candidates, zero additional policy LLM
calls. An existing save above the thread cap may continue; autonomous additions
cannot increase that overflow. Explicit player decisions retain their agency.

Risk independently allows minor/serious illness, injury/permanent injury,
relationship/career/life-role loss, accidents, NPC death and protagonist death.
Safe allows minor illness; realistic excludes permanent injury/protagonist death;
harsh excludes protagonist death; unrestricted permits all. Permissions never
select a diagnosis or require a negative outcome. Explicit evidenced player
choices may establish consequences outside autonomous limits.

Outcome preference is independent: natural, prefer_happy, guaranteed_happy_path.
Only current-protagonist-linked threads (`character_ids` or explicit `stakes_for`)
inherit it. A guaranteed path contains a grounded opportunity and possible next
step, never a performed player action. A materially affected autonomous thread
update must preserve that path; autonomous resolution must be favorable. Explicit
negative player choices remain valid. Unrelated NPC threads and already resolved
history do not change when settings or protagonist change.

## Planning and resolution

The existing ContextScope supplies bounded roles/residences, active threads,
goals, commitments and recent known milestone sources. At most 24 milestone
records for eight relevant actors are read; at most six recent sources survive.
Sources age out over thirty world days and never create a Thread or NPC by
themselves. A relocation/marriage/birth/role transition uses the same mechanism.
No source grants new Knowledge.

The evaluator ranks life opportunities, existing-thread developments and external
disruptions separately. Relevance, elapsed canonical world time, accepted recent
pressure, quiet periods, repeated-source/disruption suppression and caps determine
eligibility. It retains at most 24 diagnostic candidates and selects at most six.
Long elapsed intervals saturate a bounded relevance signal; work does not scale
with days × actors. Deterministic due transitions remain independent of this policy.

Candidates are opportunities for the normal Narrative request. Selection alone
changes no canonical state. Extraction receives the **original Narrative permit**,
not a newly enlarged selection based on generated text. Typed `narrative_developments`
link accepted events to candidate IDs and bounded escalation. Only accepted events
update pacing pressure. Ordinary scenes are valid for every preset.

`consequences` classifies harm within the existing Extraction request. Runtime
checks evidence, affected actor, source event, existing causal basis, severity and
permissions before applying a delta. New severe harm additionally needs a selected
candidate; an existing active condition can ground continuing consequences.
A condition restricting capabilities cannot masquerade as minor illness, and a
persistent injury needs permanent-injury permission. Constructive closures (such
as graduation) use `consequence_outcome=constructive`, not an automatic career loss.
Indirect closures are checked too. After domain resolution, diagnoses/injuries,
death and losses must have an accepted canonical transition; event-only harm is
rejected. Policy failures reject the entire turn, without an extraction retry that
could merely hide already narrated harm. State and History remain uncommitted.

Semantic classification and credibility remain the existing LLM's responsibility;
Runtime validates structured claims, provenance and domain changes, not a keyword
classifier over prose. A malformed or omitted semantic claim is not a reliable
proof that arbitrary free-form text contains no harmful implication. The saved
canonical state remains authoritative, and failed narrative is shown as failed.

## #38 / #40 / #42 and agency

`NarrativeDeathPolicy` implements the existing #42 `DeathPolicy` interface. Risk
is keyed to **current protagonist identity**, not temporary control or original
campaign protagonist. #38 resolves death/capabilities/conditions; #40 keeps causal
event/process provenance. #42 reconciliation clears impossible control and requests
a successor after accepted protagonist death. There is no new Game Over path.
Incapacitation alone does not require replacement or imply death.

Existing EXTERNAL guards remain authoritative. Circumstances and NPC offers can
be introduced, but commitments, consent, voluntary relocation and major responses
require player evidence. Policies never mutate personality or relationships merely
because a candidate was selected.

## Persistence, UI and diagnostics

GET/PUT `/api/saves/{id}/narrative-policy` and the small current-game “Политика
истории” dialog expose all three settings. PUT validates revision and idle state,
changes only future policy, appends History and uses the existing control-transition
snapshot lineage for rollback/branching. No schema migration or parallel store is
needed. Read migration supplies defaults without editing stored historical snapshots.
Original regeneration context and variant snapshots retain their policy.

Diagnostics include profiles, family, score, rejection/budget reasons, quiet,
pressure, selected IDs and zero additional policy calls. Actual provider attempts,
usage and cost remain in existing instrumentation; zero is not an estimate of the
whole turn's calls (existing background simulation can still run).

#43 can reuse the bounded evaluator; #44 can consume canonical profile schemas;
#45 can incorporate the current-game setting. Their other scope is not implemented.
Tabletop does not consume these settings.

See [QA protocol](manual_qa/narrative_v4/pacing.md) and `tests/test_narrative_pacing.py`.
