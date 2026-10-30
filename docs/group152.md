# Autonomous group conversations (#152)

Base: `b775f055cf8c76193bba96c8ad2fee49e89168cd` (master, includes merged #163).
Reviewed AGENTS.md, #36/#69/#70/#122/#127/#129/#138/#158. Open #119 shares
`remote.py` but owns call incapacitation; this change does not replace its call
lifecycle. #118 shares only the fixture server and owns world authoring. #33 is
Tabletop. No changes from those branches were included.

## Invariants and ownership

- Canonical WorldState/RemoteEvents remain authoritative. Every message goes
  through `remote.apply`; no alternate scheduler, message table or endpoint.
- No controlled-actor speech, decisions, goals, consent or physical relocation.
  Delivery does not grant Knowledge; canonical reads grant testimony, not truth.
- Intentions, goals, directed relationships, actor-specific Knowledge, read
  history and GM story context inform selection. A thread can motivate a
  spontaneous inquiry without a pre-existing intention. GM context is explicitly
  not speaker knowledge. Actual prose compliance remains an LLM responsibility.
- Existing job revisions, immutable before snapshots, variants and SQLite commit
  own atomicity. Rejected series leave no partial messages or Knowledge.

## R01–R09 implementation

`remote_initiative.stage` extends the existing optional Director stage. A pure
`group_planning` helper selects up to two eligible groups and four relevant NPCs
per group. The model may choose one group or the old single-action contract, or
no action. There is no requirement to fill the budget.

A chosen series contains up to three separate messages (a computational batch,
not a literary length limit). One author request plans the whole series, then
one source-bound Extraction request classifies questions/requests for the
controlled actor. Each message is separately applied. Later speakers must read
accepted earlier messages through Remote before continuing. Sender capabilities,
membership, current basis, Knowledge and pause are checked again. NPC group
backlogs do not trigger one extra LLM read decision per message.

Pause is derived from `RemoteEvent.response_request`: target, exact evidence,
semantic provenance, relevance deadline, optional canonical response ID and
closure reason. The first active request stops the rest of the series. Concurrent already accepted
questions retain separate source identities; each needs its own explicit resolution
or expiry. Repeated annotations never overwrite an outstanding request. Other
groups/direct conversations retain their own eligibility. Mere mentions do not
create a request. The phone's existing semantic extraction resolves explicit
answers/refusals using source IDs, author identity, same-group order, prior read
and quoted evidence. Read, silence and ordinary turns alone cannot resolve it.

Expiry is evaluated against canonical world time without inventing an answer.
Death/departure closes the request; leaving and rejoining does not resurrect it.
The semantic model chooses relevance deadlines. No regex/NLP heuristics classify
message meaning. Phone-generated group requests use the same lifecycle.

`Conversation.initiative_pacing` records the last consultation, including silence
and rejected proposals. Per-group cooldown is 30 world minutes **and** two turns;
global allowance is one series per turn, at least five world minutes apart.
Time Skip and Long-term Advance do not run this stage. Returning after a large
jump produces at most one current series, never replay of missed intervals.

Both fields have explicit nullable Pydantic defaults for legacy saves. No SQL
migration or historical-snapshot rewrite. Existing snapshots/History own rollback
and regenerate; canonical event/operation IDs survive replay. Completed request
text uses the existing usage journal, including source-identical reuse. A failed
optional group semantic provider request defers the whole series with diagnostics.
A later Narrative extraction Retry reuses already staged messages and does not
repeat their LLM calls.

Phone UI adds only “Ждут твоего ответа” in the group preview/composer area. The
indicator is hidden until the controlled actor reads the source. Existing themes,
Back, drafts, scrolling and calls are preserved. The pre-existing 4000-character
modern-message cap is removed so this feature does not reject authored prose;
provider output/context budgets still bound computation. Oversized optional group
context is deferred without truncating canonical text.

## T01–T12 acceptance

| Tests | Evidence |
|---|---|
| T01–T02 | NPC↔NPC initiation, NPC-only group, 3-message order/senders/recipients, read transitions, no physical changes |
| T03 | No basis → zero calls; null → cooldown; interval/turn budgets; no per-message backlog polling; context budget |
| T04–T05 | Question stops at its source; other group/direct chat independent; mention fixture does not pause |
| T06 | Read and ordinary Resolver turn preserve pause; explicit answer/refusal clears it; wrong-chat source rejected |
| T07 | Deadline without answer; source idempotence; concurrent source identities; expired requests do not bloat semantic context |
| T08–T09 | Unread/private projections; no actor transfer; stale membership/death/incapacity/channel/topic; leave/rejoin |
| T10 | Real API/jobs/SQLite, duplicate completed job, concurrent command rejected, reload, rollback, regenerate, extraction Retry, legacy defaults |
| T11 | Large jump capped; real one-year Long-term job with zero extra calls; week Time Skip without group replay |
| T12 | Start → turn → series → wait → refusal → continuation → reload → next turn; Chromium desktop/mobile |

Main tests: `tests/test_group152.py`; external provider only is replaced in
`tests/group152_provider.py`. Browser tests use the real fixture server, API,
workers and SQLite, not mocked routes/Remote/Resolver.

## Cost measurements

Deterministic provider, existing `llm_requests` accounting:

| Series | Estimated input tokens (author + group extraction) | Output characters (author + extraction) |
|---|---:|---:|
| Initial question | 4292 + 1415 = 5707 | 516 + 131 = 647 |
| Continuation after refusal | 4968 + 1521 = 6489 | 741 + 16 = 757 |
| First series after a year | 5384 + 1480 = 6864 | 648 + 16 = 664 |

These input counts are the repository estimator, **not provider-reported usage**.
Mock provider token usage is null, recorded local cost is $0. No paid calls.
Production billing uses actual usage and the existing provider pricing snapshot.
There are zero new calls without a group opportunity, one consultation on silence,
and two calls for a nonempty series regardless of its speakers/messages. Relative
to the existing one-decision planner, a chosen group adds at most one extraction
call. Output limits: 2400 + 1200 tokens; no per-NPC calls or retries for semantic
annotation failure. Existing explicit phone command continuation/semantic costs
remain separate and unchanged.

## Verification and limitations

- Focused backend results and exact commands are in the PR description.
- Production frontend build and 23 existing phone/call component tests pass.
- 26 Chromium regressions: group152, phone158, phone163, call-continuity, both
  desktop/mobile. Final group152 smoke: 4 passed (graphite/parchment).
- Actual screenshots inspected at 1440×1000 and 360×800: waiting indicator,
  canonical authors, readable messages, reachable composer; no Narrative copies.
  Screenshots remain temporary; no videos or bulk QA artifacts committed.
- Live DeepSeek, physical Android/iOS and natural-language quality across arbitrary
  settings are NOT tested. Fixtures establish structural/transactional behavior,
  not semantic accuracy. Cooldown constants may need tuning from real play.
- No full repository-wide local suite; CI owns that broader regression gate.

## Changed files

Runtime: `group_planning.py`, `remote_initiative.py`, `remote_decision.py`,
`remote_models.py`, `remote.py`, `communication.py`, `remote_semantics.py`,
`raw.py`, `resolver.py`, `context.py` (all under `backend/runtime_v3/`).
Pipeline/accounting: `engine.py`, `backend/services/usage.py`.
UI: `frontend/src/Phone.tsx`, `frontend/src/PhoneContent.tsx`,
`frontend/src/styles/phone.css`.
Tests: `tests/test_group152.py`, `tests/group152_provider.py`,
`tests/test_historical_correspondence130.py`, `tests/e2e_server.py`,
`frontend/e2e/group152.spec.ts`. Documentation: this file.
