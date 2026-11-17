# Chat Mode (#260)

Baseline: `ee343deee65f627932c5a4f13aedbb41fa06be8f` (fresh master).
Independent branch/PR; no dependency on or changes to PR #248. Nothing merged.

## Owners and boundaries

- `backend/chat/repository.py`: additive `chat_mode_v1` migration and short SQLite transactions.
- `backend/chat/service.py`: explicit jobs, one provider attempt, cancel and restart recovery.
- `backend/chat/context.py`, `prompts/chat_*`: standalone context, full user template, RP and memory prompts.
- `backend/chat/source.py`: explicit read-only snapshot of a world/current accepted Narrative state.
- `backend/api/chat.py`: `/api/chat/*` HTTP/SSE adapter; no domain interpretation in handlers.
- `frontend/src/Chat*`, `useChatScroll.ts`: campaign, messages, review/editor, settings, history and branches.
- Shared owners remain `llm.chat_stream`, `Credentials`, `tracked_stream`, `llm_requests`, model lease,
  SQLite connection infrastructure, Radix Dialog, safe Markdown, skin tokens and React/Vite.

Chat has no dependency on the Narrative generation pipeline, Extraction, WorldDelta,
Resolver, Director, repair, simulations, phone, or lifecycle controls. The one-time
source adapter reuses existing human-readable world projection; it is never called
by a Chat turn. Original source text, accepted history fragment and provenance are
captured before creating the copy; users review them before starting. No hidden LLM
conversion, title generation, search, speech, tools, memory agent or automatic rollover.

## Storage, revisions and cutoff

`chat_campaigns` carries a constant `mode=chat`, revision and active branch.
`chat_branches` has a head sequence and current memory/config/chapter references.
`chat_path` copies only prefix references on fork, not message bodies.
`chat_messages` stores original user input before provider IO and the streamed prefix;
only a running output may be updated. Terminal messages are immutable.
`chat_chapters` pins seed memory/config. `chat_memories` stores full Markdown,
parent version, covered cutoff, application point and bounded carry-over references.
`chat_configs` stores immutable settings and their application point.
`chat_jobs`, `chat_drafts`, `chat_operations` retain request snapshots, source revisions,
original partial/complete summary, idempotency fingerprints and outcomes.
`chat_sources` retains the explicit initial projection and origin.

Schema creation is additive, transactional and idempotent. Existing Narrative tables,
snapshots and saves are not converted or rewritten. Back up the whole SQLite database
and the existing `.credential-key`; disk capacity still bounds retained history.

Summary input = previous approved document + only uncovered active-branch messages.
Confirmation checks the captured revision/branch and new context size before a single
transaction creates the approved version, optional next chapter, tail and new head.
No provider call holds a transaction open. Repeating confirm cannot create another chapter.
A checkpoint without a new chapter also advances cutoff. Manual edits preserve the old
cutoff so unsummarized dialogue is never silently dropped. Their application point still
prevents using later author knowledge in an earlier fork.

Editing copies the prefix strictly before the target, adds edited text, discards no original
rows and excludes the old suffix. Memory/config parent chains restore the last compatible
application point. Regenerate/retry replays the exact recorded request context and settings,
not current future state. All referenced IDs are validated against the campaign; read-only
archive viewing never changes the active branch or calls a provider. Message pages are
bounded (40 default, 100 maximum); the browser initially renders only one page.

## Context and costs

Budget is explicitly **an estimate**, UTF-8 serialized input / 2 plus framing, output
reserve and 15% window reserve (at least 512). It is not a tokenizer. The configured
context window must match the actual endpoint/model. Soft threshold defaults to .85 and
checks both ordinary reply and the separately reserved summary request. Imported memory,
new input, prompt/model/window changes are checked again. Oversized requests are rejected
before provider IO without truncation. Confirmation reserves another 512 estimated input
tokens for the next turn. Tail is bounded by configured tokens and at most eight messages;
no messages are duplicated in stored history.

