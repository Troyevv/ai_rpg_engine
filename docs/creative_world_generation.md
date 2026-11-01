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
raw diagnostics intact. Editing that candidate permits a new proposal; at most
three distinct candidate attempts are allowed, under the existing total budget.
No automatic broad rewriting is used to repair a rejected proposal.

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
