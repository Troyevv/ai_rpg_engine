# #247 / #246: integrated Extraction recovery

Base: master `d81a52c9980b79d1be99acfde9fc1a1452d71176`.
This implementation uses no paid provider calls. The separate Live QA on b3fb833 used 20 calls; its failed semantic gate remains open. No save migration or changes to old snapshots/variants.

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
  stores canonical Event IDs. Historical saves remain readable. Newly proposed arrivals, including unmarked
  movements, need accepted sources; final_scene cannot supply arrival provenance.
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

## PR #248 follow-up audit

Three reproduced defects were fixed in the same PR:

1. A diagnostic birth could append a child card to the original resolver because
   the probe shared `cards`. Probe state, History, warnings, cards and pending
   reviews are isolated; the caller's error list is no longer appended to.
   The regression snapshots mutable resolver fields and input arguments around
   the real probe. No mutation of the passed Events was observed.
2. A birth disclosure error stopped unrelated Knowledge diagnostics. Birth checks
   now aggregate independent claims with original indexes, then the existing
   Knowledge handler checks unrelated facts. Facts whose typed birth disclosure
   failed are not applied or diagnosed as independent acquisitions. Invalid
   source Events suppress their dependent claims, not unrelated ones.
3. An unrelated rejected NPC Event suppressed completion checks for every player
   action. Only Events declaring player-action provenance can make that coverage
   inconclusive. Agency validation itself remains mandatory.

