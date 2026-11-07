# #247 / #246: integrated Extraction recovery

Base: master `d81a52c9980b79d1be99acfde9fc1a1452d71176`.
No paid provider calls. No migration or changes to old snapshots/variants.

## Confirmed causes and changes

- Knowledge combined missing Fact links with other optional perception failures.
  Valid actor/Fact/informational Event/witness acquisitions with missing
  `Event.fact_ids` now produce `knowledge_fact_link_missing`, exact Knowledge
  and Event paths, and participate in the existing bounded repair. Unknown
  actors/facts/events, missing witnesses, unsupported media and protected
  Knowledge remain separately diagnosed optional failures. Ordered revision,
  retirement and supersession validation precede link escalation; invalid optional
  proposals do not become hard failures. No automatic links.
- Completion failure stopped validation before the independent birth boundary.
  The existing resolver now aggregates action/Event/presence/Knowledge errors;
  on a failed candidate, isolated calls to existing Life/Reproduction/Commitment
  validators determine whether the temporal check is independently meaningful.
  Invalid sources suppress dependent diagnostics; accepted BirthClaim can still
  discharge the boundary. Original action indexes remain stable after source rejection, and independent
  completion failures are aggregated too. Pregnancy schedule ownership lives in its existing
  commitment handler so normal and diagnostic paths share the same rule.
- Referenced cards appeared under the title “present”. Narrative blocks now
  separate ContextScope's present, observed, remote and referenced actors.
  This ambiguity is confirmed; its causal role in the original hallucination
  is **not proven**. Extraction classifies impossible Narrative contact as
  violated, activating the existing explicit reauthor/abandon UI path.
- Current arrival assertions lacked a required Event source. The prompt schema
  requires assertion/source_event_id; Runtime checks accepted current Event,
  actor, endpoint, order and physical channel. Same-order arrival Events anchor
  the route endpoint; unrelated equal-order meetings remain ambiguous. History
  stores canonical Event IDs. Unmarked legacy payloads and historical saves
  remain readable. final_scene still owns physical membership.
- Repair duplicated camera/location context. Feedback retains the original
  Extraction and diagnostics but includes only referenced canonical locations;
  the builder removes locations already supplied in current state. Initial
  Extraction reserves soft repair headroom. Existing optional schema compaction
  also runs for untargeted actions. Critical input, Narrative, state, agency,
  Knowledge and temporal data retain the hard pre-dispatch limit.

A pair of mutually consistent invented Event/movement records is **not** proof
of a real arrival. No Python literary parser was added. Phone/Crisis semantic
quality still requires the live gate below.

## Offline evidence

Full archive was available and its SHA256 matched the Issue. Original archive,
SQLite, ledger, checkpoints and variants were not modified.

`tests/fixtures/issue247` stores the six original cases. Test-authored corrected
JSON is explicitly separate. Automated tests exercise Context Builder, jobs,
one bounded repair, reload, retry without regenerating Narrative, rollback,
regeneration/sibling selection, optional Knowledge failures, arrival provenance,
valid BirthClaim boundary discharge, 40960 repair context and 8192 no-dispatch.

The additional replay used **12 copies of the original source SQLite**, restoring
the precise original world state and History head, with original sibling hashes:

| Case | Repeat original response | Test-authored control | Acquisition delta |
| --- | --- | --- | --- |
| Family/001 | atomic error | saved, elapsed=0, no birth | 0 |
| Knowledge/002 | atomic error | saved | **4**, retained after reload |
| Phone/001 | atomic error | saved, no false arrival/scene disappearance | 0 |
| Crisis/001 | atomic error | explicit reauthor required, no commit | 0 |
| Social/001 | saved | saved | 0 |
| Campaign/000 recovered response | saved | saved | 0 |

Each failure preserved snapshot/History; each copy passed SQLite integrity_check
and Repository reload; existing variant content hashes remained unchanged.
The original SQLite hash was unchanged. Scripted calls: three for failure/repair
cases (one Narrative, Extraction, repair), two for already-valid Social/Campaign.
These are mock accounting entries, **not paid/live calls**.

Reproduce from repository root, using a new output directory (about 1.7 GB):

