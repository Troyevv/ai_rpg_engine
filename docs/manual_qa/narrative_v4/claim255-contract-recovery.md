# #255 — Extraction/6 structural contract and claim repair

2026-11-15. Existing PR #248, implementation based on `d32dc9d5cb151942401bd9d598870a6269d0aa61`. **Free verification only; live recovery and long-session acceptance remain NOT TESTED on this change.** No new world, Narrative regeneration, migration, provider call, additional repair, merge or issue closure.

## Confirmed original failure

Source: `work/issue255-playtest-resume/session-final.sqlite`, job `edab5c5ba7244f35ac556a6fd00ff13d`, revision 49. Real first Extraction `a872e6e5bb144a3f9b00cd635de41209` / reservation 666 and repair `de2aaf41ca014bb693802eb1c75bd927` / 667 both completed. Their exact response strings, hashes, Narrative, input and before-state are retained in `tests/fixtures/issue255/perceived-fact-live.json`; bulk streams/SQLite stay outside Git.

Both information steps (`step_45_03`, `step_45_05`) supplied `fact={subject_id,predicate,value}` without `text`, rather than `fact={text,claim:{subject_id,predicate,value}}`. The actual old provider schema allowed arbitrary nested objects; `PerceivedClaim.coherent` and canonical Fact did not. The original repair repeated these broken claims and added top-level Facts without linking `claim.fact_id`. That did not repair their meaning or structure. Both errors were already collected: this was **not** a first-error-only, transport, Budget or narrative-warning failure.

## Contract audit and fixes

The v6 projection now derives Fact fields and nested Claim bounds from `Fact.model_json_schema()`, including existing secrecy fields. It uses the same projected schema for provider transport, local jsonschema validation and targeted repair. Canonical identity/origin remain compiler/Runtime owned. New inline Facts require nonblank `text`; a whole existing assertion can instead use `fact_id`, exclusively, without creating a duplicate. No text, link or perception is invented. The shared v1–v5 `PerceivedClaim` model is deliberately not retyped: the stricter structural projection is confined to v6, avoiding a reinterpretation of recorded legacy jobs.

| Confirmed structural gap | Production owner / path | Minimal v6 correction |
| --- | --- | --- |
| Arbitrary inline Fact versus canonical Fact and nonempty text | `raw.PerceivedClaim`, `compile_semantic`, Fact/Knowledge resolver | Canonical Fact/Claim schema, required nonblank inline text; explicit exclusive new Fact/existing fact_id |
| Perceiver duplicates, negative revisions, rumor with known status | `PerceivedClaim.coherent`; ordinary/background information | `uniqueItems`, nonnegative revision values, rumor → suspected |
| Chronology kind allowed missing or contradictory basis fields | `ChronologyClaim.coherent` → chronology resolver | event_elapsed requires event_id/elapsed_days only; current_calendar requires date or weekday without event basis |
| Departure with endpoint, completed arrival without endpoint; deferred/nonperformed interaction with achieved targets | Scene compiler | Conditional endpoint/null and empty achieved-target requirements; corresponding redundant local structural checks removed |
| Naming decision with no components/delegation, blank/oversized components, cancellation without target | `reproduction._naming` | Expose existing component bounds, proposal delegation alternative and cancellation target shape |
| Empty possession update, introduce without identity, invalid status or relocate changing ownership | `possessions._transition`, `SignificantPossession` | Nonempty update, introduce name/kind, existing status enum, relocate location-only; other operations cannot rename identity |
| Appearance category/kind mismatch, removal with text, missing established description or invalid condition-reference shape | `appearance.apply` / existing KINDS | Reuse KINDS; expose existing operation/text and condition-ID requirements |
| Targeted repair schema allowed arbitrary replacement IDs | `scene_repair` | Replacement IDs constrained to actual scope; claim-only repairs retain step fields, count and independent claims |

These constraints describe existing declared domain consequences, not new requirements on literary detail. The patch adds no universal validator and does not move state-dependent business logic into JSON Schema. Optional annotations retain their isolation policy. Warnings do not become hard errors.

### Checks intentionally remaining with Runtime

- Actor authority, exact input provenance, contact/presence, route feasibility, camera identity, temporal boundaries and contradictions with accepted history require state/input.
- Existing Fact identity, whether its **whole** assertion was perceived, secrecy/POV, witness authority, and Event → Fact → Knowledge provenance cannot be inferred from shape.
- `expected_revisions` keys must belong to the declared perceivers (a cross-field set relation); actual revisions require state. Existing validation remains.
- New versus partial updates for roles, residence, conditions, life and motivations depend on whether the canonical ID exists. Requiring complete new records on every update would reject legitimate closures. Promotions retain existing pending-review behavior.
- TemporalValue basis alternatives and numeric bounds already come from its model schema. Ordinary/background/LTA clock ownership is intentionally different.
- Birth/Service/Name claims already expose their field types/bounds. Biological time, canonical sex, consent, source speaker, witnesses, duplicate transitions and legal decision makers remain domain checks. No weaker acceptance or forced events.
- Possession transitions depend on prior owner/holder/status; appearance depends on existing identity/revision and accepted evidence. Those owners are unchanged.

## Addressed diagnostics and bounded repair

