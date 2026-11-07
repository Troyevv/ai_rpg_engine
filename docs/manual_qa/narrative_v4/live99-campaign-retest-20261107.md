# #99 — post-merge Live Gameplay retest and campaign continuation

Refs #99. QA PR [#239](https://github.com/Troyevv/ai_rpg_engine/pull/239).
**Partial Stage C; the engine is not ready for a long user campaign.**
No product Runtime/frontend changes, no merge, no closure of #99.

## Baseline and preservation

- Master: `40bc3da23b44a025954a6b050fe71a08a2ce4a2d`, merged #230 after #219.
- Live QA implementation: `a37d2d54a066dcd90aac076aaf53167757b77b17`;
  docs-only adoption: `962555adaaa917e466112b94ee239e33da6d4244`.
  Subsequent report commits do not change the Runtime used for these observations.
- Ancestry and actual implementation were checked for #220/#224, #221/#225,
  #222/#227, #223/#228, #226/#229, #231/#235, #232/#234 and #233/#236.
  Closed Issue state alone was not used as evidence.
- AGENTS.md, #99, #36, #46 and both previous QA reports were reviewed. Existing
  `devtools/live99` remains the only harness. New preparation links the remaining
  #230 allowance instead of authorizing another budget; regression tests cover
  shared spending, immutable historical reservations and unknown-outcome blocking.
- Original #219 checkpoints were copied into an isolated SQLite database; #230's
  database/variants are preserved separately and hash-bound. Explicit browser
  rollbacks restore Campaign/Crisis targets. Family uses two isolated copies of
  the existing #78 near-due fixture, whose shortened gestation is intentional.
  Historically contradictory birth records are not rewritten.
- All six historical archives were found and their original hashes verified.
  Parent/related evidence, settled ledger prefix and sibling hashes remain intact.
  Workspace existence does **not** establish durable public availability.

## Real execution and budget

Production FastAPI, system Chromium/Playwright and real
`deepseek-flash` / `DeepSeek-V4.1-Flash-1017` were used. Key availability was checked
without printing its value. Free preflight/replay/tests had the key removed.
No parallel paid scenarios, no automatic Narrative replays, no unknown outcomes.

| Measure | This run |
| --- | ---: |
| Operations, including free controls | 23 |
| Jobs using DeepSeek | 14 |
| Saved jobs | 10 |
| Atomically refused jobs | 4 |
| New ordinary turns saved | 6 |
| Regenerated sibling / background / LTA jobs saved | 1 / 1 / 2 |
| Free abandon / rollback / select variant / switch actor | 3 / 4 / 1 / 1 |
| Completed LLM calls | 36 |
| Narrative / Extraction / Extraction repair | 12 / 12 / 4 |
| LTA Narrative / LTA Extraction | 4 / 4 |
| Input / cached input / output tokens | 479,419 / 180,608 / 24,285 |
| Usage-based USD estimate, cache/time-aware | $0.059934474 |
| Conservative peak/cold USD charge | $0.1729677 |
| Previously spent from #230 authorization | $0.1856862 |
| Shared authorization used / remaining | $0.3586539 / **$1.6413461** |
| Historical ledger total calls / operations | 283 / 175 |
| Outstanding reservations / automatic paid repeats | 0 / 0 |

Saved does not mean semantically passed: Crisis and Phone saved incorrect claims.
All 36 raw streams exactly match persisted responses, with complete status and
finish_reason. The 247 pre-existing settled reservations remain unchanged.
Historical token totals are 3,551,356 input and 175,797 output; at the same
conservative rates their aggregate is $1.2763632, not a provider invoice.

The original #230 authorization (baseline205 calls /124 actions, $2) was **not
renewed**. This run began at247 calls /152 actions with $1.8143138 and92 action
reservations remaining. The reviewed69-operation plan was curtailed by defects;
its shared action ceiling remains244. Every call reserves the full provider
context plus output before dispatch, including repair and LTA; unknown outcomes
block every linked run.

