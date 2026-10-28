# PR #133 follow-up — commitments and call activity

Baseline: `c30a69999a81f1632fd98964bab58e0c2785dd86`, existing branch
`codex/issue122-phone-scenes-commitments`. Issue #122 remains open pending user acceptance.

## Causes and contracts

**Commitments:** the remote Extraction schema left `player_assertion` and
`player_evidence` optional and did not bind the controlled actor's decision to a
specific RemoteInteraction ID. Existing fixtures always returned perfect proof.
Resolver required `explicit_choice` and an authored quote, but reported one generic
`controlled_actor_unsupported` reason. Then the adapter escalated *every* warning
into failure of the whole communication stage.

The reported production warning alone cannot distinguish a missing assertion from
an incorrect quote. The original production model response is unavailable; do not
claim its exact missing field was observed. API/job regressions reproduce all three
cases and now identify `evidence_field`: assertion, evidence, or source ID.

The new wire contract names `player_source_id`, requires the assertion/source/quote
for controlled-participant agreements in the schema, and describes both directions
of assent. The adapter binds only an explicitly asserted choice to a selected,
authored canonical message and its full text. It never supplies `explicit_choice`
merely because a player sent something. Legacy exact quotes can resolve a unique
source. Resolver restricts proof to the selected remote sources (not unrelated
messages in the whole thread). Ordinary Narrative agency checks remain active.

One bounded correction can repair rejected commitments using the same accepted
messages and same candidate IDs. A correction cannot erase a rejected meeting.
Failure stays recoverable; manual Retry replays accepted decisions and resumes
semantic correction without send/read/NPC generation/time duplication. Unusable
initial envelopes or forbidden scene mutations regenerate only the semantic
response on Retry; they are never replayed forever as accepted work. Invalid
optional intentions are rejected locally and retained as diagnostics. Snapshots,
History, Knowledge, calendar visibility and the atomic commit remain unchanged.

**Call activity:** replacing JobView with one static sentence discarded actual
job/SSE lifecycle distinctions. `callActivity.ts` projects waiting, streaming,
applying consequences, reconnect, error and stopped states. CallScene has an animated
live region outside the scrolling transcript; reduced motion keeps static visible
dots. No fake utterance, elapsed timer or percent. Stop uses the existing endpoint,
never hangup. Incomplete stopped speech can be restored to the input; completed
text continues through the existing Retry. Dialing remains the real phone lifecycle.

## Verification

- `tests/test_phone133_followup.py`: real API/SQLite/jobs, controlled adversarial provider
  responses; proposal/assent in both directions and direct/group chats, canonical
  one-hour anchor, missing/incorrect proof, optional invalid intent, repair omission,
  Retry/reload/no duplicate/time, late response after Stop.
- `tests/test_phone122.py`, `test_phone133.py`: prior calendar, read/POV, reschedule,
  cancel, intentions, rollback/variants, ordinary next turn, provider and choices.
- Frontend unit tests cover real lifecycle projection and stop eligibility.
- `phone133.spec.ts`: browser → API/job → bounded repair → one canonical meeting,
  plus existing A/B/D/E/F regression flows.
- `phone122-streaming.spec.ts`: controlled bursty SSE, stable independent anchors,
  draft/minimize/commit, lifecycle statuses, stop/restore; desktop/mobile,
  graphite/parchment and reduced motion. Screenshots/videos are actual browser output,
  not generated mockups. This test intentionally controls SSE and is not a live LLM.

Final local/CI counts are recorded in the PR report after completion.

## Evidence and acceptance limit

[Desktop graphite](waiting-desktop-graphite.png) ·
[Desktop parchment](waiting-desktop-parchment.png) ·
[Mobile 393 graphite](waiting-mobile-graphite.png) ·
[Mobile 360 parchment](waiting-mobile-parchment.png).

Videos: [desktop motion](anchors-desktop-motion.webm),
[desktop reduced motion](anchors-desktop-reduced.webm),
[mobile motion](anchors-mobile-motion.webm),
[mobile reduced motion](anchors-mobile-reduced.webm).

No DeepSeek key is available in this execution environment. Automated tests use
controlled provider responses, including deliberately broken responses; they do
not establish live-model semantic accuracy. Live proposals, cancellation/reschedule
and user acceptance remain required before closing #122. No new PR, no issue close,
no Tabletop changes, no migration or historical snapshot rewriting.
