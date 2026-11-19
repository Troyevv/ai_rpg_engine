# #259: live qualification stopped before campaign recovery

2026-11-16, existing PR #248. **Issue #259 remains incomplete. No production default changed; the campaign was not restored and no ordinary game turn was played in this run.** The planned initial candidate, one correction and one distinct fallback were all exercised. Their remaining failures do not justify putting a new version into production or playing over a false predecessor.

## What was actually run

Preparation/prototype `7510b286721e6a2ede96e1d1638dcd788fe1900a`; corrected candidate `ab3aefef7bf519a5fdf6afc4cf47fd14c8414585`; explicit profile runner `789e36c` (full SHA in raw manifest). Base production remains `4794159d32e3350a2e2776436545c0879e8009c2`.

The [preparation report](consequences259.md) freezes original/contrast inputs, severity and budget. First series: eight compound cases and three fresh v8/T controls, Flash/off. Correction: the same eight cases, Flash/off. Single fallback: the same corrected messages/schema on Flash/low, max output 16384. Narrative was never regenerated. Every case got one first answer and at most one repair, only following actual diagnostics. No oracle supplied missing claims or agency findings. No third request or output-limit escalation was used.

This was provider qualification through the real parser/compiler/Resolver/repair, on independent immutable snapshots. It was **not** eight production UI turns, nor an already recovered SQLite campaign. The authored predecessor used for independent downstream cases remains explicitly labelled. Original #257/#258 evaluations are unchanged.

## Actual outcomes

PASS below means the stated important spatial/information/agency/calendar outcome, not certification of every optional annotation or all engine domains. BLOCKED means the candidate could not reach the required final result after its one repair. Parenthetical losses remain visible rather than disappearing into a PASS count.

| Case | Initial compound/off | Corrected compound/off | Same corrected candidate/low |
|---|---|---|---|
| River arrival and conversation | PASS: both reach a new shore, three heard claims | PASS after repair: shore and heard information; three choices dropped | BLOCKED after repair: quoted player source differs from actual input |
| Cafe approach and Tamara information | PASS: joint arrival, work-after-closing claim; entry remains a future choice | FAIL: arrival saved after repair, **no Knowledge acquisition** from Galina's informative answer | BLOCKED: malformed first JSON; repair has ambiguous compound route reference and other unvalidated dependencies |
| Conversation by water | PASS: friendship and mother's changed attitude to reconciliation retained | Main friendship retained, mother's stated changed attitude omitted; relationship proposal rejected | PASS first answer: four actual acquisitions, including her revised view; no relocation |
| Partial secret | PASS: only yesterday's conversation with Nikolay learned | BLOCKED: corrected source reference rejected by prototype repair scope | PASS first answer: only stated conversation learned; optional relationship change rejected |
| Unchosen refusal of tea | FAIL: repair attaches unrelated real photograph-input quote; refusal is falsely accepted | FAIL first answer: same false authority, no agency finding | **Violation detected**, but BLOCKED before proper reauthor outcome by compound source/repair bookkeeping |
| Explicitly chosen refusal | PASS first answer | PASS first answer | PASS after repair removes inapplicable `during` link |
| Contradictory calendar date | PASS: existing Calendar requires reauthor | PASS: requires reauthor | PASS: requires reauthor; proposed elapsed 720 does not legalize the contradiction |
| Olga's background local exit | PASS after repair: home address retained, actual NPC knowledge, no hero knowledge | PASS spatial/privacy outcome first answer; relationship proposals rejected and her explicit complaint not retained as Denis's Knowledge | BLOCKED: source-to-effect references and repair scope; no background state accepted |

Fresh v8/T control: river accepted an overly broad town location rather than the reached bank; cafe omitted the informative claim; unchosen refusal was accepted. All three structurally resolved. This small control supports those particular observations, not a population-wide accuracy estimate.

