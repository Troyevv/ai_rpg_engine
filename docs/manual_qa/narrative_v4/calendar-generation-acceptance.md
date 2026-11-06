# Generation calendar and saved-candidate recovery — PR #116

Baseline: `d502b528db56dc74d150e01f54ff4e2ffdf59202` (existing PR branch).
This extends the existing generator, editor and #78 QA surface; it does not introduce another pipeline or the #117 graph.

## Evidence and exact replay

`tests/fixtures/initial_world/generation_response_calendar.json` is the exact 266,868-byte attachment `evidence/generation-response(1).json`, SHA-256 `e1825af870cae2d8326bc2e70cbd8da43738c3fcd4d4852a569f04f0a7c19e58`. It retains original provider responses, candidate version 329 and original job identity `prep_3f54af356b3f470ebaed72b4f291215d`. Tests create an isolated DB job/epoch but restore **candidate_snapshot**, not a reconstruction from the provider's first response.

Before: numeric 79560 projects 06:00 despite the explicit author start 23.10.2026 12:00; all eight birthdays null. Recorded review contains four blockers and two recommendations.

Permitted recovery diff:

- Numeric clock 79560 → 79920, matching calendar anchor and initial scene/actor snapshots; projections become Friday 23 October 2026 12:00.
- Eight missing exact-age birthdays are deterministically completed. Birth provenance and authoring metadata record inputs, seed and ownership.
- Controlled semantic repair removes exactly the three residence records identified by the recorded diagnostics after comparing the supplied brief, generated biographies, original empty residence collection and repair history. There is **no production name/ID/location-kind deletion heuristic**. Live adjudication still belongs to the reviewer/local repair.
- Five other residences, five locations, all IDs, biographies, traits, opening text, facts, Knowledge, feelings, contacts and possessions stay intact. Historical events and schedules are not globally shifted.
- `r3.attraction=40`, `r4.attraction=85`, `k4.status=known`, `k4.source_event_id=null`, `k5.status=suspected` survive preparation. The protagonist does not move in with Katya or accept her trip by recovery.

The API integration test resumes the saved candidate, edits its title, checks again, reuses the accepted unchanged review, confirms, starts, performs two ordinary turns, and compares each persisted snapshot exactly to a freshly opened SQLite repository. Source hashes are checked again after execution.

## Ownership and compatibility

- Optional `calendar_start` settings are carried by the existing CreationSettings/API/config/draft contract. Defaults are auto/null, never today's machine date. Explicit calendar/date/time fields resolve independently; localized exact `Сейчас`/start clauses and ISO/Russian dates are parsed deterministically.
- Authoring completion runs on generation/explicit Resume, not import/read/save migration. Existing canonical calendar functions own dates, weekdays, leap policy, custom month/week lengths and local time. Unsupported values stay addressed errors.
- Saved manual clock/calendar edits become authoritative; only incompatible previously automatic DOB can be recomputed. A manually edited DOB (including null) retains manual provenance. Exact-age absent DOB uses seed + stable ID, not a global RNG or process hash. Explicit unknown and `birth_provenance.twin_group` constraints are supported; approximate ages remain unknown.
- Birth provenance is copied through the existing migration boundary. No database schema change or historical save rewrite is required.
- Review contract v4 adds typed missing-value/reference/optional-detail predicates. False structural claims cannot authorize mutation. Recommendations never enter mandatory repair. General semantic findings still require a valid localized report.
- Repair response caching includes candidate content, request and contract, fixing reuse of an old numbered repair against a changed candidate. Linked residence packets require matching hash, exact deletion preconditions, scoped paths, unique new location IDs and validation before commit. Reapplication cannot duplicate records; stale packets fail. No-op repair stops rather than spending repeated attempts.
- Public draft responses do not expose authoring notes or full saved creation settings. Existing Player View/Knowledge filtering remains authoritative.

## Automated checks

Focused acceptance: `HF_HUB_OFFLINE=1 python -m pytest -q tests/test_generation_calendar.py tests/test_initial_draft_v4.py tests/test_draft_world.py tests/test_draft_response_v4.py tests/test_review_protocol.py tests/test_consolidated_review.py tests/test_draft_recovery.py` — 158 passed on the tested implementation before the final author-only settings projection adjustment; that adjustment is checked separately.

Full backend: **1673 passed in 207.71s**. Subsequent calendar weekday/presentation adjustments: **158 focused passed**, followed by **50 passed** after author-only settings projection. Frontend production build passed (existing bundle-size warning). Final publication/CI results are recorded in the PR description. `npm run build`, compileall, diff whitespace check and pip dependency consistency were exercised. Earlier red runs are not counted as success: they exposed and led to fixing malformed-JSON repair hashing and creation-setting precedence; existing equality tests were updated to assert the new hash/completion contract.

Browser tests: `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/calendar-browser/chrome-linux64/chrome HF_HUB_OFFLINE=1 npx playwright test e2e/calendar-creation.spec.ts --reporter=line` was attempted on desktop/mobile. Chromium 153 crashes before opening any page: `socket() failed: Operation not permitted`. No visual pass or screenshot inspection is claimed. Added browser cases cover empty defaults, persistence, calendar settings in API/preview, custom day 40 and validation notices; they still need execution in CI/an environment that permits browser startup.

## Provider accounting

**Live DeepSeek calls: 0 at every stage** (generation, continuation, review, repair and gameplay). No configured DeepSeek key was available. No live model success is claimed.

Exact-candidate offline recovery: zero world/continuation calls, zero special time/DOB calls; two controlled reviews + one controlled residence repair. Manual title edit adds one controlled review. Another unchanged Resume adds zero calls. Gameplay uses the repository's controlled `raw_for`/`play` fixture for start + two turns; this is separate from live provider accounting. Paid historical journal usage is retained, not reported as new spend.

## Continue the user's existing draft

Update/restart the application; open the **same workspace**, enable Author World and click **Повторить проверку**. Do not delete the database, reimport the fixture or generate a new world. Resume uses the current saved candidate/manual edits, completes time/DOB, then checks the changed world under the new report contract. If a real semantic blocker remains, its addressed repair stays recoverable. Inspect dates and residence, confirm, start, make an ordinary action and reload.

## #78/manual QA sequence

1. Load the existing #78 baseline into an isolated dev database through its documented loader; do not modify the stable baseline fixture. For custom creation checks, create a separate draft with explicit custom profile [40,40], three weekday names and date 0042-02-40, time 23:59.
2. In both Quick Creation and Scenario Creation, verify auto blanks, explicit field precedence, reload persistence and no client timezone conversion. Invalid lengths/date must have an actionable error.
3. In the generated author draft, edit start time/date and a birthday, Resume and confirm. Check that manual values remain; unrelated histories and relationships stay identical. Check a pre-existing imported null DOB stays null without explicit recovery.
4. At runtime advance past midnight/month/year, save/reload, branch/rollback through existing game controls; birthday and calendar projections must follow canonical snapshots, never re-run authoring completion.
5. On desktop/mobile check controls, month/week labels, notice text, birthday cards and horizontal overflow. These visual and branch/rollback actions are a remaining manual checklist, not a claim of completed browser validation.

Limitations: extraction intentionally handles explicit start clauses, not arbitrary natural-language temporal reasoning. Ambiguous clauses, implied kinship chronology and semantic housing choices still rely on the existing reviewer; typed twin/unknown provenance must be supplied by generation/author. No live reviewer-quality or visual acceptance result is available in this environment.
