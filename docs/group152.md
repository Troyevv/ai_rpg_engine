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

## CI regression repair — run 41145293753

Reproduced the exact six backend failures on `a771b4a`, plus the disabled group
member-removal button in Chromium. Confirmed causes:

- **Legacy checkpoint:** `backend/services/communication.py` filtered decisions by
  `stage == communication`, dropping historical frames without `stage`. It now
  normalizes only that missing metadata. Original prompt/response, schema/runtime
  validation, rejected-frame handling and source-bound reuse remain unchanged.
  Added real SQLite reload tests for flat and enveloped legacy group decisions
  plus cached semantic extraction: zero provider calls and exactly one plan.
- **Three semantic-repair tests:** repair was functioning; the call-count assertion
  still required separate read/send author calls for groups. Updated only the
  expected author count (one group batch vs two direct decisions). All exact
  evidence/agency diagnostics, repair-source equality, time, calendar, reload
  and message-count assertions remain.
- **Two missing `one-hour` plans:** the shared test provider's new group branch
  serialized Cyrillic with default `ensure_ascii=True`. Existing fixture reply
  substitution therefore left “Да, увидимся завтра.” unchanged instead of emitting
  the offer/assent required by the scenario. Restored UTF-8 fixture output as in
  its direct branch. The two meeting tests and production Extraction are unchanged.
- **E2E removal:** the fixture server did not recognize `Group communication
  reaction/1`; it returned Narrative `scene/choices/world_delta` JSON. Runtime
  correctly rejected it. Captured dispatch returned HTTP 200; subsequent Save API
  returned `job.status=error`, `narrative_complete=1`, revision 5. DOM showed
  “Не удалось получить ответ. Можно повторить”, `aria-busy=false`, and disabled
  membership buttons. `Game.pending` was protecting an unapplied failed job;
  there was no stuck loading flag. The deterministic provider now implements the
  group response contract, including silence. Production UI/Runtime guards were
  not changed. E2E additionally requires saved job, one outgoing event, busy=false,
  no error alert and an enabled removal button before the original remove/add
  and protagonist/privacy assertions.

Validation:

- Reproduction: `python -m pytest tests/test_phone133_followup.py tests/test_remote_decision_contract.py -q` → **6 failed, 41 passed**; after correction → **47 passed**.
- `python -m pytest tests/test_phone133_followup.py tests/test_remote_decision_contract.py tests/test_phone122.py tests/test_phone163.py tests/test_communication_cycle.py tests/test_group166.py -q` → **100 passed**, including all six original failures and three additional regression cases.
- `E2E_DB_PATH=/tmp/reg166-fixed.sqlite3 PLAYWRIGHT_EXECUTABLE_PATH=/tmp/chromium npm run test:e2e --prefix frontend -- phone.spec.ts --output=/tmp/reg166-phone` → **8 passed**, desktop/mobile.
- Inspected the resulting SQLite: both group jobs saved, exactly one author and
  one semantic request each, accepted frames, no unfinished/error jobs or extra
  group calls. No force-click, increased timeout or removed assertion.
- New real API/jobs/SQLite integration: player group message → two NPC replies →
  controlled Extraction outage → repository reload → Retry reuses the NPC series
  → one agreement/calendar entry → save/reload → duplicate worker is a no-op;
  retrying the already saved job is rejected. Exactly one author call and two
  Extraction attempts including the deliberately failed one. Physical scene and
  consent participants remain correct.

Repair files: `backend/services/communication.py`, `tests/test_communication_cycle.py`,
`tests/test_phone133_followup.py`, `tests/test_remote_decision_contract.py`,
`tests/e2e_server.py`, `frontend/e2e/phone.spec.ts`, and this document.
No changes to spontaneous/event pacing, `remote_initiative.stage()`, Knowledge,
`basis_ids`, group multi-speaker support, source-bound Extraction or production UI.
No full repository-wide E2E run; all provider responses were deterministic.

## DeepSeek JSON-mode regression follow-up

### Evidence and limits

