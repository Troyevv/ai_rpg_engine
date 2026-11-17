# Chat Mode (#260)

Baseline: `ee343deee65f627932c5a4f13aedbb41fa06be8f` (fresh master).
Independent branch/PR; no dependency on or changes to PR #248. Nothing merged.

## Owners and boundaries

- `backend/chat/repository.py`: additive `chat_mode_v1` / `chat_creation_v2` migrations and short SQLite transactions.
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

## Creating and starting a campaign (PR #261 follow-up)

The ordinary UI offers **Create from idea**, **Use ready Markdown**, and **Import existing world**.
`chat_creations` and `chat_creation_jobs` persist author drafts, settings, streamed output,
immutable generated variants and actual usage before any playable campaign exists. The separate
`chat_initial.md` prompt includes the entire Issue #260 template; it receives the author's idea
verbatim and requests world/NPC/knowledge/relationship setup without deciding player actions.
One streamed call normally produces the document. The author can edit/import/export it,
regenerate it, save/reopen the draft or explicitly continue an interrupted document.
Length/error/empty responses and structurally missing sections/labels require explicit review;
these are structural checks of a document, not literary validation or Narrative Runtime.

**Confirm initial memory → Start game** atomically creates the campaign, its approved initial
memory and one `start` job. The shared Chat worker streams the opening as the first assistant
message. Its recorded system context combines the RP prompt with `chat_opening.md`; there is
no artificial player action/message. Player input waits for a complete (or explicitly edited)
opening. Regeneration/retry retains the original request and creates another branch. Reload,
repeated confirmation and restart never generate another opening automatically. The old
`POST /campaigns` API is retained for compatibility; the normal UI uses `/creations`.

The additive v2 migration preserves old campaigns with `opening_required=0`; an established
conversation never acquires a retroactive opening. Creation edits use their own revision and
idempotency records; approval and opening reservation roll back together on capacity failure.
Keys, transport, workers, model lease and usage ledger remain shared infrastructure.

## Automatic context

New settings default to automatic context and output limits. Old stored settings without those
flags retain their explicit values. The server resolves capabilities on model selection/settings
save and before requests, and checks the serving limit under the model lease for retries too.
No completion is used to discover a limit.

- DeepSeek's [official model table](https://api-docs.deepseek.com/quick_start/pricing/), checked
  2026-11-17, publishes 1M context / 384K maximum output for `deepseek-flash` and `deepseek-v4-pro`.
  Its explicitly documented `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` aliases use Flash.
  The code uses a conservative decimal 1,000,000-token window. Other names require manual input.
- [LM Studio metadata](https://lmstudio.ai/docs/developer/rest/list): use the loaded instance's
  `config.context_length`, never the larger model training maximum. Ambiguous matching loaded
  instances use the smallest declared window; absent loaded-window data requires manual input.
- Compatible providers: free authenticated `GET /models` through the existing registered client;
  only explicit numeric `context_length` / `context_window` declarations are used. No inference
  from model names, parameter count or a generic training maximum.

The ordinary screen shows model selection and automatic context. Output/temperature/manual
window, thinking, summary-model override and memory reserves live under additional settings.
Automatic output is up to 4,096 for RP and 16,384 for memory, bounded by one third of the window.
Initial generation requires at least 8,192 output capacity and enough input space for the full
prompt/template; it fails before a provider call if that capacity is unavailable. This is a
capacity safeguard, not a guarantee that any arbitrary number of NPCs fits one answer.

An optional real offline tokenizer is supported for the known DeepSeek API models. The
advanced model settings offer **Install DeepSeek tokenizer for free**; this explicit action
fetches the archive linked by [DeepSeek's current token-usage documentation](https://api-docs.deepseek.com/quick_start/token_usage/).
The installer verifies pinned archive/JSON SHA-256 hashes and reads only `tokenizer.json`,
never executing the archive's Python demo or `trust_remote_code`. The approximately 1.9 MB
archive / 6.4 MB JSON are cached under `.runtime/chat-tokenizers` (ignored), not redistributed
in git. `RPG_CHAT_TOKENIZER_PATH` can select another server cache file. Offline installation
is also available via `python -m backend.chat.tokenization`. No inference or API key is used.

When the matching verified JSON and the existing tokenizers library are available, budgets
use real tokenization of the serialized request, with an additional protocol estimate and
15% safety reserve. Total request usage remains explicitly approximate because API framing
is not an exact offline contract; actual usage still comes from the response. The demo's
`model_max_length` is deliberately NOT used as the serving context window. Unknown model
identities, absent/unverified files or unavailable libraries retain the conservative UTF-8
byte estimate. No files download silently on ordinary turns and no fallback tokenizer is
guessed from an arbitrary compatible model name. Context warnings may appear early; history
is never silently removed and memory/next-chapter updates still require explicit confirmation.

The new three-part workflow has **not** used paid LLM calls. The live acceptance below predates
this follow-up; it does not verify idea generation or opening quality. Free tests substitute only
provider IO and exercise the actual production API, service, SQLite and browser UI.

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

Budget is explicitly **an estimate**: matching verified tokenizer counts when available,
otherwise UTF-8 serialized input bytes; plus framing, output reserve and a 15% window
reserve (at least 512). Provider-reported usage remains separate. The configured
manual context window must match the actual endpoint/model; known limits cap it. Soft threshold defaults to .85 and
checks both ordinary reply and the separately reserved summary request, including the
next RP output plus framing before warning about a future summary. Imported memory,
new input, prompt/model/window changes are checked again. Oversized requests are rejected
before provider IO without truncation. Confirmation reserves another 512 estimated input
tokens for the next turn. Tail is bounded by configured tokens and at most eight messages;
no messages are duplicated in stored history.

Summary target is an instruction to compress, not permission to discard critical facts.
A too-large full document stays editable; it is not silently cut. No RAG or automatic
retrieval of forgotten archived facts is promised. User-confirmed memory may contain spoilers.
Prompts direct literary behavior but do not prove model accuracy or Knowledge compliance.

Usage, finish reason, latency and versioned pricing use the existing ledger. Stages distinguish
`chat_initial`, `chat_continue`, `chat_start`, `chat_reply`, `chat_summary`, `chat_regenerate`, `chat_retry`. Unknown remote usage/cost remains
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

`GET /chat/defaults`, `POST /chat/capabilities`, `POST /chat/source`, `GET|POST /chat/campaigns`;
`GET|POST /chat/creations`, `GET|PUT /chat/creations/{id}`, `POST /generate|confirm`,
`GET /jobs/{id}|/jobs/{id}/events`, `POST /jobs/{id}/stop` under a creation;
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