Summary target is an instruction to compress, not permission to discard critical facts.
A too-large full document stays editable; it is not silently cut. No RAG or automatic
retrieval of forgotten archived facts is promised. User-confirmed memory may contain spoilers.
Prompts direct literary behavior but do not prove model accuracy or Knowledge compliance.

Usage, finish reason, latency and versioned pricing use the existing ledger. Stages distinguish
`chat_reply`, `chat_summary`, `chat_regenerate`, `chat_retry`. Unknown remote usage/cost remains
unknown; local provider pricing follows existing zero API-cost semantics. Synthetic
1000-message tests establish storage, context and UI behavior, not 1000 played turns
or literary reliability.

Live acceptance on 2026-11-17 used an explicitly approved $1 ceiling: 12 RP replies and
2 summaries with DeepSeek V4 Flash, thinking off, through the production UI in an isolated
database. The ledger recorded exactly 14 attempts, 92,811 input and 16,519 output tokens,
including 52,480 cached input tokens; the versioned tariff estimate was $0.016118490
(not an independently verified invoice). Three chapters retained all 24 messages, with
two reviewed memory versions; reload, composer draft and archive navigation worked.

Literary acceptance required manual review. The first summary hit the deliberately selected
4096 output limit and was visibly partial; it was completed/edited before explicit acceptance.
The second used 8192 output tokens and completed, preserving dates, asymmetric trust,
secrets, unknown fields and a completed promise, but needed a correction to already answered
questions. Memory grew instead of reliably reaching its target size. RP invented an earlier
meeting and twice withheld a letter's content despite explicit reading. The RP prompt now
clarifies observable action results, private reading and established knowledge; the last two
approved calls exercised that exact prompt and exposed the letter without giving its content
to the other NPC. This is limited evidence, not a guarantee against further chronology,
perspective or knowledge errors. Detailed settings and results are in the PR.

## Failure and access model

Stop, empty, length, error and interrupted outputs remain visible with explicit status.
They cannot silently become complete model context or an approved summary. Users may edit
and explicitly accept partial text or start a new paid retry. Restart recovers the saved
prefix (and a longer response journal if available), never automatically calls the provider.
A DB failure cannot mark an uncommitted answer as saved. If the disk remains unwritable,
the last durable prefix is all that can survive a restart; restore writable storage first.

This app retains the existing **trusted single-user/local server** access model and
same-origin write protection. Campaign IDs are object scope, not authentication. No new
multi-user account boundary is claimed; public hosting still requires the app's external
auth/TLS boundary. Keys use server credentials/environment only, never Chat request bodies,
localStorage, prompts or exports. Local browser storage contains only input/editor drafts
and selected UI state. Markdown uses the existing renderer with name linking disabled.

## Main API

`GET /chat/defaults`, `POST /chat/source`, `GET|POST /chat/campaigns`;
`GET /chat/campaigns/{id}` and `/messages?branch=&chapter=&before=&limit=`;
`POST /budget`, `/generate`, `/edit`, `/select`, `/memory`;
`PUT /settings`; `GET /versions`;
`GET /jobs/{id}`, `/jobs/{id}/events`, `POST /jobs/{id}/stop`;
`GET|PUT /drafts/{id}`, `POST /drafts/{id}/confirm|cancel`.
All paths have `/api` prefix. Mutations use campaign revision plus client idempotency token;
job/chapter acceptance is checked again transactionally. Draft text edits do not alter
approved versions or recorded provider context.

See [UI provenance and license](upstream.md). Test results are recorded in the PR, including
exact commands, browser matrix and unrun live acceptance. No screenshots/videos are committed.

A draft additionally has its own edit revision: competing tabs cannot overwrite each
other or confirm an older edited document. The requested rollover/checkpoint choice
survives reload. Read-only `/jobs/{id}/requests` exposes the existing sanitized request
ledger through the same campaign scope for author diagnostics and cost comparisons.