The GitHub API and fresh fetch still show #166 **open**, based on master
`b775f055`; the user therefore selected updating #166 instead of creating a new
PR containing the entire feature again. This fix starts from PR head `373b698`.

A concrete request-contract defect is confirmed: `reaction_context()` sent
`response_format={"type":"json_object"}` without the word JSON anywhere in the
system/user messages for an ordinary group conversation. The same omission
existed in autonomous `remote_group_semantics` and the pending-answer
`remote_response_semantics` gate. Serializing a schema is not a JSON instruction.
DeepSeek explicitly requires that word and an example:
https://api-docs.deepseek.com/guides/json_mode/ .

No live DeepSeek key or original failing-game diagnostics were supplied. Thus we
have **not reproduced an actual DeepSeek server response or proven the specific
user incident**. The reproduction uses the real OpenAI 2.54 SDK, HTTP serialization,
FastAPI dispatch/retry, workers, SQLite, Runtime and Resolver with an
`httpx.MockTransport` enforcing the documented JSON requirement. It does not mock
`engine.chat_stream`. Before the fix direct messages passed, while groups failed
with the reported Russian error for thinking off/low/high.

Sanitized diagnostics persisted by the existing usage service in that reproduction:

- stage: `remote_initiative` (group reaction author, not autonomous scheduling);
- HTTP status: 400; reason: `json_instruction_required`; parameter: `messages`;
- `request.has_json_instruction=false`, two system/user messages;
- `response_format={"type":"json_object"}`, author `max_tokens=2400`;
- model `deepseek-flash`; streaming with usage enabled;
- thinking off: `thinking.type=disabled`, temperature 0.2, no reasoning_effort;
- thinking low/high: `thinking.type=enabled`, matching reasoning_effort, temperature
  omitted. SDK merges `extra_body` into the wire body; no nested extra_body field.

The thinking mapping matches https://api-docs.deepseek.com/guides/thinking_mode/ .
Full phone Extraction retains max_tokens=4096 (fixture config), temperature 0.1
when thinking is off; the answer gate and autonomous request annotation remain
bounded at 1200. All calls use ordinary system/user content, with no tool calls or
assistant reasoning history. There is no evidence here for a model-name defect.
The actual user's selected model and original provider_error remain unavailable.

### Fix, compatibility and cost

Three prompts explicitly request a valid JSON object and give an empty-result
example. JSON mode, thinking, provider settings, validation and output budgets
remain enabled. No changes to `llm.py` or usage were needed: the existing
ProviderHTTPError classifier and SQLite diagnostics correctly preserve the safe
reason/parameter. No new logging, raw HTTP bodies, credentials or private prompt
artifacts are added.

The response-gate replay comparison recognizes **only the exact previous prompt**
without the newly added JSON guidance/example. All source data, schema and other
instructions must still match; the saved response still passes Resolver. This
avoids re-paying a completed gate after upgrading. The author already compares
the unchanged source context, so its completed checkpoint remains reusable too.
Other Extraction contracts retain exact comparison. There is no save migration.

Changed files: `backend/runtime_v3/group_planning.py`,
`backend/runtime_v3/remote_initiative.py`, `backend/runtime_v3/remote_semantics.py`,
`backend/services/communication.py`, `tests/test_group_deepseek_http.py`, and this
report. Pacing, multi-NPC reactions, source-bound consequences, Knowledge/basis_ids,
agency and canonical RemoteEvents are preserved.

Measured mock request counts: a successful two-NPC group reaction takes **2** HTTP
requests (one author + one Extraction). A final-Extraction HTTP 400 followed by
reload/Retry totals **3**, not four: the author is reused. A completed legacy
answer gate and author followed by a failed final Extraction incur **one** request
on Retry. Re-running a saved worker incurs **zero**. No extra stage is introduced;
only a short instruction/example adds prompt tokens. Mock usage/cost remain
unknown, and no paid requests were made; real billed cost was not measured.

### Verification

