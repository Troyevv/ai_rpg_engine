# Issue #255 — engineering record

Baseline: PR #248 `cace6ed35ede13666142e55875b71f2a38c99ae8`.
Master inspected: `ee343deee65f627932c5a4f13aedbb41fa06be8f`.
Both AGENTS.md read. Work continues in the existing PR; no merge.

## Evidence boundary

The 43-line `diary-notes.md` uploaded 2026-11-14 was read in full.
It reports 16 ordinary inputs, 9 saved (one after manual Retry), 7 rejected,
8 manual Retries, 6 abandons and two separate phone exchanges. Four attempts
to leave the cafe failed. This is player observation, not captured provider IO.
No original SQLite/requests from THAT session were found in the available
workspace or the targeted Library search. Its execution SHA is not established.
The available acceptance252 archive belongs to an earlier session and cannot
substitute for these missing originals. No historical replay of the seven
latest failures is claimed. New controls are explicitly authored.

| Diary episode | Observed failure | Proven cause in that job |
|---|---|---|
| 1, 12 retry | Duplicate fact | Unknown: exact repeat vs ID/privacy conflict needs original JSON |
| 2, 10, 12 initial | RawTurnResult/final_scene | Unknown: envelope/null/truncation needs original response |
| 7 | Input action source | Unknown: exact input/action needed |
| 8 | Controlled actor missing | Unknown: actual route and camera needed |
| 11, 18 | Presence / rejected relocation | Unknown: original steps/order needed |

Confirmed code causes: legacy parse requires final_scene before compilation;
the model separately supplies routes, action provenance and final membership;
repair requests a whole replacement proposal. These are interface properties,
not a claim that one cause explains every historical failure.

Paid provider smoke and ordinary 30–50-turn UI playtest: **NOT RUN**.
No paid budget is authorized by this issue. Engineering controls cannot prove
model understanding or satisfy the live acceptance gate.

## Implemented engineering scope

Extraction/6 replaces the duplicated model fields with ordered `scene_steps`
and a non-derived `scene` description. The production compiler supplies IDs,
route origins/order, action provenance and final camera state. It reuses the
existing information/domain validators, rather than interpreting prose itself.
The owner/consumer and remaining invariant map is in [extraction6.md](extraction6.md).

Ordinary, background and LTA use the recorded contract. Old jobs keep v1–v5,
including Retry/regeneration; new turns in old saves use v6. Remote/1 is unchanged.
A parsed candidate receives one scoped repair; malformed roots receive one full
replacement. Changes outside scope, stale candidates and silent domain-record
withdrawals fail. Reinterpretations are logged; the whole candidate is compiled
from unchanged before. Request diagnostics retain the assembled candidate and
compiled records against the exact request ID, including unsuccessful attempts.
The normal atomic commit/revision/epoch/cancel boundaries remain authoritative.

The provider adapter implements documented Responses schema output for the
explicitly supported DeepSeek model names, with a recorded json_object path for
other/local models. Mocks verify payload shape, streaming/status/usage, cancellation
and no hidden fallback. Actual acceptance of the full schema by DeepSeek remains
**NOT RUN**, not a claim of strict-mode compatibility.

## Free verification record

- New v6 compiler/provider/production/repair/persistence suites: **59 passed**.
- New suites + context compaction + three affected legacy suites before the final
  audit additions: **149 passed**. Legacy assertions remain intact and request
  their original contract explicitly where they inspect that schema.
- Initial full backend run: **4013 passed, 1 skipped, 5 failed**. Three failures
  exposed an unintended legacy repair-intro change (fixed for v1–v5); two inspected
  the legacy schema through an unversioned context call (now explicitly v5).
  All five were included in the successful 149-test rerun. This initial run is
  not presented as a final full PASS.
- Frontend unit suite: **153 passed**; TypeScript/production build passed.
- Saturated 32K triplet context passes with full Narrative and reserved birth
  identities retained. No context/output limits were increased. The generic
  schema itself did not become smaller: compact JSON was 32,171 bytes (v5)
  versus 32,807 (v6); reduction is in duplicated response semantics, not a claimed
  measured token/cost win. Actual provider token/cost/latency comparison is unrun.
- Desktop/mobile local Playwright launch was blocked before any application
  assertion: Chromium `process_singleton_posix.cc: socket(): Operation not permitted`.
  The shared browser could not reach the isolated loopback server. This is an
  environment limitation, not UI PASS. A production UI test covers failed v6
  processing, reload, visible recovery, explicit Retry, save and next turn on
  both viewport projects; CI results must be checked separately.

All new provider responses are authored controls. The #254 domain controls use
original before/Narrative with an explicitly authored v6 representation; they
preserve Knowledge (6 acquisitions), Campaign (9), Social (0), and family birth
(10, same reserved child). They do not replay original DeepSeek v6 responses.

## Additional domain review

Code-path inspection exposed missing internal evidence defaults when bypassing
legacy parse. The default now belongs to RawTurnResult construction, and linked
domains inherit source metadata from the exact semantic node. Objective occurrence
steps can link Facts without inventing perceivers. Possession, appearance and
personal-development sources inherit the selected input once; their original
owner/identity/revision/outcome validators remain unchanged.

Partial new-NPC cards still enter pending review. Existing optional annotation
owners retain field-local rejection; a malformed optional annotation or choices
list cannot veto an independent accepted route. Existing domain size caps have
one shared owner and remain in the v6 projection.

Final repair review found that multiple indexed diagnostics in one section
overwrote the earlier record scope. The scope now unions those records while
keeping unaffected neighbors protected. The new regression plus the v6/provider
and context-compaction suites passed: **63 passed**.

Full CI #514 exposed a UI regression on desktop and mobile: the existing
Crisis/001 test could no longer see the reason for an agency refusal because
JobView had collapsed it into technical details. Narrative contradictions that
require a new scene now retain their actionable explanation in the alert;
ordinary processing errors keep technical details collapsed. The existing
browser assertions are unchanged; final-head CI must confirm the correction.

## Outstanding acceptance

1. Check final-head CI, including real desktop/mobile E2E.
2. Obtain a new paid budget before even a small full-schema provider smoke.
3. After that smoke, play 30–50 ordinary sequential turns as a player, continuing
   the last accepted Berezovsk state; keep the diary separate from investigation.
4. Latest 16-turn session originals remain unavailable. Do not replace its lost
   state with an older, more convenient world or call authored controls its replay.

Issue #255 and the live acceptance of #254 remain **NOT ACCEPTED** until these
explicit gates are resolved. No paid calls were made during this implementation.
