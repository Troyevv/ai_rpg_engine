# Historical correspondence (#130)

`LETTER`, `COURIER_LETTER`, and `TELEGRAM` are RemoteEvent channels, not a
second runtime or history. `world_time` is the canonical send minute;
`delivery_due_at` is captured on send, so later profile edits do not reschedule
mail. `updated_at`, `delivered_to`, `read_by`, and ordinary Remote History
transitions record delivery/read provenance. The payload is stored once in the
canonical event; immutable snapshots and job recovery records retain their
normal copies. No mailbox database, timers, per-day simulation, or send/read LLM
request is introduced.

## Authoring and transport

Previously `llm.chat_stream` published `delta.content` verbatim to engine job
progress, and ignored `delta.tool_calls`. An inline letter or JSON suffix could
therefore escape into SSE before Extraction saw it. The old completion check
also rejected the `tool_calls` finish reason.

Worlds with historical channels (or retained historical correspondence) now
request one `publish_narrative` tool result containing `narrative` and typed
`artifacts`. The existing Narrative request authors both. The adapter buffers
arguments, accepts one tool call, validates the complete object and unique
artifact IDs/JSON keys, and then yields only public narrative text. Raw content,
unknown/multiple tool calls, missing/truncated payloads and interrupted streams
fail closed; no private argument bytes enter job progress or exceptions.

**Tradeoff:** this transport buffers the public scene until the provider finishes;
it does not provide token-by-token public prose in historical worlds. Modern
worlds keep their original prose transport. Returned Narrative, SMS, group chat
and CallScene presentation formats remain unchanged. No second generation call
is made to finish a tool interaction.

DeepSeek thinking mode does not support forced named tool selection. With
thinking enabled, use `tool_choice=auto` but still require a valid typed result
locally. A provider that returns plain prose instead fails safely; thinking is
not silently disabled. See the [DeepSeek API contract](https://api-docs.deepseek.com/api/create-chat-completion/).
Live adherence of a specific model is **NOT RUN** without a configured key.

The existing job table has an additive `private_artifacts_json` column. Payload
and narrative completion are checkpointed in one transaction, guarded by status
and attempt epoch. Extraction retry uses those original bytes. Extractor receives
artifact metadata, not contents, and binds `artifact_id` to an accepted send.
Runtime requires matching IDs/channel, rejects missing/unbound/reused payloads
and rejects model-authored voluntary sends/reads for the controlled actor.
Extraction cannot repair a missing letter by writing one.

Background and Long-term Advance authoring use the same adapter and existing
bounded LLM budget. GM author context is limited to six correspondence records;
NPC-only contents are not public Character Knowledge. An explicit NPC read may
be extracted for an existing delivered event; an answer is optional and must be
another Narrative-authored artifact. No deterministic reply is manufactured.

## Delivery and access

CommunicationProfile `delivery_minutes` accepts positive bounded integer minute
delays. Defaults: letter 4320, courier 1440, telegram 60. Explicit `instant`
delivery policy overrides the delay; default historical presets remain delayed.
The field is accepted by generation input/import/editor profile APIs and is not
requested again from the world-author model.

Any living canonical recipient is addressable by ID without contact, device,
number, geography or address. Landline uses the existing voice-call mechanism.
Pending mail is settled in `(due minute, ordinal, ID)` order by ordinary clock
advancement, Time Skip and Long-term Advance, including zero-LLM-budget advances.
A dead recipient produces `undeliverable`, retaining the original correspondence.
In a normal turn, deadlines before its life-change boundary observe the earlier
life state; later transitions cannot retroactively undo delivery.

Delivery grants no Knowledge and does not expose text. Explicit read uses the
existing Remote command and creates a source-bound communicated-text fact and
Knowledge acquisition once. This is knowledge of testimony, not proof of every
assertion inside the letter. Agreements still require the existing #66 mutual
perception/assent checks.

- `GET /api/saves/{id}/correspondence`: controlled-actor projection. Incoming mail
  is absent before delivery, and has no content field before read.
- `POST /api/saves/{id}/correspondence`: existing revisioned Remote command service;
  `send` requires a historical `channel`, `character_id`, authored `content` and
  `operation_id`; `read` requires `event_id` and `operation_id`.
- The existing `/phone` command path remains compatible. No parchment UI or new
  communication application is introduced; those belong to #131/#132.

The phone projection excludes historical events. Public patches omit historical
payloads; fact/Knowledge projections respect the controlled actor's read access.
Accounting retains usage/timing but removes GM request/response bodies for saves
that used the private transport, even after rollback. Archive responses retain
public turn summaries, not raw snapshots. Server-side canonical history and
request logs are retained. These are structural projections, not text regexes,
CSS hiding, or client-side filtering.

## Verification

`tests/test_historical_correspondence130.py` exercises real provider adapter
chunk handling with simulated HTTP, real Resolver/Remote, API/jobs and SQLite:

- typed NPC send; no Extractor authorship; missing/malformed payload and agency;
- all three channels, profile timing, direct recipient without location/contact;
- delivery != read; exact text and one Knowledge acquisition; NPC read/reply/silence;
- death before delivery and later death after a due deadline;
- Time Skip before/across deadline and real one-year zero-budget LTA jobs;
- retry without another Narrative call, regenerate, rollback, alternate variant
  selection, new Repository reload and next ordinary turn;
- API/SSE/accounting/archive/History projection privacy, including NPC-only reads;
- interrupted/multiple/wrong-finish/duplicate-key transports at character boundaries.

`frontend/e2e/historical-correspondence130.spec.ts` checks browser DOM, received
responses/logs, reload and explicit API reading on desktop/mobile. Existing
phone, phone-completion, narrative-phone138, communication-profile and long-term
browser suites cover compatibility. No browser video or generated QA artifacts
are committed. Live model semantic adherence remains separate from fixture proof.
