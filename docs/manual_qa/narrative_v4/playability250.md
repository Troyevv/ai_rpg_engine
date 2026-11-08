# #250 — consequence-first Narrative playability

Implementation continues PR #248 from `c978a8f76d52672e1286cb0dbeb7a2bda40dc3f6`.
No new PR, merge, paid calls, world regeneration or repair of original Narrative.
Real-game acceptance is **NOT RUN**: no new paid budget was authorized. Current
CI results and the tested commit are recorded in the PR, not inferred here.

## Error policy and owners

| Role / examples | New handling | Required protection |
|---|---|---|
| Optional `narrative_audit`, absent review, general uncertainty, malformed unreferenced action-list | Advisory; no mandatory repair | Does not grant completed interaction or domain authority |
| Explicit significant `unauthorized_choice`, `status=violated`, changed input | Existing nonrepairable `narrative_agency_conflict` | Reauthor/abandon; malformed audit link cannot erase the signal |
| Referenced PlayerAction, `player_action_event_mismatch`, `player_action_completion_invalid` | Existing bounded repair / atomic rejection | Exact input source, actor, targets, delivery, aggregate coverage |
| Identity, `movement_*`, `life_transition_invalid`, birth/temporal boundaries | Existing strict domain owners | No invented contact, relocation, parenthood, birth/death or player consent |
| Declared known-fact acquisition with invalid Event/witness/channel | Repairable error in new foreground policy | No successful prose with a silently lost declared acquisition |
| Known input-only `diagnostic` / `diagnostics` | `raw_feedback_ignored`, non-executable | Unknown nonempty roots still reject; raw response retained |
| Optional choice with unsafe/unknown basis | Discard only the choice under existing rules | No invented source, Knowledge or channel; free input remains usable |
| Independent background validation/transport failure | Discard its whole state/History candidate; save foreground once | Cancellation/stale revision/SQLite failure and mandatory boundaries still fail |
| Rejected LTA group | Bounded repair within total cap, then unresolved group | Other independent accepted groups survive; no deferred application |

The policy follows consumers, not just exception names. Linked player Events
still undergo all source/target checks. NPC response Events can independently
support Event→Fact→Knowledge; no synthetic question Event is manufactured.
Unlinked inventory is removed before optional shape validation and is never
persisted as verified completion. Domain-specific explicit player sources remain
required even if there is no PlayerAction inventory. A model flag cannot override
those dependencies.

## Implementation and confirmed causes

1. `player_actions.review()` previously made missing/full audit and `uncertain`
   global gates before consequence validation. New server-owned producer version
   **3** makes them optional while preserving explicit significant conflicts.
   Context/schema instructions agree with the policy. `target_mode` remains
   explicit for linked new actions; absent duplicate Event quotes still inherit
   only from their verified action. Existing v1/v2 jobs and regenerated siblings
   retain their recorded contract; new turns of old saves use v3. No schema
   migration or historical response/snapshot rewrite.
2. `RawTurnResult.parse()` formerly rejected feedback copied into root
   diagnostic(s), making a non-executable field cost another call or the turn.
   Only these two known fields are normalized to warnings. Unknown substantial
   containers, malformed roots and canonical source conflicts remain errors.
3. `simulate()` previously allowed an optional background failure to escape into
   the foreground job. It now resolves on deep-copied candidates and appends only
   accepted background results to the one existing SQLite transaction. Provider
   failures are bounded; partial responses/accounting remain in existing request
   receipts. Rejected background reauthor diagnostics are scoped and cannot mark
   the accepted foreground Narrative as requiring reauthor.
4. `background_candidate()` used current-turn duration for 45/60-minute gates.
   A minimal snapshot cursor (`background_considerations`) now retains canonical
   origin, per-cause last attempt and last dispatch minute/turn. History records
   accepted/rejected considerations. This is scheduling metadata, not a queue or
   outcome store. Reload/rollback naturally follow the active snapshot branch.
   Unconsidered/oldest causes get the bounded slot; ordinary dispatches have a
   15-minute spacing and existing 30/45/60-minute cause intervals. Removed cause
   IDs are pruned. Due births retain their existing once-per-new-turn opportunity,
   including zero-time turns where the birth itself holds the scene clock; they
   must not be deadlocked by polling cooldown. Incapacity to act does not suppress
   an otherwise valid due birth. No forced birth after N turns.
5. LTA previously conflated any player-linked candidate with a new player choice,
   and had no group repair. Mixed thread/communication causes can now develop an
   independent NPC part. The original actor IDs are retained; actual player
   participation/changes/Knowledge still reject. Scheduled/player commitments,
   reproductive boundaries and other unresolved player decisions stay strict.
   Each group gets at most one Extraction repair using unchanged Narrative,
   debited from the same `max_llm_calls` cap. Regeneration pins the original
   recorded group IDs and Narrative contexts across selection-policy changes. Unattempted later groups are reported
   separately. A group with discarded declared Events is rejected, not called
   calm. Empty accepted groups must not hide a domain state change. Extraction
   context failure rejects only that group: repair requires an actual response
   from the current attempt, never an unset/stale payload from another group.
