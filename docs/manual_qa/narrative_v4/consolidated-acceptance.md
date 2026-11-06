# PR #116 consolidated recovery and presentation acceptance

This follow-up starts at `d9292c98a6f4311407e351638e7121bc3e8ff5cc`.
It preserves the existing generator, append-only drafts, Runtime, provider budgets,
fragment assembly, Motivation and relation normalization. No #117 graph is added.
Exact final command counts, published SHA and Actions conclusion belong in the PR.

## Evidence and P0

`tests/fixtures/initial_world/generation_response_review.json` is the second user
journal, copied unchanged after checking for credential fields/token patterns:
`90b08ec8b348956ea76c55536806a46fa5ff59e2c465fc7e6c9c9aeb50579b6e`.
The earlier overlap fixture retains
`a72bbdb4f2861bea0a58e2935b131031aea60cc9801256209e82912845f2bfdd`.
The complete 80,363-character world requires **zero** continuation/world calls.
All four real reports retain their 34/33/33/33 messages. Their 6/3/2/1 address
problems become recorded navigation warnings for recommendations; unsafe patch
paths are removed, never expanded. The final calendar alias resolves only because
`/world_clock/calendar` exists. List IDs resolve only with a unique exact match;
`world.characters` never redirects to character cards. Unknown severity, duplicate
keys, broken envelope, truncated JSON and malformed substantive items still fail.

This export does not contain the full frozen author input or candidate snapshot.
The documented reconstruction hash is
`9d8704c9c79c513f49ff3f6cecbe6c6e6cd630a10e3f0afe4f1cc0d0fd5e21c7`, not the journal's
`44e4b82777a8a0902fb2094c7ba8eb1f43b29034a612d3fd210809d3d3200599`.
Consequently tests do NOT claim byte-identical reproduction of the user's edited
candidate or a live test on the user's workspace. They do not substitute the older
Volkov brief for the missing frozen input. The new author-only raw export includes
the current candidate/version and author text/source/outline, excluding config and
credentials. Original replies and failure records remain separate and immutable.

The reconstructed-world integration test performs three controlled requests:
review → exact biography/situation patches → review. It reconciles the age/adoption
clauses and Yura's situation with the existing court location; it does not invent a
prosecutor location in Python. One subsequent author title edit needs one review.
It then runs Start Game, start, ordinary turn, SQLite reopen and another turn.
Knowledge, relationships, symmetric ties, contacts, residences, Motivation and
unchanged raw world parts are asserted. No new world or continuation is requested.
These are **controlled model replies**, not proof of live semantic recall. Existing
night/departure/appointment prose remains subject to the full reviewer; no Python
regex classifier infers prose truth or reclassifies recommendations as blockers.

## Review operation

Contract v3 adds actual roots and card/location ID→index addresses. A complete,
current-input report can be reparsed locally; changing contract/input/candidate
requires a current review. A valid recommendation with an invalid optional link
keeps its text and original issue, with a protocol warning and no unsafe mutation
permission. Genuine blockers remain blockers. Recommendations never run patches.

Report-format correction sends only rejected items, exact error paths, address
information, author constraints and relevant addressed values. Correct siblings
stay in code and are merged back in their original positions. Missing/repeated
correction items fail; raw provider output remains journaled separately. It does
not accumulate full world audits in successive correction messages. Attempts and
all existing reservations/caps remain bounded; repeated no-progress failures stop.

## UI coverage and boundaries

`runtimePresentation.tsx` is a disposable view of the supplied server-filtered
state, not a canonical model. Field names and enums are localized; nested values
are recursive lists/definitions, not implicit object strings. Null, false, zero
and empty collections differ. Missing references show a diagnostic placeholder;
original IDs/data remain in author technical details. The editor advertises only
server-allowed fields and uses Runtime enums. Extension evidence and nullable
periods follow their actual model contracts instead of legacy list assumptions.

