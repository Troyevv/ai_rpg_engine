# CI: required gates and full regression

## Execution and dependency policy

`verify` requires backend pytest, frontend Vitest, TypeScript + production build,
and a valid selection plan. Backend and frontend run concurrently. Browser jobs
start after frontend, without waiting for pytest. The production bundle is built
once and transferred as a run-scoped artifact. Only pip/npm download caches are
reused; databases, browser profiles and application state are never cached.

`e2e-smoke` is the stable required aggregate for both desktop and mobile. It
requires four successful shard jobs and validates their JSON reports, including
actual passed tests in every critical suite on both projects. A skipped job,
missing report, empty collection, timeout, interrupted test or retry cannot pass.
When policy requires full, this gate also requires and validates full regression.
Do not make the conditional `e2e-full` check a globally required check.

`e2e-full` runs all specs on desktop/mobile, two shards each, nightly at 01:17 UTC,
via Actions → Verify RPG Engine → Run workflow, and for risky PR changes. The
nightly runs the default branch. Until this workflow is merged, a genuine scheduled
run cannot be demonstrated. Manual dispatch also requires the workflow to exist on
the default branch; do not claim it has run merely because YAML validates.

The explicit dependency map is `scripts/ci/e2e-policy.json`. Phone changes include
all phone/call specs (including new matching files), current-game, reachability,
portrait integration, communication and mobile navigation. Calendar, genealogy
and relationships include their cross-domain integration suites. Shared components,
backend/API/Runtime/state, tests/fixtures/config/dependencies and unknown files
require full regression. A failed/empty diff expands to full. Renames inspect both
old and new paths. There are no paths filters on required jobs.

Smoke uses existing real API/SQLite scenarios: dossier includes Start Game → turn
→ reload → next turn; runtime covers variants/rollback; knowledge and POV cover
canonical knowledge separation; protagonist covers controlled actor transitions;
phone and call-continuity cover messages/calls; calendar, genealogy and mobile-menu
cover navigation and persisted state. No assertions or application code are changed.
Entire critical suites run, including future tests added to those files.

## Isolation

Keep `workers: 1`. The fixture server has module-global provider modes/counters;
multiple workers sharing it are unsafe. Shards run on separate GitHub-hosted VMs:
network namespaces (including legacy auxiliary servers on 8012/8014), processes,
workspaces, environment, SQLite paths, temporary files and artifact names are
independent. Playwright creates a new BrowserContext per test by default. No
storageState/persistent context is shared. The main DB path includes lane/project/
shard in runner.temp. `reuseExistingServer: false` prevents attaching to a stale
server. Locally, set distinct E2E_PORT/E2E_DB_PATH/E2E_OUTPUT/E2E_HTML/E2E_JUNIT/
E2E_SUMMARY for concurrent runs. Full suites contain legacy fixed auxiliary ports
and evidence paths: use separate containers/VMs for concurrent full runs, not
multiple workers or unisolated processes on the same host.

## Safe rollout and branch protection

On inspection 2026-10-30, master `0d6e3c5` reported `protected: false`, protection
`enabled: false`, no required contexts, and repository rulesets `[]`. Detailed
protection read returned 403 (integration lacks administration). Protection has
NOT been enabled by this change.

1. Before allowing merges, repository Settings → Branches → Add branch protection
   rule → pattern `master`. Enable Require a pull request before merging, Require
   status checks to pass before merging, Require branches to be up to date, and
   Do not allow bypassing the above settings. Require exact check names `verify`
   and `e2e-smoke` after they have appeared. Do not require individual matrix names.
   Keep force pushes and deletions disabled. Review any admin/custom bypass lists.
2. Default rollout runs full alongside selected smoke on every PR. Leave repository
   variable `CI_SELECTIVE_ENABLED` unset until successful full/selected comparisons,
   negative-gate checks, #163 integration and measured time/cost have been reviewed.
   Both are blocking through e2e-smoke; this is intentionally not a false promise
   of immediate 5–10 minute CI during migration.
