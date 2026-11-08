# Berezovsk follow-up: choices, geography, compound Retry

Implementation starts from PR #248 HEAD `2ad8c0f9fceb6d778f2cf5e9d6fd016fc3f6dffd`.
No new PR, merge, paid provider request or regenerated world. #250 behavior is
retained. This is offline engineering verification, **not new Live QA**.

## Confirmed causes and changes

| Case | Recorded failure | Change |
| --- | --- | --- |
| D/002 | Extraction sees an off-scene referenced NPC's hidden Fact and a duplicate legacy Thread and the NPC's private goal. Plain choices have no checked knowledge source; separate labelled actor context does not isolate one model's attention. | Actor-mode context excludes unnecessary off-scene private Facts/Threads and psychological state, including redundant scope/Director references. New optional choices declare per-item Fact/scene sources; Runtime checks actor Knowledge, typed current-scene attribution and optional continuity basis. Reject only that invalid item, without repair, state changes or restrictions on typed input. |
| LTA Pasha | Reconciliation iterates `(previous present ∪ observed) − present` and clears the known location. Visibility is incorrectly treated as departure. | Observed characters never lose geography from observation. New ordinary turns and all background/LTA preserve known locations on scene absence. An actual exit with unknown destination is an explicit existing Movement, bound to its accepted Event at the known origin. |
| D/005 | One PlayerAction combines distinct clauses/targets; linked Events use conflicting quotes; arrival asserts interaction without the target among participants. The repair fixes some fields but omits `final_scene`. Retry takes only that latest partial proposal. | Compound-action instructions explain separate consent/target boundaries. Repair requests a full schema with the populated consequence sections. Retry finds the preceding complete proposal and supplies only omitted sections as **unaccepted context**. It never merges or applies proposals itself. |

Producer contract v4 is server-owned and recorded in jobs. Old v1–v3 ordinary
jobs/regeneration retain their original contract and implicit absence convention;
new turns on old saves use v4. Background/LTA and observed-character geography
are corrected regardless of producer. Saved snapshots and History are not
rewritten. No SQLite migration or second source of canonical truth is added.

Departure uses `assertion=departure`, `to_location_id=null`, a known
`from_location_id`, `source_event_id`, and matching event/movement order.
A null **completed_arrival** remains invalid. Actor, contact, physical endpoint,
source order, agency and final-scene contradictions still fail validation.
The source departure Event occurs at the origin; subsequent contact cannot use
that old location. Creating a new location still does not prove arrival.

## Evidence and reproduction

Archive SHA256/source paths: `tests/fixtures/issue250/source.md`.
Original Narrative, inputs, response strings and before states are unchanged.
`lta.json.gz` adds both original LTA groups and their recorded state projections.

```sh
PYTHONPATH=tests:. python scripts/reproduce_berezovsk_followup248.py /path/to/evidence
python -m pytest -q tests/test_berezovsk_followup248.py
```

The evidence directory must contain both extracted original archive directories.
The script uses SQLite backups, verifies original database hashes unchanged,
and patches provider transport. Results on the implementation:

- Original LTA checkpoint actually contains Pasha at `null`. Regenerate uses its
  recorded original groups/contexts and four exact responses. Both groups save;
  Pasha remains `loc_home_kovalev`. Knowledge is unchanged. SQLite reload and
  rollback to the original before snapshot pass; `quick_check=ok`.
- Original D/005 SQLite matches the committed before state. The original
  Extraction/repair still fail atomically (three transport attempts including
  one Narrative). Normal Retry with a **human-reviewed corrected test response**
  saves all four original Events and the actual arrival with one Extraction
  attempt, no new Narrative. Reload, History and rollback pass. Repeating the
  original incomplete repair instead leaves the save unchanged and supports abandon.
- Original D/002 under its historical v3 reproduces the unsafe suggestion without
  adding Knowledge. New contexts contain neither the hidden Fact nor the duplicate
  off-scene Thread. A v4 control preserves the original six proposed texts and
  adds explicitly reviewed source declarations: five safe suggestions survive and the letter
  suggestion is rejected. Paraphrases with the same unavailable source also fail.
  New saved choices survive reload; typed questions remain available.

**Limits of this replay:** the original six D/002 choices have no source metadata.
Replaying that old JSON as a new v4 response rejects all six individually as
unproven; the engine cannot safely identify their meaning from prose. It does not
claim automatic semantic classification of the archive or successful new DeepSeek
repair. Safe-item preservation is tested with the separately labelled v4 provider
control. Historical stored choices are not retroactively rewritten.

## Regression coverage and verification

`test_berezovsk_followup248.py`: 25 cases through Context Builder, real Runtime,
engine jobs/Retry, LTA, History and SQLite. Covers original cases, paraphrases,
unknown/known/missing choice sources, private legacy continuity basis, no Knowledge
minting, free input, per-item rejection, absence/observation, departure sources,
origin/order/contact failures, complete Retry and repeated failure/abandon.

Existing departure fixtures now explicitly author their actual unknown exits in
v4; legacy raw archive tests remain unchanged. Synthetic provider fixtures that
expect choices declare their scene sources. Assertions on source validation,
locations, action recipients, History and transaction rollback are retained.

