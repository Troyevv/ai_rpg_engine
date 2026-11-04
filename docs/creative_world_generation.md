# Creative development of initial worlds (#172)

New generation jobs use journal generation contract 6:

1. Generate and structurally check the initial candidate (existing bounded repair).
2. Checkpoint that candidate before requesting creative development.
3. Request one coherent creative proposal, apply it to a copy, validate the entire
   result, then append a candidate version.
4. Run the existing full semantic review and addressed repair loop.
5. Save the final draft for the existing editor and Start Game flow.

This replaces the optional post-review quality batch **for new jobs only**.
Historical jobs (including contract 5 and journals without a contract) retain
quality/recovery behavior. Runtime, started games and save formats are unchanged;
there is no database migration.

## Proposal boundary

`draft_changes.apply_proposal` is a pure preparation/validation boundary suitable
for reuse by #173. It does not persist or claim semantic approval. The caller owns
review, revision locking, confirmation and versioning. The future editor must
supply its own author-instruction policy and deletion policy; no AI-editor UI,
confirmation workflow or modifications of started games are implemented here.

A proposal contains an exact `candidate_hash`, a `rationale`, and `changes` with
`op`, JSON Pointer `path`, `value` and artistic `reason`. New records may refer to
other records in the same batch. Cards/locations append through `/-`; existing
records change by fields. Add/replace preconditions reject collisions, overlapping
paths and stale candidates. Deletion and identity changes are outside the
initial-development policy. References, chronology, relations and Knowledge
sources pass the existing initial-candidate and canonical checks. Manual paths,
player motivations/emotion/commitments, clock/settings/control and server-owned
provenance are protected. Prose-level author constraints and agency remain the
responsibility of the mandatory semantic reviewer; deterministic checks cannot
prove literary fidelity.

The model gets the intact author brief/settings and all relevant canonical
content. Derived display projections are omitted; repeated schema fragments use
JSON Schema references. No entity quotas, mandatory plot ingredients or text
length requirements are added. An empty changes list is allowed with an
explanation when the model judges further expansion unnecessary; it is not a
server assertion of creative quality.

## Recovery, cost and limits

The existing response transport stores raw parts, effective configuration,
request fingerprints, usage/cost, continuation state and token reservations.
The new `draft_world_creative` request stage and `developing` job phase are visible
through the existing polling/SSE lifecycle. Full context preflight can reject a
large candidate before a provider call; increasing the configured context and
resuming preserves the candidate. Content is never silently clipped to fit.

The proposal checkpoint and resulting candidate text share one journal write.
A crash before the version append can reapply that exact cached proposal without
another LLM request. Applied development is not repeated after review, repair or
manual edits. A rejected structural proposal leaves the previous candidate and
raw diagnostics intact. At most two targeted corrections may change only validator-addressed
proposal fields (or drop a specifically rejected scope operation). The full proposal
is hash-bound and revalidated atomically; good sibling operations cannot be rewritten.
Original/corrected replies, diagnostic scopes and every transport attempt remain in
the journal and author diagnostic export. Interrupted corrections resume their exact
slot without regenerating the creative batch; exhausted attempts stay exhausted
across reloads. Unaddressable failures remain rejected.

Editing that candidate permits a new proposal; at most
three distinct candidate attempts are allowed, under the existing total budget.
No automatic broad rewriting is used to repair a rejected proposal. Corrections
use the existing repair output budget and request accounting. Changing transport
policy can recover an empty length-limited response without discarding paid partial
text or bypassing identical-empty-request blocking.

Empty terminal responses reuse #170's explicit one-request retry grant; identical
empty requests are blocked without a fresh grant. Cancellation/network unknown
outcomes retain the existing acknowledgement requirement. JSON continuation is
bounded by the existing five-fragment limit. Semantic failures keep the last
structurally valid candidate editable with existing warning-based start behavior;
prior candidate versions remain in the existing append-only history.

## Verification limits

