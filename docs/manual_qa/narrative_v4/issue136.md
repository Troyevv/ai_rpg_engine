# Issue #136 — Narrative authority and Extraction acceptance

## Baseline and scope

Implementation starts from `master` **c64505465737b6ed9db8f014a00c5248f2825884**
(rechecked through GitHub after implementation). Read repository `AGENTS.md`, Epic #36,
#136 and #134. PR #133 is merged (parent 21be61435fbcebe1e7e9e58f33e59658d3050d9e).
PR #135 HEAD e92ae9e3294ff8919e363f013ed6701e358311c8 was inspected; its observed
characters, context/UI and regression ideas were integrated selectively. Its arrival
proof gates were not carried over. #135 remains open; neither PR is merged by this work.
Branch: `codex/issue-136-narrative-extraction`, target `master`.
PR: https://github.com/Troyevv/ai_rpg_engine/pull/137 (open; no automatic merge).

The original user's failed job/SQLite/provider response is unavailable. Existing E5
export and #78 test-world fixtures supply the integration worlds; all new narrative
and Extraction responses are explicitly **synthetic**. They are not live traces.

## Architecture and implemented behavior

Player owns voluntary Controlled Actor decisions. DeepSeek authors the story and NPC
actions. Extraction interprets the completed story. Runtime validates structure,
identity, provenance, chronology, Knowledge, agency and explicit world restrictions,
then commits the canonical world and History atomically. Director/Pacing preferences
steer future generation; they cannot license an already completed NPC event retroactively.
This clarification is recorded in `AGENTS.md`; its agency/source requirements remain.

* `final_scene.present_character_ids` owns physical membership. NPCs synchronize to
  the camera location without `movements`, arrival assertions or literal name/place
  quotes. This creates technical `derived_from=final_scene` position history, never
  an invented arrival Event or route.
* `observed_character_ids` is a disjoint, persisted Camera field. Observed characters
  are available to context/Inspector while outside the physical scene. No artificial
  boundary location is required. Remote contact remains distinct; visibility grants
  no Knowledge. Unknown departure positions become null, not invented destinations.
* Ordered explicit routes remain in History. Known endpoints, origin consistency,
  duplicate/unknown IDs and player-owned or accepted involuntary movement sources
  are checked, including movement of the protected actor outside the POV camera.
  Initial framing of a turn-zero save with no camera is still compatible.
* Malformed optional Pacing/initiative/continuity/projection annotations produce local
  diagnostics. Death, injuries, roles/residences, agreements and call termination keep
  their canonical outcomes. Invalid essential sections and established commitments
  use the existing bounded repair instead of silently disappearing. Explicit risk
  switches remain hard pre-commit constraints; settings and Tabletop were not changed.
* Ordinary turns require an explicit nonnegative integer `elapsed_minutes`; zero is
  valid. Start/POV retain compatibility. Time Skip and background/LTA keep their
  existing deterministic clock owners. The old prose-based sleep override is removed.
* Existing two-attempt Extraction repair uses the same before/context/narrative.
  Classified vital outcome identity is retained across repair and manual Retry after
  restart using existing request logs. Contradictory/omitting repair fails atomically.
  No new mandatory LLM stage, hidden regeneration or larger retry/token budget exists.
* Streaming text is visibly provisional until commit. Failed jobs preserve input,
  response and diagnostics but do not create a canonical turn. Existing revision,
  worker epoch, rollback, variants and regeneration mechanisms remain authoritative.

## R01: validation audit and disposition

`issue136-evidence/baseline-guards.txt` preserves the initial source inventory.
`issue136-evidence/validation-sites.json` expands the immutable baseline inventory
with every fatal/reject/warning/error site in the Narrative runtime and commit owners.
The table below supplies the disposition by owner/invariant; inventory entries retain
source line, enclosing function and source expression for review. Inventory is evidence
of inspected code, not a claim that every possible malformed input was exhaustively tested.

