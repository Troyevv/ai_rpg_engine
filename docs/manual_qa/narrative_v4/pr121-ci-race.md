# PR #121 — CI desktop/mobile: phone read vs control revision race

Base: `fec5f83e787be16984383b62b781f69658546990`.
Failed run: https://github.com/Troyevv/ai_rpg_engine/actions/runs/40386178724

Both browser jobs failed only `portrait-polish: temporary phone owner and real outgoing API use its portrait`. Desktop: 158 passed / 1 failed; mobile: 140 passed / 18 skipped / 1 failed. Backend/build job passed.

## Root cause

The desktop Playwright trace confirms overlapping real mutations:

- 19:40:11.120 UTC: `POST /api/saves/120/phone`, action `read`, revision 7 → 200, revision 8.
- 19:40:11.357 UTC: `POST /api/saves/120/protagonist`, temporary actor `qa_timur`, revision 7 → 409 (stale save).

Phone kept request busy state locally. Closing its UI did not stop the request, but Game's actor/turn controls remained enabled until `onCommit` arrived. Mobile's subsequent picker timeout was a consequence of the rejected control change. The navigation helper compounded the issue by waiting on the always-enabled Current Game entry button rather than the actor projection and actual control readiness.

## Fix

`Phone` reports in-flight mutation state to `Game`; automatic read participates too. The existing Game revision barrier then keeps controls disabled until the committed save projection arrives. Closing the phone does not release the lock. Completion/error clears pending state; automatic read records its attempted owner/conversation/revision to avoid retries driven solely by busy-state changes. Server concurrency checks, canonical sender/counterparty semantics, history, model calls and save schemas are unchanged.

The actor test helper verifies the response, projected actor and actual enabled actor control. The regression holds the real read response and subsequent GET separately, closes the phone, asserts controls remain locked at both stages, releases the responses and switches twice. No sleeps, increased retries or weakened assertions. Evidence output can be redirected outside tracked screenshot files.

## Validation

- `npm --prefix frontend run build`: passed (TypeScript + Vite); existing large-chunk warning remains.
- `CI=true DOSSIER_EVIDENCE=/tmp/pr121-ci-dossier PORTRAIT_EVIDENCE=/tmp/pr121-ci-evidence PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell npm --prefix frontend run test:e2e -- phone portrait-polish protagonist pov current-game dossier.spec.ts`: **70 passed, 8 skipped**, 4.9 min. Includes phone failures/Retry/calls, control revision barrier, both skins and ordinary-turn save/reload smoke. Skips are duplicate viewport coverage.
- Final rebuild also includes unconditional release of the shared request lock when a different save/owner is selected during a request. `CI=true PORTRAIT_EVIDENCE=/tmp/pr121-ci-evidence PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell npm --prefix frontend run test:e2e -- portrait-polish presentation runtime-v2 --grep 'temporary phone owner|legacy world defaults|general relationships'`: **6 passed**, desktop/mobile. Covers delayed-read regression and the other actor-helper consumers.
- `git diff --check`: passed. No backend/domain/schema modifications; original CI backend/build job was green. Browser validation uses Chromium emulation and deterministic provider through real API/storage; these local results do not claim a completed new GitHub Actions run.