New regressions include mixed Event/BirthClaim/Knowledge failures, probe isolation,
multiple actors moving through two new locations with unsorted input rows,
wrong actor/source/order, canonical source IDs in History, reload, rollback and
sibling selection. Full results and exact tested commit are in
[PR #248](https://github.com/Troyevv/ai_rpg_engine/pull/248).

Artifact audit: unused intermediate Knowledge/Campaign replies removed. Six exact
readable before-state/input/Narrative/selected-response fixtures remain (~560 KiB).
No SQLite, ledger, screenshots, videos or test logs are committed. Original QA
archive and source SQLite remain unchanged. No save schema/migration changes.

## Fixes after the actual Live #248 report

Source: [Live report](https://github.com/Troyevv/ai_rpg_engine/pull/248#issuecomment-6713382739).
Archive `live248-raw-evidence-20261107.tar.gz`, SHA256
`d2b4916503a616c3058cf1afcae6a549c66d4c9b280123d5bc89c6a251028b31`.
All three archived SQLite databases passed read-only integrity checks.

- **Crisis:** original final repair accepted Vera's home→library teleport. The
  resolver built that route from final_scene, and presence then trusted its END.
  Conflicting bundled/schema instructions explicitly allowed this. A change of
  established location now needs an explicit movement and its accepted Event;
  an omitted assertion marker cannot bypass provenance. Initial world placement
  for actors with no established location and new NPC creation remain possible.
  A missing first camera cannot erase an already known location. The error joins
  independent diagnostics.
  Repair must report violated prose via the existing explicit reauthor/abandon
  path; it cannot invent an arrival to rescue the original impossible scene.
- **Knowledge/Social:** original and repair JSON omitted the player's address
  while retaining the NPC reply. Completion validation already refused both.
  Feedback now names the missing action/actor/exact quote and explicitly asks for
  a separate address Event, retaining the NPC response and all its disclosures.
  No Runtime synthesis of a question, reply, agreement or knowledge link.
- **Phone:** reference target-set mismatch was treated as a prose agency failure.
  With preserved meaning, reference mismatch is now a repairable Extraction
  inconsistency. Changed/uncertain meaning and interaction retargeting still
  require reauthor. No contact, endpoint or player permission is required for
  noninterference or an independently authored departure.
- **Family:** the schema demanded a canonical speaker for every announcement,
  encouraging substitution of a known participant for an unregistered clinician.
  `source_actor_id=null` now represents that unknown identity when the actual
  source's direct observation is established. No doctor Character is fabricated;
  prior Knowledge still needs an identified source. Listeners remain distinct
  Event witnesses; no knowledge is assigned to the unidentified speaker.
- **Context:** existing default-prompt upgrade registry recognizes the replaced
  bundled prompt. Retry/regeneration omit recognized historical defaults rather
  than repeating obsolete instructions beside the current contract. Custom
  overrides and saved prompt snapshots remain unchanged. Repeated instruction
  wording is compacted to keep the saturated phone context within its existing
  hard budget; no canonical data or validation is removed.

The original Family claim naming Vera is **still structurally admissible**: Runtime
cannot detect that its evidence describes a doctor without interpreting prose.
The source-representation fix and explicit contract are tested, but whether the
model now attributes the speaker correctly is an **open Live QA gate**. Likewise,
scripted Knowledge/Social repair proves recoverability, not model compliance.

### Exact offline evidence and controls

`tests/fixtures/issue247/live248.json` retains the five exact input/Narrative/reply
cases (~103 KiB), reusing unchanged #245 states and hash-checking exact subsequent
checkpoint updates. No bulk databases, request dumps or UI captures are committed.
Existing synthetic movement tests now explicitly declare their route Event
sources. They are not represented as real model traces.

On the pre-fix b3fb833 worktree, the first 13 new checks gave **10 failures / 3
passes**. On the changed implementation, they passed. Additional tests cover
alternate field/startup bypasses and immutable historical/default/custom prompt
handling. The 12 original #245 SQLite replays were also repeated successfully;
all 22 disposable replays retained the original source database hashes.

`tests/replay_live248_sqlite.py` restored the exact before snapshot/History head
through normal abandon/rollback in **10 disposable copies of the original SQLite**:

| Case | Original response replay | Explicit human-reviewed control |
| --- | --- | --- |
| Crisis/002 | atomic refusal; no teleport | explicit reauthor, no commit |
| Family/001 | accepted wrong speaker: characterization, **not a fix/pass** | unknown clinician identity; birth, male child, 10 acquisitions to Kirill/Vera only |
| Knowledge/001 | atomic missing-address refusal | separate player Event; **4 acquisitions after commit/reload** |
| Phone/002 | repairable mismatch, repeated response refused atomically | reference corrected; Timur departs, location=null |
| Social/001 | atomic missing-address refusal | player address and NPC response retained separately |

Every old sibling hash was preserved; original database hash unchanged. Additional
job tests cover regeneration, sibling selection, rollback and reload. Controls are
labelled and never modify the source evidence. All provider streams are mocked.

```sh
python tests/replay_live248_sqlite.py /path/to/live248 .runtime/replay248-new
python -m pytest -q tests/test_live248_recovery.py
```

Desktop/mobile E2E extends the existing integrated247 fixture endpoint with these
exact #248 replies and explicit controls. Local Chromium cannot launch in this
workspace (`socket() failed: Operation not permitted`); full CI must verify it.
Detailed final counts and the tested commit belong in the PR description.

## Short repeat Live QA — proposed, NOT authorized or executed

Use the reviewed final commit and isolated original SQLite checkpoints. Production
Context Builder/jobs/Resolver/History, existing live99 harness and ledger only.
No new budget class, baseline table or dispatch-guard implementation is required.
Count new request receipts against this operation list; do not reset historical
spending. The supplied ledger ends at receipt318 (318 settled, zero unknown);
record that existing cutoff and count only later receipts for this proposed run,
without changing its historical phase baselines. Recheck it before execution.
No full campaign, Stage C or LTA. No success rerolls, model switching or
extra retries beyond the existing one bounded Extraction repair per job.

Settings: `deepseek-flash`, thinking off, context65536, Narrative cap2000,
Extraction/repair cap8192. Build initial/repair contexts offline before dispatch.
Restore only through supported rollback/abandon; never edit job status to make a
saved/abandoned/sticky-reauthor job eligible for Extraction retry.

| Case / checkpoint | Exact operations and acceptance | Base calls | With repair |
| --- | --- | ---: | ---: |
| Crisis / #245 failed job `e3b9501fc2494c6d9a8bb9c6a35206b6`; #248 `crisis/002/before` | Retry the eligible original failed job: impossible presence must request reauthor without commit. Independently, one fresh original-input turn from the exact before state: no inferred arrival; a real autonomous arrival requires its Event/movement. | 3 | 5 |
| Knowledge / #248 `knowledge/001`, job `fac034db9ecb4765a81b35114edeca72` | One eligible Extraction retry, **no new Narrative**. Separate player request and Vera reply, two fact links, all four acquisitions after commit, History and reload. | 1 | 2 |
| Social / #248 `social/001`, job `4141409d79ad411fad952918041a9fc7` | One eligible Extraction retry, **no new Narrative**. Preserve the addressed Vera Event and unavailable Timur action. If saved, one consent/request turn below; no invented consent or reply. | 3 | 5 |
| Family / #245 original failed due-boundary job; #248 `family/001/before` in an independent copy | Retry the original ongoing-labor text: elapsed0, no fabricated contact/birth. Independently, one observation turn from the pre-birth checkpoint. Actual birth must retain identity/time/sex; doctor's announcement must not name Vera as source. Unknown clinician identity stays null; only actual listeners gain Knowledge. | 3 | 5 |
| Phone / #248 `phone/001/before` and `phone/002/before`, independent copies | One original preparation/intent turn. One original noninterference/departure turn after abandoning the old hard-refusal job (it is not eligible for retry). If departure saved, one native observer/background scene following Timur to examine independent arrival/new-place creation; restore player POV without another model call. No player action is assigned to Timur. | 6 | 9 |
| Campaign / #239 `campaign/011/before`, failed job `df90fbfbb25c4018911b4ba13c2d8f77` | One eligible Extraction retry only: same original text, absolute minute2631444, complete player provenance, no invented call/commitment. No campaign continuation. | 1 | 2 |
| **Total** | **5 saved-text jobs + 6 authored jobs** | **17** | **28** |

Use `intent.json` verbatim for original inputs. Social's only additional input:
«Я согласен сейчас сортировать фотографии по датам, оставляя оригинал карты на месте.
Прошу Веру показать первую пачку.» Family observation:
«Я остаюсь рядом и наблюдаю, что происходит с Верой, не вмешиваясь в её действия.»
Phone noninterference:
«Я не удерживаю Тимура и продолжаю разбирать фотографии. Не предлагаю ему место назначения.»
The observer step uses the native background operation with Timur as camera subject,
empty player input, and no Time Skip. If no real arrival/new place/room-exit occurs,
record that contrast as **NOT OBSERVED**; do not force an outcome or reroll.

Expected **17 calls without repairs**, at most **28** for listed jobs. Reserve four
calls for auxiliary production stages only if they actually occur: proposed total
ceiling **32 calls / $1.00**. At verified peak/cold Flash prices of $0.30/M input and
$1.20/M output ([official pricing](https://api-docs.deepseek.com/quick_start/pricing/)),
even pessimistically charging65536 input +8192 output for every one of32 calls is
$0.9437184. This overcounts the context window intentionally; no cache/off-peak
saving is needed. Recheck tariffs before execution. This plan grants no paid-call
authorization and does not reuse the previous run's allowance.

After every step inspect the full prose alongside both Extraction responses,
diagnostics, Events, movements, final_scene, character_changes, Knowledge and
History. A saved status is not semantic acceptance. Check UI/reload on desktop and
mobile using the same saves, with no paid replay. Any semantic contradiction or
unknown provider outcome stops dependent steps; retain every original receipt.
Old siblings, revisions, input and source archives must remain unchanged.
