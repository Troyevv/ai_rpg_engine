# Life248: launch with warnings and retained-candidate repair

PR #248; baseline `c2134eb708962349dbe10760ed3a790592470d59`.
Source: `life248-recovery-live-evidence-20261108.tar.gz`, SHA256
`b8e3da0e9750fcaf50997b577d73671eacced62e643b4a8cedbc21f44cdd807e`.
No paid request was made during this work. Original evidence was not modified.

Five reduced regressions fail on the baseline and pass with the fixes; an
additional atomic Event/Fact/Knowledge regression passes. Final verification:
**556 passed, 1 skipped** in the owner suites (282.90s), plus **120 passed** in
generation/calendar/contact suites (57.99s). The earlier focused run was
136 passed, 1 skipped. The skip is the existing opt-in private-export test.

```sh
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_draft*.py tests/test_initial_draft_v4.py \
  tests/test_review170.py tests/test_review_protocol.py \
  tests/test_story_secrets*.py tests/test_secrets183.py \
  tests/test_secret_handoff181.py tests/test_editor_portrait_traits.py \
  tests/test_workshop_portraits.py tests/test_portrait_visual_age.py \
  tests/test_live99*.py tests/test_life248*.py tests/test_providers.py
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_generation_stability.py tests/test_generation_scenarios.py \
  tests/test_generation_calendar.py tests/test_contact_free_generation.py \
  tests/test_calendar_start_policy.py
```

Provider transports were controlled for these tests. The ordinary PR workflow
can run full CI after this tested change is pushed; no manual full rerun is needed.

## 1. Confirmed launch blockers

**Off: none observed.** On an isolated copy of the real saved Off candidate, the
production UI accepted the explicit warning acknowledgement, confirmed draft
version 15, created world/save 1, and opened the game screen with all 11 characters.
Browser reload and Repository reload preserve the snapshot; zero added provider
requests and no browser JavaScript errors. The first paid scene was not requested.
This was verified on the unchanged baseline, before product fixes.

**Unrepaired Low: structural blocker.** Unsupported Motivation dependencies and
invalid Fact references must be addressed. Warning acknowledgement must not bypass
these checks. Tests continue to validate the entire candidate before persistence.

The previous report's decision to wait for completed semantic review before even
trying Off launch was incorrect QA organization. Warnings are an intentional,
nonblocking product feature; a successful warning-based launch is a valid result.

## 2. Nonblocking semantic warnings

The Off draft has an incomplete semantic review and possible authored agency/
biography inconsistencies. These are recorded as concerns, not hard launch errors.
The user can acknowledge them through the existing confirmation flow. No new
warning gate was added, and the confirmation contract was not changed.

History audit reports five `history_provenance_incomplete` entries for initial
Knowledge. Canonical knowledge is retained; this is not a failed save/reload. It
requires observation during gameplay rather than inventing historical Events.

## 3. Optional creative preparation

The saved Off proposal has an invalid Event → Fact → Knowledge link and two empty
corrections. Validation correctly rejects the complete proposal atomically. The
base world contains none of its rejected Knowledge/Event/Fact records.

Previously that recorded rejection escaped the preparation pipeline as a fatal
job error. The pipeline now retains the structurally valid base candidate and
continues its existing review/save stages. A visible author warning describes the
unaccepted optional addition. Original responses, corrections and diagnostics
remain intact. Transport interruptions, unknown outcomes, cancellation and budget
failures still stop dispatch; invalid base worlds cannot use this fallback.

An atomic proposal regression checks that an incomplete Event/Fact/Knowledge set
changes nothing, while a coherent linked set is accepted together. The scope was
not widened to arbitrary edits of accepted canon. Failure of an optional addition
no longer requires accepting its erroneous provenance to complete preparation.

## 4. Structural generation and bounded repair

The generation schema now exposes only Runtime-supported Motivation dependency
kinds (`characters`, `roles`, `organizations`), with its existing eight-ID limit.
No fact-dependent goal mechanic was added; legacy Runtime/save handling is unchanged.
Unsupported dependencies are diagnosed early at exact paths, alongside independent
provenance/portrait errors, before legacy salvage could discard them.

For the retained Low candidate, an explicit addressed repair can keep the supported
dependency entries and copy the exact unsupported input into the goal's `evidence`,
labelled as non-executable original metadata. The server requires preservation of
previous evidence and supported links; silently clearing dependencies is rejected.
Goal IDs, text/status and source Facts remain intact. This is visible, recorded
repair, not silent normalization or executable support for `facts` dependencies.

