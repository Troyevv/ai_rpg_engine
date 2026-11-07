# Issue #232 — player action targets and Narrative recovery

## Evidence

Baseline: master `25c834b094a9047471406d7166111c8b6b755f75`, including #226.
Read #232, #99, #203, #207, #226 and QA #230. The external
`live99-stage-c-retest-20261107/crisis/001` and `crisis-addressee-replay.json`
were not present in this executor. The reproduction is explicitly **equivalent**,
using the maintained developer checkpoint, an ordinary start job and the public
protagonist transition to Nina. Only provider responses are scripted.

Before changes, Nina is in the library with Marina/Asya/Zoya; Vera is at home,
without a remote channel. The input names Vera; Narrative addresses Marina.
Both direct StateResolver and a real engine job accept the mismatched Event.
A new SQLite Repository reads `player_interaction=true`, participants Nina/Marina,
the original quote naming Vera and clock +1. The job saves after two provider
calls, without repair. No Knowledge acquisition is claimed by this reproduction.

Cause: the old Event ingestion checked `completed_interaction`, membership of the
controlled actor in participants and ownership of an exact input quote. That
proves the source of the quote, not its addressee, author or correspondence to
what the Narrative actually describes. Optional continuity/initiative annotations
are not a suitable authority for a mandatory action check.

## Contract and ownership

The existing Extraction call owns the semantic review; no extra interpreter,
intent store, lexical parser or model stage is added. `player_agency` reviews the
unchanged full Narrative, even actions omitted from Events. `status` distinguishes
preserved, violated and uncertain agency. Actions have local IDs, input evidence,
input target IDs, Narrative target IDs, outcome and meaning correspondence.

Events reference these actions through `player_action_id`, actual `actor_id` and
`target_ids`. Runtime compares identities, source ownership and completion. A
copied quote alone cannot create `player_interaction`. Failed/partial/deferred acts
retain their intended targets without turning absent addressees into participants.
NPC reactions remain separate Events. Multiple actions and group targets do not
collapse into one undifferentiated participant set. Aliases/pronouns are resolved
by Extraction; Python does not inspect names or compare literary wording.

Accepted Event provenance includes its typed action. Full proposals and reviews
remain in the existing request/change journal. WorldState/save format and SQLite
schema are unchanged; old History is not rewritten. Existing presence, channel,
Knowledge, POV and continuity validators still run. Established communication
command pipelines continue to own phone/chat/letter authorization.

## Recovery and cost

Missing/invalid structural proof or an Event inconsistent with a reviewed correct
Narrative uses the existing one bounded Extraction repair. A violated/uncertain
Narrative is a hard `narrative_agency_conflict`: no canonical commit, no automatic
Narrative regeneration and no extraction-only laundering. Retry of that same
prose is rejected before launching a worker, including after reload. The normal
abandon transaction preserves diagnostics/variants and makes zero model calls.
The UI restores the original input when its physical composer is empty, leaving
any user-authored new draft intact. Resubmission is an explicit user action.

Old recorded contexts keep their original state/input on regeneration; the
current agency safety rule is appended if absent. The normal two-stage path stays
two calls, structural repair stays at most three, and a detected Narrative
violation stops at two. Provider failures/manual retries retain the existing
usage accounting. No paid DeepSeek call was made.

Mandatory review adds context tokens. Repair feedback now carries the essential
code/path/source/reason instead of duplicate diagnostic fields and redundant
location descriptions; full diagnostics remain stored. The final relationship
source is retained until lossless/default/schema compaction has been attempted.
Under remaining hard pressure, the existing optional Director-schema pruning also
applies to mandatory player provenance. Scene, Event, Knowledge and player review
contracts stay present; optional annotations are still accepted and validated.
Neither token limits nor canonical checks are relaxed.

## Regression coverage

`tests/test_player_action_targets.py` exercises real jobs, builders, resolver,
History and SQLite reload with explicitly authored provider replies:

- Crisis/001 before/after equivalent payload and quote-only false completion;
- substituted Narrative with either mismatched or formally input-aligned Event;
- correct Narrative / wrong Extraction, successful repair and repeated failure;
- absence, partial execution, unsuccessful attempt, postponement and no execution;
- valid present targets, alias/pronoun IDs, groups, no target and multiple actions;
- independent NPC initiative and response to another character's question;
- active, closed and unavailable phone channel without teleportation;
- malformed sources/roles/targets, missing review and omitted Events;
- reload, failed/successful regeneration, original context, sibling selection,
  rollback and a new branch; retry rejection and zero-call abandon.

`frontend/e2e/player-agency.spec.ts` covers desktop/mobile rejected prose,
reload, disabled extraction retry, zero-call abandon, restored input and explicit
resubmission. Existing #226 and continuity/relationship suites are retained.
Older scripted providers receive explicit review envelopes; this is test data,
not a production fallback. New omission/negative tests bypass the legacy adapter.

## Verification and limits

Final command results and CI links are maintained in the PR description. Local
Vitest: 148 passed; production build passed. Local Chromium cannot create its
UNIX socket in this executor; the requested unsandboxed execution was rejected
by the environment policy. Desktop/mobile validation therefore runs in GitHub CI.

A structurally self-consistent but semantically false Extraction can still be
wrong. The change does not claim deterministic proof of arbitrary natural language
or immunity to a model misidentifying both input and Narrative. Such proof would
require a different authority or user confirmation. Within the existing
Extraction-owned architecture, missing, uncertain and contradictory claims are
rejected, and an observed prose violation cannot be silently repaired in History.
