# #259: one mandatory semantic revision does not qualify

2026-11-17, existing PR #248. Experiment implementation: `f0b8bca6b33b6bfd63973339621a3ca2d794da7a`, based on `2bb34e6`. **Do not adopt the mandatory revision as a production default.** It did not repair the confirmed information omission or correctly recognize the unchosen refusal. #259 remains incomplete; no campaign recovery or ordinary play session was started.

## Authorized scope and frozen method

The user separately approved **8 new Flash/off calls / $0.50**, following the [previous result and proposed alternative](consequences259-live.md). All eight calls were used, no further repair or regeneration. Previous allowances were not reused for this stage.

Selection was declared before dispatch: **all eight first responses of the corrected/off series**, not a mixture of the initial/corrected/low answers. This selects one complete comparable series containing both failures and successful controls; no successful Narrative or Extraction was rerolled. The first responses were reused byte-for-byte. Their earlier usage was not charged again.

`devtools/issue259/revision.py` prepares the only candidate with the existing compound adapter and evaluates it from its original before-state. It sends real structural diagnostics when present, plus one generic request to review substantive omissions, movement, perceived information, player choices and chronology against the full unchanged Narrative/input. No expected answers, case-specific missing claims or synthetic diagnostics are sent. The paid request uses the existing Responses schema transport, Flash/off, temperature 0.1, max output 8192. Actual receipts have zero reasoning tokens.

This is explicitly **whole-candidate semantic review**, not the narrower ordinary repair scope. Named source/domain records can be addressed; unmentioned records remain unchanged, existing source/effect deletion guards, hash binding and typed dependency checks still apply. It can add a missed consequence even without a structural error. The wider scope itself cannot prove semantic preservation. Choices remain unchanged, rather than giving the reviewer another generation task. Optional Runtime warnings are recorded in the evidence but not promoted into structural diagnostics or new hard errors.

There is exactly one new provider dispatch per case, including first responses already structurally accepted. The response is a patch to the same candidate, never a second independent story/world summary. Compiler/Resolver run again from the original before-state. Any remaining error is final for this experiment. There is no automatic third Extraction, profile switch or hidden retry.

## Observed outcomes

The table separates recognition of a real prose conflict from an accidental technical rejection. Structural resolution is not a saved production job.

| Case | Actual revision | Important final outcome |
|---|---|---|
| River | Removes the player-input source incorrectly attached to Galina's question | **PASS for travel and received information**: both reach the new bank, two compound claims retained. Existing optional relationship/choice warnings remain. Same state/History as prior ordinary repair. |
| Cafe | Adds the valid player-input quote to arrival; says no other consequential changes exist | **FAIL**: both arrive, but Galina's actual statement about Tamara working after closing still produces **zero Knowledge acquisitions**. |
| Conversation by water | Restates the same effects and says no change is needed | **PARTIAL, unchanged**: regular friendship retained; mother's explicit statement that she would now approach first to reconcile is still omitted. The invalid optional relationship source remains rejected. |
| Partial secret | Selects the exact information effect as the relationship source | **PASS for privacy/information**: only yesterday's conversation with Nikolay is learned, not the larger secret. Original optional relationship and all four choice proposals are rejected by their existing owners. |
| Unchosen refusal | Adds a second completed refusal interaction, citing Narrative itself as player input; does not add `unauthorized_choice` | **BLOCKED, semantic failure**: Runtime rejects `player_action_source_invalid`. It prevents a commit, but the reviewer has not correctly requested reauthor for the unchosen decision. No further repair was sent. |
| Explicitly chosen refusal | Returns the same source and says no correction needed | **PASS**: the chosen refusal remains accepted; no false agency rejection. |
| Contradictory date | Retains the concrete narrator date, explicitly leaves it for reauthor and does not shift time | **PASS, correct reauthor**: `narrative_chronology_conflict`, rather than false acceptance. |
| Olga background | Restates the same sources and says no new consequences exist | **PASS for local exit/privacy, other omissions unchanged**: home address retained, no hero Knowledge. Denis still gets no acquisition for Olga's explicit complaint; optional relationship proposals remain rejected. |

All **six resolved state/History pairs exactly equal the earlier corrected/off result after its ordinary processing**, using the free adapter fixes from the previous report. The additional review produced no improved accepted canonical consequences in these cases. The two non-resolved cases are the correctly retained calendar conflict and the incorrectly interpreted refusal that happens to fail source validation.

