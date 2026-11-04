# Story notifications and dossier fog (#168)

Depends on merged #178 / #179. Privacy and story classification remain separate.

## Transaction and visibility

`notifications.record_story_changes` consumes the accepted before/after state and
History batch. `append_history` records its reference-only receipts in
`state_changes` inside the same SQLite transaction as the snapshot/variant. A
failed/cancelled/rejected operation publishes neither snapshot nor notification.
Ordinary engine jobs (including communication) and direct phone read commands use
this boundary. No event is derived from streaming text or a load-time state diff.

Secret discovery uses `secrets.first_confirmations` unchanged: classified story
secret, same controlled actor, first confirmed `known`, witnessed source and
canonical fact link. A secret created and learned in the same operation produces
one `secret_new`; an existing one produces `secret_revealed`. Suspicions, delivery,
other minds, private household messages and repeat reads do not produce notices.

New extracted Threads receive runtime-owned `discovered_by` from a valid accepted
source Event's witnesses, with source facts checked against their disclosure
rights. Participation/stakes alone grant nothing. A later witnessed update can
make the line visible but cannot emit a second creation event. Extraction cannot
set this list directly. `None` preserves existing authored/legacy Thread
visibility, without inventing an opening on load. The raw schema describes the
existing `source_event_id` field; this adds no model call.

`read_story_receipts` queries only notice receipts from the active immutable
History ancestry. It is independent of the bounded narrative context tail.
`story_notifications` resolves text from the current authorized projection and
filters by controlled actor. Unknown fact text/evidence never enter a receipt or
a response. Retired/refuted/replaced knowledge leaves a neutral historical marker
without republishing objective fact text or linking to a now-hidden entry.

## Presentation

`notification_history` supplies the three story event types. Existing relationship
and lifecycle notifications keep their runtime and renderer. The shared display
setting controls live popups; the story journal remains available when disabled.
Live additions are queued after a new save revision. Initial load/control change
establishes a baseline. Queue membership is intersected with active history so
rollback cannot leave a stale popup. Phone, dialogs and inspector defer popups;
hover/focus pauses dismissal. Explicit journal/notification navigation preserves
the mounted Narrative workspace, scroll, composer draft and actions.

Each committed event has an opaque ID derived from its unique History commit and
canonical transition. Thus independent regenerated variants cannot share a viewed
receipt. A shared secret has one event and one row identity across its subjects.
The server adds `reveal_id` only to confirmed rows with a committed discovery;
known-at-start/legacy entries have no reveal animation. Unknown slots remain the
#178 `{id,status}` contract.

`storyPresentation` stores only presentation acknowledgements, scoped by save,
controlled actor, event and kind (`fog` or `toast`). This is not Knowledge. Reload
and repeated opening do not replay completed effects; an unseen committed reveal
waits for the first visible dossier visit. Rollback restores canonical closed
rows and excludes the former event from active history. Browser storage denial
falls back to session memory; clearing browser storage resets presentation only.

## Fog and accessibility

`fogRenderer` rasterizes one periodic, domain-warped, multi-octave density texture.
Each row composites three layers with different speeds, phases and directions.
Disclosure gradually thins the volume, separates the layers and opens a soft
central clearing over 2.1 seconds. Adjacent closed rows continue independently.
No hidden text is rendered under a mask: the text appears only in an authorized
known response. All closed rows use the same geometry and neutral label.

One shared animation clock caps rendering at 24 fps; IntersectionObserver,
explicit workspace activity and document visibility stop inactive work. Canvas
resolution is bounded, noise is shared, and each visible frame composites textures
rather than recalculating per-pixel noise. Reduced motion uses stationary volume
and immediate readable disclosure. Semantic labels, focusable long-text regions,
source details, keyboard navigation and theme tokens work without canvas semantics.
The effect does not require WebGL, an asset download or an LLM request.

## Compatibility and checks

No SQL schema migration, new canonical store or historical snapshot rewrite.
New optional Thread metadata defaults to legacy visibility. Existing saves and
initial knowledge produce no synthetic notifications.

Focused tests cover commit failure, first knowledge/suspicion, private reading,
source-bound Threads, actor changes, repeated commands, shared/world secrets,
context-tail exhaustion, retired knowledge, real engine commit/reload, sibling
regeneration and rollback. React tests cover queue and presentation receipts,
phone deferral, exact navigation payloads and hidden-tab scheduler cleanup.
Playwright exercises desktop/mobile, Graphite/Parchment/Cyberpunk, idle bitmap
changes, in-place and first-visit disclosure, long text, history navigation,
phone reading, reload, draft/actions and reduced motion. Frame samples are
reported for browser emulation, not claimed as physical-device benchmarks.

Runtime verifies semantic provenance; the existing Extractor still determines
whether a literary source confirms truth. No paid provider call is added or
required by the deterministic test fixtures.
