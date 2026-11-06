# Historical correspondence (#130)

LETTER, COURIER_LETTER and TELEGRAM extend the existing RemoteEvent, History,
calendar and SQLite transaction path. No second runtime or mailbox store exists.

## Authoring and ordinary streaming

The updated #127/#130 decision (2026-10-30) permits the reader to see an NPC's
letter in Narrative. Reader visibility never grants character Knowledge.
All worlds now use the ordinary provider `delta.content` stream, including
historical/mixed worlds and turns without letters. There is no
`publish_narrative` tool, forced tool choice, JSON envelope, callback or whole
scene buffer. An incomplete/interrupted stream remains provisional under the
existing #72 job contract and cannot commit a letter.

When authoring a new outbound NPC letter, Narrative includes its complete text
in an optional top-level Markdown fence with the language `letter`:

~~~~markdown
Она перечитала написанное и запечатала конверт.

```letter
Дорогой друг,

Завтра я вернусь домой.
Анна
```
~~~~

This ordinary, reader-visible Markdown is streamed unchanged. The reader sees
letter fences as literal literary quotations, not code blocks, both during
streaming and after reload. Rendering does not alter the authored source; other
Markdown fences keep their usual behavior. No special block
is required on a turn without a new letter; SMS and calls keep their formats.
The scene may describe writing without quoting the text a second time, but a
completed letter must have a complete authored source block. Quoting/reading an
existing letter does not use a new `letter` fence and does not create a send.

`letter_sources.parse` uses the existing CommonMark parser, accepts only closed
top-level letter fences, and copies the full original body between delimiters.
Only the framing newline before the closing fence is excluded. Empty,
unclosed, nested and unbound sources are rejected. There is no regex
inference over arbitrary literary prose. Neither source count nor historical
letter length has an application limit. Canonical text is never truncated;
Context Builder selects input within the model budget without rewriting stored
letters. Infrastructure/context exhaustion is a technical error, not a
literary validation failure. Sources receive local IDs `letter-1`,
`letter-2`, etc. Extraction interprets sender/recipient/channel and binds the
source ID; Runtime copies the full body. Extractor-supplied content cannot
replace it, and a summary or missing body cannot become a fictitious send.

The complete Narrative is already checkpointed by the existing job system.
Retry reconstructs the same source blocks from those recorded bytes, without a
new Narrative call. Background simulation and bounded LTA use the same source
contract. GM correspondence support is included in the common Context Builder
token budget; older optional rows are removed under pressure, never appended
after budget selection. Source validation does not judge literary meaning or require optional
semantic annotations. Player letters use explicitly supplied Remote command
content; model-authored controlled-actor sends/reads remain prohibited.

## Canonical delivery, Knowledge and API

The canonical event stores exact content, stable identity, sender/recipient,
`world_time` (sent minute), `delivery_due_at`, lifecycle and provenance. Opening
returns that stored text without any LLM call. Delivery and reading are distinct:
only an accepted explicit read acquires source-bound communicated-text Knowledge,
once. This is testimony, not proof of every assertion in a letter. Commitments
still require the existing mutual perception/assent rules.

CommunicationProfile controls channel availability and `delivery_minutes`.
Defaults are 4320 minutes for letters, 1440 for couriers and 60 for telegrams;
explicit instant policy overrides the delay. All living canonical NPCs are
addressable without a contact, device, number, geography or physical address.
Landline calls reuse the voice runtime. Correspondence never moves characters
or creates a shared physical scene.

Due events settle in chronological order through ordinary turns, Time Skip and
Long-term Advance, including zero-LLM-budget year advances. A dead recipient
produces `undeliverable`. No real-time timers or per-day/per-NPC polling exist.
Retry, regeneration, rollback, branch selection and reload use the existing
revisioned snapshots/history and idempotent Remote command path.

- `GET /api/saves/{id}/correspondence`: controlled actor's mail projection;
  delivered incoming metadata is available before read; content after read.
- `POST /api/saves/{id}/correspondence`: `{revision, command}`. Sending uses
  `action=send`, historical `channel`, `character_id`, player-authored `content`
  and `operation_id`. Reading uses `action=read`, `event_id`, `operation_id`.
- The existing `/phone` command path remains compatible. Historical events stay
  outside modern phone projections. #131/#132 own the immersive writing/reading UI.

A reader may already have seen the same text in Narrative. Character-facing
Knowledge, context and projections still obey read access. Public literary text
is not interpreted as automatic perception by every character.

## Compatibility

Canonical events and historical snapshots are not rewritten. The old
`game_jobs.private_artifacts_json` column is retained as a read-only recovery
fallback for completed Narrative checkpoints made by the previous PR version;
new jobs do not populate it. Existing request logs marked as using the old
private transport retain their diagnostic redaction. New historical worlds do
not activate that blanket redaction. No new schema or parallel payload store
is introduced by this revision.

## Verification

`tests/test_historical_correspondence130.py` uses the actual provider adapter
with simulated streaming HTTP, real Resolver/Remote, API/jobs and SQLite. A
blocked provider proves public progress is visible before generation completes,
with/without a letter in historical-only and mixed worlds. It also covers full
literal text, missing/incomplete sources, reader vs character Knowledge, player
agency, API send/read without generation, delivery deadlines, death, NPC
read/reply/silence, year LTA, legacy checkpoint retry, rollback, regeneration,
variant branches and fresh-repository reload.

The desktop/mobile browser test checks visible authoring while the job is still
generating, reader-visible letter text, unread canonical mail, reload, and exact
API reading. Existing SMS/group/CallScene and streaming suites remain in CI.
Live DeepSeek adherence is NOT VERIFIED (NOT RUN without a safely available key); provider
fixtures prove transport and lifecycle, not semantic adherence by a live model.
