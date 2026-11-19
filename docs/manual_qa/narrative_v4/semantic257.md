# #257: frozen comparison before selecting a production change

Baseline: `4424a9475162817fa7442059d6b2a3c132490c30`, PR #248. Last genuine acceptance **FAILED on 2026-11-15**: recovery saved both travellers on Lenin Street despite unchanged prose ending at the porch of a home on Lesnaya. [Original report](https://github.com/Troyevv/ai_rpg_engine/pull/248#issuecomment-6897991118). This supersedes any earlier “live acceptance not yet performed” wording. No solution has been selected; no new paid calls or production changes in this preparation.

## Evidence and frozen inputs

Both source archives were found and their complete SHA256 verified against Issue #257:

- `issue256-recovery-live-evidence-20261115.tar.gz`: 64,507,946 bytes, `1004f8666cc360e76fc6960ed5b8a3dff36f6076647f04e4e1c53b868ba382e5`.
- `issue255-claim-live-evidence-20261115.tar.gz`: 95,557,322 bytes, `6736c9c23e8751190c0b693a519cf2fa3ba0ac0f8d3bdf4aa45281817b095b30`.

`devtools/issue257/prepare.py WORK NEW_OUTPUT` freezes the original porch, river walk, river conversation, cafe, and Olga background. The four foreground contexts use #256's explicitly authored production recovery predecessor setup. This is **not real campaign recovery**. Both foreground before and memory_before are recorded. Background gets its own observer projection of the corrected predecessor; its original narrative and authority boundaries remain. It does not reuse an ordinary context. Historical requests remain in the original archives; these normalized comparison requests are not labelled identical historical replay.

Semantic expectations are in `EXPECTATIONS` and `cases.json`, fixed before paid evaluation. Four authored regressions adapted from existing #255 tests cover partial secret disclosure, significant unauthorized refusal, authorized refusal, and a narrator calendar jump without time skip. Six authored holdouts cover a reached known street, similar names, new exterior landmark, unstarted journey, separated companions, and local departure/private speech in a medieval fantasy castle. Holdouts are evaluation inputs only, never prompt examples. If a holdout informs a redesign, replace it with a new independent control.

Accept alternate IDs and appropriate location granularity when they preserve outside/inside, real traveller set, endpoint identity, perception, information sources and unchosen decisions. Never require a predetermined porch/river ID. A correct textual summary cannot excuse contradictory canonical routes. Inspect all significant consequences after resolving; `resolved` is explicitly `REQUIRES_INDEPENDENT_REVIEW`. After selecting a solution, production commit/reload and recovery must establish persistence separately.

Generated 15-case bundle: `/workspace/work/issue257-preparation/frozen-v4/`. It contains snapshot/input/Narrative/message/wire-schema hashes, UTF-8 Narrative hashes, and immutable expected outcomes. Bulk snapshots and source archives stay outside git. The preparer fails if its destination exists. The original suffix recovery controls are reusable via `devtools/issue256/replay.py`; they remain explicitly authored, never provider successes.

## Minimal hypotheses

| Arm | Model | Context/schema | Thinking | Temperature/output |
|---|---|---|---|---|
| A | `deepseek-flash` | Current v7 projection and schema | off | 0.1 / 8192 |
| B | `deepseek-flash` | Same schema; existing lossless `compact_choice_context` applied before hard-limit pressure | off | 0.1 / 8192 |
| C | `deepseek-v4-pro` | Exactly A messages and schema | off | 0.1 / 8192 |

All use existing `responses_json_schema` transport and 131072 configured context. Temperature is the actual production Extraction value, not the 0.8 Narrative setting. The adapter sends the schema once through Responses and removes its text block. C changes only model ID. Initial and repair retain each arm's profile.

B replaces only identical values already present in GM state with the existing `state_ref` representation, preserving the actor-owned projection. It adds the existing reference interpretation instruction. It removes no identities, locations, aliases, secrets, dates, domain capabilities or choices. Four original foreground requests shrink about 5–6% in bytes; Olga A/B are identical, explicitly a repeatability control. A modest reduction is not evidence of overload or improved semantics. No new endpoint interface, context domain pruning, critic, fallback or Runtime gate is proposed yet.