For every rejected patch below, **before remains canonical and no partial after is
committed**. A recoverable error may yield one repaired after from the same narrative.
For optional warnings, only the annotation is dropped and the domain after commits.

| Owner / invariant | Before → after policy | Recovery / test evidence |
|---|---|---|
| raw envelope, essential sections/types/unknown keys | silent loss → repairable path diagnostic; empty optional sections remain no change | authority136, fuzz, corpus |
| raw bounded Knowledge/profile input | silent truncation → explicit overflow; bounded context projection stays independent | knowledge_lifecycle, possessions |
| resolver arrivals / situation anchors | literary proof gate → authoritative typed scene and derived position | authority136 T45–T50, runtime_handoff |
| resolver IDs, explicit endpoints/origins, canonical fact identity | retained structural blocker | runtime_v3_domain/corpus/fuzz |
| camera known/unique/disjoint participants, controlled actor | retained; observed added; protected movement strengthened | authority136, protagonist, pov |
| life / condition / social state transitions | missing NPC quote no longer rejects; malformed established transition repairs | life_social, corpus, authority136 death/retry |
| residence / roles / geography | source/identity/chronology retained; established malformed changes repair; repeated identical phases idempotent | residence_roles, corpus |
| pacing candidate, intensity budget, classification, happy preference | optional attribution/generation steering; never an outcome permit | narrative_pacing |
| pacing explicit user risk exclusions / death policy | retained hard pre-commit restriction; no partial canon | narrative_pacing, protagonist |
| initiative annotation IDs, budgets, response hints | malformed auxiliary attribution warns; actual accepted Event persists | npc_initiative |
| initiative player source, adult/capability and Knowledge ownership | retained technical/agency boundary | npc_initiative, knowledge |
| continuity beats/transitions/compression, pending-response hint | local warning/guidance; no manufactured response or elapsed-time gate | narrative_continuity, temporal_guard |
| continuity canonical thread reopening / calendar boundary | retained source and chronology blocker | narrative_continuity, temporal_guard |
| commitments sources, identity, assent, temporal/dependency graph | structural rejection now repairs, never saves an established agreement as no change | commitments, commitment_readiness, phone133_followup |
| remote semantic adapter | carries StructuralDeltaError into existing phone semantic diagnostic/recovery | phone122/133, remote_decision_contract |
| call lifecycle | typed completed NPC hangup accepted without literal quote; player command/call ID remain strict | call_continuity, phone133_followup |
| call historical agreement sources | exact immutable source/author binding retained, not a literary interpretation | call_continuity, phone133_followup |
| physical projections / choice hints | presentation fallback from accepted Event; no event or physical location inferred | call_continuity, browser call-continuity |
| Knowledge witness/event/fact/medium/revision | no narrative substring judge; all ownership and belief boundaries retained | knowledge_lifecycle, relationships |
| personality / values / motivations | no NPC prose match; accepted experience/source lifecycle, player ownership and revision retained | personality, goals_values |
| appearance / possessions / reproduction | no NPC literary anchor; accepted source Event/identity/state transition and player boundary retained | appearance, possessions, reproduction |
| models / migration / old snapshots | strict current invariants; absent observed reads as []; historical bytes unchanged | runtime_handoff, runtime_v3_storage |
| background / simulation / LTA | protected actor/visible Knowledge and clock invariants retained; same resolver/atomic batch | background_time, long_term_advance, temporal_guard |
| engine / storage commit | original lineage, epoch/revision, one atomic commit retained; all terminal structural diagnostics recorded | repair_policy, runtime_handoff, runtime_v3_storage |

Remaining exact matching has a specific technical purpose: player-owned input,
immutable phone source attribution, or selecting an optional presentation excerpt.
It does not decide whether an NPC entered, died, moved or completed an action.

## Assembled prompt audit (R15)