The existing jsonschema validator now reports errors from the matching step-kind union arm and actual nullable Fact branch. Each nested claim diagnostic retains the step ID, step index, claim index, field path and reason, with contractual options (new Fact text/structured claim, or an explicit reference to the same existing assertion).

For the real response this includes both `scene_steps[2].claims[0].fact.text` and `scene_steps[4].claims[0].fact.text`, plus both misplaced structured-claim field errors, in **one** repair feedback. Unrelated union errors are not substituted for these paths. Each missing required field retains its own reason; three missing structured-Claim fields produce three diagnostics, not a nine-row cross-product.

When diagnostics address only claims, the existing repair scope records their indexes. Sharing an actor/location no longer grants permission to rewrite independent steps. Repair cannot drop a claim, alter unaffected claims/step text, add steps or withdraw consequences. A new top-level Fact must actually be referenced by a repaired claim; merely adding unrelated valid Facts cannot satisfy repair. Existing candidate-hash binding, compiler checks and atomic commit remain. Four additional malformed-repair controls (null claim, nonstring fact_id, null Facts section/item) exposed parser exceptions in the new scope guard; the guard now leaves these as structural diagnostics. They are implementation regressions caught offline, not newly observed DeepSeek failures.

## Separate input-provenance finding

Correcting only the two Facts exposes another error already present in the real first response: two `input_source.quote` values add outer opening/closing quotation marks at boundaries not present in the actual input. The existing `player_action_source_invalid` check rejects them. This is input-dependent provenance, **not another hidden required JSON field**. No product quote rewriting, substring-rule relaxation or automatic input invention is added.

The Fact-only control explicitly asserts this remaining rejection. A second, labelled authored control removes just those extra quote delimiters and verifies the resulting strings occur in the original input. It is a test control, **not a successful DeepSeek response**. A real recovery must still produce valid provenance itself; a second failure after its one bounded repair must stop the session.

## Free production replay and regressions

Isolated evidence: `/workspace/work/issue255-claim-free/` (final-code replay also in its `final/` subdirectory) (script, original rejection diagnostics, projected transport schema, labelled control, jobs/requests, before/after, working and accepted SQLite copies). Original source SHA256 remains `fe4991bdcf0373cdf4c86c3d9e4ecb6601f0fa813790df06e9093909f11c6454`.

- Both original real responses replayed unchanged and rejected; original candidate hash retained.
- One authored repair corrects both claims and compiles without changing independent steps, choices or Narrative. Existing-fact reference separately resolves without duplication.
- Production FastAPI Retry on a copy of the original SQLite uses the **same** Narrative, before-state, revision context and memory; only provider IO is replaced by the explicit control. It commits two Facts and two Alexey Knowledge acquisitions with source Events. Prior History is preserved.
- Cold production reload equals the saved snapshot; rollback restores the complete before-state. Source SQLite untouched; no second server on the same database.
- Integration test exercises one initial Extraction plus **one** bounded repair for both original Fact errors, preserving independent consequences and saving/reloading. It labels the separate corrected quote evidence as authored input control.
- SDK transport test verifies the exact `responses.create(text.format.schema=...)` envelope for both initial Extraction and repair; schemas validate under Draft 2020-12. This is free transport-contract coverage, **not evidence of acceptance by the real provider**.
- v1–v5 projections are unchanged; existing recorded Retry/regeneration, background/LTA, agency, timing, reproduction and provider-recovery tests are included. No SQLite/API migration or Budget changes.

Broader focused result: **332 passed in 110.36s**. After the final missing-field diagnostic correction, the four directly affected suites passed again: **103 passed in 25.31s** (`test_claim_contract255`, `test_scene_steps255`, `test_scene_error_collection255`, `test_structured_extraction255`). `git diff --check` passed.

Command (final focused run):

```bash
python -m pytest -q tests/test_claim_contract255.py tests/test_scene_steps255.py tests/test_scene_error_collection255.py tests/test_structured_extraction255.py tests/test_extraction_semantics248.py tests/test_integrated_repair247.py tests/test_request_responses.py tests/test_reproduction.py tests/test_birth_sex.py tests/test_background_time.py tests/test_long_term_advance.py tests/test_event_chronology.py tests/test_repair_policy.py tests/test_provider_recovery255.py
```

Full CI results for the implementing commit are linked in PR #248 after completion, separately from earlier green runs. This report does not claim full CI or live acceptance before those checks finish.

## Paid recovery proposal (not executed)

Keep reservation 665's full conservative charge and actual receipts 666/667 unchanged. No new ledger rows/calls were created for this free stage. The previous two real extractions used 44,009 input / 2,936 output tokens, conservative cost $0.0167259; this is an estimate source, not a new authorization.

Request a separate short stage: **at most 2 DeepSeek Flash calls / $0.70 conservative ceiling**, thinking off, same unfinished photo-exhibition Narrative, one manual Retry with its existing single repair if required. Expected receipt cost is around $0.02; the larger ceiling accommodates the existing worst-case reservation (~$0.324 per call), not invented usage. Unknown outcomes keep their reserve and stop pending safe accounting. Stop on failure or either cap. Do not regenerate Narrative or edit provider responses.

If real recovery succeeds, propose continuation through production UI to 30–50 total natural turns (four already saved), under a separately explicit total allowance. The free control cannot establish that this session is playable. #255 remains open and PR #248 unmerged.
