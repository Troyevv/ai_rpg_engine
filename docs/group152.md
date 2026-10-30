# Autonomous group conversations — #152 / PR #166

Base master: `b775f055cf8c76193bba96c8ad2fee49e89168cd`, including #163.
Initial implementation reviewed AGENTS.md, #36/#69/#70/#122/#127/#129/#138/#158
and open #119/#118/#33. The follow-up updates the existing PR166 branch; it does
not import those other PRs or create another PR.

## Ownership and invariants

Canonical WorldState and RemoteEvents remain authoritative. Each message and
read goes through `remote.apply`. There is no second scheduler, message journal,
NPC runtime or API. Conversation pacing and event-bound response requests live
in the existing snapshots, so revision, retry, variants, rollback and reload use
the existing transaction/history boundaries.

No NPC authors player speech, consent, goals or movement. Delivery is not reading;
reading creates testimony about the message, not proof that its claims are true.
Existing Knowledge and `basis_ids` validation, including continuation basis
handling, are unchanged by this follow-up (the separate P1 review is out of scope).
A conversation ID supplies a scheduling basis when an actor has no prior
intention/thread/event. It does not establish factual knowledge.

## Initiative and pacing

The existing `remote_initiative` offers at most two eligible groups and four
speakers per group to its one author request. The author may choose a short
series, a legacy action, or silence. The Runtime does not classify literary
importance or impose topics.

`Conversation.initiative_pacing` stores the latest attempt time/turn, a digest of
canonical inputs, and considered canonical History event IDs. Changed intentions,
goals, relationships, Knowledge, plans, messages or threads permit a new attempt
without waiting 30 minutes. History events involving group NPCs also qualify,
including offscreen events. GM event/story context is explicitly not NPC knowledge.
The author decides whether any of this warrants conversation in the same request.

Without changed context, a spontaneous attempt becomes eligible after **30 world
minutes**. No intention, thread or new message is required. Everyday conversation,
news, rumours, work, jokes, relationships and personal plans are allowed; silence
is valid. The old two-turn and global five-minute gates are removed.

At most one autonomous attempt/series runs globally per Narrative turn. Null and
rejected results also consume the attempt. Inputs are consumed after the accepted
series, including its own read transitions, so its output cannot immediately
trigger itself. An event is not replayed on every subsequent turn. New canonical
consequences can motivate another conversation. Time Skip and Long-term Advance
do not run this stage; returning from a jump permits one current attempt, never
one attempt per missed interval.

A nonempty autonomous series remains a small batch of at most three messages:
one author call and one request-annotation Extraction call. Later speakers must
explicitly read previous accepted messages. The ordinary Narrative Extraction
also receives these accepted sources and applies consequences; there is no
additional autonomous consequence-extraction call.

## Player group messages and waiting

The existing communication job now offers **one group reaction**, with several
NPCs and returning speakers allowed. NPCs may answer the player and one another.
There is no fixed reply-count cap: the author output/context token budgets bound
processing. Empty replies are valid. Selected speakers read the source through
Remote; later speakers also read preceding replies. Direct chats and calls retain
the original communication cycle.

A player message bypasses autonomous cooldown. If the group is waiting for a
voluntary decision, the same phone Extraction adapter first interprets only the
player's answer/refusal against canonical request IDs. Only then can the group
author run. This conditional gate is necessary to keep `remote.apply`'s existing
pause enforcement intact; no Runtime guard is disabled. It is not an urgency
classifier or a per-NPC call. The usual consequence Extraction follows even if
NPCs choose silence: explicit agreement must still reach the calendar.

Pause remains derived from `RemoteEvent.response_request`: target, evidence,
provenance, deadline, resolution source and closure reason. Read, silence,
mentions and Narrative turns are not answers. Only the relevant autonomous group
pauses; other groups and direct chats remain eligible. Expiry/death/departure can
close a request without supplying an answer. Authoring ends at a player decision;
autonomous acceptance stops immediately at its annotated request.

Communication consumes its source/context once, preventing a second autonomous
response job for that message. Accepted author frames are reused on retry.
Recorded legacy group journals retain their original decision contract when
retried/regenerated. New pacing fields have defaults; no SQL migration or rewrite
of old snapshots is required.

## Consequences

The existing phone adapter passes meetings, locations, intentions, threads and
directed relationships to the common Extraction/StateResolver/domain handlers.
Proposals are not agreement; agreement is not occurrence. Player consent remains
source-bound. Intention and thread changes require accepted message provenance.
Explicit player-directed feelings must refer to the current player message.

For #107 relationships, a projection of accepted, actually perceived RemoteEvents
supplies canonical interaction evidence to the existing relationship reader.
Stable RemoteEvent IDs prevent delivery/read transitions from counting as fresh
relationship evidence. Existing immutable History receipts enforce consumption,
player override fences and the common step budget. No new relationship store.

The physical scene and NPC locations remain unchanged. Phone UI retains the
existing unobtrusive “Ждут твоего ответа” indicator, shown after reading, along
with navigation, skins, drafts, scrolling, calls and desktop/mobile layout.