No additional information leak or loss of previously accepted canonical outcomes was found among the resolved cases. This does not validate omitted consequences or justify the new call. No new rare-domain, holdout, birth/death or UI acceptance claim is made.

Two representative original responses:

- Cafe: “No other consequential changes found.” Yet the unchanged Narrative says Tamara works on papers or dough after closing; both the first candidate and revision omit this proposition entirely.
- Unchosen refusal: “Добавлен пропущенный отказ Алексея ... как отдельное завершённое взаимодействие”. Its new `input_source.quote` is `Алексей отвечает: «Нет, не хочу»`, which comes from Narrative, not the actual player input `Рассматриваю фотографию на столе.`.

Those are confirmed provider-output errors. The adapter cannot persist an omitted claim; it did not discard a correctly emitted one. The refusal's source check works as intended. The hypothesis that a separate revision would reliably revisit meaning rather than primarily repeat/fix the first candidate **is not supported by this run**. The data do not establish an internal attention mechanism or prove all possible two-stage designs impossible.

## Usage, latency and preservation

Reservations **815–822**, all settled by real usage receipts, zero unknown paid outcomes:

- **8 new calls, 222,217 input / 4,498 output tokens; reasoning 0.**
- **$0.0720627 conservative spend**, peak cold-input/output $0.30/$1.20 per million. This is not a claim about the provider's discounted invoice.
- New revision duration including local post-processing: mean **4.13 s**, median **3.57 s**.
- Historical first-response provider duration plus actual new revision duration: mean **9.89 s**, median **9.30 s**. This is an explicitly paired estimate, **not a newly observed production two-call turn**.
- Historical first responses cost $0.066705; first+revision paired cost is $0.1387677 for eight cases. Only $0.0720627 is new spending. Narrative, background and UI latency/cost are excluded.
- There are eight second Extraction requests by design, **zero additional repair requests**. Six structural resolutions do not mean six complete semantic passes.

The previous experiment's 37 calls/$0.3718506 remain separately recorded. Combined #259 experimentation so far: **45 calls/$0.4439133**, with distinct authorizations; this is not a renewed allowance. The current dispatch manifest is completed/stopped at its eight-call limit. Unused money does not authorize more requests.

Messages and input/response hashes were frozen during free preflight. The actual dispatched request hash was checked before every call. All context blocks other than rules/schema projection remain identical to their frozen source; original Narrative/input/before-state and first response are not edited. Operations were sequential under the existing Budget lock, without two servers sharing a database. No production server or SQLite state writer was launched for this qualification. The game saves are therefore **not claimed to have committed or recovered**.

## Code, free checks and evidence

Only QA code and tests were added:

- `devtools/issue259/revision.py`: one recorded first candidate → one explicit semantic revision → existing compiler/Resolver, no retry loop.
- `tests/test_revision259.py`: valid first response still gets one revision; no-op preserves state/History; a labelled authored missing-claim control demonstrates expressibility; real structural diagnostics, malformed revision, stale hash and effect deletion do not trigger another call.

`python -m pytest -q tests/test_revision259.py tests/test_compound259.py tests/test_technical258.py tests/test_candidates258.py`: **40 passed**. Free preflight also built/validated all eight real request schemas with an explicitly authored no-op transport. These controls are not presented as actual DeepSeek successes.

Evidence: `work/issue259-revision-live/` contains frozen source cases/first replies and provenance hashes, preflight, original streamed revisions, request schemas/configs, before/revised candidates, Runtime diagnostics and state/History, usage/timings, provider attempt/reservation identity and raw streams, ledger before/after, metrics and the stopped dispatch manifest. Original evidence and SQLite are preserved. No answers were manually repaired after receipt.

Production contract/version, provider defaults and canonical domain owners are unchanged. Full CI was not rerun for this unqualified QA-only branch; commits explicitly use `[skip ci]`. Production integration, save/reload/rollback of the new flow, desktop/mobile, independent confirmation, sequential Berezovsk recovery and 30 new ordinary turns are **NOT TESTED/NOT RUN**. Prior green CI is not substituted for them.

## Decision

Do not make the extra revision mandatory in production. Its measured extra call did not remove the cafe blocker, and the refusal still does not reach the correct narrative-recovery outcome. Adding more automatic repair or declaring the six structural resolutions a playable campaign would conceal the result.

The approved alternative is now tested and rejected on these acceptance criteria. No new paid variant is scheduled, no further budget is assumed, and no new PR/merge/issue closure is performed. #259 still requires a qualified path before campaign recovery and gameplay; this negative result is not completion of that task.
