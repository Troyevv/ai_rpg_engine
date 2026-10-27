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

## Current verification and limitations

Local component tests: 10 passed. Local backend smoke/API/runtime-handoff: 50
passed. Production frontend build passed. Browser launch is blocked locally by
`socket() failed: Operation not permitted` before any page is rendered. No local
before/after video or browser/performance result exists. GitHub Actions results
must be reviewed separately before marking the PR ready.

Physical Android/IME behavior is **not** covered by viewport emulation. Real
phone keyboard opening/closing, touch scrolling during long generation, phone
notifications and Inspector transitions still require manual visual acceptance.
Markdown with lists/headings changes geometry when final formatting arrives;
perceived smoothness and within-paragraph reading anchors need browser review.

## Dependency/performance decision

No runtime dependency or virtualization was added. Memoized articles and an
isolated reveal loop remove frame-driven journal rerenders. This is an
architectural observation, not a measured browser speedup. A react-virtuoso
proof-of-concept is not justified without the requested successful profiling;
record actual before/after frame/heap/network measurements before deciding.
Vitest/jsdom are development-only dependencies for deterministic component tests.
No invented timing or memory thresholds are reported.

## Manual acceptance checklist (not yet completed)

- [ ] Slow / fast / bursty response; partial Markdown; full-text equality.
- [ ] Exactly one visible narrative; no fade/replay at commit; choices below it.
- [ ] Follow at bottom; upward wheel/touch disables follow; jump restores follow.
- [ ] Scroll-up anchor during final Markdown, commit and choices.
- [ ] Stop, recoverable error, Retry, transport disconnect/reconnect.
- [ ] Navigate away/back mid-stream; preserve draft and visible prefix.
- [ ] Graphite/Parchment, desktop/393px/360px, reduced-motion.
- [ ] Physical Android keyboard, phone notifications, Inspector open/close.
- [ ] Long journal under constrained mobile CPU; compare recorded metrics.
- [ ] Review real smoke recording and API persistence assertions.
