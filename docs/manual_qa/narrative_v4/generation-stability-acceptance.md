# Generation stability and quality — PR #116

Audit base and fetched PR head: `69de2cda49e69407433203636ad639fc36239749`.
All earlier calendar, DOB, editor, fragment, Motivation and Resume changes are retained. This is an incremental update to the same generator and Runtime; no #105 pipeline or #117 graph was imported.

## Immutable evidence

| Fixture in `tests/fixtures/initial_world` | Candidate | SHA-256 |
| --- | --- | --- |
| `generation_response_calendar.json` (E1, unchanged) | 329 | `e1825af870cae2d8326bc2e70cbd8da43738c3fcd4d4852a569f04f0a7c19e58` |
| `generation_response_stability.json` (E2) | 339 | `9d4c22292be2ccd3bee8ba78e7c7b58f452a5d55521e412c5dc128c41b353372` |
| `generation_response_missing_reference.json` (new attachment `generation-response (2).json`, E3) | 351 | `1963faa9457d186438678fee4d31be22fd622d0d346a2044488c8ba7a343dad4` |

Tests hash the original bytes and replay actual malformed reviewer responses and the actual E2 repair. E2's exact candidate exposes `/world/residences/res_ilya/until_date` rather than `/`. Its pre-final-repair test state is explicitly a **reconstruction**: reverse only the four recorded final assignments on a copy of the snapshot. It is not presented as a historical snapshot. The actual repair then fails atomic trial validation, leaving the source unchanged.

E3 originally reports `missing_reference` on three dictionary collections. Type checking now returns three actionable report errors without a membership operation on a dict/list. The two independently valid fact remarks survive. The recorded three-item corrections, including repeated and empty replies, cannot erase them. A real-API Resume test keeps the world response bytes, uses the saved candidate, makes two controlled review calls, and makes **zero further calls** on unchanged Resume after an identical item-correction failure.

## Implementation and boundaries

| Area | Result |
| --- | --- |
| P0: repair acceptance | Every scoped automatic assignment/add/remove is trial validated before candidate acceptance. Raw rejected responses, before/after diagnostics and hashes remain in `repair_failures`; accepted candidate text is not replaced. Initially invalid worlds can retain independent existing errors. Newly exposed validation failures are quarantined as unresolved, not asserted to be introduced regressions. |
| P0: dates | Phase dates use the active Gregorian/custom profile and exact paths. Reversed dates have a chronology diagnostic. A partial year cannot become an invented January 1: repair must retain the year in context/evidence and set the exact date null. |
| P0: operation permissions | `response_schema` matches assignment, scoped removal and linked-location operations. Diagnostic paths do not grant removal. Removal needs explicit `remove_paths`, matching candidate hash and exact prior record; duplicates and overlapping paths are rejected. Linked location/reference packets are checked after all operations. |
| P0: reviewer | Contract v5 retains assertion, target, original issue, record matcher and concrete basis. `missing_reference` accepts only a nonempty scalar string ID and a target ID map. `missing_record` checks identifying fields in a record collection. Blank strings/containers are missing; zero/false are values. Supplied basis is checked against the snapshot. |
| P0: semantics | Travel/current position is not residence closure; unknown housing remains optional. Destructive residence lifecycle changes without two concrete basis records stop for author clarification. Directed feelings and symmetric kinship remain separate. Reviewer still judges semantic incompatibility; exact basis validation is not a proof of natural-language truth. Genuine blockers are not globally downgraded. |
| P0: correction/Resume | Valid sibling issues are retained when only rejected items are corrected. Empty corrections cannot erase them. Repeated identical item corrections are fingerprinted and stopped across unchanged Resume. Candidate/settings/model/contract changes invalidate the relevant review key; general envelope failures can still be explicitly retried. |
| P0: lossless intake | NPC legacy short goals enter canonical goals only at initial generation, so a later manual clear stays clear. Conflicting dual representations remain visible. An inherited player-only short goal is retained with an agency diagnostic, not silently turned into a decision or discarded. |
| P0: duplicate data | Compatible directed-pair dimensions and contexts merge without averaging; reverse pairs remain independent. Conflicting relationship values and Knowledge statuses stop instead of last-wins. Canonical comparison checks supported Relationship and Knowledge fields. Character ID normalization does not rename prose field keys. |
| P0: time ownership | Model-provided authoring metadata cannot create manual provenance. Server-owned resolved clock values survive unrelated normalization/repair; manual editor writes update their resolution explicitly. Automatic repair cannot change protected clock/DOB/provenance. Existing deterministic DOB and old-save behavior are retained. |
| P0/P1: progress | Accepted field value histories detect returns to earlier values, including cosmetic whitespace cycles. Rejected trials do not enter that history. Manual recovery epochs allow legitimate author changes. |
| P1: schedules | Draft schema/validation accept nullable due time and preserve temporal anchors, intervals, dependencies and location through migration. New generation uses explicit time semantics: zero is a real minute, null is unknown. Existing saved legacy zero-sentinel semantics remain unchanged. |
| P1: quality | One optional batch is selected from reviewer recommendations, without length quotas or per-NPC requests. It uses the same atomic boundary and one bounded full re-review. A rejected optional enhancement keeps the previously validated world and shows an author warning. Successful re-review is cached against the actual enhanced candidate; unchanged Resume adds no calls. |
| P1: budgets/prompts | World/review/repair/quality have size-based output envelopes under the existing overall token/cost reservations. Saved user prompts are not overwritten; only known bundled hashes upgrade. Journals record prompt hash and bundled/custom/legacy contract provenance. Existing in-flight messages and completed responses remain intact. |