- `python -m pytest tests/test_group_deepseek_http.py tests/test_providers.py tests/test_group152.py tests/test_group166.py tests/test_phone133_followup.py tests/test_remote_decision_contract.py tests/test_phone122.py tests/test_phone163.py tests/test_communication_cycle.py tests/test_runtime.py -q`: **153 passed**.
- `test_group_deepseek_http.py` contains 10 cases: direct/group × thinking
  off/low/high; final-Extraction 400/reload/Retry; every group JSON stage through
  HTTP; exact pre-fix group prompt rejection and recovery; a completed legacy
  answer gate + author followed by final-Extraction failure/reload/Retry and a
  canonical calendar agreement. Changed evidence/context is not replay-compatible.
- Chromium `phone.spec.ts group152.spec.ts`: **12 passed**, desktop/mobile,
  including group reaction, autonomous invitation, player answer, meeting and
  reload. After the checkpoint compatibility change, `group152.spec.ts` was
  rerun on the final code: **4 passed** (desktop/mobile, graphite/parchment).
  E2E uses the existing deterministic provider, not the live DeepSeek API.
- `npm run build --prefix frontend`: passed (existing large-bundle warning).
- `git diff --check`: passed. No full repository-wide E2E run.

Remaining limitation: live provider acceptance, real billed tokens and the
specific reported game failure require its sanitized request/provider_error and
model/config, or a live API test. Do not send API keys or private prompts for
that comparison. The fix addresses a documented, reproduced contract violation;
it does not claim every possible HTTP 400 has this cause.

## Group channel context and sequential Phone presentation

Confirmed causes: group authoring supplied members/history but did not explicitly
identify a remote text channel or include individual voice profiles. The Phone
rendered every newly committed event in the same render. Atomic commitment and
identical world_time are correct and are retained.

### Context and compatibility

Both reaction_context and autonomous group authoring now share explicit
TEXT_MESSAGE instructions. The context includes the canonical CommunicationProfile
(including technology/delivery policy), the existing bounded personality projection
or legacy character/voice fields, and each speaker's own location. Canonical
present_character_ids are supplied only for a speaker who actually belongs to
that physical scene; matching location IDs alone never establishes perception.
Other speakers' personal context is explicitly not shared Knowledge. Existing
per-speaker Knowledge and authored/read history remain unchanged.

The instructions allow real known co-presence and figurative language, humour,
gossip, conflict, profanity, and short or long messages. There are no creative
text filters, output-length rules, mandatory messenger style, new classifier or
LLM stage. Group instructions apply only to group TEXT_MESSAGE: letter/courier/
other-channel prompts and general Narrative prompts are untouched. Profiles
without text_message still offer no group initiative; custom delayed text policy
is passed through rather than assumed instant.

An exact pre-change reaction checkpoint remains reusable on Retry: only the
specific added context fields/instruction are omitted when comparing its old
source context. Other evidence/history/source changes still invalidate reuse;
Runtime validates replayed output as before. No WorldState/save/schema migration,
changes to basis_ids, remote.apply or acceptance logic were needed.

### Presentation

usePhoneArrivals retains ID/deadline metadata, not a second message/content store.
PhoneMessages always renders a filtered view of the current authorized canonical
projection, in its original order. Only newly arriving incoming IDs in the already
open group are staggered: 180 ms initial delay, normally 420 ms between messages,
with the entire planned delay capped at 2.6 seconds for large series, plus a
180 ms opacity/5 px entrance. One finite timeout targets the next deadline; no
scheduler, polling, typing state, API call or canonical timestamp is introduced.

Initial history, reload, reopening, switching groups, member management,
backgrounding and reduced motion show all available history immediately. These
transitions clear pending presentation timers. Known IDs do not replay on refresh,
Retry or rollback/reappearance. Outgoing messages flush older pending appearances.
Only pinned readers follow new bubbles; an older reading position remains fixed.
The animation uses the existing message layout and skin styles. Delivery/read
commands and their timing are unchanged.

### Verification and cost

