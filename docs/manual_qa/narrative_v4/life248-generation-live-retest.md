# Life248 generation recovery: real DeepSeek retest

**Follow-up correction:** the Off world's uncompleted semantic review and rejected
optional creative proposal are not launch blockers. Starting with warnings is an
intended product flow, not a manufactured PASS. The subsequent free production UI
check successfully confirmed this exact 11-character world and reloaded its game
save. See [launch, structural fixes and next Live QA](life248-launch-and-repair.md).
The observations below remain the historical record of the earlier run; its
decision not to launch was a QA limitation, not a technical launch failure.

2026-11-08 · PR #248 · tested HEAD `96448e0f94ffaa982b1b88b9da3267fe10e08a54`.
Follow-up to [the fixes and free regressions](life248-generation-recovery.md).
**Recovery fixes worked, but neither creation pipeline completed. Lifecycle
gameplay remains NOT TESTED.** No product code changed during this retest.

## Execution and accounting

Production FastAPI, real `deepseek-flash`, existing Budget and ledger. Original
Off and Low checkpoints were copied independently; only one QA server ran at a
time. Startup recovery and Runtime checks remained enabled. The Off candidate
kept its original Off configuration; Low world generation and its structural
repairs used its pinned Low configuration. No ordinary Narrative/Extraction call
was made; their Off settings were unchanged.

Authorization was **10 new calls / $1.00**. Existing ledger baseline remained 205;
the cumulative configuration was 198 calls / 2,385,478,300 nano-USD, exactly the
prior usage plus the new allowance. No new budget system or authorization table.
New reservations 394–401: **8 calls, 79,114 input tokens, 55,729 completion tokens,
$0.090609 conservative** at $0.30/M input and $1.20/M output. All receipts settled;
no unknown reserves. Two calls / $0.909391 remain unspent, not a renewed allowance.
Historical ledger rows were unchanged. Including the earlier four lifecycle
attempts, this campaign has used 12 calls / $0.1567173 conservative.

| Case / stage | Thinking | Input | Completion | Reasoning subset | Seconds | Conservative USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Off / portrait repair | Off | 4,063 | 55 | 0 | 2.16 | 0.0012849 |
| Off / retained Knowledge repair | Off | 2,995 | 215 | 0 | 4.78 | 0.0011565 |
| Off / creative proposal | Off | 32,982 | 5,221 | 0 | 99.21 | 0.0161598 |
| Off / creative repair 1 | Off | 11,358 | 51 | 0 | 1.92 | 0.0034686 |
| Off / creative repair 2 | Off | 11,366 | 51 | 0 | 1.85 | 0.0034710 |
| Low / world recovery | Low | 10,957 | 47,473 | 21,976 | 659.09 | 0.0602547 |
| Low / structural repair 1 | Low | 2,315 | 546 | 497 | 5.67 | 0.0013497 |
| Low / structural repair 2 | Low | 3,078 | 2,117 | 2,024 | 16.94 | 0.0034638 |

Each provider attempt finished with `stop`; this does not imply semantic success.
No successful response was regenerated. Only the existing two-attempt repair
loops ran. No full CI, new PR, merge, LTA or campaign run.

## Results

| Check | Status | Evidence |
| --- | --- | --- |
| Off: recover original Knowledge / portrait blockers | PASS | Same retained world; two real repairs; all 11 characters retained; structural validation passes |
| Low: Resume after cached OutputLimitReached | PASS | Same job dispatches changed policy, receives complete JSON; old 24k response retained |
| Off: complete creation pipeline | BLOCKED | Creative proposal has invalid Knowledge provenance; two empty corrections |
| Low: complete creation pipeline | BLOCKED | Repair exposes unsupported Motivation dependency keys and cannot address them |
| Historical evidence and SQLite reload | PASS | Original responses, request records and document versions preserved; both source SHA256 checks match; both SQLite integrity checks are `ok`; reloaded jobs/versions match |
| Creation UI | PASS for observed error/recovery presentation | Both display retained results; no JS errors or horizontal overflow at 1440×1000 |
| Confirm / playable save / opening Narrative | NOT TESTED | Creation acceptance gate did not pass; no warning-based start was used to manufacture a success |
| Relationships, marriage, divorce, pregnancy, birth, death, aging, personality development | NOT TESTED | No gameplay or LTA occurred |