Local focused runs overlap and are not summed: 25 new regressions; 82 source,
context, legacy and browser-provider checks on the final source contract; 143
personality/values/reproduction/birth/secrets/POV checks; 73 narrative authority,
NPC promotion and persistence checks. Frontend unit: 151 passed;
TypeScript/production build passed. The first broad local run ended with
3774 passed, 25 failed, 1 skipped before all protocol fixtures were updated;
it is not a green final run. Its failures included legacy expectations of
observation erasing geography, unannotated synthetic choices, hardcoded producer
v3, a missing optional legacy thread field, and over-filtered active authors.
Those failures were reproduced and corrected without suppressing assertions.

Intermediate CI #490 on `cb0447e` was **not green**: backend 3794 passed,
12 failed, 1 skipped; full browser shards also exposed legacy synthetic departure,
unannotated seeded choices, the obsolete doorway-location expectation and an
undersized model capacity advertised by the new Berezovsk provider. The fixes keep
the existing assertions for actual departure, repair attempts, six safe seeded
choices and state equality. Direct subprocess checks of the browser provider now
pass all 13 scenarios; the fixture/provenance integration subset passes 50 tests.
These results are not a substitute for the final complete CI.

CI #491 reached 3815 backend passes and one failure: the newly added shared
fixture assertion incorrectly required six choices even for an incapacitated
protagonist. That checkpoint now explicitly requires zero choices, while healthy
checkpoints still require six. Runtime capability enforcement is unchanged. The browser family seed had the
same shared assertion; its endpoint now explicitly checks healthy/incapacitated
choice counts through a subprocess TestClient control. The 60-test family/fixture
subset and that HTTP endpoint control pass locally.
The earlier campaign repair overflow was also traced to five repeated Narrative
quotes in test choice metadata (5325 characters); typed scene attribution removes
that duplication and restores the expected bounded repair within the same budget.

The active-author correction preserves NPC-owned knowledge needed to author a
message, including explicit uncertainty, while a merely mentioned off-scene NPC
still contributes no private goals/facts/threads. Semantic retrieval diagnostics
retain selected-versus-included counts outside the model prompt. Old snapshots
without `Thread.discovered_by` retain their legacy default. Departure feedback
matches the recorded ordinary contract; background always uses explicit exits.

Two new browser scenarios run for both desktop/mobile: D/002 keeps five safe
choices through reload; D/005 error → reload → Retry preserves one Narrative and
commits the arrival. The existing #249/#250, choices, phone, POV, saves, LTA and
full browser suites remain enabled. Local Chromium cannot start because the
host denies its singleton `socket()`; no bypass was attempted. **Final full CI
results and exact HEAD are published in PR #248**, not inferred from local builds.

## Remaining risks

- Source declarations are produced by the same model. Runtime checks canonical
  access and supplied references, not whether a literary sentence truly follows
  from the declared scene. A model can still misdeclare a secret as scene-based or
  omit a secret presupposition. No regex classifier or extra verification model
  is introduced. Removing unnecessary GM context reduces the observed cause but
  is not proof of zero possible semantic leaks.
- Required per-choice provenance may reduce the number of suggestions when the
  model omits it. It never blocks the turn or free input and buys no repair call.
- Repair remains probabilistic. A contradictory or partial retry remains an
  explicit recoverable failure; no fake Event or silent consequence loss is used.
- Background still receives private NPC context needed for autonomous life;
  its outcomes do not grant player Knowledge. NPC-only secret content is not
  globally deleted from the world.
- Green deterministic CI cannot establish story quality or real provider accuracy.

## One proposed Live QA, not started

Use a copy of the existing Berezovsk save, never regenerate the world. After
separate authorization of the paid run and budget, play 20–30 ordinary turns and
three bounded LTA groups of intervals (choose durations from the actual current
calendar and unresolved boundaries, up to four calls per LTA initially).

1. About 8 short domestic/social turns: varied questions, quiet actions, one
   compound visit, free input, reload. Check NPC initiative after accumulated time,
   choice sources and meaningful agency; do not require an Event for every gesture.
2. About 8–12 relationship/life turns, including returning to NPCs after independent
   activity. Observe durable relationships, obligations, personality evidence and
   actual geography, not merely interesting text. Include one LTA then reload.
3. Remaining turns and two LTA at appropriate causal points: inspect existing
   marriage/divorce/pregnancy/birth/death opportunities and protected boundaries.
   Do not force rare events or treat their absence as failure. Use NOT OBSERVED
   where a mechanic did not naturally occur; deterministic regressions cover it.

Record actual Narrative, Extraction/repair, diagnostics, request counts/cost,
History and SQLite before/after. Separate saved turns, safe optional omissions,
rejected groups and failures needing player recovery. Check hidden facts in both
prose and choices, actual sources of learning, actor agency and commit/reload.
Stop at the agreed budget or a confirmed integrity failure. Acceptance is a
playable, engaging continuation with durable significant consequences, not perfect
semantic agreement for every line.