- Backend: `python -m pytest tests/test_group_channel_context.py tests/test_group_deepseek_http.py tests/test_group152.py tests/test_group166.py tests/test_remote_decision_contract.py tests/test_phone133_followup.py tests/test_communication_cycle.py -q` — **112 passed**.
  After adding a canonical voice-profile assertion, channel/HTTP tests were
  repeated: **14 passed**. Includes actual API/jobs/SQLite, SDK mock HTTP,
  multi-NPC reaction, autonomous series, agency, Knowledge, waiting, calendar,
  reload/Retry and exact legacy author-checkpoint reuse.
- Frontend: `npm test --prefix frontend -- phoneArrivals.test.tsx phone158.test.tsx phone122.test.tsx` — **28 passed**. Covers deadlines, long text, closed/other
  views, reduced-motion changes, backgrounding, cleanup, known IDs and large series.
- Chromium: `phone-arrivals.spec.ts phone.spec.ts group152.spec.ts` — **20 passed**
  desktop/mobile, with existing graphite/parchment coverage. Then the arrival
  suite was extended to three distinct NPCs and a real failed-Extraction Retry:
  `phone-arrivals.spec.ts` — **10 passed** desktop/mobile. DOM MutationObserver
  records assert 1 → 2 → 3 canonical incoming IDs, separated by visible delays;
  reduced motion records all three immediately. Tests verify exact long content,
  unchanged world_time, stable old-history scroll, switching to another chat,
  closing/reopening during a series, and immediate history after reload.
- Actual E2E SQLite inspection: both desktop/mobile Retry jobs saved; each has
  **one author and two Extraction attempts (one failed)**, three requests total.
  No duplicate events. Screenshots inspected on both viewport sizes; artifacts
  remain outside the repository. No full repository-wide E2E run.
- Production build and `git diff --check` passed; existing bundle-size warning.
- Additional LLM calls: **zero**. Repository input-token estimates in the two-NPC
  fixture: reaction 1407 → 2327 (**+920**), autonomous author 2904 → 3810 (**+906**).
  Actual context growth depends on speaker profiles; existing context budgets
  remain enforced. These are estimates, not provider-billed tokens. No live
  DeepSeek call or paid cost measurement was made.

Files: runtime group_planning.py and remote_initiative.py; service communication.py;
Phone.tsx, PhoneContent.tsx, lib/usePhoneArrivals.ts and styles/phone.css;
frontend/tests/phoneArrivals.test.tsx and frontend/e2e/phone-arrivals.spec.ts;
tests/test_group_channel_context.py, test_group_deepseek_http.py,
group152_provider.py and e2e_server.py; this document.

Remaining risks: prompt compliance and literary quality still require real
DeepSeek playtesting; this fix does not claim a deterministic guarantee about
creative wording. Existing saved dialogue is not rewritten. Browser timing can
be delayed by a busy main thread; expired deadlines reveal immediately on the
next callback, and background/closed views never accumulate a replay. Physical
mobile devices were not tested. Knowledge/basis_ids P1 remains outside scope.

## Shared digital writing style for direct and group chats

The follow-up found concrete context gaps: the direct planner used a separate
six-item personality excerpt and lacked legacy voice, directed relationships and
emotion; group relationships excluded the controlled actor when only NPC authors
were selected. These gaps are fixed without claiming to prove why a live model
previously chose not to use emoji.

`remote_authoring.speaker_context` now serves both planners. It uses the existing
`personality.context_profile`, legacy Character/Communication Style card fields
when no canonical profile exists, the speaker's outgoing relationships to actual
interlocutors/group members (including the controlled actor), and the speaker's
own emotion/situation. Private opinions/context are not broadcast Knowledge.
Existing per-speaker Knowledge and read-history selection are unchanged.
CommunicationProfile is now also supplied to direct planning.

One `DIGITAL_TEXT_STYLE` block is used by direct `planning_context`, group
`reaction_context`, and the autonomous planner (which already reuses
planning_context). It appears once per request. It permits emoji, abbreviations,
slang/profanity, informal punctuation, expressive text and varied message lengths,
with individual and audience-dependent choices. No emoji is explicitly equally
valid. There are no quotas, random probabilities, stereotype assignments, output
filters, emoji insertion, new personality fields or style classifiers.

