# Berezovsk: targeted follow-up to real gameplay QA

Baseline: `aa6811f9e20595c1c5851d411f5fc2f10f13243a`, PR #248.
Source: `life248-game-live-evidence-20261108.tar.gz`, SHA256
`711d89d106f3a7432a4f75292876ccb396da1b07e9edee5ad3d40fec5c044bf0`.
No paid calls, regeneration, manual production state corrections or schema changes.

## Confirmed causes and changes

* Ordinary responses omit player-address Events or their actor/target/action links.
  The evidence-first paragraph had retained audit instructions but compressed away
  the operational coverage rules present in the older paragraph. It now states the
  exact linkage, separates NPC replies, and distinguishes the recipient of a question
  from the person mentioned in it. Evidence-first audit remains required. This is a
  confirmed instruction omission, **not proof of causal model regression**.
* Galina/003 repair copied `diagnostic`/`diagnostics` from the feedback envelope.
  Feedback now explicitly identifies input-only envelope keys and requests the complete
  RawTurnResult, not an envelope or patch. Unknown-field rejection remains unchanged.
* Visit/005 used arrival order 1 versus Event order 2, colliding with farewell.
  The contract explicitly requires a common arrival order after farewell. No Events,
  actor links or ordering are generated automatically by Runtime.
* Choices in 002 reference `ev3/ev4/ev5`; choices in 007 reference the current
  `event_viktor_*` IDs. These are not supported continuity bases. This is **not** a
  Runtime requirement to invent an Event for a proposal. The contract now defines
  allowed basis kinds and permits omission/[] for a new scene-based suggestion.
  Unknown links remain rejected; no expansion of the canonical basis registry.
* LTA correctly used background, but supplied the old undated conversation situation
  as current after moving the clock three months. The context projection now supplies
  those transient descriptions as explicitly dated prior observations, clears them
  only in the LLM projection, and distinguishes independent NPC resolution from a
  continuation of the old player dialogue. StateResolver receives the original
  canonical baseline, **not the stripped projection**. Protection of the player,
  Knowledge, existing/new locations and NPC autonomy are unchanged.

The old LTA response still fails, appropriately. The changed prompt has not yet
been shown to produce a valid live outcome. The existing bounded loop continues
with other already-selected groups after a rejection; it does not retry the same
failed group. QA gave it two calls, enough for only one group. Eight other reasons
were budget-unselected, not failed product tests. No retry loop was added.

## Offline evidence and recovery

`tests/fixtures/issue247/life248.json.gz` retains the original before states,
Narrative, input and relevant model replies for 002/003/005/006/007/008. Tests replay
rejections, real accepted replies, production jobs with zero/one repair, original
visit failure then real successful Retry, History, SQLite reload, rollback and
Galina abandon. Scripted transport replays are **not new Live PASS results**.
The Galina Narrative remains recoverable in principle but has no successful original
Extraction in this archive. Its actual recovery requires the separately authorized
live test; no hand-corrected substitute was used to claim success.

Two new context/feedback regressions fail on the detached baseline. New test harness
errors accessing History as an object and calling a nonexistent rollback method
were corrected to the actual public APIs; these were test errors, not product bugs.
The prior decision to treat semantic warnings as launch blockers was also QA error.
Warnings remain nonblocking, and no generation/creative behavior changed here.

## Comparison of #249

All 12 members of the retained six C/D pairs were re-evaluated without dispatch;
structural outcomes match the recorded results. Knowledge's four acquisitions and
background's absence of player learning are preserved. Original timings are retained,
not replaced with cheap replay timings. The historical experiment compared complete
contract/schema candidates on identical Narrative/input/state, not one isolated rule.

| Historical metric | pre-249 C | evidence-first D |
|---|---:|---:|
| Correct first results | 1/6 | 4/6 |
| Correct final results | 3/6 | 4/6 |
| Jobs needing repair | 5/6 | 2/6 |
| Ordinary full latency mean | 12.145 s | 8.460 s |
| Ordinary full latency median | 11.098 s | 9.570 s |