Official [pricing](https://api-docs.deepseek.com/quick_start/pricing/) was checked:
Flash peak/cold input $0.30/M, cached input $0.006/M, output $1.20/M; 1M context.
The provider reports a 1,048,576-token context; app contexts remain40,960 and65,536
for Family. The balance endpoint reported **CNY16.59 before /16.23 after**, USD0,
account available. This rounded account movement is distinct from the usage
estimate. Published peak CNY tariffs (2/M input,8/M output) also covered the
remaining cap; no currency exchange-rate assumption or blind context increase.

## Targeted retest and six-group coverage

| Group / target | Observed result | Gate / limitation |
| --- | --- | --- |
| Crisis/001, #232 | Vera remains the named target; no substitution by Marina. Initial Extraction adds absent Vera as physical participant; repair removes her but retains `player_action.outcome=completed` without a channel or completed-interaction assertion. Saved History repeats the false completion. | **Held: P2 #237.** No new death, succession or prolonged Crisis sequence. |
| Social/001, #233 | Explicit consent produces a coherent scene, but a two-action input's Event quote differs from the referenced action quote; repair repeats it. | **Held: P2 #238.** No accepted live consent result; #233 cannot be called fully confirmed. |
| Family/000–002, #221/#231 | LTA stops exactly at due1980, requested20700. First local labor/help scene saves at1980; no birth or sex disclosure. Next ongoing-labor Extraction advances2 minutes despite the explicit zero-minute contract; Runtime refuses atomically. | **Held: P2 #240.** Child creation, canonical sex vs Narrative, birth History/Knowledge, remote birth, age and milestones remain unverified live. |
| Knowledge/recovery, #222 | Exact old unsupported commitment still rejects offline. Browser abandon makes zero LLM calls and preserves canonical state. New explicit-consent input reaches DeepSeek but fails the same quote mismatch as Social. | **Held: #238.** Recovery transport/abandon confirmed; successful next save, secrets/rumors/outdated Knowledge propagation not confirmed. |
| Phone/006, #223 | Same old input now saves. Narrative only departs and mentions future plans; Extraction invents completed arrival in the workshop. Canonical location becomes workshop, not unknown. | **Held: reopened #223**, not a duplicate. Old null-endpoint refusal gone; required unknown-destination semantics still fail. No new calls/chats after this defect. |
| Campaign/014, #220 | Original input and next question save Events at2105840 and2105842 inside their respective turn intervals. Date2030-10-06, provenance and agency preserved. | Targeted chronology passes; conditional NPC time suggestion is not counted as a typed calendar commitment. |
| Campaign continuation | Real regeneration, prior sibling selection, rollback and different branch succeed. Observer mode is explicit. One-year LTA and switch back to Kirill succeed; the next question fails after repair fixes time but leaves a missing Event/action reference. | **Held: #238.** One-year world progression fails the quality goal; no five-year escalation. |

Structural History audit found no duplicate active Event IDs or provenance-schema
warnings. This does **not** clear the semantic defects in Crisis/Phone.
No new Knowledge acquisitions or relationship changes were accepted in this run;
absence of a leak in these observations is not broad Knowledge coverage.
The absent-Vera physical participant is rejected before repair, supporting #226's
presence guard, while #237 exposes a different completion-provenance gap.

## Confirmed defects and diagnostic controls

- **P2 [#237](https://github.com/Troyevv/ai_rpg_engine/issues/237)** — Runtime accepts
  completed player-action metadata aimed at an absent target when the Event omits
  the stronger completion assertion. Exact replay accepts; adding that assertion
  correctly rejects. No teleportation or new Knowledge was observed.
- **P2 [#238](https://github.com/Troyevv/ai_rpg_engine/issues/238)** — Extraction/repair
  produces inconsistent action/Event provenance. Social and Knowledge mismatch
  quotes; Campaign omits the action reference. Runtime correctly refuses each.
  One-field/pair diagnostic controls accept the same Narrative. Controls were
  never persisted or counted as live successes.
- **P2 [#240](https://github.com/Troyevv/ai_rpg_engine/issues/240)** — ongoing labor
  ignores the explicit elapsed_minutes=0 contract. Exact replay rejects; changing
  only elapsed time to0 accepts without birth. Distinct from #221's old absent
  due-scene context, which is now present.
- **P2 [#223](https://github.com/Troyevv/ai_rpg_engine/issues/223)** — reopened because
  its unknown-destination requirement still fails. Omitting only the unsupported
  arrival in an offline control preserves departure and yields location=null.
  This is an Extraction semantics failure, not evidence that Runtime should parse
  literary prose or weaken endpoint validation.

Duplicate searches and prior issue bodies were checked. No new Runtime/frontend
fixes were made in this QA PR. Group holds are evidence-hashed and block resume.

## Long-term progression and Narrative quality

The one-year advance is reproducible from six saved responses with **zero new
provider calls**: 2105844→2631444 (2030-10-06→2031-10-06), accepted0/14 candidate
causes. Eleven were not attempted because of the explicit six-call budget; three
attempted groups were unresolved. The first Extraction omitted required
advance_candidate_ids; the other two supplied no accepted Event. These failures
are recorded as invalid_outcome; all six raw responses and selected candidate IDs
are retained. No characters, relationships, roles, Knowledge, commitments or
History Events changed: only world_time/turn_id. A calendar anniversary is a
computed occurrence, not evidence of world development.

Narrative remains readable and NPCs initiate questions, propose work and state
boundaries without assigning new commitments to Kirill. But long-term responses
repeat old workshop discussion or describe a background character walking with
unfinished training. After the year, Vera says little time has passed since the
morning. That failed turn is not persisted. Repeated rocking/“малыш” language for
a canonically four/five-year-old child is a weak age cue; canonical birth date and
child stage remain intact. These are quality/continuity observations, not proof
of another deterministic Runtime corruption. Unknown outcomes are permitted;
zero accepted groups alone does not prove a separate Runtime bug. The larger
five-year plan was not used to manufacture a success count.

## Verification and reproducibility

- Focused QA: **65 passed**; integrated-fix Runtime suite: **170 passed**.
- Production FastAPI/Chromium preflight: all6 groups × desktop/mobile passed.
- Final browser review: **12/12** desktop/mobile views loaded settled content;
  calendar/family/phone navigation and subsequent reload preserve SQLite snapshots.
  Phone's existing conversations are visible; this is not new live chat coverage.
- Four refusal snapshots, including History and sibling hashes, are exactly equal
  before/after. Selection and rollback restore exact historical snapshots; the
  regenerated sibling and new branch preserve prior variants.
- Resume of retest and continuation returns incomplete/held, **zero new requests,
  zero actions**, no checkpoint/evidence/ledger changes. All six holds persist.
- SQLite integrity checks pass for game, historical shared ledger and budget
  baseline. Parent/related files and all six historical archives retain hashes.
- Full backend pytest, Vitest/build and all desktop/mobile shards run through the
  unchanged workflow. The exact final-HEAD run and conclusions are recorded in
  [PR #239 checks](https://github.com/Troyevv/ai_rpg_engine/pull/239/checks) and its
  description; live success is not inferred from green CI. Initial [run445](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42374872997)
  on962555 verified backend3436 passed/1 existing private-export skip (1198.49s),
  Vitest151/151, production build, desktop342 passed and mobile318 passed/24
  existing project-specific skips. No tests or assertions were weakened.
- Embedding retrieval used the existing structural fallback (`OSError`). No
  claim is made about active semantic embeddings or every device/browser.

## Evidence availability

Durable, reviewable minimal reproductions and controls are linked in #237, #238,
#240 and reopened #223; aggregate counts, immutable archive hashes and checkpoint
verification are in [the evidence index](live99-campaign-retest-20261107-evidence.json).
Full raw evidence is preserved locally, **not publicly downloadable yet**:

`live99-campaign-evidence-20261107.tar.gz` — 29,089,712 bytes,
SHA256 `3979c8b87ce923ccf21737c8a7cd17718f218b36535997b752c5118d4d15a277`.
353 internal files verified. It includes isolated SQLite, complete shared ledger,
raw streams/context/responses, before/after/Delta/History/Knowledge, request IDs,
finish reasons, token usage, screenshots, holds, replay and resume receipts.
Archive members and nested gzip payloads were scanned for current environment
credentials and common secret formats: zero matches. This does not by itself
establish that every payload is appropriate for public distribution.

Automatic approval review blocked publication of the full historical/current QA
payload to a **public GitHub Release**, requiring explicit consent for that
exposure. Proposed durable destination: a non-latest QA evidence prerelease in
this repository, with append-only assets and SHA256 verification after download;
a private artifact store with controlled access is an alternative. No upload was
performed or bypassed. `/workspace/work/...` is an ephemeral location, not an
artifact URL. Until storage approval and upload verification, long-term raw
availability remains an acceptance limitation.

## Readiness and next retest

**Not ready for long user campaigns. Stage C and #99 remain incomplete.** Fix and
retest #237/#238/#240 and #223 in separate product PRs, using these paid payloads
for free regressions first. Preserve #220's chronology repair, strict agency,
presence and Knowledge guards. Then verify an accepted birth locally/remotely,
successful recovery submit, real communication, death/succession and meaningful
long-term outcomes before broader campaigns. Remaining funds are not permission
to replay held jobs automatically or renew the authorization. The QA PR can be
reviewed as partial evidence/infrastructure; it does not certify gameplay.