No discovered leak was repaired by granting everybody Knowledge. No route participant was inferred from end visibility. Harmless route-order differences were not reclassified as blockers where listeners/outcomes remained the same. Nevertheless, lost actual information and unchosen decisions were never downgraded to literary style.

## Confirmed causes and limits

1. **Semantic omission/false authority persists on off.** Corrected cafe's response contains movement and an invitation, but no information effect for Galina's substantive answer. Compiler/Resolver therefore have no claim to persist. The corrected refusal explicitly maps “Рассматриваю фотографию на столе.” to “Нет, не хочу” as preserved meaning. Runtime cannot discover that semantic mismatch without interpreting prose. These are present in actual provider output, not losses introduced by the adapter.
2. **The prototype still imposes unnecessary identity work.** Compound groups expand into effect IDs; multi-effect domain references require suffixes. Low frequently names the meaningful whole source instead. `expand` rejects the first ambiguous typed reference before later independent ones are collected. That is a limitation introduced by this experimental adapter, not evidence that existing Runtime geography is intrinsically wrong.
3. **Repair ownership is incomplete in the prototype.** Corrected partial-secret and low Olga/unrequested-refusal repairs identify a particular effect but are rejected as a new unrelated domain record. The inherited protocol keys ID-less records by content digest; changing their source changes the key. Group-level dependency sets also lack derived effect identities. Simply allowing the new reference would not suffice: the old ambiguous record would remain without an explicit withdrawal. Actual first/repair responses and exact failures are retained. The deterministic scope/key defect is fixed after this series, as described below; the live table is not rewritten as a new model success.
4. **An exact source quoting failure remains.** Low river initially omitted player authority. Its repair supplied `Иду рядом с мамой к Березянке, подстраиваясь под её шаг. «Покажи ту тропинку.»`, while actual input continues the same quotation with the question about friends. The preserved evidence check rejects the altered quote. This is not proof the player's walk was unchosen, and the test does not portray it as such.
5. **Low cafe first response is malformed, not a missing receipt or output-limit failure.** JSON reports `Extra data` at char 2861: the root closes before `choices`. The full repair fixes syntax but then contains the ambiguous `during_step_id=step_3`, arrival without its authority source and an NPC input source taken from Narrative. Only the first of those is reported by the current prototype at that point. There is no authorized second repair to hide this result.
6. **Domain burden was not removed sufficiently.** Restoring the existing shared relationship contract supplies `grounded_feelings`/`rationale`, omitted by the initial compact rules. Some replies still propose deltas as absolute values: existing Alexey→Galina trust 70, proposed 2. Existing gradual-change protection correctly drops this; it is not disabled. Low Olga uses sensible absolute values, but that candidate fails earlier. One successful domain proposal is not lifecycle acceptance.

Implemented within the single correction: exact single-effect source aliases; original-field authority feedback instead of asking the model to edit internal PlayerAction records; composition of the existing relationship instructions; retained warnings/choices in qualification records. The low runner records its explicit profile and actual context/output allowance. These are QA-only changes. They do not silently alter server-recorded v8 jobs.

The candidate removes per-effect generated IDs, text and evidence, and the repeated scene situation, but has not eliminated enough cross-domain bookkeeping. It is not a satisfactory completed implementation of the issue's “one semantic source, Runtime owns technical identity” goal. No causal claim that model complexity alone explains every failure is established.

## Free deterministic correction after the paid series

The experimental adapter was then corrected without changing prompts, schema, provider replies, canonical owners or paying for more attempts:

- Collect all independently detectable ambiguous source references/invalid local route indexes in one pass, with nested field paths, rather than raising at the first reference.
- Include the selected source's derived effect identities in the existing repair dependency scope.
- Translate an explicit model refinement of a whole-source reference to one of its effects into a keyed replacement for an ID-less domain record. This happens only when exactly one scoped predecessor matches **every other field byte-for-byte**. No effect is selected by code, no text/feelings/outcome inferred, and no independent record is removed. The provider payload is copied, never altered; the technical reference replacement is recorded in candidate revisions.
- Leave unresolved optional annotation references to their existing owners. `OPTIONAL_SECTIONS` already designates these as non-blocking; the experimental adapter must not promote them to hard errors. The owner rejects their authority with warnings. Actual effects, Knowledge and agency findings remain independently checked.

