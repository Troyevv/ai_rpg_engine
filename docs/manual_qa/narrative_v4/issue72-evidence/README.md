# Issue #72 — streaming continuity

Base: `41a288943c5f74f861145062241af0a65140d08e` (merged #123).

## Render/scroll audit

Before: `Game` renders every SSE narrative through debounced HTTP `Markdown`;
its narrative effect and a separate ResizeObserver both write scrollTop. A saved
job disappears before refresh mounts a new animated article. Choices then change
height independently. Mobile disables browser anchoring; desktop did not.

After: `presentationEntries` projects one article keyed by active variant job ID.
`NarrativeTurn` keeps that identity through commit; its `NarrativeText` owns the
sole reveal loop, isolated from memoized historical turns. Snapshots remain
server-owned. Revealing paragraphs use the existing typography without HTTP.
The completed text uses the existing `/markdown` endpoint once caught up, with
character links and link_names intact. Controls/choices remain blocked until
canonical commit and the local presentation backlog finish. Job status is below
the narrative so removing it does not move the text's origin.

`useStoryScroll` owns one coalesced resize frame for container and story changes.
It uses immediate functional follow rather than restarting smooth scrolls.
Upward input disengages follow; jump-to-latest re-enables it. An article anchor
and session scroll preference support navigation and changes above the reader.
Draft storage remains per save/controlled actor. Retry retains the same job key;
stale same-attempt refresh snapshots cannot regress observed text/status.

No backend, Runtime, schema, save format, phone or Inspector layout changes.
Regeneration still uses the server's target/variant contract. #87 should reuse
these components and scroll owner; do not add a second stream or scroll loop.

## Reproduction

```sh
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npx --prefix frontend playwright install chromium
# Run from frontend:
npm run test:e2e -- streaming72
```

`streaming72.spec.ts` uses the existing isolated test server. Controlled snapshot
tests route only this test's save/job projection; they do NOT validate backend
stream transport. They exercise 60 long historical scenes, bursty and small
snapshots, processing stages, commit, choices, manual scroll, reduced motion,
4× CPU throttling, Inspector and narrow viewport resize with composer focused.
The separate smoke uses real FastAPI, SQLite and the deterministic provider:
Start Game → ordinary turn → persisted reload → next ordinary turn.

The `Streaming continuity evidence` workflow runs the same capture against the
PR base and the implementation. It uploads WebM, screenshot, per-frame samples,
Markdown counts, long-task durations and heap sample as
`streaming72-before-after`. Baseline mode records observations without applying
the new invariants. Baseline and after run independently; missing recordings
must not be treated as successful acceptance.

## Verified runs and recordings

- [Full CI on b4d944b](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40464967849):
  2170 backend tests, 171 desktop E2E, 148 mobile E2E passed; 23 mobile tests
  skipped by the existing viewport conditions. Production build and component tests passed.
- [Before/after capture run](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40464967831):
  6 baseline scenarios and 6 implementation scenarios passed.
- [Download recordings + screenshots + raw metrics](https://github.com/Troyevv/ai_rpg_engine/actions/runs/40464967831/artifacts/12715928308).
  Contains `before/after-{desktop,mobile}-{motion,reduced}.webm`, screenshots,
  JSON frame traces, and `smoke-{desktop,mobile}.webm`. Artifact retention: 14 days.
- Local final component coverage: 14 passed, including the subsequent Stop/live
  worker fix and historical React Profiler assertion. That follow-up is validated
  independently by the latest PR checks; the links above identify the exact
  earlier code revision and must not be described as testing later changes.

Local Chromium cannot launch (`socket() failed: Operation not permitted`). All
reported browser results and recordings therefore come from GitHub Actions,
not an invented local run. Static frames extracted from the mobile recording
were reviewed for layout, reading position, status, choices and viewport resize.
They do not establish smoothness on a physical phone.

## Measured baseline / after (b4d944b)

60 long history records, 4× Chromium CPU throttling, controlled snapshots.
The two after Markdown requests are the static player action and final narrative;
there are no narrative HTTP requests driven by animation frames.

| Measurement | Desktop before → after | Mobile before → after |
| --- | --- | --- |
| Markdown requests during scenario | 6 → 2 | 6 → 2 |
| Same narrative DOM after commit | no → yes | no → yes |
| Reading-history scroll delta at commit | 0 → 0 px | 0 → 0 px |
| Mutations in historical narrative | 0 → 0 | 0 → 0 |
| Text growth updates (motion) | 6 → 110 | 6 → 116 |
| Largest growth (characters) | 1410 → 264 | 1410 → 264 |
| Frame interval p95 (whole recording) | 73.0 → 73.8 ms | 64.0 → 68.9 ms |
| End JS heap sample | 19.3 → 60.3 MB | 19.3 → 35.1 MB |

These are single-run observations including automation, recording, panel actions,
and GC timing, **not** a claim of higher FPS or lower memory. Reduced motion
intentionally retains immediate snapshot-sized updates (6 growth updates).
Its p95 intervals were 47.8 → 45.1 ms desktop and 47.6 → 45.2 ms mobile.
Later capture scripts also record per-frame heap samples and input-to-next-frame
latency; consult their own artifact rather than extrapolating these measurements.

Regression gates use semantic invariants: same DOM, one narrative, no historical
mutations, at most two Markdown requests in this isolated scenario, less than
2 px bottom/reading-anchor drift (rounding tolerance). They do not enforce an
invented frame-time budget. Component Profiler checks separately verify that
reveal frames do not commit renders in historical articles.

## Dependency/performance decision

No runtime dependency or virtualization was added. Existing DOM/React APIs
remove frame-driven journal work; the measured traces do not isolate list
rendering as a bottleneck warranting react-virtuoso. A virtualized implementation
would introduce new focus/variant/partial-turn anchoring risks without measured
benefit. The heap samples above do not establish a memory trend or leak by
themselves. Revisit virtualization only with repeatable evidence of a retained
history bottleneck. Vitest/jsdom are development-only dependencies; the existing
Vite bundle-size warning remains, with no new runtime library.

## Acceptance coverage and remaining manual limits

- [x] Small/bursty snapshots, processing stages, completion and final Markdown.
- [x] Exactly one narrative and stable DOM identity at commit; choices after commit.
- [x] Bottom-follow during streaming, scroll-up preservation, jump-to-latest.
- [x] Recoverable error, Retry, simulated transport disconnect/reconnect.
- [x] Unit regression for Stop while worker remains live, then Retry availability.
- [x] Draft retained through reload and Inspector navigation.
- [x] Desktop/mobile, reduced motion, long history, phone open/close with unread notification.
- [x] Required real FastAPI/SQLite persisted ordinary-turn smoke on both projects.
- [x] Existing skin/navigation/phone/variant regressions in the full E2E suite.
- [ ] Physical Android IME/touch acceptance. Resizing a focused mobile viewport
      exercises geometry but does not emulate an actual Android keyboard.
- [ ] Human review of perceived smoothness on a low-end physical phone, including
      formatting-heavy prose and within-paragraph reading anchors.

Keep these limits explicit during review. No automatic merge is authorized.
