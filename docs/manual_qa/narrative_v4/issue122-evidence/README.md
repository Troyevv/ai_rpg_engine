# Issue #122 — separate call scene and canonical phone consequences

Base: `master` at `50d6694db0ee838c99a34f2159386e05e04186a8` (includes #72 / PR #124, #120, #121). Branch: `codex/issue122-phone-scenes-commitments`. No database migration or historical-snapshot rewrite.

## Audit and ownership

Read AGENTS, #122, Epic #36, #70, #66, #37, #75, and integrated #72. The existing `/phone/dispatch` already owned atomic source commands, source-bound continuation, accepted decision checkpoints and Retry (#120). Runtime `communication.run` advanced canonical time and persisted RemoteInteractions, but committed only a receipt: no semantic Extraction consumed the accepted reply. The normal Narrative turn did run Extraction. `Game` rendered communication jobs and their receipts alongside physical turns. Phone focus selected the main composer channel. Calendar/participant projections did not distinguish unread message evidence.

The change reuses these owners:

| Owner | Responsibility after this change |
| --- | --- |
| API / game_jobs | Typed `interaction_channel`; actor/call/conversation presentation route; revision and capability guards |
| `communication.run` | Existing call/text lifecycle, accepted decisions and canonical clock |
| `services/communication.py` | Journaled `remote_semantics` stage after substantive accepted text; Retry replays decisions and repeats only the failed semantic stage |
| `remote_semantics.py` | Bounded full-source adapter to **existing** RawTurnResult / StateResolver; no new agent or world store |
| `commitments`, `lifecycle`, `calendar` | Existing #66 / #75 transitions and #37 date adapter, now with source-bound minute offsets, remote intention authorship and call provenance |
| History / StatePatch / snapshots | One atomic branch lineage for messages, agreements and intentions |
| `surfaces.py`, `presentationEntries.ts` | Disposable physical/phone/call projections of that same history, including accepted mixed physical events |
| `NarrativeTurn`, `NarrativeText`, `useStoryScroll` | **Unchanged ownership from #72**: one renderer/buffer per entry, stable job identity across commit; same scroll hook with separate container/key |
| `CallScene` | Layout, explicit controls, focus, separate session draft; no EventSource, animation buffer, Markdown request loop or independent scroll observer implementation |

Ordinary autonomous incoming messages reuse the existing Narrative Extraction with complete accepted sources. Voice dialogue uses the existing Narrative → Extraction pipeline. Opening, minimizing, restoring, ending and rereading do not request a summary or call a model. The existing read transition remains authoritative.

## Requirement and test matrix

| Requirement | Implementation and evidence |
| --- | --- |
| R01 | Structured filtering before rendering pending/saved turns, including receipts/tools. Unit tests cover six job states and commit identity; ten-message browser test checks no main cards or pending slots. |
| R02 | Existing direct/group Phone, delivery/read rules, shared portraits and local recovery retained; processing history/variants stay inside Phone. Existing phone suites retained and updated for the new scene. |
| R03 | Connected-call-only desktop overlay / mobile surface, large shared avatar, status/time, transcript, composer and explicit end. Real API browser flow in two themes. Existing runtime audio/channel boundary tests retained. |
| R04 | Minimize/restore, Escape, browser Back, backdrop and workspace navigation preserve canonical call. Explicit call composer vs physical composer; shared busy guard and synchronous request lock. |
| R05 | Independent main/call drafts and anchors, explicit end restores main input; read-only ended-call journal. Reload no longer waits for a hidden presentation completion. |
| R06 | Same world clock and consequences. Mixed accepted physical Events project to the story; exact accepted physical evidence is removed from the call projection, without language heuristics. Duplicate phone tools are suppressed on physical fragments. |
| R07 | Routes carry stable actor/call/conversation IDs. Legacy communication kind and answered-call snapshot links are used conservatively. Phone/call records of other owners are excluded from read responses; unread consequences are filtered from preloaded changes. |
| R08 | Existing #120 checkpoints and recoverability plus journaled semantic errors; source send/reply/time cannot repeat on semantic Retry. Desktop, mobile 360/393, graphite/parchment, reduced motion and keyboard-height tests. |
| R09 | Full send → decisions → accepted messages → Extraction → Resolver → atomic History/WorldState path; autonomous incoming replies use normal Extraction. Actual attempts go through `tracked_stream`. |
| R10 | Proposal/assent distinction, each group participant needs authored evidence, exact source timestamps, minute/day/weekday/period windows; stable-ID reschedule/cancel and duplicate guards; fresh assent for reschedule. |
| R11 | Existing calendar and participant personality tab read the same commitments. Unread confirmation is absent from calendar, cards and preloaded change summaries. Time Skip stops at a pending meeting; due does not resolve it. |
| R12 | Exact authored intention text + remote source ID; no goals/Emotion/value changes in text semantic adapter. Existing lifecycle validates transitions; old message cannot prove a new intention status. |
| R13 | Same before/after snapshots, journal, revision guards, regeneration, variants, rollback and History DAG; no PhoneCommitmentStore or backfill of historical plans. |
| R14 | Real API/job/provider-fixture smoke and the coverage mapping below; independent browser SSE fixture for #72 anchoring invariants. |

| Checks | Executable evidence |
| --- | --- |
| T01 | `phone122.spec.ts`: ten sequential messages; `test_ten_long_messages_keep_plan_and_full_source_context` |
| T02, T04, T05 | Existing `phone.spec.ts`, `phone-completion.spec.ts`, `test_remote_communication.py`, `test_communication_cycle.py`: incoming/group read, ringing/answer/decline/missed and portraits |
| T03, T06–T08 | `phone122-streaming.spec.ts`: long bursty SSE, separate upward-scrolled containers, stable node at commit, minimize/restore/end, drafts, keyboard height, Escape/Back, reduced motion |
| T09–T11 | Existing runtime remote boundary/privacy tests plus mixed physical event and owner-switch test in `test_phone122.py`; legacy routing unit case |
| T12–T16 | Existing communication recovery, actual provider failure/Retry/reload browser scenarios; variants/rollback test; two-theme real browser flow; full regression suites include Tabletop |
| T17–T20 | API dispatch + worker + deterministic provider + real read/calendar; 09:00 proposal / 09:01 reply stays 11:00, day/weekday/period parameterization, actual calendar and both participant cards in browser |
| T21–T22 | Stable-ID reschedule/cancel; complete API smoke with Time Skip stopping at due and later accepted evidence resolving only that plan |
| T23 | Exact player-authored intention with canonical RemoteInteraction source; existing lifecycle suite covers terminal/dependency reevaluation |
| T24 | Four-member canonical group, only the two authors in the agreed plan, other member's calendar remains empty |
| T25 | Real connected-call job with agreement, mixed physical event, explicit end and next ordinary turn |
| T26–T27 | Provider outage/invalid semantic delta, atomic no-commit, Retry only failed stage, no resend/time duplication, reload/regenerate/variant/rollback/owner switch; existing History DAG tests |
| T28 | 22 full messages including >400-character proposal; bounded source context retains original evidence and one plan. Existing #66 stable-ID/duplicate and ordinary plan tests retained. |
| T29 | `test_api_jobs_meeting_unread_read_calendar_reload_next_turn`, `test_full_smoke_skip_stops_at_meeting_then_evidence_resolves_and_next_turn`, autonomous incoming job test; **not** Resolver-only mocks |

G1–G6 are covered by the surface/lifecycle/recovery/browser rows; G7–G9 by the semantic/calendar/agency/full-pipeline rows and the recorded baseline comparison. Completion is contingent on the final verification results below, not a successful build alone.

## Real before / after evidence

`before-*` was captured by running the original base in a separate worktree, with the same controlled provider transport and user actions. No images were generated. `after-*` uses the implementation branch. Device screenshots have native device scale; mobile CSS widths are 360 (graphite) / 393 (parchment), desktop 1440×1000.

| Surface | Before | After |
| --- | --- | --- |
| Desktop call | [graphite](before-desktop-graphite-call.png) | [graphite](after-desktop-graphite-call.png) |
| Mobile call | [parchment](before-mobile-parchment-call.png) | [parchment](after-mobile-parchment-call.png) |
| Desktop return | [graphite](before-desktop-graphite-return.png) | [graphite](after-desktop-graphite-return.png) |
| Mobile return | [graphite](before-mobile-graphite-return.png) | [graphite](after-mobile-graphite-return.png) |

Videos: [desktop before](before-desktop-graphite.webm), [desktop after](after-desktop-graphite.webm), [mobile before](before-mobile-parchment.webm), [mobile after](after-mobile-parchment.webm). Additional files include the other skin/device combinations, processing views and long-call anchor scenarios. Calendar/participant screenshots and `.json` read projections are captured by the real API smoke. The committed browser transport outputs explicit assent; production does not contain its test phrase matching.

## Reproduction and verification

```bash
python -m pytest -q
cd frontend
npm ci
npm test
npm run build
npx playwright test --reporter=line
```

In this constrained runner, Playwright uses `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/issue122-browser/chrome-headless-shell-linux64/chrome-headless-shell`. Video uses the installed ffmpeg. CI uses its normal Playwright installation. Browser fixture server disables optional neural retrieval: its deterministic structural fallback requires no locally installed embedding model; embedding behavior is tested separately. An inherited property test exceeded its arbitrary 200ms deadline on both unchanged master and this branch; only that wall-clock deadline was removed, preserving all invariant assertions and generated cases.

Focused results recorded during implementation: backend communication/remote/commitment/calendar suite **97 passed**; expanded phone + context suite **17 passed**; incoming/privacy suite **16 passed**; final focused phone/communication/commitment suite **48 passed**; frontend unit suite **23 passed**; phone browser suites **26 passed**; long call / anchors **4 passed**; original-master comparison **4 passed**. These overlap and must not be added together. Final full-suite/CI results are recorded below after completion.

## Cost and limits

No paid provider was invoked: actual paid cost for these tests is **$0**. Controlled providers do not report token usage, so tokens/model cost estimates are **unknown**, not invented zero-token usage. A normal accepted direct-text test invokes two existing remote decisions (read/reply) and one bounded semantic Extraction. Retry after semantic failure invokes only Extraction. Autonomous incoming smoke invokes one remote decision, Narrative and the already-existing Extraction. UI transitions invoke none.

Legacy prose without reliable typed provenance is left unchanged, never classified by wording. Source context retains full latest 24 messages plus pending-plan evidence, at most 48 messages / 64,000 content characters; overflow produces a recoverable error, not silent evidence truncation. Existing model context limits also apply. Semantic interpretation was tested with controlled providers; paid-model language quality is not certified by these tests. Native iOS/Android software keyboard behavior is represented by a browser visual-viewport resize; physical-device verification remains manual.