No schema-constrained DeepSeek API experiment was added. Existing provider abstraction and JSON mode remain; JSON mode is not advertised as semantic validation.

## New-workspace integration

`tests/fixtures/generation_scenarios/inputs.json` contains the six independent ideas and expected invariant categories: E2 from scratch, modern daily life, explicit historical date, custom fantasy calendar, adoption/asymmetric knowledge, and organizations/unknown addresses/unscheduled plans.

`tests/test_generation_scenarios.py` creates **six empty workspaces** and exercises real application APIs for generation → author title edit → Resume → confirm/Start Game, then the existing engine with controlled start and ordinary-turn replies, and reopens SQLite. It imports no `candidate_snapshot` into these jobs. Source briefs, manual title, canonical relations, Knowledge, facts and possessions are compared across save/reload. Custom-year rollover and birthdays use Runtime calendar functions. These are deliberately controlled provider fixtures, not samples of model quality.

The existing E1 exact-candidate recovery still exercises the same saved world through manual edit, Start Game, ordinary turns and reload. The controlled deletion adjudication now explicitly supplies the new removal permission rather than inheriting it from a diagnostic.

## Validation

Local full backend run: **1704 passed in 210.21s**. After the final defensive intake guards and strengthened scenario fixtures: **64 focused tests passed in 14.09s**, including all six fresh-workspace paths. Production build, compileall, dependency consistency and diff whitespace checks passed. Exact published-head CI status is recorded in the PR description. Commands used:

```sh
HF_HUB_OFFLINE=1 python -m pytest -q
HF_HUB_OFFLINE=1 python -m pytest -q tests/test_generation_stability.py tests/test_generation_scenarios.py
cd frontend && npm run build
```

Production build passes with the existing large-chunk warning. Earlier red runs exposed a legacy relationship metadata incompatibility, retry compatibility for report envelopes, and a stale `short_goal` in a controlled fixture that intentionally cleared player goals. Those were corrected; they are not counted as successful runs. No visual UI acceptance is claimed locally: Chromium startup was previously blocked by `socket() failed: Operation not permitted`; this change adds no new visual controls. CI and the existing desktop/mobile calendar cases provide the executable browser checks.

## Actual provider calls and live probe

**New real DeepSeek calls: 0** — world, continuation, reviewer, repair, quality and gameplay. `DEEPSEEK_API_KEY` / `DEEPSEEK_KEY` were not configured. Historical requests in the three evidence files are retained evidence, not calls performed by this change. Offline replay/mocks are reported separately above. There is no measured live success rate, quality improvement percentage, actual token/cost comparison, or baseline-vs-new live comparison.

Opt-in command (requires a configured key and an explicit finite budget):

```sh
python scripts/probe_generation_stability.py --budget-usd 2 --runs 2 --output /tmp/pr116-live-probe
```

This probe creates independent workspaces for all six ideas, splits the total reservation cap across the requested runs, records successes **and failures**, and never retries unknown pending outcomes. It saves commit, scenario, settings, contract, request rows by stage, actual tokens, elapsed time and known costs. Unknown cost remains null. The probe is **generation-only**; it does not claim live gameplay acceptance. The complete editor/gameplay/reload path is currently covered by controlled integration. The script's `--help` was executed; the paid command was not.

## #78 manual follow-up and limits

Use an isolated DB for the existing #78 baseline; do not rewrite historical snapshots. In the author's actual workspace, update the application and Resume the saved candidate rather than generating again. For E3, inspect the preserved valid fact remarks alongside the three report-protocol errors. An unchanged repeat after a proven item-correction cycle makes no paid calls; an actual candidate or relevant configuration change permits a new review.

Manual desktop/mobile checks should cover warning visibility, ordinary author edits, time/calendar changes, nullable plans, Start Game, branch/rollback, and reload. Ambiguous semantic contradictions may still need author clarification. Exact snapshot evidence and bounded review protect data integrity but cannot establish that an LLM's prose is correct. No live model-quality guarantee or completed visual inspection is asserted.
