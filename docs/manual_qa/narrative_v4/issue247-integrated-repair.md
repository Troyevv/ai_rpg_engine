# #247 / #246: integrated Extraction recovery

Base: master `d81a52c9980b79d1be99acfde9fc1a1452d71176`.
No paid provider calls. No migration or changes to old snapshots/variants.

## Confirmed causes and changes

- Knowledge combined missing Fact links with other optional perception failures.
  Valid actor/Fact/informational Event/witness acquisitions with missing
  `Event.fact_ids` now produce `knowledge_fact_link_missing`, exact Knowledge
  and Event paths, and participate in the existing bounded repair. Unknown
  actors/facts/events, missing witnesses, unsupported media and protected
  Knowledge remain separately diagnosed optional failures. Ordered revision,
  retirement and supersession validation precede link escalation; invalid optional
  proposals do not become hard failures. No automatic links.
- Completion failure stopped validation before the independent birth boundary.
  The existing resolver now aggregates action/Event/presence/Knowledge errors;
  on a failed candidate, isolated calls to existing Life/Reproduction/Commitment
  validators determine whether the temporal check is independently meaningful.
  Invalid sources suppress dependent diagnostics; accepted BirthClaim can still
  discharge the boundary. Original action indexes remain stable after source rejection, and independent
  completion failures are aggregated too. Pregnancy schedule ownership lives in its existing
  commitment handler so normal and diagnostic paths share the same rule.
- Referenced cards appeared under the title “present”. Narrative blocks now
  separate ContextScope's present, observed, remote and referenced actors.
  This ambiguity is confirmed; its causal role in the original hallucination
  is **not proven**. Extraction classifies impossible Narrative contact as
  violated, activating the existing explicit reauthor/abandon UI path.
- Current arrival assertions lacked a required Event source. The prompt schema
  requires assertion/source_event_id; Runtime checks accepted current Event,
  actor, endpoint, order and physical channel. Same-order arrival Events anchor
  the route endpoint; unrelated equal-order meetings remain ambiguous. History
  stores canonical Event IDs. Unmarked legacy payloads and historical saves
  remain readable. final_scene still owns physical membership.
- Repair duplicated camera/location context. Feedback retains the original
  Extraction and diagnostics but includes only referenced canonical locations;
  the builder removes locations already supplied in current state. Initial
  Extraction reserves soft repair headroom. Existing optional schema compaction
  also runs for untargeted actions. Critical input, Narrative, state, agency,
  Knowledge and temporal data retain the hard pre-dispatch limit.

A pair of mutually consistent invented Event/movement records is **not** proof
of a real arrival. No Python literary parser was added. Phone/Crisis semantic
quality still requires the live gate below.

## Offline evidence

Full archive was available and its SHA256 matched the Issue. Original archive,
SQLite, ledger, checkpoints and variants were not modified.

`tests/fixtures/issue247` stores the six original cases. Test-authored corrected
JSON is explicitly separate. Automated tests exercise Context Builder, jobs,
one bounded repair, reload, retry without regenerating Narrative, rollback,
regeneration/sibling selection, optional Knowledge failures, arrival provenance,
valid BirthClaim boundary discharge, 40960 repair context and 8192 no-dispatch.

The additional replay used **12 copies of the original source SQLite**, restoring
the precise original world state and History head, with original sibling hashes:

| Case | Repeat original response | Test-authored control | Acquisition delta |
| --- | --- | --- | --- |
| Family/001 | atomic error | saved, elapsed=0, no birth | 0 |
| Knowledge/002 | atomic error | saved | **4**, retained after reload |
| Phone/001 | atomic error | saved, no false arrival/scene disappearance | 0 |
| Crisis/001 | atomic error | explicit reauthor required, no commit | 0 |
| Social/001 | saved | saved | 0 |
| Campaign/000 recovered response | saved | saved | 0 |

Each failure preserved snapshot/History; each copy passed SQLite integrity_check
and Repository reload; existing variant content hashes remained unchanged.
The original SQLite hash was unchanged. Scripted calls: three for failure/repair
cases (one Narrative, Extraction, repair), two for already-valid Social/Campaign.
These are mock accounting entries, **not paid/live calls**.

Reproduce from repository root, using a new output directory (about 1.7 GB):

```sh
python tests/replay_issue247_sqlite.py /path/to/live99-postfix-20261107 .runtime/replay247-new
python -m pytest -q tests/test_integrated_repair247.py
python -m pytest -q
cd frontend
npm test
npm run build
npx playwright test e2e/integrated-repair247.spec.ts --project=desktop --project=mobile
```

## Validation status

- Original SQLite replay: 12/12 expected outcomes, zero paid calls.
- Focused integrated suite covers 39 cases. Final test totals and exact CI commit
  are recorded in [PR #248](https://github.com/Troyevv/ai_rpg_engine/pull/248).
- Frontend unit: 151 passed. Production build passed (existing chunk-size warning).
- Desktop/mobile E2E added: 10 scenarios. Local browser startup is blocked by
  `process_singleton_posix.cc: socket() failed: Operation not permitted`; no local
  browser success is claimed. See PR #248 for CI browser results.
- Full backend commands/results are tracked in PR #248. Initial implementation run had 124 failures,
  3460 passes, 1 skip; these exposed legacy movement compatibility, context
  pressure and obsolete diagnostic assertions. An intermediate concurrent run
  also exhausted `/tmp`; subsequent runs use a repository-local basetemp.
  Original failures are not evidence of a clean baseline and are not hidden.

## Remaining live gate (not authorized or executed)

Use existing `devtools/live99` harness / #245 QA checkpoint machinery, copied
original saves and a new explicit calls/cost authorization. The previous QA
budget does not authorize this run. Do not run a campaign or LTA1/5 first.

1. Crisis/001: inspect all physical/referenced context groups, then the generated
   prose and agency review. Correct prose with an Extraction-only cast mistake
   must repair; impossible prose must require explicit reauthor, preserve input,
   and prohibit an automatic Narrative retry.
2. Knowledge/002: one repair must receive both independent diagnoses and retain
   two facts/four acquisitions, Event fact links, History and reload consistency.
3. Family/001: observation/reference plus ongoing zero elapsed; separately test
   a genuinely completed BirthClaim, including remote/non-parent control.
4. Phone/001: inspect Events, movements, final_scene and character_changes as a
   whole. Contrast preparation, room exit, departure with unknown destination,
   intention to visit a new place and genuine arrival at a newly created place.
5. Social compound/split action and Campaign targeted recovery: preserve action
   identity, absolute time, the original Narrative and one repair limit.

Record original/repair responses, all diagnostics, call counts/cost, before/after
state, History, Knowledge, variants and reload. A saved job alone is insufficient;
review semantics against the prose. Never repeat successes to select favorable
output. #99/Stage C/multiyear campaign reliability is not established here.
