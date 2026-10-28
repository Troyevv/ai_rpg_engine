# #134: literary arrivals and visible thresholds

Base: `50d6694db0ee838c99a34f2159386e05e04186a8` (master, including #116 and #124).
This extends [runtime handoff QA](runtime_handoff.md) and the #78 harness.
No original gameplay job, raw extraction or SQLite from the reported failure is
available. E5 world.json is the existing user-supplied world export; all gameplay
provider replies here are explicitly **synthetic**, including the issue's exact
sentence. No paid-provider/live-model result or original-user-job replay is claimed.

## Confirmed cause and evidence boundary (R01)

Start/turn requests reserve a job and immutable before snapshot; Context Builder
selects physical/camera data; Narrative is saved before Extraction. RawTurnResult
passes to StateResolver, followed by at most one extraction repair. Commit writes
World State, History and time together; terminal errors retain narrative/before.
Retry repeats Extraction on those saved inputs. Thus retries cannot solve an
incompatible contract on their own.

The master guard requires destination_evidence to be an exact canonical name or
alias in the same quoted evidence as the actor name. A correct deictic assertion
("вошла внутрь", anchored to the recorded room) fails regardless of retries. The
same guard correctly refuses to treat "стоит в проёме" as completed entry. However,
the previous camera contract has no representation for a visible boundary actor:
putting them in present co-locates them inside; excluding them omits scene agency.
These are confirmed code/reproduction findings, not proof of the unknown original
LLM payload. See [baseline diagnostics](issue134-evidence/baseline-red.json), with
before camera, actor origin, exact synthetic payload/evidence and both attempts.
Master has no per-predicate diagnostic or filtered-movement detail for these cases;
quotes in both records are supported (no movements were evidence-filtered).

Reproduce with the baseline checkout and current test dependencies:

```sh
git worktree add ../baseline134 50d6694db0ee838c99a34f2159386e05e04186a8
python docs/manual_qa/narrative_v4/issue134_replay.py ../baseline134 /tmp/red.json
python -m pytest -q tests/test_scene_arrival134.py tests/test_runtime_handoff.py
```

The initial two new acceptance tests against master failed: contextual entry ended
in scene_arrival_unsupported; doorway lacked canonical visibility. The trace script
also records a deliberately wrong inside assertion for the exact issue prose.
It must remain rejected after the fix; correct boundary extraction is tested separately.

## Contract and compatibility (R02–R09)

- `literal` keeps the existing exact-name/alias check. `camera_location` resolves
  deictic evidence to the **before** camera ID. `named_location` relates a quoted
  grammatical surface form to a canonical name/alias. Every explicit claim validates
  source quote, actor identity, actual origin and target; ordered routes chain origins.
- An open threshold uses an existing Location (`kind=boundary`, parent=room) and
  Camera.observed_character_ids. Assertion `observed_at_boundary` records observed
  position, not completed entry/travel. Present means inside; observed means visible
  at the boundary. Visibility must be reconfirmed; omission never moves the actor.
  This is an additive field in the existing camera, not a parallel Scene State.
- Context retains full observed actor cards and their boundary location; initiative
  allows conversation/departure but no physical contact across locations. Visibility
  does not grant Knowledge. Control/POV changes clear the old visibility projection.
- New explicit assertions are fail-closed even for the hero, unknown origins,
  filtered evidence or blocked self-movement. The old initialization path for
  unknown-position NPCs at independent places retains master behavior; no existing
  arrival guard is removed. No verb/substring NLP classifies narrative in Python.
- Prompt, schema, repair feedback and resolver share the physical contract. Known
  relevant actor origins/locations/ancestors reach Extraction. Under hard context
  pressure optional scenic location descriptions are omitted; IDs/names/aliases/
  topology, physical positions, current narrative and existing token caps remain.
- Structured failure names the violated condition, origin/target, prior/final
  presence, movement candidates and before hash. Public jobs expose only safe
  stage/code/condition; detailed payload stays in author diagnostics. Retry text
  explains that the same narrative is reused and repeated attempts may still fail.
- Two extraction attempts remain the limit; successful path adds no LLM call.
  Existing transactions, revision guards and attempt_epoch remain unchanged. The
  new camera field defaults to []; no SQL migration or historical-snapshot rewrite.

## Acceptance map

| Requirements / tests | Evidence |
| --- | --- |
| R01, R03, G4 | baseline trace, contextual-entry API test, structured validation negatives |
| R02/R04/R06, T01/T02/T05/T09, G1 | real import/start API, literal/deictic/named/boundary contracts, long prose, unknown origin, boundary context/initiative/control |
| R03/R08, T03/T04/T06, G2 | non-arrival API cases, actor/origin/target/source rejection, group ordered routes and exit, alias reuse, hero bad-quote regression |
| R05/R07, T07/T08, G3 | bounded repair and reopened SQLite Retry, unchanged text/before, one commit, time/history uniqueness, all 19 identities, uninvolved geography/Knowledge, stale/epoch tests in runtime_handoff |
| R07 | old save immutable bytes plus boundary regenerate/variant/rollback |
| R09/T10/G5 | real-provider-boundary Playwright entry/doorway/retry × desktop/mobile; CI required before readiness |
| G6 | this report and PR validation results; original gameplay payload unavailable |

## Validation status

- RED: initial two acceptance tests on master: 2 failed; baseline trace committed.
- Focused #134 API/Runtime suite: 28 passed; context-budget suite: 20 passed;
  Runtime/domain/storage/scene/context regressions: 76 passed. The initial full run
  reported 2188 passed/7 failed; all seven failures were reproduced and corrected,
  with affected checks passing. A complete final rerun and Actions remain required.
- Local frontend unit tests: 14 passed; production build passed (existing chunk-size warning).
- Local Chromium download failed (CDN returned a non-ZIP response); no local E2E
  pass is claimed. Full desktop/mobile execution is required in GitHub Actions.

## Remaining risks

The external extractor still owns semantic classification (including negation and
whether a surface phrase denotes a place). Runtime checks structured claims and
provenance; it cannot independently prove prose meaning without duplicating NLP.
Synthetic negatives verify safe extraction semantics and invalid-claim guards;
they do not measure a live model's error rate. Original user's gameplay artifacts
remain unavailable. Old saved jobs benefit on Retry because current contract/repair
uses the saved text and before snapshot; unresolvable contradictions remain errors.
