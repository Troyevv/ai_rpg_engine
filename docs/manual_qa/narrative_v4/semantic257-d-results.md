# #257: destination experiment D — not selected for production

2026-11-15. Tested HEAD `bbd66dfbfa6c817b942522cb972955e92a84f432`; unchanged production implementation `4424a94`. This is the separately authorized destination experiment following [A/B/C](semantic257-results.md), **not campaign recovery or gameplay**.

**D does not pass the critical cases.** It improves the porch destination in this sample, but still loses information and chronology, and cannot complete the river repair. There is no qualified production candidate. The conditional confirmation series and six holdouts are NOT RUN; production integration, sequential recovery and gameplay remain blocked. Issue #257 is not accepted. No defaults, Runtime rules, original saves or historical snapshots changed.

## Scope and accounting

Authorization: at most **54 new Flash/off calls / $1.50**, including a conditional confirmation series. Actual first series: **9 candidates, 12 calls**, reservations **744–755**, **$0.09892680 conservative**. All streams completed with real usage receipts and zero reasoning tokens. No unknown new outcome remains; all 743 historical reservation rows match the pre-run ledger copy. No extra repair or reroll occurred.

The existing Budget used Flash cold/peak rates of $0.30/$1.20 per million input/output tokens, without cache discounts. Existing phase ceilings were configured from 538 historical phase calls / $4.4041512 to 592 / $5.9041512 for this authorization. The full unknown-outcome reserve remained $0.3244032. This is configuration of the existing guard, not a new budget subsystem. The unused allowance is not permission to run a failed candidate's confirmation or gameplay.

D replaces movement endpoint plus a separate new-place declaration with one destination: `{existing_id}` or `{name, anchor_id, relation}`. The QA-only adapter creates an ordinary Location/ID and invokes the unchanged v7 compiler, Resolver and patch protocol. It does not infer meaning, address, parentage or Knowledge. No production module imports the prototype.

All nine Narrative/input/snapshot values and A messages were checked against the previous frozen series. A below is the **already recorded control**, not a fresh concurrent repeat. D uses Flash/off, Responses JSON Schema, temperature 0.1 and max output 8192. Only the destination schema/instructions and necessary adapter differ. The experiment includes four explicitly authored regression narratives alongside five original spatial/background cases; corrected predecessor setup is also explicitly authored, not a recovered live campaign.

## Independent semantic assessment

| Case | Recorded A | D first response | D after sole repair / final |
|---|---|---|---|
| Original porch | FAIL: Lenin Street | Correct new exterior entrance anchored to Galina's home; missing player movement source | **PASS**: source added, both at exterior entrance; river remains a proposal |
| Original river walk | FAIL: remains at porch | Correct new shore and both travellers, but incompatible action targets; conversation placed after arrival | **FAIL**: repair repeats incompatible values; no accepted outcome |
| Original river conversation | PASS | Correct shore, player interactions, two disclosures with sources | **PASS**, no repair |
| Original Olga background | PASS after repair | Local room exit; home address retained; protected heroes and world time unchanged; no Knowledge broadcast | **PASS**, no repair |
| Original cafe | FAIL: information lost | Both reach cafe, entry question open; Tamara's after-closing work remains only in movement prose | **PARTIAL / FAIL**, no Knowledge acquisition, no repair triggered |
| Partial secret | FAIL: disclosure lost | Does not reveal full relationship secret, but omits the disclosed conversation with Nikolay from Knowledge | **FAIL**, structurally accepted, no repair |
| Unrequested refusal | FAIL: unauthorized refusal accepted | Attributes the Narrative's refusal quote to player input; source validation rejects it | **FAIL recognition**: repeats the false quote; blocked safely but no semantic reauthor |
| Authorized refusal | PASS | Correct explicit refusal and photograph action | **PASS**, no repair |
| Narrator calendar contradiction | PASS: correct refusal | Omits date claim; accepts contradictory prose while retaining old clock | **FAIL**, no repair |

The porch Location is `destination_e3e6568214b0ad53f6a2`, named “Крыльцо подъезда дома Галины Фёдоровны”, described as outside at the entrance, anchored to `loc_home_galina`; it is neither Lenin Street nor the shore. It does not acquire an inferred parent or street. Its single success establishes feasibility, not reliability on unseen geography.

River D supplies `intended_target_ids=[char_galina]` in the movement source. The unchanged compiler derives an empty `narrative_target_ids` for a movement, unlike an interaction. The Resolver reports `player_action_targets_inconsistent` at `scene_steps[0]`. The patch repeats the same values while claiming in its reason that it corrected them. The actual fields, not that claim, determine the result. The response also lacks `during_step_id` for the en-route disclosure; even removing the target inconsistency would not establish complete semantic acceptance. This experiment does not establish that target validation should be disabled or that companions should automatically become conversational addressees.