3. After evidence review, Settings → Secrets and variables → Actions → Variables →
   New repository variable: `CI_SELECTIVE_ENABLED=true`. Document the enabling
   decision. Low-risk mapped changes then run smoke + domain suites; risky changes
   still require full. Removing the variable immediately restores full comparison.
4. Re-read protection/required checks or verify them in Settings. A green workflow
   alone does not prove merge protection. Test a failing PR cannot merge.

Nightly failure is a failed visible workflow/check and creates or updates the open
`CI: nightly regression on master` issue. The dedicated scheduled-only alert job
has issues:write, no checkout and no execution of artifacts or PR code. Subscribe
to that issue/repository for notification delivery; email delivery is not proven.
A red nightly blocks declaring master healthy: disable selective rollout, triage,
fix and rerun full before resuming. There is no cross-run branch-health lock;
GitHub PR checks only govern their own commit.

## Failure diagnostics and security

JUnit, HTML, retain-on-failure traces and JSON are uploaded per lane/project/shard.
The job summary links each artifact and lists failed scenarios with errors. Pytest/
Vitest summaries report test counts; the timing job lists every job/step duration
and summed runner minutes (not exact billed minutes, which GitHub may round).
Commands run directly: no continue-on-error, pipeline masking, automatic retries
or timeout inflation as the optimization. Full/shard timeout is 45 minutes as a
safety ceiling; existing per-test timeouts are preserved.

Concurrency cancels only older pull_request runs for the same PR. Event name and
unique run ID isolate nightly/manual from PR and each other. A timeout, superseded
commit and test failure are distinct: inspect start/end, next commit/run timestamps,
configured timeout and logs. Generic “operation was canceled” is insufficient to
prove the initiator. Interrupted work never counts as success.

Workflow runs untrusted PR code only under pull_request, with contents:read,
no inherited secrets and checkout persist-credentials:false. Timing reporting gets
only actions:read; the scheduled-only issue alert gets issues:write. Neither
executes PR content. No pull_request_target, PR write token,
cache of world state or workflow_run execution of downloaded code is used. Fork PR
approval remains GitHub's normal policy; it does not bypass the required gates.

## Baseline (GitHub Actions, 2026-10-30)

| Run | verify | pytest | Desktop tests | Mobile tests | Workflow wall time |
|---|---:|---:|---:|---:|---:|
| 41088107339 (#162, successful) | 395s | 316s | 1068s | 967s | 1592s (26:32) |
| 41102730739 (#163) | 461s | 369s | 1099s, interrupted | 1085s, interrupted | 1688s |
| 41108404299 (#163) | 641s | 547s | 1107s, interrupted | 1129s, interrupted | 1867s |
| 41114228341 (#163) | see timing API | 549s | interrupted | 1054s, failed | 1884s |

Successful #162 consumed 395 + 1191 + 1055 = 2641 runner seconds (44.02 min),
excluding billing rounding/queue. Browser preparation duplicated pip (45–61s),
npm ci (4–5s), build (11–16s), browser install (16–30s). Tests dominate.

For runs 41102730739 and 41108404299, both browser jobs lasted about 20:20 including
cleanup, matching the configured 20 minute ceiling. Next PR runs started only after
they ended. The latest desktop cancellation also aligns with this ceiling. Evidence
therefore supports job timeout, not supersession by those later commits. The logs
only say “operation was canceled”; the connector rejected check-run annotations,
so the exact GitHub cancellation annotation was not accessible. Earlier run
41097809369 overlaps its successor and must not be assigned the same cause without
its own evidence. Real assertion failures in #163 consumed timeout budget too.

## #163 integration checklist

This branch starts from master and does not contain #163 commits. Reviewed #163
head `ee76add8784c729a2c2e4358a85d33999c6f578a`: new phone158/phone163 specs and
portrait/reachability/current-game changes are selected by phone patterns and
cross-domain mappings. Its backend/fixture changes independently force full.
After #163 merges, update this branch from master, rerun selector tests and
collection, then smoke + phone/domain and full comparison once. In particular
check portrait identities, Back/draft restoration, newly created meeting locations,
calendar commitments and call continuity. Keep this PR behind #163 in merge order.