The real builder sends a differing saved override once, then the current
`EXTRACTION_CONTRACT`, applicable domain contracts, time rules, schema, canonical
slice, entity IDs, choice context, player input, whole completed narrative and optional
repair feedback. The current contract explicitly takes precedence over saved overrides;
no saved prompt is rewritten. Bundled `state_update_prompt.md` is not duplicated.

| Former conflict | Current assembled instruction |
|---|---|
| completed_arrival/name/place anchors vs situation_evidence | final scene owns membership; significant routes optional |
| doorway requires boundary geography | observed is separate visibility; no boundary required |
| Director candidate / severe-event permit | report actual outcome and dependent canonical changes |
| mandatory scene_actions / favorable path / six choices | annotations and suggestions optional; player agency remains strict |
| exact NPC quote on every change / hangup | typed extracted meaning with turn provenance; historical/player sources remain bound |
| missing elapsed interpreted as zero | ordinary elapsed explicit; special clocks retain ownership |
| shorter prompt by dropping rare domains | domain schemas/contracts remain conditionally available |

Reproduce with `python devtools/measure_extraction136.py`; run the same script at the
baseline checkout root for the before result. Full assembled samples and selection
metadata are in `issue136-evidence/prompts-{before,after}.json`. No provider is called.

| Same synthetic input | Estimated input before | After |
|---|---:|---:|
| 4 actors, 20 sentences | 23105 | 23047 |
| 124 actors, 20 sentences | 23105 | 23047 |
| 4 actors, 1800 sentences | 55145 | 55087 |
| 124 actors, 1800 sentences | 55145 | 55087 |
| active phone | 25014 | 25039 |
| Time Skip | 22973 | 22905 |

These are estimator values, **not actual billed tokens or measured DeepSeek latency**.
Unrelated NPCs do not enlarge the selected context. Long completed prose is retained
whole; the phone increase is small and keeps source/agency contracts. This is a conflict
fix, not a claim that reducing prompt length improves model quality.

## R01–R16 traceability

| Requirement | Implementation / evidence |
|---|---|
| R01 | source inventory and disposition table above; baseline RED retained |
| R02 | essential vs ancillary error paths; structured diagnostics; atomic rejection |
| R03 | pacing/initiative/continuity and generation contracts; explicit risk tests |
| R04 | life/conditions/social/roles/residences and repair outcome retention |
| R05 | scene reconciliation, explicit route history, unknown endpoint handling |
| R06 | unchanged #133 phone ownership plus source-bound commitments/hangup regressions |
| R07 | existing Knowledge/POV/player/canonical/revision tests; off-camera movement regression |
| R08 | provisional JobView, real jobs and unchanged atomic commit boundary |
| R09 | same-narrative two-attempt repair, persistent diagnostics and manual Retry outcome retention |
| R10 | default observed field, old-save/branch/rollback/regen/idempotence tests; no DB migration |
| R11 | NPC literal anchors/permits removed; technical matching exceptions documented above |
| R12 | root/nested diagnostics, essential envelope/type repair and overflow detection |
| R13 | explicit ordinary elapsed; special clock owner tests; no prose-duration parser |
| R14 | independent raw-response scorer + 23-case corpus; live **NOT RUN** |
| R15 | actual assembled requests, schema validation, overrides and budget comparison |
| R16 | final-scene authority, observed scope/UI, full real API/SQLite/browser journey |

## T01–T51 evidence map

`authority136` = `tests/test_narrative_authority136.py`; `corpus136` =
`tests/test_extraction_corpus136.py` and `tests/fixtures/extraction136/semantic-corpus.json`.
Other short names refer to `tests/test_<name>.py`. Browser specs are under
`frontend/e2e`. API tests substitute provider transport only; direct domain/property
tests supplement them and are not presented as full-stack tests.