The controlled provider tests exercise linked entity creation, rejection,
checkpoint replay, semantic review/repair, editor access, Start Game, turns and
save/reload. They **do not measure live DeepSeek artistic quality**. Creative
quality and literary preservation must still be assessed on representative live
briefs with provider credentials; no API key is included in fixtures or logs.


## Context measurements (offline, 2026-11-02)

Reproduce with `python scripts/measure_creative_context.py`. Full requests include
canon, author source/settings, rules and schemas; no truncation. Measurements use
six existing controlled scenario worlds, one historical real DeepSeek candidate,
and the existing 36/56-character cast-boundary fixtures. The latter are synthetic
scale tests, not 56 independently authored character biographies.

| World | UTF-8 bytes | Input reservation | Context for full output allowance |
| --- | ---: | ---: | ---: |
| Volkov controlled scenario | 72,278 | 36,972 | 60,972 |
| Everyday / historical / fantasy / adoption / organizations | 48,900–49,700 | 25,283–25,683 | 47,576–48,336 |
| Historical real provider candidate | 74,808 | 38,237 | 62,237 |
| 36-character cast fixture | 98,430 | 50,048 | 74,048 |
| 56-character cast fixture | 132,332 | 66,999 | 90,999 |

Input reservations use the existing conservative UTF-8 estimator plus 512; they
are not actual tokenizer counts. Output is bounded by the existing policy and a
24,000-token configured ceiling for this measurement. 32K cannot fit the Volkov
case; 64K cannot fit even the minimum 256 output tokens for the 56-character case.
Preflight rejects those calls without spending; increasing context and resuming
keeps canon and previous paid responses. No default limits were increased.
Request construction measured 84–235 ms in this environment during concurrent
tests; this does not measure provider latency.

Using the repository's tariff snapshot `2026-09-15` at its peak uncached rate,
one creative request reserves approximately $0.0343–$0.0489 at the output ceiling.
This is a code-derived budget estimate, not verified current pricing or actual
DeepSeek spending. Corrections/continuations and semantic review add separate
reservations under the existing total cap. Missing usage remains unknown, and
unknown-outcome requests retain their reservations until explicitly handled.

## Reload regression diagnosis (#176)

The failed `creative172` browser fixture installed an unconditional init script.
Every reload reset `localStorage.selection` to the unrelated theme seed world,
removing the save ID selected by draft confirmation. The failing CI trace shows
`GET /api/saves/22` before reload but `GET /api/worlds/8` afterwards, with the DOM
showing the seed world's title and “Создать прохождение”. `App` initializes React
selection from that storage value and consequently loads no save. This was test
setup corruption, not loss of persisted choices.

Seed storage once instead. Keep the six-choice assertion and additionally verify
that the selected world/save survives reload, the second turn is actually saved,
and API turns, canonical state and draft request history remain identical. Run
all three modes (success, explicit empty retry, addressed correction) in both
skins and viewports. Recovery tests also interrupt correction transport and
simulate process loss after response, correction and applied checkpoints; cached
responses must be reused without additional provider calls.

A subsequent E2E assertion confused the draft and save contracts:
`GET /api/saves/{id}` returns `ui_view`, whose `state.world` does not contain
`organizations`. Canonical records remain under
`Repository.get_snapshot(id)['world_state']['organizations']`. Social labels in
the public response use `state.residence_roles`; this fixture's role has no
knowledge fact, so it must not appear there. The actual API response after Start
Game plus two ordinary turns has three turns, the new character, fire fact,
Knowledge and thread, while the organization and role remain intact in SQLite.

The browser test now checks public records through the existing API and reads
canonical organization/role/relation/fact/Knowledge/thread records and the source
event through a read-only route in the browser-only fixture server. It compares
those records after each ordinary turn and after refresh, using a reopened
Repository. Backend integration also reopens the whole application and compares
public state/turns and the canonical snapshot. No production API or Knowledge
visibility rule is changed to satisfy this test.
