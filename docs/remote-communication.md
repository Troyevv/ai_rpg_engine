# Remote communication (#70, Epic #36)

Communication extends Runtime v3. There is no additional runtime, phone database,
avatar store or Knowledge propagation service.

## Canonical ownership

`Meta.communication` declares available text/voice channels, presentation and an
explicit region/emergency-number profile. Defaults disable communication. Existing
saves acquire defaults during read normalization; historical snapshots are not
rewritten. Explicit initial JSON can supply `world.communication`, `contacts`,
`conversations` and `remote_events`. A relationship never creates a contact/group.

Contacts belong to a Character and keep their saved label separate from canonical
names. Person links may be unresolved. Shared/service addresses remain destinations;
an individual reached through them need not become their permanent owner. Exact
address evidence, not name similarity, is required to reuse an existing identity.
Minimal new Characters are established only by an actual endpoint interaction.

`WorldStateV3.remote_events` contains canonical interaction state. Immutable History
batches audit transitions to those records, including the same stable interaction
ID. The phone, call log and notifications are projections, not separately writable
copies. Commands use operation receipts in the existing History DAG; a replay with
different content is rejected. Transactions check save revision and active jobs.
Rollback and variant selection restore original snapshots and their History heads.

## Agency and information

Player commands are typed operations. Exact authored text is retained. A delivery
does not grant Knowledge. Explicit reading creates a secret communicated-testimony
Fact and normal Knowledge/History provenance; it does not certify the message's
assertions as objective World Truth. Group delivery freezes its recipient set;
joining later does not inherit messages. Leaving stops future group delivery.

Calls retain physical locations and camera presence. `interaction_focus` selects
physical or connected-call speech. Answer/decline/ignore/end are deterministic
phone controls. Canonical elapsed time can expire ringing. No browser telephone
scheme, external emergency endpoint or real telephony API is used.

## Event-first orchestration

The existing #69 initiative permit exposes a bounded remote opportunity set.
An actual pending interaction or established active intention/thread may permit one
optional planning request. There is no per-contact/group loop of LLM calls and no
request on opening the phone. Structured proposals are validated before narrative
generation. Rejected proposals cannot create phone state. Accepted events are
staged in the job's immutable original context; public job prose is withheld until
the event and final narrative commit atomically. Retry and regeneration reuse that
staging. Failed/cancelled generation publishes neither provisional event nor cue.

The existing ContextScope/Context Builder includes at most six recent accessible
communications, bounded message text and explicit call constraints. Unread message
content is excluded. Phone-disabled worlds receive no phone instruction payload. Under budget pressure,
older communication rows are omitted while the latest cue and active call remain.
Raw remote lifecycle audit payloads never bypass the perception-filtered projection.
Existing extraction is not permitted to create phone lifecycle transitions.

## UI and portraits

`Phone.tsx` uses existing Dialog/theme primitives near the main composer. It exposes
contacts, direct/group conversations, freeform send, call controls/history, and
configured emergency entries. No suggested phone replies are generated.
`CharacterAvatar` and the existing portrait selection/API serve all phone subjects.
Unknown contact identities have no Character asset URL or portrait prefetch.

## Verification boundaries

Deterministic tests cover the protocol and branch/variant behavior. They do not
prove arbitrary provider prose obeys semantic instructions. No paid DeepSeek calls
are part of this change. #43/#44/#45/#46 remain separate; final phone visual polish
belongs to #45. Browser checks and the complete acceptance audit must pass before
the PR leaves draft. Message-derived #66 agreements use the existing
`scheduled_event_changes` handler: referenced messages must be perceived by the
agreement participants, player consent must quote actual authored input, and
relative dates anchor to the proposal message's canonical timestamp. The
`remote_source_ids` field preserves that provenance on the ordinary commitment.

## Acceptance coverage

| Issue #70 criteria | Runtime / UI coverage | Deterministic evidence |
| --- | --- | --- |
| 1–5 | Capability-gated UI, owned contacts, independent labels, control switch, exact player text | contacts/switch, ordinary cycle, persisted idempotency; phone E2E |
| 6–8, 24–27, 30 | One optional typed initiative before prose; no autonomous player response; explicit read provenance | event-first failure/retry/regenerate, rejected proposal, raw History/UI privacy, delivery/read tests |
| 9 | Ordinary #66 handler, mutually perceived source IDs, authored player consent, canonical proposal time | message agreement test with unread and forged-proof rejection |
| 10–11 | Physical scene retained; explicit call focus; restricted audible witnesses; canonical timeout | call controls, extraction audibility, setting-neutral channel, device-choice tests |
| 12, 14 | Bounded relevant context, no contact polling, no #43 implementation | saturated newborn-triplets world with 200 unread messages; existing context-compaction regressions |
| 13, 29 | Existing save snapshots, History DAG receipts, original generation context | persisted replay, outage/retry, variant selection, rollback and ordinary save/reload cycle |
| 15–17 | Existing Dialog/theme/avatar system; ordinary Narrative and Tabletop remain independent | desktop/mobile phone E2E plus complete existing Python/Playwright suites |
| 18–23 | Explicit direct/group containers and membership, frozen delivery recipients, no social-graph inference | late join/removal/former-member reading tests; group membership E2E |
| 28 | Phone chat and call log derive from canonical records after reload | phone E2E and repository reload checks |
| Later identity additions | Unresolved contacts, exact-address linking, minimal individuals, shared/service destinations | lazy identity, reply-container continuity and unavailable/blocked endpoint tests |
| Later emergency additions | Configured services only, selected service retained even with a shared number, canonical call history | emergency configuration/shared-number tests and emergency E2E |
| Later portrait additions | Shared current portrait/crop and silhouette/initials; unknown identities have no asset URL | portrait authorization test, shared portrait E2E, existing #74 tests |

A provider can still violate literary instructions; deterministic fixtures establish
Runtime boundaries, not universal compliance of arbitrary model prose. Manual QA
in `docs/manual_qa/narrative_v4/phone.md` covers the live-provider visual/semantic review.