6. Existing report/API/UI now distinguish `developed`, `quiet`, `incomplete`,
   `calendar_only`, with accepted/quiet groups, rejected causes and budget misses.
   Public projection retains existing privacy filtering. Calendar-only with zero
   budget is permitted. Dated old LTA situations remain dated, not current prose.

There is one current Narrative policy, not a selectable strict/free mode. There
are no new mandatory LLM calls, automatic foreground retries, thinking mode,
semantic regex/NLP, alternate canonical store, or delayed legalization of an
already saved consequence. More short turns can now legitimately trigger bounded
NPC activity; this may increase background usage versus the previously starved
path, while the ordinary Narrative+Extraction path remains two calls.

## Free verification

New `tests/test_playability250.py` uses real Context Builder, RawTurnResult,
StateResolver, engine jobs, SQLite Repository and History; provider transport is
scripted. It covers:

- optional/malformed audit and unreferenced inventory, independent NPC response,
  all four original Knowledge acquisitions, exact reload and rollback;
- invalid acquisition source/listener and explicit major decision (including a
  malformed audit link), unknown significant root, atomic rejection;
- eight 5-minute turns without background, a ninth at minute 45 with failed
  background/repair/transport, then the other cause at minute 60; persisted cursor,
  no hidden Knowledge transfer, rollback, zero elapsed and repeat isolation;
- background agency rejection without foreground reauthor, cancellation and stale
  revision without saving, no partial background Events or character mutations;
- mixed independent LTA groups, repair success/failure, total cap, unattempted
  causes, quiet versus rejected versus zero-budget outcomes; SQLite report reload
  and rollback; no player participant or unsolicited knowledge; real Context
  Builder overflow on the first group's Narrative followed by an accepted group;
- exact latest D/005 original error/repair, optional rejected choices and next input.

Existing birth, pregnancy boundaries, life/social, personality, relationship,
provenance, Knowledge, original #247/#249/life248, call and storage lineage tests
remain the regression owners. Historical policy checks are explicitly pinned to
v2; new-policy tests no longer demand rejection merely for uncertainty. Synthetic
fixtures that claim an observation now declare the observation medium. Imported
checkpoint/test-clock setup resets its scheduling origin, while actual played
intervals retain accumulation. The group-chat integration now verifies the new
background stages after two 31-minute turns instead of expecting starvation.

The full local diagnostic run started before these fixture/policy updates; its
initial failures are not presented as a green final run. Targeted failures were
reproduced and repaired before the final CI submission. Two stale expectations
were reproduced on untouched `c978a8f` too: the fixed context-size threshold and
creative-rejection blocking. The new agency contract is shorter and stays under
the original context test limit; no context/test limit was raised. World generation
already allowed rejected optional creative proposals to preserve a structurally
valid base; the API test now checks that existing behavior. Historical rejected
creative-journal revalidation retains its separate test.

The first GitHub full browser run exposed the corresponding old phone/social
three-call expectations and the creative browser fixture returning an entire
world instead of a semantic-review response. These are updated to assert first-pass
acceptance and review/confirmation of the unchanged valid base respectively;
no rejected creative changes or secret Knowledge are applied. The exact browser
fixture is also exercised through the API before resubmission. The initial CI
failures are retained as diagnostic evidence, not called a successful run.

Frontend unit tests and TypeScript/production build pass locally. Targeted
Chromium E2E could not launch locally: AF_UNIX socket creation is denied by this
runtime; the separate headless download also failed. No product E2E pass is
claimed from those attempts. Desktop/mobile acceptance is delegated to the full
GitHub CI with expanded `evidence-first249.spec.ts` and `long-term.spec.ts` covering
optional-warning save/next turn/choices/reload, genuine retry/abandon and incomplete
LTA coverage. Full CI must be checked on the pushed commit, not an earlier HEAD.

## Original evidence and residual defects

See [independent findings](playability250-independent-findings.md) and
[fixture provenance](../../../tests/fixtures/issue250/source.md). Both original
archives were available and their SHA256 values checked. The earlier visit saves
without unnecessary bookkeeping; latest D/005 still correctly rejects actual
source conflicts and an incomplete repair. Original D/002 leaks a letter through
a choice, and original LTA second group loses Pasha's location. Both are confirmed
on current code and deliberately remain separate defects, not advisory warnings.

## Short authorized-live plan (not executed)

Continue the same saved Berezovsk: freeze the start checkpoint, 20 ordinary turns
and at most two LTA runs of 4 calls each. Include conversation, a composite visit,
several short turns reaching background eligibility, free input after rejected
choices, reload and one rollback; no special anti-teleport user instructions.
Capture original requests/responses/repair, final SQLite, branch History, usage,
latency and strict consequences after every turn. Track real stops/manual
recoveries, first-pass acceptance, repair rate and background consideration versus
accepted events. Assess story quality separately. Stop on a new canonical loss or
Knowledge leak; preserve evidence. Rare life events use explicitly labelled
existing checkpoints if separately authorized, not a regenerated world or a quota
of marriages/deaths. Set an explicit total monetary cap before running; the issue
itself authorizes no paid calls. Passing CI is necessary, not proof of semantic
reliability or completion of this live acceptance.