| Test | Evidence / scope |
|---|---|
| T01 | authority136 death + repair/reload; corpus136 death_ellipsis |
| T02 | corpus136 rumor/hypothesis/negation; explicit no-death assertions |
| T03 | corpus136 npc_initiative; npc_initiative accepted event without permit |
| T04 | npc_initiative malformed optional annotations; raw optional section test |
| T05 | narrative_continuity invalid beat/transition and accepted canonical events |
| T06 | narrative_pacing; authority136 death without candidate/classification |
| T07 | narrative_pacing risk switches, protagonist death policy; atomic hard errors |
| T08 | authority136 no-movement Start; runtime_handoff grammatical variants; browser entry |
| T09 | corpus136 doorway/closed_door/future_arrival/phone_remote; browser doorway |
| T10 | authority136 owned/forged/involuntary/off-camera movement; player_agency |
| T11 | corpus136 new_location/new_npc; runtime_v3_domain identity/dependency repair |
| T12 | life_social, residence_roles; corpus136 npc_marriage/npc_resigned/recovered |
| T13 | call_continuity physical event without projection/choices; desktop/mobile |
| T14 | call_continuity NPC hangup; phone133_followup and full browser journey |
| T15 | commitments, phone122/133_followup, remote_decision_contract; corpus agreement/decline/reschedule |
| T16 | authority136 Start/interaction/reload/next; browser full journey |
| T17 | authority136 structural repair one narrative/commit; repair_policy |
| T18 | authority136 omission/atomic failure; runtime_handoff restart/stale/retry; provisional UI |
| T19 | repair_policy variants; runtime_handoff old-save regenerate/variant/rollback; life_social |
| T20 | protagonist, pov_transitions, npc_initiative, knowledge_lifecycle; browser POV |
| T21 | temporal_guard, commitment_readiness, long_term_advance, background_time; browser LTA |
| T22 | browser streaming72, phone133 recovery, call-continuity and full journey |
| T23 | runtime_v3_engine/storage 100 turns; context budgets, 124-actor prompt comparison |
| T24 | runtime_v3_fuzz/storage, Hypothesis domain tests, runtime_handoff epoch/stale/duplicate guards |
| T25 | authority136 death_ellipsis, corpus136; no literal death word required |
| T26 | runtime_handoff variants and corpus historical/metaphorical/indirect wording |
| T27 | corpus136 negative outcomes scored before Resolver; no Python semantic inference |
| T28 | npc_initiative/continuity/pacing/call_continuity optional defects; authority136 |
| T29 | source/identity/revision/canon tests retained; authority136 invalid scene and forged movement |
| T30 | authority136/corpus136 count one narrative + one Extraction on success |
| T31 | raw root typo and nested life typo path tests; final-scene unknown fields diagnosed |
| T32 | authority136 real ordinary jobs repair malformed life/movement/agreement sections |
| T33 | quiet scenes in narrative_pacing/runtime tests; no required event quota |
| T34 | authority136 missing/0/5/type/range; API repair; temporal_guard/calendar boundaries |
| T35 | engine/background/LTA/Time Skip/start/POV/phone clock tests; no second clock |
| T36 | raw scorer/expected-vs-actual implementation and synthetic replays; real model **NOT RUN** |
| T37 | bounded opt-in DeepSeek evaluator; safe key absent → **NOT RUN**, zero live calls |
| T38 | authority136 actual builder/long narrative/override; before/after assembled artifacts |
| T39 | conflict matrix above; absence of obsolete permit instructions tested |
| T40 | 23 independent annotated cases + raw scorer + actual API application; live quality **NOT RUN** |
| T41 | context/Knowledge/agency/POV/remote source suites; browser POV and Knowledge |
| T42 | actual corpus schema validation; context compaction/rare-domain and reproduction/profile suites |
| T43 | six prompt samples above; phone/Time Skip/long-world budget suites; live usage **NOT RUN** |
| T44 | saved override/old-save/lineage/phone routing tests; real jobs and SQLite |
| T45 | authority136 Start, no movements/proofs, exactly two provider calls, reload/next |
| T46 | observed without boundary/movement; context/Inspector and browser doorway |
| T47 | authority136 route/history and unknown departure; corpus multi_event_route |
| T48 | corpus negative/remote/past/future/negated scenarios; phone integration separation |
| T49 | authority136 types/IDs/duplicates/disjoint/location/player-source; existing POV tests |
| T50 | runtime_handoff original E5 import, repair/retry/rollback/next; browser entry/doorway |
| T51 | old snapshot migration/read-only bytes and existing hierarchy tests; desktop/mobile observed UI |

