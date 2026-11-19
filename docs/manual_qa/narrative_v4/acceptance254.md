# Issue #254 — offline implementation and acceptance boundary

Base: `406f3e864b61fb1d592aa673f52a478edcc331c8`, PR #248.
The Live QA on 2026-11-14 **ran and failed**. These changes address its causes;
offline authored controls are not a new DeepSeek semantic acceptance.

## Evidence and reproduction

Original archive: 980818428 bytes, SHA256
`bd13a4839c498140a8502e04b5cf8c0a4c6f3a1eb5f4d26765f23db056b1b54e`.
All 330 manifest files verified; all 36 archived SQLite files passed read-only
integrity checks (includes checkpoint copies, not 36 distinct campaigns).
Small compressed fixtures retain original before state, text, replies and source
hashes. Full SQLite archives remain outside git.

Commands:

```sh
python -m pytest tests/test_acceptance254.py tests/test_policy252.py tests/test_integrated_repair247.py tests/test_event_presence.py tests/test_movement_semantics223.py tests/test_reproduction.py tests/test_player_agency.py tests/test_long_term_advance.py -q
python -m devtools.live99.replay_acceptance254 ARCHIVE_ROOT OUTPUT_DIRECTORY
python -m pytest -q --junitxml=pytest-results.xml --durations=15
cd frontend
npm test
npm run build
npx playwright test policy252 playability251
```

The offline SQLite runner uses the real resolver, domain readers, atomic
`Repository.commit_job`, reload, History-prefix comparison and rollback. Its
paired arm mirrors the original experimental scope (no background generation).
Its LTA arm restores the exact original before snapshot through rollback and
runs production `engine.run_job`, replacing only provider IO. Source hashes are
rechecked. No paid calls are made. Results distinguish original replies,
cause-only counterfactual and an explicitly authored hypothetical interpretation.

## Changes and consequences

- LTA describes both `events` and `information_events`. Compiler-owned provenance
  maps derived Events back to source section/index/local ID. All missing or
  unselected causes are reported together with allowed selected IDs. Causes are
  never inferred from participants or automatically assigned to all events.
- A malformed optional NPC contact annotation loses contact authority. A
  relationship proposal cannot upgrade it into a global failure. Relationships
  still reject unsupported sources locally; real information sources remain
  strict. Birth identity and sex/Knowledge validation remain with reproduction.
- The original birth reply has a second omission: an unidentified clinician's
  announcement has `source_assertion=null`. After removing the contact blocker,
  the existing sex-source check correctly requests Extraction repair. An authored
  `direct_observation` repair preserves the original Narrative, reserved boy and
  ten acquisitions. This is not a first-response semantic PASS.
- A unique explicitly linked Event owns Movement order in v5. Source-less routes
  retain their own order. Existing source actor/place/channel and route checks
  still validate before commit. Original Arrival now uses step 2 and preserves
  the earlier goodbye; contradictory geography is not normalized away.
- Movement endpoint errors no longer hide independently checkable Event/Action
  provenance errors. Dependent presence is inconclusive on an invalid route,
  not a fabricated extra error. The whole candidate still fails atomically.
- `chronology_claims` supports `current_calendar` date/weekday and legacy
  `event_elapsed`. Calendar does arithmetic, Extraction identifies meaning.
  Unknown absolute dates are not invented; custom weekdays and in-scene times
  are supported. Current time outranks historical titles. Objective conflicts
  use existing explicit local correction, fresh Extraction, immutable original
  and rollback. Recheck requires the same time and claimed date/weekday field.
- Compact contrasts clarify partial/full secrets, hypothetical statements,
  preparation/departure/arrival, impossible contact and unrequested decisions.
  `fact_id` denotes the whole assertion; no new Knowledge store, prose parser,
  mandatory critic, retry loop or increased repair cap was added.
- Saturated 32K requests exposed a regression from the expanded contract. Six
  existing production-path tests passed at the base but exceeded the context
  limit with the first implementation. The final v5 wording consolidates repeats
  and removes legacy-output instructions from new semantic generation; recorded
  legacy contracts and repair-required legacy schema remain supported. No budget,
  canonical input, output invariant or repair limit was relaxed.

Offline results on original SQLite: original v5 Knowledge (6 acquisitions),
Campaign (9), Social, ongoing Family and Arrival accepted; Crisis, both Phone
cases and original completed-birth reply rejected. The authored birth source
repair accepted with exactly one reserved child and 10 acquisitions.

The LTA cause-only counterfactual **does disclose the full secret to Tamara**.
This is a newly executed counterfactual on a disposable copy, not a leak in the
original rejected run. `secret_disclosure_invalid` is a warning and does not
undo separately asserted Knowledge. Thus a structural saved result is a semantic
FAIL for that raw. The authored conditional-question interpretation accepts one
group without expanding the secret. Original LTA still rejects with source-local
cause diagnostics; all copies pass reload/rollback. Prompts clarify the semantic
error; Runtime cannot verify the meaning of a falsely asserted full perception.

## Hard-fail invariants in changed paths

| Guard | Protected invariant | Negative coverage |
|---|---|---|
| LTA missing/unselected causes | Outcomes belong to selected causes; no fabricated resolution | Original LTA initial/repair, unselected/multiple-cause controls |
| Information source contact | Real perceiver/source ownership; malformed semantic sources cannot grant Knowledge | policy252 information negative controls, Knowledge/secret suites |
| Birth sex source, identity, listeners | Canonical reserved child, true announcement source, bounded Knowledge | Original null source assertion, reproduction suite and birth controls |
| Movement endpoint/source/route/presence | No invented destinations or incompatible co-presence | Original Phone, movement223/event_presence suites, source-less and tied routes |
| Event/Action provenance | Player input authorizes delivered actions, not mere mention | Original Phone independent diagnostics, agency suites |
| Chronology type/source/reference | Known Calendar/History at the actual in-scene instant | Unknown event time, invalid reference, custom/unknown dates, legacy tests |
| Objective chronology conflict | New prose cannot rewrite established time | Wrong weekday and five-days/yesterday recovery; belief/lie/quotation controls |
| Correction recheck | Changed text is reinterpreted against the same canonical ground | Missing/downgraded/other-minute/other-field claims; fresh Extraction/reload/rollback |

Removed gate: relationship proposals no longer make decorative contact fatal.
Removed duplicate: source-linked Movement no longer requires a second independent
step number. No substantial outcome is silently removed to increase saved rate.

## Remaining acceptance

New model responses have **not** been generated. Original Crisis and Phone replies
remain semantic failures, safely rejected structurally; prompts alone do not
prove improved classification. Original calendar prose without a claim remains
undetectable by deterministic code; no universal prose correctness is promised.
Partial secret tests with authored JSON prove scoping, not model understanding.

Four ordinary original Berezovsk turns were also replayed through production
jobs with recorded foreground/background replies. Every final world_state exactly
matches its archived after snapshot; reload and rollback pass. The first turn's
unclaimed calendar contradiction remains a semantic FAIL, not a successful check.

Final paid acceptance needs separately approved budget: the same seven valid and
two invalid Narrative cases, partial/full/rumor/conditional contrasts, one normal
bounded repair, short continuation of the same campaign and meaningful LTA.
Keep first responses and actual canonical outcomes. Do not reroll to PASS.

Local browser attempts failed before opening a page because Chromium's socket
creation is denied by this environment. Desktop/mobile outcomes must come from
the final-head CI run. Exact final test counts, SHA and CI links belong in the
PR description; green CI alone does not close #254 or authorize merge.
