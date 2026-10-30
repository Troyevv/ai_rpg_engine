# Modern phone redesign (#158)

Base: master `0d6e3c588509c0f75bfcc1e8d0136652dfce944d`.

## Ownership and baseline inventory

Before the change Phone owned contacts/labels/blocking, the #129 live-NPC directory and search, direct conversations, group creation/join/remove/leave, emergency services, unread entry notifications, read commands, outgoing/incoming/ignored/declined calls, history links to the existing CallScene, and communication job progress/retry/wait. Drafts were scoped by save + controlled actor + conversation/contact/recipient in sessionStorage. Scroll positions were held per thread. All mutations used the existing revision and operation_id contract, with a synchronous request lock and parent busy state. Incoming reads used the existing explicit-open/visible-thread behavior.

That behavior remains. PhoneContent is a read-only presentation of the authorized PhoneState; it stores no messages and never reads the omniscient world model. Message order, time, sender, delivery and read counts come from the existing events. Unread content remains withheld until the read command succeeds. `sent` is labeled “Отправлено”, not a fabricated ongoing network request.

#129 is merged. #131/#132 remain responsible for historical communication surfaces, capabilities routing, letter composition/reading and parchment presentation. This change does not add those screens or alter historical artifacts. No enabled channel is inferred from year/genre. The existing server projection still controls whether Phone exists. At the initial review, open PRs #118 (world builder), #119 (incapacitation/Remote), #33 (Tabletop) had no changed-file overlap with this implementation. Their builders and navigation helpers are untouched. The P0 follow-up below extends only the phone semantic adapter/service and adds fixture-server scenarios.

## Screen structure

- Contacts: searchable directory, compact action targets, preserved saved-label/contact management and emergency actions.
- Threads: event-order sorting, portrait/group identity, authorized preview, canonical timestamp and unread count; empty groups do not pretend to have unread messages.
- Chat: incoming/outgoing bubbles, group author, canonical date separators, full unmodified text, one scrolling message region, pinned composer with bounded auto-growth and Ctrl/Cmd+Enter. Existing server content validation is unchanged; text is never silently truncated.
- Group creation and membership use distinct screens, not controls competing with the message scroll.
- Call history preserves outcome/direction/time. Transcript links are offered for existing call text (or an active conversation), using the original CallScene.
- Escape and browser Back navigate one screen back; explicit minimize preserves the selected chat. The existing CallScene takes over the phone history entry when opening a call, preventing a phantom phone step on Back. Focus returns to the initiating thread/directory item; tab navigation stays inside the open phone. Closing restores the phone trigger.
- Desktop remains a bottom drawer/device. The collapsed mobile affordance keeps the #126 composer seam; expanded mobile fills visualViewport without a nested device frame. Skin tokens, safe areas and reduced motion remain authoritative.

## Architecture and compatibility

The UI redesign changes no backend contracts. The P0 follow-up below changes the phone semantic adapter/service; API, WorldState, save schemas, migrations, canonical event storage, Knowledge/POV and agency remain unchanged. The shared Avatar and Button components are reused. Draft/request keys remain compatible. The pending-request cache now retains each unresolved intent independently (and reads the old single-request shape): a successful read or another command no longer erases the operation_id of an uncertain send. Canonical event storage is unchanged. API failures keep the draft and pending operation ID; refreshing the save after a revision conflict acquires the same mutation lock before retry.

Existing tests that intentionally minimized the phone now click its named minimize action. Their former Escape behavior was intentionally changed to hierarchical Back. The mobile dock test retains collapsed seam checks and now checks fullscreen expanded bounds instead of asserting that the open screen remains above the Narrative composer.

## Validation coverage

- `phone158.spec.ts`: hierarchical Escape/browser Back, focus, personal/group drafts, authorized group authors and dates; request failure + double-submit + same operation ID; revision conflict/refresh; controlled actor privacy; long-text scroll restoration; 1440/768/360/393, graphite/parchment, 200% text, reduced motion, visualViewport keyboard.
- Existing phone/phone-completion tests: actual API/jobs/SQLite, contacts, group membership, incoming/outgoing/ignored/declined/missed calls, CallScene restore/end, unread/read, provider failure/retry, portrait integration, no changed physical choices or Narrative draft.
- Existing communication-profile smoke: generate/start → turn → reload → next turn. Historical correspondence and Remote tests protect existing none/mixed/historical behavior, canonical read and rollback/branch invariants.
- Unit presentation tests check stable event ordering, unread privacy, no invented read status, group authors and complete long content.

Exact executed commands/results and visual QA are recorded in the PR description. Temporary images/traces/logs stay outside the repository. Live DeepSeek and physical Android/iOS keyboards require a configured provider/device; deterministic provider fixtures do not establish model prose quality or native mobile behavior.

## PR #163 P0: phone places and optional consequence recovery

The phone adapter previously removed `locations` from the common Extraction schema and rejected that section on input. Its GM context also lacked canonical place identities. This prevented a valid new place from reaching the existing `StateResolver → apply_locations()` before a dependent commitment. A failed semantic repair then aborted the entire continuation.

The adapter now admits common `locations`, supplies compact id/name/aliases/parent_id context to Extraction only, and instructs it to reuse canonical identities, create places established by accepted text, and leave `location_id=null` when no meeting place was agreed. Location existence, aliases and hierarchy are still resolved exclusively by the common handler. No Python interpretation of consent or prose was added.

One existing source-bound repair remains the maximum. If it cannot repair an identified optional commitment (including malformed repair or provider interruption), the original candidates are revalidated on isolated snapshots. Only addressed invalid records and their exclusively attached new places are deferred; valid candidates are resolved together and committed with the accepted exchange. Existing canonical plans are never deleted. Full responses, repair attempts, source IDs and defer diagnostics remain in the existing job/request journal. An unparseable initial envelope, physical scene mutation or canonical identity conflict remains a hard error with the existing Retry path. Cancellation still commits nothing.

Recovery uses existing regeneration/variant history or a subsequent extraction of the retained thread evidence; no new recovery store or API is introduced. A saved exchange with deferred consequences is not represented as an NPC refusal or as a confirmed calendar entry. This is an intentional change from older tests expecting every invalid optional plan to abort the whole exchange. Diagnostics explicitly identify the deferred consequences.

Focused coverage in `test_phone163.py`, the updated #122/#133 tests and `phone163.spec.ts` includes new/standalone places; place + plan in one SQLite variant; known IDs and aliases without duplicates; unspecified/unknown place; proposal without assent; source-anchored time and participants; invalid/omitted/provider-failed repair; preservation of valid/existing plans; conflict Retry and repeated operation without double time/messages/events; reload, rollback and calendar visibility only after read. The original greeting/office/one-hour dialogue is replayed using deterministic provider responses in the existing two-participant QA world. Browser tests exercise both successful location creation and unresolved unknown place on desktop/mobile.

These fixtures prove adapter/persistence behavior, not live DeepSeek extraction accuracy. Live provider testing is NOT RUN.