## Required #78 integration journey

`test_required_journey_api_jobs_sqlite_phone_reload` and browser
`136 complete journey` use the #78 phone world and real API/jobs/Runtime/SQLite:
Start Game → arrival without movement → interaction → observed doorway/unknown
position → call → explicit player offer/NPC assent → scheduled agreement → NPC
hangup → reload → ordinary next turn. Assertions cover physical vs remote membership,
clock, preserved agreement and no duplicate turn. Browser runs at desktop and Pixel 7
viewports and checks horizontal overflow. E5 #134 entry/doorway reproductions separately
retain all 19 identities, prior Knowledge, one Extraction per turn and subsequent contact.

## G01–G21 acceptance interpretation

| Gate | Evidence / limitation |
|---|---|
| G01 | AGENTS clarification and architecture above |
| G02 | canonical death/arrival/movement/agreement tests without narrative permits |
| G03 | optional annotation and projection regression suites |
| G04 | tested outcomes and History agree atomically; arbitrary model omissions remain a live-quality limitation |
| G05 | strict ownership/Knowledge/canon/risk/revision guards and negative tests retained |
| G06 | bounded targeted repair, persisted diagnostics, restart/omission protection; no automatic infinite retry |
| G07 | expectations updated to new authority contract, essential-loss assertions strengthened; no new skips |
| G08 | actual API/SQLite, desktop/mobile and lineage/budget suites; live explicitly separate |
| G09 | no SQLite schema migration or second store; default observed and historical-byte tests |
| G10 | regression report below; no claim that synthetic tests prove all future model outputs |
| G11 | owner audit and semantic-vs-source exceptions; T25–T30 |
| G12 | meaningful unknown/malformed essential sections repair, empty sections remain valid |
| G13 | ordinary elapsed explicit, special clocks preserved |
| G14 | raw-response benchmark and report exist; real DeepSeek **NOT RUN** |
| G15 | current assembled contract removes arrival/Director permits and preserves source rules |
| G16 | before/after samples and schema/domain coverage; live semantic non-regression is not established |
| G17 | default/custom/phone/background paths and saved lineage tested; live limitations explicit |
| G18 | present authority is enforced at existing resolver/Camera boundary |
| G19 | observed/remote separation in canonical state, context and Inspector; no boundary invention |
| G20 | explicit intermediate Events/routes and protected movement preserved |
| G21 | E5/#78 real integration and desktop/mobile; #133 preserved, #135 untouched |

## Results and compatibility

* Frontend `npm run build`: PASS (existing bundle-size warning only).
* Frontend `npm test`: 34 passed across 3 files.
* Playwright selected desktop/mobile matrix: first 48 passed in 7.8m; final repetition
  and the intervening mobile timeout are documented in the delivery-results appendix.