Free replay of the exact saved first/repair responses now accepts corrected-off partial-secret (actual narrow claim retained), and low Olga (actual local departure and NPC outcomes). Low unchosen-refusal now reaches the correct agency reauthor on its **first saved response**, so its historical repair is not needed in this replay. No new successful JSON was authored. Every already-resolved live state/History stays identical. Optional choices referring to a step instead of an accessible Fact can still be dropped; this correction does not pretend to solve that model error.

Low river still fails exact player-source validation; low cafe still fails its ambiguous actual route reference after the one syntax repair. Off's false acceptance and missing information remain. Thus this correction repairs demonstrated adapter defects but **does not qualify the candidate** or turn an offline replay into live acceptance. The first live errors, costs and timings above remain reported unchanged.

Regressions cover independent errors, exact reference-only replacement without duplication, unchanged effects/Knowledge, refusing to silently replace a record whose other meaning changed, optional-annotation warnings and preservation of the real agency conflict. A new test initially omitted required `SceneAction.modality`; that fixture was corrected before the final passing run. No assertion was weakened.

## Usage and latency

Actual usage receipts; peak cold-input/output conservative rates $0.30/$1.20 per million, including reasoning output. These are conservative costs derived from usage, not an assertion about the provider's discounted final invoice. Full Extraction duration includes its repair and local resolution, excludes human reading.

| Series | Cases | Calls / repairs | Input tokens | Output tokens | Conservative USD | Mean / median seconds |
|---|---:|---:|---:|---:|---:|---:|
| Fresh v8/T control, off | 3 | 3 / 0 | 84,993 | 3,319 | 0.0294807 | 6.32 / 6.29 |
| Initial compound, off | 8 | 10 / 2 | 227,008 | 9,163 | 0.0790980 | 6.93 / 6.52 |
| Corrected compound, off | 8 | 11 / 3 | 254,060 | 9,114 | 0.0871548 | 7.31 / 7.16 |
| Corrected compound, low | 8 | 13 / 5 | 301,173 | 71,471 | 0.1761171 | 44.30 / 37.26 |
| Total | 27 | 37 / 10 | 867,234 | 93,067 | **0.3718506** | — |

Low output includes **55,715 reasoning tokens**. It detects the refusal but increases output, latency and repair frequency. Four of its eight cases remain technically blocked; two first answers resolve, one gets correct calendar reauthor, one resolves after repair. It is not recommended as the new production profile on this evidence.

Technical first resolutions: initial compound 5/8, corrected off 4/8, low 2/8; each also has one correct first calendar refusal. Repairs reaching a resolved candidate: 2/2, 2/3, 1/5 respectively. These are explicitly **not semantic accuracy**: the first series' refusal and corrected cafe/refusal demonstrate why resolution counts are misleading. Cost per actual request: initial compound $0.0079098, corrected off $0.0079232, low $0.0135475; cost per case including repairs: $0.0098873 / $0.0108944 / $0.0220146.

Matched first request input tokens drop from v8/T 30,260→27,112 (river), 30,152→27,004 (cafe), 24,581→21,433 (refusal), about 10–13%. The correction adds 157 input tokens to these candidate requests. Schema/world/Choice context still account for substantial load. Character-count reduction is not presented as billed-token reduction.

Reservations **778–814**, all settled with real receipts; zero new unknown outcomes. Initial stage used 13/$0.1085787 of 22/$0.75. Shared correction+fallback used 24/$0.2632719 of 32/$1.25. Total used 37/$0.3718506 of the approved 204/$6. No budget transferred into another stage. Dispatch manifest is stopped; confirmation, recovery and game allowances were not consumed.