## Acceptance and tests

`tests/test_group166.py` covers the follow-up, alongside `tests/test_group152.py`.
Only the external LLM provider is deterministic; API, jobs, Remote, Resolver,
SQLite and history/variants are real.

| Follow-up checks | Evidence |
|---|---|
| 1–2: new/consumed cause | Changed thread, relationship, intention, message; offscreen canonical event; consumed event does not repeat |
| 3–4: spontaneous/silence | No intention/thread/event; two NPC messages; null consumes cooldown |
| 5–6: group reaction | Six replies including returning speakers in one author call; explicit reads and NPC↔NPC replies |
| 7–9: waiting | Immediate answer/refusal path; read and Narrative preserve pause; another group works without a global time gate |
| 10–11: agreement | Invitation creates no plan; explicit assent creates pending calendar entry, including when NPCs decline to reply |
| 12: persistence | Retry after provider failure reuses author; completed-job replay, reload, rollback, regenerate, variants and legacy journals |
| 13–14: load | Week Time Skip and year-long advance without backlog; one current series; bounded calls/context/output |

Integration: **Start → player group message → three NPC replies → spontaneous
continuation → invitation → wait → read/silence → explicit assent → immediate
reaction (or silence) → calendar agreement → reload → next turn → rollback**.

Verification runs (overlapping, not additive):

- `python -m pytest tests/test_group166.py tests/test_group152.py tests/test_communication_cycle.py tests/test_phone122.py -q -s`: **62 passed** before the final two follow-up cases.
- `python -m pytest tests/test_group166.py tests/test_group152.py -q -s`: **37 passed** with those cases.
- Final `python -m pytest tests/test_group166.py -q -s`: **11 passed** after tightening current-source relationship evidence.
- `python -m pytest tests/test_group166.py::test_relationship_and_thread_consequences_use_common_resolver_and_receipts tests/test_relationship_evidence.py -q`: **22 passed**.
- Broader targeted run included phone163 and remote communication. Its 15 failures identified the SQL projection defect and outdated group test provider; both were corrected and affected tests rerun above. It had 111 passing tests; it is not represented as an all-green run.
- `npm run build --prefix frontend`: passed; existing bundle-size warning.
- `npm test --prefix frontend -- phone158.test.tsx phone122.test.tsx callActivity.test.tsx`: **23 passed**.
- `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/chromium npm run test:e2e --prefix frontend -- group152.spec.ts phone163.spec.ts --output=/tmp/group166-ui-fixed`: **8 passed**.
- Chromium desktop/mobile, graphite/parchment: group reaction, waiting, assent,
  calendar and reload. Screenshots inspected at 1440×1000 and 360×800 CSS pixels.
  Initial browser test incorrectly treated the calendar map as an array; fixed
  the assertion and reran. No screenshots/videos committed.
- `git diff --check`: passed. No full repository-wide local E2E run.

## Measured cost

Repository input estimator and existing `llm_requests` instrumentation, final
fixture run; these are **not provider-reported tokens**:

| Path | Calls | Estimated input tokens | Configured output ceiling |
|---|---:|---:|---:|
| Spontaneous autonomous invitation | 2 | 5052 + 1661 = **6713** | 2400 + 1200 |
| Player message → three NPC replies | 2 | 2086 + 10416 = **12502** | 2400 + 4096 |
| Answer to pending question → three NPC replies | 3 | 2543 + 3279 + 12527 = **18349** | 1200 + 2400 + 4096 |
| Answer to pending question → NPC silence | 3 | 2543 + 3279 + 11581 = **17403** | 1200 + 2400 + 4096 |

The conditional wait gate adds one call, 2543 estimated input tokens in this
fixture, capped at 1200 output tokens. Without waiting, batch group replies use
one author instead of one decision per read/speaker. Autonomous silence costs
one author call; an ineligible/cooldown attempt costs zero group calls. Ordinary
Narrative generation/Extraction is separate. The existing bounded phone
commitment-repair mechanism remains available for invalid optional plans; no new
autonomous repair loop was added. Retry reuses accepted author output; regeneration
is an explicit new user request and may generate new output.

Mock usage is null, recorded local cost is **$0**, and no paid provider was called.
Actual DeepSeek cost/quality and physical Android/iOS remain untested. Production
usage/cost continues through the existing pricing/accounting mechanism. Semantic
correctness in arbitrary prose remains dependent on the model; fixtures establish
structural, agency, persistence and UI behavior. The separately excluded P1
Knowledge/basis review remains outside this follow-up.

## Follow-up files

Runtime: `backend/runtime_v3/{communication,context,group_planning,remote_initiative,
remote_models,remote_semantics,repository}.py`.
Pipeline: `backend/services/{communication,usage}.py`, `engine.py`.
Tests: `tests/{test_group166,test_group152,group152_provider,test_communication_cycle}.py`,
`frontend/e2e/group152.spec.ts`. Documentation: `docs/group152.md`.