* Focused suites: 132 passed (authority/commitments/Knowledge/#133/corpus), 232 passed
  (risk/initiative/life/residence), 62 passed (diagnostics/repair/#133/authority).
* Initial baseline: 7 RED regressions; see `baseline-red.txt`.
* Complete backend: **2297 passed in 800.89s (13:20)** on the committed production
  source. `issue136-evidence/backend-final.txt` contains the full result.

Screenshots inspected: `issue136-evidence/authority136-journey-{desktop,mobile}.png`,
`authority136-doorway-mobile.png` and `authority136-entry-desktop.png`. No horizontal
overflow or uncaught page errors in the new entry/doorway scenarios. Browser runs used
Chromium via `PLAYWRIGHT_EXECUTABLE_PATH`; no browser dependency was added to the project.

No database migration, rewrite of old History, additional runtime, mandatory provider
call or production dependency was introduced. Old snapshots without observed membership
read as an empty list; snapshots already containing it retain it. Legacy movement hints
are diagnosed but do not become arrival permissions. `assertion=established` and NPC
`evidence` are optional where the typed domain change already expresses the outcome;
producer schema and consumer behavior agree. Player and historical phone source fields
remain mandatory where they establish ownership.

## Live quality and unverified scope

**DeepSeek: NOT RUN.** No safe user-owned `DEEPSEEK_API_KEY` is available. No paid
calls were made. `issue136-evidence/deepseek-report.json` records zero calls; synthetic
fixtures must not be reported as real model accuracy, recall, latency or cost.

Opt-in reproduction (after supplying a safe server-side key and choosing a model/budget):

```bash
python -m devtools.evaluate_extraction136 --live --model MODEL --max-cases 3 --max-tokens 4096 --output /tmp/extraction136-live.json
```

The evaluator captures raw expected/actual before Resolver, structural validity,
false negatives/positives, identity/time mismatches, model/contract/prompt/schema hashes,
usage and latency. This is a one-pass Extraction benchmark (`repair_attempts=0`);
live repair effectiveness and long open-ended campaigns are **not measured** here.
The corpus is small, synthetic and cannot prove universal semantic completeness.
Actual real-device mobile browsers, production deployment and the original user's
unavailable failed DB trace were not tested. Pixel 7 here is Chromium viewport emulation.


## Delivery results (2026-10-28)

Production code tested: `2abe43a81ba8af9f24b4833246ae66fba9c69862`, tree
`e2710c413b5b5266e05f7a939c3d0cdb67dbbf27`. Subsequent commit
`f814b78608a29598b28c0f7baa02b3bb151f87f1` changes only the browser Retry test;
final documentation/evidence commits do not alter production behavior.

| Command | Result |
|---|---|
| `python -m pytest -q` | 2297 passed, 800.89s |
| `cd frontend && npm test` | 34 passed, 3 files |
| `cd frontend && npm run build` | PASS; existing bundle-size warning |
| `npm run test:e2e -- runtime-handoff.spec.ts --project=mobile --repeat-each=3` | 3 passed, 44.3s |
| Final selected desktop/mobile matrix below | **48 passed, 7.3m**, final test source f814b78 |
| Real DeepSeek evaluation | **NOT RUN**, no safe key, zero live calls |

Browser command (run from `frontend`, with the locally available Chromium path in
`PLAYWRIGHT_EXECUTABLE_PATH`):

```bash
npm run test:e2e -- narrative-authority136.spec.ts call-continuity.spec.ts phone133.spec.ts runtime-handoff.spec.ts pov.spec.ts knowledge.spec.ts long-term.spec.ts commitments.spec.ts narrative-continuity.spec.ts npc-initiative.spec.ts narrative-pacing.spec.ts streaming72.spec.ts
```

The intermediate repeat had 47 passes and one mobile Retry timeout. Trace evidence
showed a successful `saved` job after 13.218s, including 11.041s validation/apply;
the UI assertion allowed 12s. Backend and browser suites were running concurrently;
the individual delay was not profiled. The test now allows 30s for that real commit
and retains exact canonical/provider assertions. Cleanup no longer masks an original
failure with incomplete call counts. Three mobile repetitions passed. See
`retry-timeout-diagnosis.json`, `retry-repeat.txt` and `e2e-final-48.txt` in
`issue136-evidence`. This is a test timing correction, not a claim of a Runtime
performance improvement.

The final backend run covers all collected tests, including Tabletop regressions.
The local browser result is the explicitly listed 48-test acceptance matrix, not a
claim to have run every browser spec locally. GitHub's workflow runs its full browser
projects separately; its live status is linked on PR #137. CI status is not used as
proof of real-model Extraction quality or unobserved production behavior.
