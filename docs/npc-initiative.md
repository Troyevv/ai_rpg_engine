# Autonomous scene initiative (#69)

Parent: [Epic #36](https://github.com/Troyevv/ai_rpg_engine/issues/36).

## Architecture

The existing Director emits `scene_agency` from the existing disposable
ContextScope. Up to eight present or established-remote actors can receive
permission; the current EXTERNAL actor and actors unable to act are excluded.
Scope ranking bounds participation, not personality or romance. At most three
meaningful initiative beats may be extracted per turn. Zero is always valid.
These are resource caps, not action frequencies, probabilities or story quotas.
Referenced authors and incidental mentions do not create a communication channel.
New remote contact availability/phone UI remains #70's responsibility.

The existing Narrative request chooses a natural action using the already selected
canonical character/card personality (#67), communication style, intentions/goals
(#75), emotion, directed relationships, Knowledge (#76), capabilities, scene,
History/Milestones and commitments. No parallel context selector or agent exists.
Reserved and impulsive traits influence expression and motivation, not eligibility.
A silent character is never forced to act. The contract explicitly supports starts,
continuations, topic changes, invitations, information sharing, help, conflicts,
refusals, boundaries, departures and adult affection/romance/intimacy proposals.
The existing literary rules and configured game language remain in force.

Ordinary initiative does not consume a #68 development candidate or wait for quiet
pressure to expire. Significant developments/harm still go through the existing
pacing/risk validation and canonical domain handlers. Initiative creates no separate
romantic state, score threshold, relationship ladder or daily simulation.

## Agency and evidence

The normal Extraction request emits optional typed `scene_actions` for meaningful
initiative (not each reactive utterance). Each claim names an AUTONOMOUS initiator,
targets, a current Event, phase/modality, exact narrative evidence, knowledge used,
and whether an EXTERNAL response is open, supplied or involuntary.

Resolver verifies the original permit/budget, actor and target/Event references,
current capabilities, remote/physical constraints, adult eligibility, evidence and
actor-specific known/suspected knowledge. Suspected beliefs support inquiry only;
truth elsewhere in World State does not silently correct an actor's belief.
An interruptible action toward EXTERNAL must leave its response open unless actual
current player input supplies it. Involuntary effects require a matching #68
consequence and its validated canonical outcome. Invalid claims fail the turn
atomically and non-repairably: no extra call merely removes a conflicting audit.

Accepted action metadata is attached to the existing canonical History Event,
which already owns identity, participants, audience, evidence and turn/time.
The attempt/invitation itself may be a completed Event; this does not complete the
attempted kiss, establish a marriage, schedule an agreed date, invent consent or
create reciprocal feelings. Existing Extraction/Resolver domain handlers continue
to own Knowledge, relationships, goals, commitments, conditions and Milestones.
There is no persisted pending-interaction FSM or second source of social truth.

#42 remains authoritative: temporary control changes the protected actor, not the
protagonist's identity/personality/knowledge. Observation has no EXTERNAL actor and
permits the present autonomous cast to continue. Background simulation uses the
same contract inside its existing bounded candidate scene and protection rules.

## Persistence, compatibility and cost

Engine reads `scene_agency` from the exact stored Narrative messages and passes it
to Extraction and Resolver. Regeneration never reconstructs permits from later
state or the completed prose. Old contexts without a permit retain their normal
legacy flow; they cannot acquire new initiative claims by regeneration. No schema
migration or historical-snapshot rewrite is necessary. Event annotations and
canonical effects follow existing atomic snapshots and History lineage through
reload, variant selection, rollback and branching. Tabletop is untouched.

Normal turns still have Narrative + Extraction only. There is no per-NPC request,
additional semantic validator, or extra mandatory retry. Diagnostics include the
same `initiative` permit; input token usage remains recorded by the normal request
instrumentation. The wire omits duplicate capability presentation in Extraction.

## Verification and limits

`tests/test_npc_initiative.py` exercises permission, all phases, adult proposals,
refusal, EXTERNAL protection, capabilities, knowledge status, remote restrictions,
observation/temporary control, pacing, involuntary outcomes and actual engine job
lineage with exactly two provider calls. It also exercises #78's `initiative`
checkpoint. `frontend/e2e/npc-initiative.spec.ts` checks proposal/refusal/reload on
both viewport projects. The full suites retain ordinary Narrative and Tabletop
coverage. See [manual QA](manual_qa/narrative_v4/initiative.md).

These deterministic fixtures test contracts and state effects, not a real model's
literary quality. The normal model still classifies semantic concepts such as
interruptibility, romance, voluntary response and belief use. Runtime cannot prove
that arbitrary prose matches a claim or detect every omitted/misclassified claim
without semantic evaluation. It checks the structured evidence and permissions;
this is not a claim that every real-provider scene is guaranteed free of agency
violations. No paid/live-provider literary evaluation is required in CI.