Low UI disables Start Story. Off UI offers Start Story with an explicit warning
that semantic review is incomplete: its base candidate is structurally valid,
while its creative addition was rejected. Thus Off is not an absolute inability
to launch; it is a failed end-to-end preparation check. We did not accept that
warning as proof of semantic readiness. A browser probe initially used an exact
accessible-name locator that did not match the disabled Low button; the QA locator
was corrected and the check rerun for free. This was not a product failure.

## New confirmed blockers

**Off creative provenance and narrow correction scope.** The proposal adds
`know_pasha_quarrel`, with `fact_id=fact_kovalev_marriage_history` and
`source_event_id=event_kovalev_quarrel`. The Event lists Pasha as a witness but has
empty `fact_ids`; its text describes overhearing a quarrel, not learning the
parents' marriage history. Runtime correctly rejects it. Correction is limited
to `/changes/18/value/source_event_id`; Event/Fact changes and dropping this new
operation are unavailable. Both real repair replies contain empty `patches` and
`drop_indices`. The rejected proposal did not mutate the valid base candidate.

This is world creative preparation, not ordinary Extraction. Exact saved-response
replay reproduces the provenance diagnostic, narrow scope and empty-correction
rejection. We have not proved that every possible source-field value must fail;
clearing the source would not establish semantic correctness.

**Low contract/Runtime mismatch plus hidden repair diagnostics.** The world
response uses `dependencies: {"facts": [...]}` in five NPC goals: Valentina,
Sergey, Kirill, Larisa and Petr. The generated schema accepts arbitrary dependency
keys, but `runtime_v3.lifecycle.DEPENDENCIES` permits only `characters`, `roles`,
`organizations`. Legacy salvage removes these unsupported dependencies; the
draft's lossless check correctly prevents acceptance. The goal text/status itself
is retained: the observed loss is specifically the fact dependencies.

Earlier provenance diagnostics concern `or_larisa_marina.fact_id` and
`role_marina.fact_id`: the referenced café-ownership Fact names only Larisa,
not Marina. Both model repairs set these optional links to null. Trial validation
then exposes five `lossy_normalization` errors. The trial is rejected; the second
repair retains the old scope and repeats the same two link edits. Neither reply
can correct the newly exposed goal dependencies. Exact real replies reproduce
this chain offline; no corrected control JSON was substituted for the live result.

There is also pre-existing semantic uncertainty in the Off candidate: it assigns
Alexey a decision goal, breakfast intention and emotion, with invented evidence
of a conversation with his mother, despite the brief reserving his future choices
and feelings to the player. This was present before this retest, not introduced
by the new repairs. Structural validity alone does not resolve it.

## Settings and next work

The Low world call used context **131,072**, max_tokens **64,000**, and returned
79,026 visible characters: 21,976 reasoning tokens plus 25,497 non-reasoning
completion tokens. The complete response took about **11 minutes**. This validates
changed-policy recovery on real DeepSeek and shows 64k was sufficient for this
response; it does not establish the profile as generally reliable or guarantee
space for JSON. The prior 24k failure remains in the journal. Separate visible
output reservation is still unsupported by the documented API.

Proposed next fixes, **not implemented during this experiment**:

1. Align the world-generation dependency schema and early typed diagnostics with
   Runtime's actual supported keys. Preserve valid semantic links; do not remove
   nonempty metadata silently or broaden Runtime semantics just to pass QA.
2. Surface independent intrinsic failures before repair, or carry newly exposed
   diagnostics into a bounded scope. Avoid asking the same old-scope repair to
   resolve a different downstream error.
3. For new creative proposals, permit a dependency-checked correction of the
   inconsistent Event/Fact/Knowledge set, or explicit rejection of the offending
   new operation. Keep accepted canon and unrelated proposal entries protected.
4. Add the two exact-response regression cases, then recover these retained
   candidates/proposals. No fresh random world is needed. Complete semantic review
   and canonical acceptance before resuming the lifecycle game.

Raw provider streams, messages, receipts, journals, diagnostics, first replies,
repairs, SQLite before/after/final copies, UI screenshots and free reproductions
are retained outside git under `/workspace/work/life248-recovery-live`.
The two user-supplied archives and source checkpoints remain unchanged.
Neither generation pipeline, Narrative playability nor Stage C is certified.

Evidence archive: `life248-recovery-live-evidence-20261108.tar.gz`, 5,306,367 bytes.
SHA256: `b8e3da0e9750fcaf50997b577d73671eacced62e643b4a8cedbc21f44cdd807e`.