The block is omitted for profiles without text_message; with mixed profiles it
explicitly applies only to suitable TEXT_MESSAGE technology/settings, not letters,
couriers, telegrams or spoken calls. Historical correspondence and general
Narrative prompts are untouched. Existing personality remains the common source
for a recognizable person across channels.

Accepted pre-style author checkpoints can be reused on Retry through an exact
prior-context projection. Direct legacy personality formatting comes from the
original job snapshot. Source, options, Knowledge, history and unrelated fields
must still match, and Runtime validates accepted operations. No additional LLM
stage, new state/schema, Extraction change or message transformation was added.
Pacing, waiting, agency and basis_ids are unchanged.

Validation:

- Targeted backend command: `python -m pytest tests/test_digital_style.py tests/test_group_channel_context.py tests/test_group_deepseek_http.py tests/test_remote_decision_contract.py tests/test_group166.py tests/test_communication_cycle.py tests/test_phone133_followup.py tests/test_communication_profile.py tests/test_historical_correspondence130.py -q` — **148 passed** before the final autonomous API test was added. Final `test_digital_style.py`: **7 passed**, including that additional test (149 distinct backend cases checked).
- New integration cases use actual API/jobs/SQLite and the real SDK with deterministic
  HTTP. They cover direct/group Unicode and plain replies, failed Extraction,
  pre-style accepted journals, reload/Retry without another author, unread privacy,
  explicit read, canonical events and agency. The autonomous API/job case preserves
  Unicode NPC↔NPC content and uses one author plus existing group annotation.
  Its long transcript needs a 64K test context for ordinary Extraction; the 32K
  production budget guard correctly refused overflow and was not weakened.
- Frontend: `npm test --prefix frontend -- phone158.test.tsx phoneArrivals.test.tsx phone122.test.tsx` — **30 passed**.
- Chromium `phone-digital-style.spec.ts group152.spec.ts` — **8 passed** on
  desktop/mobile. Direct/group Unicode cases verify exact mixed Russian/English,
  combining accent, emoji modifier/ZWJ/variation-selector sequences, long text,
  punctuation, unchanged IDs after reload, and Retry author counts via accounting.
  A plain reply is deliberately present too; no test requires a live model to emit emoji.
- Screenshot inspection first exposed missing emoji fonts in the container:
  exact DOM/SQLite text was present but glyphs were boxes. Installing Noto Color
  Emoji in the test environment (no application assets or CSS changes) corrected
  rendering. Repeated Unicode E2E: **4 passed**; desktop/mobile screenshots were
  inspected with visible composed colour emoji. No screenshots/fonts committed.
- `git diff --check` passed. No full repository-wide E2E run.

Additional author calls: **zero**. Measured input estimates in the small fixture:

| Author request | Before | After | Added |
|---|---:|---:|---:|
| Direct planner | 1722 | 2489 | 767 |
| Group reaction | 2327 | 2916 | 589 |
| Autonomous planner | 3810 | 4581 | 771 |

These are repository UTF-8 estimates, not billed provider usage; actual growth
varies with profiles/relationships. Existing context/output budgets remain active.
No live DeepSeek calls or paid cost measurements were made.

Files: `backend/runtime_v3/remote_authoring.py`, `remote_initiative.py`,
`group_planning.py`; `backend/services/communication.py`; `tests/test_digital_style.py`,
`digital_style_provider.py`, `test_group_channel_context.py`, `e2e_server.py`;
`frontend/tests/phone158.test.tsx`, `frontend/e2e/phone-digital-style.spec.ts`;
this document.

Remaining risks: literary quality and frequency of expressive choices require
live playtesting; a restrained character may still legitimately use no emoji.
Emoji appearance depends on the user's platform fonts. Long transcripts with
small context windows can reach existing budget limits. Knowledge/basis_ids P1
remains outside scope.
