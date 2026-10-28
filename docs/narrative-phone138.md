# Narrative → canonical phone (#138)

Baseline: `master f19ae96b2086ea91e27056fd80097e3f19462dc8`, the merge of #137.
The implementation follows #136's semantic authority contract. The newer #138
supersedes #70's historical prohibition on creating communication from Extraction.
The existing event-first communication planner and player phone commands remain
compatible; neither is a required permit for this bridge.

## Contract and ownership

Ordinary DeepSeek Narrative authors NPC communication; the same ordinary Extraction
returns optional `RawTurnResult.remote_events`. No new provider request, prose parser,
phone store, screen, database table or Runtime is introduced. `narrative_remote.py`
is an adapter in StateResolver, calling `remote.apply()` with `RemoteCommand` and
`autonomous=True`, not a second lifecycle implementation. The resulting `RemoteEvent`
and History transitions join the existing StatePatch and atomic repository commit.

Each extracted record carries canonical `sender_id`, `recipient_ids`, `channel`,
exact authored `content` for a message, optional absolute `minute`, `status`,
`ended_at`, `contact_id`/`conversation_id`, `existing_event_id`, `source_event_id`,
and ancillary `evidence`. `ExtractedRemoteEvent` is an input DTO, not persisted state.
The producer schema and parser use that same model. Missing `remote_events` means
no change, preserving old extraction payloads and saves.

- A new message must have nonempty extracted text. Nothing generates missing text.
- A new call rings; caller hangup or canonical timeout may finish it in the same
  scene. Interleaved messages and endings retain timestamp order. Existing answered
  calls still end through #133's `call_lifecycle_changes`.
- Established direct routes and exact group membership are reused. An explicit new
  address may use `established_contact={label,address}`; the existing contact command
  and identity boundary apply it. Repeated addresses are reused, conflicting identity
  requires repair. There is no automatic reverse address or bulk contact creation.
- The adapter never sends, reads, answers, declines or ignores on behalf of the
  controlled actor. A reference to an already committed player-authored message is
  read-only. UI buttons keep their existing deterministic API.
- Delivery is not reading. Linked message Events cannot grant an unread recipient
  Knowledge or expose their content as a public Fact. The existing Remote read
  operation grants source-bound testimony. Hidden sender identity stays hidden in UI.
- Event timestamps lie inside the canonical turn interval. A genuinely unspecified
  time uses the final turn boundary with `remote_time_unspecified` diagnostics.
  No second elapsed time is applied; timeout uses existing Remote advancement.
- Operation identity is derived from turn, Resolver mode/namespace and ordinal,
  never a random invocation/job ID. Retry and regenerate use the original snapshot;
  rollback/variants restore the existing History DAG. An existing event depiction
  is linked by `existing_event_id`, not sent again.

The original narrative is retained byte-for-byte by this bridge. A phone event never
adds the sender to physical presence, changes POV or moves a Character. Following
contexts use the existing bounded communication projection. Direct IDs can resolve
an established route only when a remote event is actually extracted: no new per-contact
poller or whole-contact-book projection is added to ordinary eventless turns.

## Failure and prompt budgets

Invalid required payload, routing, identity, time, agency or Knowledge references
raise a targeted repairable structural diagnostic. The engine's existing maximum
one extraction repair uses the same prose and original context. Exhaustion publishes
no partial WorldState/History/phone event. Missing optional evidence or an unavailable
auxiliary source Event does not discard a complete communication event; turn provenance
is sufficient. Existing #136 semantic revision rules remain in force.

Phone instructions/schema are conditional on setting capabilities. Both generation
and extraction receive explicit disabled capabilities for settings without phones.
The old “never invent incoming messages/calls” instruction is removed. Under hard
context pressure, optional scene/Director attribution schema may be omitted before
essential phone outcomes; runtime parser support, physical state, agency, Knowledge,
time and completed narrative are retained. Limits and provider call counts are not raised.

## Acceptance coverage

| Tests | Coverage / source |
|---|---|
| T01, T05, T06 | Exact message, unchanged prose, unread projection, read testimony, remote location, source-bound Knowledge/public-Fact rejection; `test_narrative_phone138.py` |
| T02 | Real ringing plus existing answer/decline/ignore; new unit tests and existing phone API/browser regressions |
| T03 | Negative, intention, offer, past quotation, rumour, mention and dream semantic fixtures return no new event; no Python interpretation of prose |
| T04, T07 | Multiple messages, call/message interleaving, timestamp order, one clock, direct/group contacts, hidden identity, explicit new address/reuse |
| T08 | Missing text, bad IDs/address/time/agency, bounded repair, late failure rollback, no fabricated message or false successful commit |
| T09 | Deterministic identities, existing-event reference, real API Retry/regenerate/variant/rollback/sibling/reload, exactly one accepted History delivery |
| T10 | Real API/jobs/SQLite Start → message → read/reply → incoming call → answer → conversation → NPC hangup/agreement → reload → next ordinary turn |
| T11 | `narrative-phone138.spec.ts`: same path through actual browser controls in desktop/mobile, graphite/parchment, no overflow, persisted events/prose |
| T12 | Disabled setting rejects delivery, capabilities in assembled generation context, capability-gated schema |
| T13 | 110 additional NPCs, long completed prose retained, bounded communication projection; successful ordinary API path has Narrative + Extraction only |
| T14 | Existing Remote, phone122/133, call-continuity, initiative, authority136/extraction137 and full backend regression suites |

R01–R11 are implemented by the above contracts. G01–G04/G06 have deterministic
coverage; G05 is gated by the final-head verification commands below; G07 is this
contract plus PR results. Actual counts and failures belong in the PR verification
report, not an assumption that fixture success proves free-model fidelity.

## Reproduction

```bash
RPG_SEMANTIC_ENABLED=0 python -m pytest tests/test_narrative_phone138.py -q
python -m pytest -q -o faulthandler_timeout=45
npm test --prefix frontend
npm run build --prefix frontend
PLAYWRIGHT_EXECUTABLE_PATH=/path/to/chromium npm run test:e2e --prefix frontend -- \
  narrative-phone138.spec.ts phone.spec.ts phone122.spec.ts phone133.spec.ts \
  call-continuity.spec.ts narrative-authority136.spec.ts
```

New API tests substitute only external provider streaming/model-discovery IO. API
handlers, background workers, Resolver, Remote, persistence and SQLite are real.
Browser fixtures generate semantic provider responses and import a canonical test
world through the existing fixture importer; they never inject incoming messages
or calls directly. Start Game is clicked in the browser.

## Compatibility and limits

No SQL or WorldState migration. Old saves, absent extraction sections, Tabletop,
phone-only messaging, #133 physical/call continuity, commitments and #136 recovery
keep their owners. Existing optional communication planning calls are preserved;
this change adds no mandatory call or per-contact agent.

**Live DeepSeek: NOT RUN.** No safely supplied credential and agreed live budget
were available. Synthetic semantic fixtures prove integration, not arbitrary model
accuracy. In particular, an event completely omitted by Extraction cannot be detected
by Runtime without the forbidden second semantic interpreter. A delivered message
whose content is genuinely absent cannot be reconstructed: targeted repair either
resolves the omission from the same scene or the turn remains uncommitted. No invented
text, number or unknown sender identity is used as a fallback.

The mobile checks are browser emulation, not a physical-device keyboard test. The
phone keeps its tab/navigation state: an incoming call is accessible via the existing
call link or Calls tab while a message thread is open; no new modal or forced tab switch.