```sh
python tests/replay_issue247_sqlite.py /path/to/live99-postfix-20261107 .runtime/replay247-new
python -m pytest -q tests/test_integrated_repair247.py
python -m pytest -q
cd frontend
npm test
npm run build
npx playwright test e2e/integrated-repair247.spec.ts --project=desktop --project=mobile
```

## PR #248 follow-up audit

Three reproduced defects were fixed in the same PR:

1. A diagnostic birth could append a child card to the original resolver because
   the probe shared `cards`. Probe state, History, warnings, cards and pending
   reviews are isolated; the caller's error list is no longer appended to.
   The regression snapshots mutable resolver fields and input arguments around
   the real probe. No mutation of the passed Events was observed.
2. A birth disclosure error stopped unrelated Knowledge diagnostics. Birth checks
   now aggregate independent claims with original indexes, then the existing
   Knowledge handler checks unrelated facts. Facts whose typed birth disclosure
   failed are not applied or diagnosed as independent acquisitions. Invalid
   source Events suppress their dependent claims, not unrelated ones.
3. An unrelated rejected NPC Event suppressed completion checks for every player
   action. Only Events declaring player-action provenance can make that coverage
   inconclusive. Agency validation itself remains mandatory.

New regressions include mixed Event/BirthClaim/Knowledge failures, probe isolation,
multiple actors moving through two new locations with unsorted input rows,
wrong actor/source/order, canonical source IDs in History, reload, rollback and
sibling selection. Full results and exact tested commit are in
[PR #248](https://github.com/Troyevv/ai_rpg_engine/pull/248).

Artifact audit: unused intermediate Knowledge/Campaign replies removed. Six exact
readable before-state/input/Narrative/selected-response fixtures remain (~560 KiB).
No SQLite, ledger, screenshots, videos or test logs are committed. Original QA
archive and source SQLite remain unchanged. No save schema/migration changes.

## Short Live QA plan — NOT authorized or executed

Purpose: test model semantics separately from deterministic recovery. Model:
`deepseek-flash`, explicit non-thinking; no fallback/model switching. Use the
reviewed PR head, real production jobs/Context Builder/Resolver/History/SQLite.
No world generation, background/LTA campaign, external tools or success rerolls.

### Preparation (zero paid calls)

- Verify original archive SHA256 above. Use SQLite backup into disposable copies;
  retain the original DB, ledger, responses and snapshots unchanged. Restore the
  exact six before states and History heads using the same abandon/rollback
  sequence verified by `tests/replay_issue247_sqlite.py`, never SQL state repair.
- Use independent copies for saved-Narrative extraction and freshly authored
  turns. Preserve prior variants; record head/revision and state/History hashes.
- Build all initial and repair contexts offline first. Context: 65536, Narrative
  output cap 2000, Extraction/repair cap 8192, thinking disabled. Fail before
  dispatch if mandatory context cannot fit; do not silently enlarge the window.
- Saved-Narrative checks use real recorded job context and the normal Extraction
  retry path after verifying eligibility. If an original job is not eligible,
  mark that check blocked; do not rewrite lifecycle fields to force a retry.
- Bind one newly authorized run directory and exact operation list to the existing
  live99 budget/stream guard; preserve historical spending and a new-run baseline.
  Enforce **42 additional provider dispatches / $2.00 additional spend**, including
  repair, continuations and optional remote stages, across restarts. Sequential
  requests only; unknown usage/timeout stops the run.
- The current generic harness has a 320-call ceiling and larger campaign plans.
  Its existing `prepare-campaign-retest` command is **not** this short plan.
  Before live execution, wire the reviewed per-run 42-call ceiling and this exact
  operation list into that harness and verify fail-closed behavior without API
  calls. No second runtime or separate provider bypass. This plan alone does not
  claim the short runner or fresh authorization already exists.

### Ordered cases and provider-call accounting

A saved Narrative costs one Extraction (+ at most one existing bounded repair).
A fresh turn/regeneration costs one Narrative + one Extraction (+ at most one
repair). No automatic reauthor of invalid prose; record the refusal and stop that
branch. The fresh Crisis branch below is a separately planned independent run.

| Case / original checkpoint | Exact work | Base calls | With one repair per job |
| --- | --- | ---: | ---: |
| Crisis / `crisis/001` | 1 saved-Narrative Extraction; 1 fresh turn using original input | 3 | 5 |
| Family / `family/001` | 1 saved-Narrative Extraction; original-input fresh turn and 1 observation continuation | 5 | 8 |
| Knowledge / `knowledge/002` | 1 saved-Narrative Extraction; 1 fresh original-input turn | 3 | 5 |
| Phone / `phone/001` | 1 saved-Narrative Extraction; original-input fresh turn and 2 continuations below | 7 | 11 |
| Social / `social/001` | 1 fresh turn with explicit two-recipient input below | 2 | 3 |
| Campaign / `campaign/000` | 1 fresh original-input turn, then 1 regeneration from its recorded original context | 4 | 6 |
| **Total** | **4 saved-text jobs + 10 authored jobs** | **24** | **38** |

Reserve up to four further dispatches within the same **42-call hard cap** for
production remote/continuation stages if they actually occur. They are not extra
retries or permission to repeat a success. If a branch fails, report fewer calls
and do not run dependent steps. A fifth auxiliary request stops at the global cap.

Inputs not taken verbatim from the archived `intent.json`:

- Family continuation: «Я остаюсь рядом и наблюдаю, что происходит с Верой,
  не вмешиваясь в её действия.»
- Phone continuation 1: «Я не удерживаю Тимура и продолжаю разбирать фотографии.
  Не предлагаю ему место назначения.»
- Phone continuation 2: «Я продолжаю заниматься фотографиями. Если кто-то уже
  ушёл, я не считаю, что он прибыл куда-либо, пока этого не произошло.»
- Social: «Я спрашиваю Веру, какую пачку фотографий взять следующей, а Тимура —
  когда он собирается позвонить Олегу. Выслушиваю каждого, не отвечая за них.»

### Semantic acceptance, not merely saved status

- **Crisis:** referenced Vera is not labelled physically present. Impossible
  contact in the original prose requires explicit reauthor with no canon commit;
  correct fresh prose must preserve control, POV and actual presence.
- **Family:** reference/observation does not invent completed interaction. Ongoing
  birth cannot cross an unresolved boundary; completed birth requires canonical
  BirthClaim, sex disclosure/provenance, one child identity and no Knowledge leak.
  If the model authors only one outcome, the other remains **not observed**.
- **Knowledge:** saved original prose retains the two confirmed facts/four
  acquisitions, Event links, provenance and History after reload. Fresh prose is
  judged on what it actually disclosed; do not demand four gains if it differed.
- **Phone:** manually compare prose against Events, movements, final_scene and
  character_changes for preparation, room exit, departure and actual arrival.
  New places and autonomous NPC action are allowed. If real arrival/new-place
  creation does not occur in these three turns, mark that contrast **not observed**;
  do not force an NPC action or claim a semantic pass from deterministic coverage.
- **Social:** both target IDs remain attached to the original action(s). One joint
  Event or split Events are acceptable when the authored interactions occurred;
  refusal/defer and NPC initiative must not be rewritten as player agreement.
- **Campaign:** absolute time, action provenance and same-Narrative repair remain
  consistent. After regeneration, select both siblings, reload and rollback with
  zero further model calls; original sibling content and before state must match.

For each call capture existing usage/ledger receipt, original and repaired JSON,
full diagnostics, before/after state+History+Knowledge, job revision and variant
IDs. UI desktop/mobile checks can view/reload the same saved results without paid
replays. Any unexpected semantic commit stops dependent branches and blocks the
live gate; a failed but atomic rejection is not a successful semantic repair.

### Conservative budget

Official pricing checked 2026-11-07:
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).
Use peak cache-miss rates **$0.30/M input + $1.20/M output**; ignore cache/off-peak
savings. At 65536 input + 8192 output tokens for every dispatch (even Narrative),
24 calls estimate at most **$0.71**, 38 **$1.13**, 42 **$1.24**. These are planning
estimates using a local context allowance, not provider token receipts.

Proposed additional hard budget: **$2.00**, not previously authorized. The existing
guard reserves the full 1,048,576-token provider window before each request
(~$0.3244 including 8192 output) and settles only verified usage. With ordinary
receipts this leaves conservative headroom. At literal full-window consumption,
42 requests would cost ~$13.63: the $2 cap must stop early, never promise all cases
will fit or auto-increase the allowance. Recheck prices/model before dispatch.

No paid calls were made for this follow-up. Deterministic passes establish
validation/persistence behavior, not that DeepSeek's semantic mistakes are fixed.