For the unrequested refusal, the supplied input is only “Рассматриваю фотографию на столе.” Both answers use “«Нет, не хочу»” as player evidence. Runtime correctly blocks that invalid source twice. This is safer than A's false acceptance, but it is not the required diagnosis that the Narrative made an unchosen decision and needs reauthoring. No arbitrary structural failure is counted as a semantic PASS.

Cafe and partial-secret before-states were checked against the frozen reference assessment: these are newly disclosed facts, not already-known information. Zero acquisitions here means lost consequences. Calendar D has no chronology claim at all, so structural validation cannot see the omitted contradiction. No oracle feedback was sent to obtain another answer.

## Measured results

| Metric | Recorded A | D |
|---|---:|---:|
| Semantically usable first outcome | 3/9 | 3/9 |
| Semantically usable final outcome | 4/9 | 4/9 |
| First response conforms to provider schema | 9/9 | 9/9 |
| Cases requiring repair | 3/9 | 3/9 |
| Correct final outcome among repaired cases | 1/3 | 1/3 |
| Resolver accepts final candidate | 8/9 | 7/9 |
| False acceptances | 5 | 3 |
| False refusal of a valid case | 0 | 1 (river) |
| Calls | 12 | 12 |
| Input tokens, including repair | 287502 | 290548 |
| Output tokens, including repair | 10303 | 9802 |
| Mean full case latency, seconds | 7.113 | 6.346 |
| Median full case latency, seconds | 7.083 | 4.710 |
| Mean provider-stream total, seconds | 6.783 | 6.025 |
| Median provider-stream total, seconds | 6.638 | 4.430 |
| Conservative expense, USD | 0.09861420 | 0.09892680 |
| Mean USD per call | 0.00821785 | 0.00824390 |
| Mean USD per case, including repair | 0.01095713 | 0.01099187 |

D's first-input tokens increased by 2664 across nine cases (**1.2055%**) versus A. All 12 D replies conform to their actual initial/repair schemas. Full latency includes repair, local validation and journaling; provider-stream latency includes transport/recording overhead. These are not server-only timing measurements.

False acceptance means acceptance by the real Resolver of an incorrect structured consequence, **not a campaign SQLite commit**. Three such outcomes remain in D. Smaller false-acceptance count is encouraging locally, but the new calendar failure, river rejection and unchanged 4/9 final score do not justify superiority or production adoption. Sample size is small, A is recorded, and no qualifying confirmation was run. Differences outside the destination field cannot be causally attributed to destination design from one stochastic response per case.

## Evidence, free checks and decision

Raw evidence: `work/issue257-d-live/`, with frozen input/schema hashes, first replies, patches, candidate/compiled records, diagnostics, before/after data, provider streams, receipts/timings and ledger before/after. Each candidate has its own isolated in-memory copy; no server shared an active game SQLite. Existing SQLite sources and authored setup are retained separately for reproducibility. The archive manifest identifies their provenance; they are not D campaign commits.

`transport-inputs.json` files are deterministic projections through the unchanged Responses adapter, not network packet captures. The adapter strips the textual schema message and sends the same schema in `text.format`, with reasoning effort `none`. Provider response IDs and terminal completion metadata are retained. No API keys are included.

Free post-run checks validated all 12 replies against recorded wire schemas, matched tokens to all 12 settled reservations, checked unchanged frozen inputs and all 743 historical reservations, and verified background address/clock/protected-character preservation. The original, recovery-boundary and authored-setup SQLite copies all passed integrity checks and match their source hashes. Minimal extracts of river/refusal initial and repaired steps confirm exact equality of the defective fields; these are retained as `minimized-original-failures.json`. A reporting helper initially looked for a nonexistent top-level `clock`; it was corrected to `meta.world_time` and rerun without a provider request. This QA helper error did not affect model input, responses, Runtime or expenditure.

The preceding frozen prototype profile was **60 passed** (11.97 s); no production code changed in this live phase, and full CI was not rerun. This report does not promote those authored tests into live acceptance. Commit/reload, rollback, variants, production UI and long-session playability of D are **NOT TESTED**.

**Decision:** retain current production, keep D an unselected prototype, stop at the predefined critical-case gate. The immediate unresolved problems are meaning coverage (information/date), correct agency recognition, and the movement source/addressee mismatch that repair fails to resolve. A further experiment must address these specific failures and be separately scoped; simply increasing retries, changing every contract again, or shipping D because one porch worked is unsupported. The next narrow design question is whether movement authority can avoid the irrelevant interaction-target field and whether the existing extraction instructions distinguish consequential disclosures from dialogue summaries clearly enough. That requires a frozen, bounded comparison, not a presumed cure or automatic rollout. No new architecture or paid campaign continuation is authorized by this result.

PR #248 stays draft; #255/#256/#257 remain open. There is no gameplay diary for this experiment because no game session was run.