`compare.run` accepts an already Budget-wrapped provider and mandatory evidence recorder. It uses current SceneCandidate/StateResolver, the existing patch scope/schema, and at most one repair for actual structural diagnostics. It preserves the frozen context for repair, adds production repair instructions and schema, and never supplies the semantic oracle. Its resolved state/history are comparison outputs, not committed campaign saves. Production persistence follows selection; the comparison must not be presented as gameplay.

## Free checks performed

- Complete archive hashes verified; latest ledger reservation 699, no open unknown outcomes. Old full reserve charges remain intact.
- Source first response + source repair replayed using current compiler/Resolver: two recorded responses, accepted wrong `loc_street_lenina` for both actors. No provider call and no claim that Python detects that literary mismatch.
- All 15 case A/B/C schemas validated, contexts within the unchanged hard budget; A/C messages identical and B schemas identical.
- Lossless projection test expands references back to the exact actor-owned data, including no extra secret Knowledge; original messages remain unchanged.
- `RPG_SEMANTIC_ENABLED=0 python -m pytest -q tests/test_experiment257.py tests/test_spatial256.py tests/test_spatial256_recovery.py tests/test_claim_contract255.py`: **56 passed**, 9.28 s.
- Full CI is deferred until a confirmed production change stabilizes. Existing green baseline CI does not establish #257 acceptance.

## Proposed paid phase — NOT AUTHORIZED / NOT RUN

Official pricing checked 2026-11-15: https://api-docs.deepseek.com/quick_start/pricing . Authenticated model-list GET exposes `deepseek-flash` and `deepseek-v4-pro`; repository transport supports both. Official table lists Responses, non-thinking mode, 1M context for both. Real full-schema Pro support is still a smoke question, not established by the model list.

1. First C call on `authorized_refusal` is the provider smoke and also its first corpus result. At most one repair; no extra duplicate smoke. On unsupported provider parameters, stop C and report partial results.
2. Nine primary cases (five originals + four regressions), one first response in A/B/C: **27 initial, at most 27 repairs**. Rotate ABC/BCA/CAB by case; the explicit first C smoke is the exception. One arm's semantic failure does not stop independent cases.
3. Confirmation: A and the provisionally selected B/C on three fixed originals (porch, river, cafe) and six holdouts: **18 initial, at most 18 repairs**. This is a predeclared repeat, not reroll-to-PASS. If no candidate resolves the critical cases, do not spend this confirmation allowance automatically or change production defaults; report the specific next experiment.

**Ceiling: 90 new calls / $6.00 conservative**, including smoke and all allowed repair. No D, sequential campaign recovery, or gameplay included. Expected actual expense roughly $0.6–$2.0 from the recent 48,113-input/2,122-output two-call receipt, allowing variation for larger scenes. Approximate duration 30–60 minutes including manual semantic review; not a latency guarantee.

Peak/cold token prices per million: Flash $0.30 input/$1.20 output; Pro $1.32/$3.96. Pro full pre-dispatch reserve at 1,048,576 input + 8192 output is **$1.41656064**. Use the existing Budget and ledger, sequentially; configure the stage's conservative accounting at Pro rates for every new reservation/receipt, with cumulative limits anchored to existing ledger totals. This deliberately overcharges Flash in the guard; report actual per-model conservative costs separately. Existing historical rows/unknown resolution records must not be modified or counted as new calls. No new tables/authorization subsystem. An unresolved stream retains its full reserve and stops dispatch. The money bound may stop the stage before 90 calls.

Before dispatch, freeze the exact schedule, verify current HEAD and hashes, set existing cumulative limits from the then-current ledger, and verify guard behavior using a temporary ledger. No paid phase can start from this document alone: explicit user approval is required.

## Decision and remaining work

Rank meaningful false saves/lost outcomes first, false refusals next, then latency/cost/complexity. Record first response separately from repair, all receipts, complete latency, and independent semantic verdicts. A single good reply or small equal sample is not proof of superiority. If B/C succeeds, integrate the smallest demonstrated change into current owners with recorded profile/projection compatibility; do not implement a destination redesign merely because the issue describes it. If all fail, preserve results and justify a bounded D experiment before changing wire semantics.

After selection: production initial/repair/background/LTA integration, legacy v1–v7 and full CI; separately authorized unchanged-prose recovery 9–12 plus Olga; cold reload and next UI turn; separately bounded ordinary play to 30–50 total actual player inputs. Until those succeed, #255/#256/#257 remain unaccepted and PR #248 remains unmerged.