Both missed the semantic violations in Phone/Crisis; D is not semantically complete.
C failed PlayerAction/Event on Phone, Detail and Explicit choice, time in Knowledge,
and completion in Crisis; D failed target consistency in Phone and an audit reference
in Crisis. No general regression is established. **There is no pre-249 response for
the new Berezovsk inputs**, so their matched first-response accuracy, repair frequency
and latency comparison remains untested. Replaying D under C validation is not a
counterfactual C model response. The old contract was not restored wholesale.

## Acceptance and remaining impact

Repairs and loss of ordinary scenes are substantial playability problems. Missing
choices are noticeable but free input remains usable. One rejected LTA group does
not establish failure of the whole feature. Existing tests cover accepted NPC roles,
residences, birth, personality evidence, locations, protected knowledge, jobs,
reload and rollback; those controlled outcomes are not lifecycle events from this
real campaign. Weddings, divorce, birth and death remain NOT OBSERVED in Berezovsk.

Existing full CI's creative185 tests still expect pre-aa6811f rejection/resume
behavior; this work does not silently weaken them or label that run green. Full CI
was not manually rerun after each edit. Generation/legacy creative test adaptation
remains separate from these gameplay changes.

## Proposed paid gate — requires new approval

Use existing Budget/ledger, originals copied into isolated SQLite, one server per
working DB; DeepSeek Flash thinking off, no new world. Proposed ceiling **24 calls /
$0.75**; expected $0.20–0.45, roughly 15–25 minutes. Existing receipts remain charged.

1. Four frozen ordinary Narratives (002/003/005/007), one initial C and current D
   Extraction each, maximum one existing repair per result: at most 16 calls.
   Identical input/state/model parameters; preserve the first result and full latency.
2. Production Retry of the original Galina failed job, preserving Narrative:
   at most 2 calls. Verify History/Knowledge/reload and visible choices.
3. Resume the pre-LTA Berezovsk checkpoint, three-month LTA with existing cap 4:
   at most 4 calls, inspecting each selected group's accepted consequences.
4. Two-call reserve; no automatic retries beyond the existing bounds. Do not start
   a new ordinary scene without enough budget for its possible repair.

After this gate passes, propose a separately budgeted longer campaign from the same
save. Visit the families naturally, then use existing LTA for longer processes;
check remembered relationships, family links, age, personality/goal behavior and
Knowledge. Do not force rare events or substitute calendar progress for life changes.

## Validation results

- Profiled regression command below: **256 passed** (202.40 s).
- Final LTA + new replay suite after isolating the context projection from the
  resolver baseline: **48 passed** (27.16 s); includes 13 new tests and a protected
  actor situation assertion in the accepted NPC outcome integration test.
- Existing choices browser journey: **2 passed**, desktop/mobile (19.9 s).
  This confirms rendering/persistence of supplied valid proposals, not that the
  new prompt will make DeepSeek supply valid proposals on every turn.
- Detached baseline: the two new envelope/context expectations fail as intended.
- Historical C/D: 12 retained paired results replayed; no paid dispatch.
- `git diff --check`: clean. Full CI not manually rerun; normal PR CI may run on push.

```sh
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_life248_playability.py tests/test_long_term_advance.py \
  tests/test_narrative_choices.py tests/test_comparison249.py \
  tests/test_integrated_repair247.py tests/test_player_action_completion.py \
  tests/test_player_action_group_completion.py tests/test_action_provenance_repair.py \
  tests/test_movement_semantics223.py tests/test_due_boundary_repair.py
# Final changed owner subset:
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_long_term_advance.py tests/test_life248_playability.py
# frontend/, Chromium installed locally; test provider, no DeepSeek:
PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium npx playwright test \
  e2e/choices.spec.ts --project=desktop --project=mobile
```