| Section | Data / view coverage | Edit / persistence / visibility |
|---|---|---|
| Cards, life status, stage, physical state | populated `runtime_presentation.json`; scalar/null/boolean component cases | existing actor/card edit; browser and backend start/reload; public server projection retained |
| Capabilities, personality, appearance | populated synthetic restrictions and nested items; false vs unknown | existing JSON field editor; no flattening; author-only dynamic details |
| Goals / intentions / obligations | existing populated Motivation fixtures and browser suite | all three edit metadata/start/reload regressions preserved |
| Calendar / opening / locations | Friday 23 October 2026 08:00; next day; custom two-month/three-day calendar; relative date | Runtime calendar functions on server; calendar editor; browser screenshot; numeric clock remains authoritative |
| Birth date | exact age boundary at current world date; generated/null compatibility; leap/custom arithmetic covered by calendar suite | explicit field AI request now carries card age and calendar; no automatic fill on import/reload |
| Directed feelings | existing real-world and synthetic relationship records | existing separate A→B editor and visibility; no merge with objective ties |
| Objective ties | exact participant resolver, directional vs symmetric heading; existing merge/recovery fixture | existing fields, relation merge and revision checks; full graph is #117 |
| Residences | two actors, one location, active and historical phases; grouping by actor/location | browser edits context and reloads; nullable periods retain type; current position independent |
| Contacts | owner, label, optional identity/address/status; hidden identity component case | Runtime enum editor; author-only extension data; no invented phone number |
| Communication settings / other retained world structures | recursive read-only view under More | explicitly marked read-only; do not fabricate conversations/remote events in the initial-world schema |
| Organizations / roles | synthetic organizations and roles plus real group data | existing field editor / canonical start; names resolved from current records |
| Facts / Knowledge | real and synthetic secret/provenance fixtures; actor+fact headings | existing edit and server Knowledge filtering; character_ids is not a knower list |
| Scenes / events / threads | existing world suites; named scene locations and nested temporal values | existing editor; future scheduled records get typed field editing; history remains separate |
| Possessions | distinct synthetic owner, holder, place, availability | model validation and Start Game/reopen assertions; no inventory subsystem |
| Conditions | restriction effects and string evidence fixture | Runtime typed edit, no forced evidence list; canonical validation still applies |
| Pregnancy / reproductive events / naming | separate valid `runtime_family.json`, created through Runtime test fixtures | author browser rendering and backend Start Game/reopen preserve all three maps; public draft does not expose them |
| Values / name history / identity metadata | generic nested renderer; existing domain persistence regressions | existing allowed actor fields; technical/provenance blocks retained; not a new specialized form |
| Empty / unknown / invalid references | component cases plus empty sections in both synthetic worlds | invalid references are recovery diagnostics, not claimed valid worlds |

Browser coverage includes the existing creation/review/fragment/Motivation/merge
suite and two additional complete author-world scenarios on desktop/mobile.
Component cases exercise nested values, localization, missing refs, direction and
concealed contact identity. Screenshots are inspected; overflow is asserted.
This is a readable field editor, not the full form/graph constructor from #117.
Graph dragging, auto-layout, gestures and a graph keyboard alternative remain in
#117; they are not duplicated here. Specialized forms for each nested model are
also not claimed by this PR.

## Existing workspace recovery

1. Update this branch, stop the old app normally and restart it. Open the **same**
   workspace. Do not remove SQLite, discard versions or click Create world again.
2. Open author view if the player view is withheld. Inspect the saved result and
   diagnostics. **Проверить структуру локально** does not pay for a semantic audit.
3. Click **Повторить проверку**. Complete saved world parts are reused. Only the
   unfinished check/necessary exact repairs run. Current context/output settings
   apply; saved model/thinking and total spending caps remain unchanged.
4. A real blocker must be corrected/reviewed; optional navigation warnings in a
   recommendation do not block Start Game. Edits still stale the accepted review.
5. Confirm → Start Game → ordinary turn → reload → next turn. If the provider is
   unavailable or there is a real unresolved contradiction, retain the workspace
   and download diagnostics; don't regenerate an already saved world.

The contract update deliberately does not reuse a report under a different full
review signature. In that case one new semantic check of the same candidate is
necessary. Replaying old report text locally is not a claim that its severity
assignments correctly identified every real-world contradiction.

## Budgets, platform and CI

The existing HTTP 429/503, unknown-outcome, total-token/cost, context-preflight,
fragment and lineage tests are preserved. Thinking is not a JSON repair switch.
No DeepSeek key was available in this environment and no paid calls were made.
Full live-generation/model-quality acceptance remains unperformed; the saved
world was never regenerated. Windows/Python 3.14 has not been reproduced.

Launcher inspection: `start.bat` chooses `py -3` when available; `prepare()` uses
an existing `.venv` or creates one from that interpreter. It hashes requirements
and frontend sources, runs npm ci/build when changed, serves the production
bundle, and polls readiness with a bounded timeout. An already-running managed
server is reused before rebuilding. Thus stop/restart is needed after switching
branches; this is not evidence that it caused the reported WinError 10054.
Linux build, pip check, launcher tests and browser HTTP startup are separate from
Windows validation. On the laptop, preserve `.runtime/server.log`, note the venv
interpreter version, run `.venv\\Scripts\\python -m pip check`, and record build and
asset-request failures. Do not suppress all connection-reset errors or delete DBs.

The original HEAD Actions run 40123949223 completed successfully. Historical
cancelled run 40105881873 is not presented as a current failure. The existing
split desktop/mobile workflow and timeouts are unchanged. Final-head CI status
must be read after publication and reported as completed/success only if observed.
