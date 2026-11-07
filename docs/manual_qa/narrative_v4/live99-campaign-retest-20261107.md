# #99 — post-merge Live Gameplay retest and campaign continuation

Refs #99. **In progress; Stage C is not complete.** No product Runtime/frontend
changes, no merge, no automatic closure of #99.

Baseline master: `40bc3da23b44a025954a6b050fe71a08a2ce4a2d` (merged #230, after
#219). Ancestry and implementation include #220–#223/#226 and #231–#233.
Live QA code starts at `a37d2d54a066dcd90aac076aaf53167757b77b17`.

## Preservation and budget

Existing Stage A/B/C archives and SQLite are present in this workspace, verified
by hashes; workspace existence is not durable publication. This run copies the
original #219 checkpoints into an isolated SQLite database, preserves #230's
database/variants separately, and uses explicit UI rollback for Campaign/Crisis.
Family uses separate copies of the existing #78 near-due fixture; historical
contradictory birth records are not rewritten.

The existing #230 authorization is linked, **not renewed**: baseline 205 calls /
124 actions, already spent peak/cold $0.1856862. Start of this run: historical
247 calls / 152 actions / 0 unknown outcomes. Remaining allowance **$1.8143138**,
92 remaining action reservations; the plan has 69 operations including free
abandon, rollback and protagonist transitions. Retest and continuation share the
same cap. Unknown paid outcomes stop every linked run; resume cannot repay a
completed operation or grant another allowance.

DeepSeek API key presence, model availability and balance were checked without
printing credentials. Balance before: **16.59 CNY**, USD balance 0. Official
[pricing](https://api-docs.deepseek.com/quick_start/pricing/) confirmed Flash
peak/cold USD $0.30/M input, $1.20/M output (CNY 2/M and 8/M respectively), 1M
context. This remaining cap corresponds to at most CNY 12.095426 under those
peak/cold tariffs, below the provider balance; this is a tariff comparison, not
a currency exchange-rate claim. Guard reserves the full provider context window
before each dispatch, including repair and LTA. Actual usage estimates and the
conservative ledger remain distinct.

## Targeted retest — initial findings

- Crisis/#232: chosen addressee remains Vera, but repair removes the absent Vera
  from Event participants while preserving `player_action.outcome=completed`.
  Exact free replay confirms the inconsistency; completion-flag control rejects
  it. **P2 [#237](https://github.com/Troyevv/ai_rpg_engine/issues/237)**; Crisis held.
  No new Knowledge acquisition or teleportation observed.
- Social/#233: coherent explicit consent scene fails because Event full-input
  evidence differs from its referenced action quote; repair repeats the mismatch.
  Exact replay rejects; changing only the quote in a diagnostic control passes.
  Refusal is atomic. **P2 [#238](https://github.com/Troyevv/ai_rpg_engine/issues/238)**;
  Social held. This blocks live confirmation of #233; it is not its old missing
  continuity-beat evidence failure.
- Family pregnancy_due: real LTA stops at minute 1980, requested 20700; no overshoot.
  Local birth, remote birth/Knowledge and remaining groups are still running.

## Verification and evidence status

- QA pytest: 65 passed. Integrated-fix targeted pytest: 170 passed.
- Production FastAPI / Chromium preflight: 6 groups × desktop/mobile passed.
- Narrative/Extraction/raw streams, state before/after, diagnostics, usage,
  History and checkpoints are captured by the existing harness after each action.
- Embedding retrieval uses the existing structural fallback (`OSError`); no live
  result is claimed for active embedding retrieval.
- Durable archive URLs and final counts/CI will be added after packaging and
  download/hash verification. Local workspace paths are not download links.

The engine is **not yet confirmed ready for a long user campaign**. Current
confirmed blockers are tracked separately; independent groups continue. No
claim of completed Stage C or #99 is made.