If a trial reveals further structural errors, its diagnostics join the next
bounded request against the **uncommitted original candidate**. The same two-attempt
budget applies; all changes are resubmitted and fully validated atomically.
Regression: resolving a missing actor reference exposes conflicting duplicate
Knowledge; the second request gains the evidence path and resolves both without
persisting the first rejected trial. Manual-path and provenance guards remain.

## 5. Real launch versus controlled recovery

| Check | Result |
| --- | --- |
| Real Off candidate, production UI warning acknowledgement and save creation | PASS, zero model requests |
| Browser and SQLite reload of that real save | PASS |
| Base world unchanged by failed creative proposal | PASS; 11 characters, 6 Facts, 5 Knowledge, 10 objective relations |
| Off original failed job resumed with new code | Controlled integration PASS; one review fixture, no repeated world/creative generation |
| Low original candidate resumed with new code | Controlled integration PASS; repair + creative no-op + review fixtures; no world generation |
| Low facts and five goal dependency payloads preserved | PASS; exact source IDs retained in evidence, unsupported dependencies not executed |
| Historical responses/request records/document versions | Preserved in both copies |
| New real DeepSeek Narrative → Extraction → Runtime turns | NOT TESTED, awaiting spending authorization |

Controlled responses are explicitly labelled in raw evidence and are not DeepSeek
receipts or semantic PASS. The real Off save used for the next game session is
separate from these controlled-recovery copies. No new SQLite schema/migration.

## 6. NPC lifecycle mechanics

No actual new marriage, divorce, pregnancy, birth, death, aging or personality
transition was simulated. These remain **NOT TESTED**, not failures or successes.
Once the live session runs, untriggered rare events will be **NOT OBSERVED**.

A free production Long-term Advance preview for three months succeeds, targeting
2026-07-11 09:00 with eight candidates and one player-decision candidate. Preview
leaves the snapshot unchanged and makes no model call. This verifies availability,
not successful world evolution or outcomes.

## 7. Remaining impact and proposed Live QA

The existing Off world is playable up to the first model-generated scene. Its
warnings do not block entry. Remaining uncertainty concerns actual player agency,
NPC initiative, relationship evolution, knowledge secrecy and continuity during
real turns, and the real model's ability to use the revised Low repair scope.

Proposed hard ceiling: **24 new calls / $1.00**, through the existing shared
Budget/ledger. No calls before explicit approval; prior unused allowance is not
used during this free phase. Historical lifecycle spending remains 12 calls /
$0.1567173 conservative, with no unsettled reservations.

If approved, the minimal existing Budget configuration change is
`LIMIT_CALLS=220`, `LIMIT_NUSD=2476087300`, retaining phase baseline 205. Current
phase usage is 196 calls / 1,476,087,300 nano-USD (ledger ends at reservation 401),
so those ceilings allow exactly 24 further calls / $1.00. No configuration or
authorization table is changed before approval.

- Start from the already-created real Off save: opening scene and about five
  natural actions (conversation with mother, visiting relatives, following
  invitations or conflicts that actually arise), roughly 12 primary calls.
- Resume the same original Low candidate through real bounded repair; no world
  regeneration. Baseline estimate three calls, more only within the overall cap.
- After stable ordinary play, one three-month LTA with its existing
  `max_llm_calls=4`, then one return scene (about two primary calls). Respect
  interruptions requiring a player decision; do not force rare outcomes.
- About three calls of headroom for existing repair/background/memory work.
  Baseline estimate 21 calls; stop at either hard limit and report partial coverage.

Estimate 0.30–0.80M input and 0.05–0.17M completion tokens, including reasoning
inside retained Low world preparation: **$0.15–$0.45 conservative** at existing
peak rates. The $1 ceiling accommodates full-context reservations in the existing
ledger. Allow roughly **20–40 minutes**, depending on provider latency and repair.
World preparation stays Low where pinned; ordinary Narrative, Extraction and LTA
use Off. No extra retry loops or new mandatory model stages.

After every real turn, compare prose, extracted changes, player agency, World
State, History, Knowledge and reload. Preserve first replies and all failed
attempts. Changes in calendar or a `saved` job alone do not establish lifecycle
progress. No full campaign or forced wedding/birth/death is proposed here.

Free raw evidence and the playable Off save are in
`/workspace/work/life248-launch-fixes` (excluding its detached baseline worktree).
PR #248 remains unmerged. Stage C and lifecycle playability are not certified.