## Free checks and evidence

`python -m pytest -q tests/test_compound259.py tests/test_technical258.py tests/test_candidates258.py`: **34 passed** after the final free adapter correction (31 at the live profile-runner SHA). Prior preparation also includes actual job→SQLite→cold reload→rollback using a labelled authored provider seam. That is not evidence of live production-schema integration.

A subsequent **free replay of all 27 actual recorded candidates** reproduces all 19 resolved states and Histories exactly and all eight remaining diagnostic-code sequences. Historical first-series code is loaded for its replay, not silently replaced by the correction. No model request is issued by replay. It confirms where the failures occur, not that unresolved candidates became successful.

Raw root: `work/issue259-live/`: immutable inputs for all three stages; messages/provider schema, original responses/chunks, repair, candidate audits, diagnostics, before/result state and History, timings, request/attempt/reservation metadata, provider-streams, ledger before/after, metrics and replay results. Source SQLite/archives remain unchanged. The raw manifests record full SHAs and input hashes. `summary.stage_totals` in the per-case runner is the **whole #259 run total**, despite the legacy field name; stage accounting above is separately calculated from reservation ranges.

Full CI, new production version integration, live SQLite chain recovery, desktop/mobile and the 30-turn diary are **NOT RUN**, because the required qualification gate failed. Prior green CI is not claimed as evidence for this candidate. No new PR, merge, issue closure, direct SQL state change or successful-response reroll.

## One concrete alternative for separate approval

The current result supports neither another renamed schema nor a claim that Flash/low solves the problem. A bounded next experiment would reuse the **same candidate**, its existing compiler and the one repair mechanism, but make that second Extraction invocation an explicit consequence revision even when structural validation succeeds:

- First Extraction proposes the only candidate. Before, full original Narrative/input and the candidate remain fixed; no separate narrative summary or second world state.
- The second invocation receives real structural diagnostics, if any, and reviews missing substantive claims/travel and unchosen decisions. It returns only hash-bound edits to that candidate (or no edits), with explicit source-linked reasons; it does not issue a self-certifying PASS boolean. Existing owners validate the entire revised candidate atomically from before.
- This replaces conditional repair with one mandatory revision slot: **Narrative + Extraction + revision**, at most two Extraction calls, no extra repair after revision and no hidden critic/reroll. It costs one additional call on currently first-pass turns. A reviewer can still miss or introduce errors; qualification must test preservation of already-correct outcomes as well as omissions.
- Use the free deterministic compound source/record-key scope correction below, retaining the tests for multiple independent errors and unaffected records. This does not justify guessing an ambiguous effect or accepting malformed JSON. No broader Runtime redesign is required or proposed.

Minimal new paid test, **not authorized by the previous plan**: one revision of each of the eight already recorded first compound/off replies, Flash/off, 8192 maximum output, **8 calls / $0.50 cap**, expected roughly $0.06–0.10 and 5–15 seconds per call from these receipts. This reuses first responses, so it cannot choose a luckier first Extraction. No additional repair or Narrative regeneration. The cap accommodates existing full-context reservation without bypassing Budget. Evaluate all eight outcomes and any harm to original PASS cases before considering production.

If that compromise is accepted and qualifies, production integration and the already planned independent confirmation, sequential recovery and 30 ordinary UI turns remain required. The gameplay allocation of 110 calls would cover 90 base calls for 30 three-call turns plus its existing 15 background/5 player-visible recovery reserve; no silent increase. This is a proposed separately approved flow, **not an implemented production default, guaranteed cure, or completed #259**. Low recognized more meaning here, but a full successful low pipeline still has not been demonstrated; the data do not prove that it could never work after further binding improvements.

## Approved follow-up result

On 2026-11-17 the separately approved eight-call revision experiment was executed using all eight corrected/off first responses. See [the revision result](consequences259-revision.md). It did not qualify; this historical report and its original costs/results remain unchanged.
