# Master generator adaptation (#44)

This implementation starts from master `4bc5ec66`, not PR #105. It preserves
`draft_generation → draft_world → versioned world_draft → confirm_draft → migrate_snapshot`.
There is one creative world response, optionally continued, followed by at most
two technical repair responses. No AuthorBrief, planner, compiler, second Runtime,
checkpoint table, or staged world generation is introduced.

## What changed

- `draft_generation.py`, `draft_schema.py`, `draft_initial.py` and the existing
  prompt extend the editable draft with Runtime-owned life/social, geography,
  organizations, occupations, possessions, contact and conditional lifecycle data.
  Schema annotations duplicated by the prompt are omitted in provider requests.
  Python fills map IDs/defaults, normalizes invalid character IDs consistently,
  sorts symmetric family endpoints and checks references and chronology.
  Calendar anchor defaults/numeric strings are normalized without inventing dates;
  calendar, observance-reference and birth-date errors retain exact repair paths.
  A saved complete response that failed the old generic calendar check can resume
  validation/repair without another world-generation request.
- `draft_world.py` exposes applicable fields in the existing editor. New generation
  must pass typed Runtime validation and canonical migration before publication;
  confirmation revalidates the current edited version. Legacy draft imports retain
  their existing editable compatibility path. Runtime salvage must not discard new
  supplied extension, character or Knowledge data silently.
- `runtime_v3/migration.py` preserves physical state, personality/values, structured
  fact claims, Knowledge lifecycle/provenance and explicit reproduction records.
  Parent/subsidiary organization ownership uses existing typed Fact.claim references
  (`predicate=parent_organization`), not an economic subsystem.
- Only `world_creation_settings.py` and `WorldCreationSettings.tsx` are transferred
  from #105: primary/secondary/custom genres, NPC expressiveness, cast presets/counts,
  world type/geography, pacing and risk. Targets are preferences, never cast quotas.
  Pacing/risk and expressiveness reach canonical Meta; expressiveness also reaches
  ordinary Narrative context. Old saves default to realistic expressiveness.
- `draft_response.py` owns bounded transport of the same JSON. `preparation_jobs`
  receives one additive `response_journal` JSON column; no new checkpoint table.
  Existing `llm_requests` remains authoritative for usage, finish reason and pricing.
  Journals/raw output are excluded from public job projections.
- `draft_repair.py` sends only affected records and diagnostics for localized errors,
  and accepts exact-path patches only. Syntax-only repairs must retain
  all complete JSON literal tokens in order. Unlocalizable errors and destructive
  repairs are rejected rather than granting permission to regenerate the world.

## Continuation and recovery

For `length` / OutputLimitReached, commit every received character and the completed
fragment's offset/hash; retain the original request and full preceding response in
the next request. Validate incremental JSON grammar, order and integrity. Reject
ambiguous repeated boundaries instead of trimming them or guessing missing syntax.
Each response is limited to five fragments. The original world response and each
of the maximum two repairs share a persistent total token reservation envelope.
No global context/output limit is raised. API callers may additionally supply
`budget.max_total_tokens` and `budget.max_cost_usd`; unknown prices block a request
when a monetary cap is required. Costs are estimates using existing project rates,
not a provider-side billing guarantee.

The existing resume endpoint/button can continue a confirmed boundary or finish
validation/publication after restart. The revision and single active job constraints
prevent stale or concurrent resumes. Pending/cancelled/network-interrupted calls
have an unknown outcome and are **never replayed automatically**. Already committed
requests are reused. Credentials are resolved again and never stored in the journal.

A transport cannot detect an omission that the model makes *inside a string* if the
result is still valid JSON and contains no detectable overlap. Offsets/hashes detect
missing or reordered stored fragments, not semantic changes in newly generated prose.
This remains a live-model acceptance concern.

## Verification

- Full Python suite, frontend build and Playwright are required; exact final results
  are recorded in the PR.
- `tests/test_draft_response_v4.py`: cuts within strings/escapes/arrays/objects,
  multiple limits, repeated boundaries, missing/reordered/corrupted fragments,
  context/token/cost exhaustion, cancellation, network uncertainty and reuse.
- `tests/test_initial_draft_v4.py`: both complete input ideas, configured constraints,
  strict local repairs, references, SQLite reopen/resume, concurrent/stale resume,
  author editing, confirmation, ordinary turns, persisted reload and policy survival.
- The full original Volkov input is `tests/fixtures/initial_world/volkov_user_brief.txt`.
  Its offline reply fixture preserves eight named characters/biography text, adoption
  knowledge, subsidiaries and Friday 08:00 court opening. This is a controlled fixture,
  **not evidence that DeepSeek reproduces the brief**. The large fixture explicitly
  uses a 65536 context; the shorter fixture uses 32768. An 8192 preference may reject
  the schema/idea before spending tokens; it is never silently increased.
- `frontend/e2e/draft-v4.spec.ts`: settings, continued JSON, editor, start and reload
  on desktop/mobile. Existing complete browser suite uses one worker because the
  test server temporarily patches process-global providers during fixture setup.

## Live acceptance still required

No paid DeepSeek requests are authorized by this task. Do not mark fully ready
without a separately agreed budget and real tests for both full inputs, inspecting
cast completeness, source fidelity, knowledge secrecy, creative quality, opening
agency, ordinary turns and reload. No mock result substitutes for that check.

## Real-response completeness regression (PR #116 follow-up)

`tests/fixtures/initial_world/volkov_deepseek_real.json` is the complete, unchanged
user-uploaded DeepSeek response. Before this fix it passed canonical validation
with empty objective relations, roles and residences, Thursday/Friday display
conflicts, yesterday-evening events placed this morning, and an invented controlled
actor intention. Tests retain the full original brief. That brief does **not**
contain the later dinner clarification: the regression appends the user's explicit
clarification separately, naming the five family members present. It does not
silently rewrite the original input or give absent friends knowledge of the secret.

The existing validation loop now includes `draft_completeness.py`: one read-only
provider check of the full author idea and candidate state, followed only when
needed by the existing exact-path repair. This is not staged world generation.
Review responses are journaled under the hash of their complete input; resuming or
rechecking an unchanged candidate does not repeat an already completed review.
There are still at most **two repairs total**, shared between technical and semantic
errors. Every request uses the same cancellation, context, token/cost envelope and
usage logging (`draft_world_validation`). No approved report means no publication.
Malformed/broad review reports fail visibly and cannot authorize a world rewrite.

The reviewer checks established family/social links, jobs/education, residences,
corporate subsidiaries, revelation chronology and per-person Knowledge, opening
conditions and player agency. It requests new records by ID or existing fields by
exact pointer, not replacement collections. Repair prompts carry only affected
records, selected related context, relevant schemas, an ID/name directory and the
intact author input. Correct biographies and unrelated records stay in Python.
Python does not infer biological family, professions, witnesses or unknown dates.
The reviewer remains an LLM: semantic recall and accuracy require live acceptance.

Missing calendars receive Runtime's relative Gregorian anchor with no exact date.
The semantic check reconciles an explicitly stated weekday/date with that anchor.
Both compatibility time displays use Runtime calendar functions and the numeric
clock. Editing the starting minute retains the calendar. For vague history times,
`event.minute=null` retains text/evidence and order; no guessed exact minute is
needed. Existing migration preserves events and knowledge-acquisition provenance
in History. Reference validation now localizes missing knowledge source events,
organization locations, event participants/witnesses and fact references.

`tests/test_draft_completeness.py` checks the real response, localized repair,
unchanged biographies and emotional relationships, adoption vs biological parent,
Apex subsidiaries, professional roles, residence vs current court location,
knowledge of attendees only, preserved user goal and removed invented intention,
Start Game, ordinary turn, SQLite reload, bounded failure and completed-response
reuse. Provider review/patch replies are explicitly controlled test doubles.
Transport-only tests use `accept_semantics_unchecked` and do not claim semantic
coverage. Browser tests also assert a separately accounted validation request.

Live acceptance: generate both short and full briefs with an explicitly permitted
budget, inspect the reviewer issues and local patches, and verify the final world
against the actual input. In particular compare the old brief (only Ilya learned)
with the clarified family-dinner brief (all five family members heard it). Do not
claim production semantic quality solely from green offline tests.

## Stabilization and editable recovery (2026-10-24)

This section supersedes older statements above about publication requiring a valid
world and about inventions being restricted to literal source facts. The latest
user specification supersedes Issue #44's staged pipeline/spans requirements.
The existing single-world response, local patches and Runtime remain the owners.

- Creative generation/review may invent internally consistent people, secrets,
  history and roles. Explicit author facts/prohibitions remain constraints. Initial
  protagonist characterization is creative; future voluntary actions/consent and
  active commitments remain protected. Import and Python normalization do not
  invent circumstances. Recommendations do not block publication.
- Gregorian month lengths are computed by Python, including leap years. Custom
  profiles are retained. The provider schema now describes Gregorian/custom
  conditional constraints, mutually exclusive temporal bases, and false/null
  Condition effects. Missing participant positions may project the explicit opening
  scene; conflicting explicit positions are errors.
- Typed validation precedes legacy preparation. Independent references, condition
  effects, symmetric duplicates, chronology, fact participants and relation cycles
  have pointers; migration preservation differences are collected recursively.
  Unlocalized legacy failures still fail visibly rather than authorize whole-world
  repair. A root diagnostic means that automatic localized repair is unavailable,
  not that the other areas have been verified.
- Parsed candidates use the existing append-only `world_draft` journal. They are
  author data until confirmed. No second canonical model/table is added. Previous
  valid versions remain restorable. Invalid candidates are withheld from Player
  View; author recovery can assign exact fields, retain other errors and unknown
  data, and inspect the complete JSON. This fallback is deliberately a field-level
  JSON editor, not a new visual schema/form system. Successful candidates use the
  existing normal editor. Invalid JSON remains available in the raw response export.
- A malformed semantic report is an incomplete check and blocks confirmation.
  It gets at most one bounded report-format retry; accepted reports are cached by
  input hash and checked before reuse. Resume allocates a new repair/review epoch,
  preserving world output, earlier attempts and accounting. Current-revision Resume
  adopts the manually edited candidate instead of overwriting it. Technical-only
  manual recovery still requires the author to assess semantic fidelity; offline
  validation cannot prove that arbitrary prose matches the author's intent.
- Resume accepts a new context/output limit (UI uses current model preferences),
  keeping explicit total-token/cost caps unchanged. Confirmed HTTP 429/503 gets up
  to two delayed retries; other confirmed HTTP rejections retain their status.
  Unknown outcomes require explicit acknowledgement of possible duplicate billing.
  Partial text and reservations remain in history. Cost reservations are conservative
  upper estimates, not provider billing guarantees. Provider caps for the known
  DeepSeek Flash/V4 names are distinct from application preferences; other compatible
  providers use their configured limits. Capability source:
  https://api-docs.deepseek.com/api/list-models/ (checked 2026-10-24).

### #78 manual recovery scenario

1. Reset the existing isolated developer world using the commands in this folder's
   README. Retain its workspace/version and a baseline save for comparison.
2. Import/export its JSON and verify the baseline still opens, starts and reloads.
   In a separate workspace, exercise generated failure with controlled provider
   replies (the browser fixture marker is `TEST_CANDIDATE_RECOVERY`). Do not use that
   marker as evidence about a live model.
3. Open the author result after failure. Check exact error paths, complete candidate
   and original raw output. Change one broken ID, save while another error remains,
   reload the page and correct the remaining error. Check that secrets/biographies
   and unknown properties have not been removed. Restore the previous version and
   verify it remains intact; restore the candidate again.
4. Resume with the current revision after manual editing; verify only repair/review
   requests occur, never another world request. Change context/output preferences
   and verify the resumed request uses them without raising the explicit total cap.
5. Confirm, start, ordinary turn, persist, reload, next ordinary turn. Verify the
   same Knowledge holders and adoption/biological distinctions. Exercise the
   existing baseline branch/rollback/regenerate scenarios; generator recovery does
   not rewrite historical game snapshots.
6. Simulate malformed review, confirmed 429/503 and interrupted stream. Check
   bounded requests, visible incomplete-check state, persisted fragments and explicit
   recovery for unknown billing outcomes. Repeated/concurrent/stale Resume must not
   start two workers or overwrite a manual edit.

Automated coverage: `tests/test_draft_recovery.py`, existing initial-world,
completeness, response transport and draft tests; `frontend/e2e/draft-v4.spec.ts`
now includes author recovery/start on desktop and mobile. Full Volkov input and real
response fixtures remain byte-for-byte unchanged. All model replies in these tests
are controlled, including semantic acceptance; they do not establish live quality.

Live acceptance remains unperformed: no `DEEPSEEK_API_KEY` was available in this
execution environment. No paid requests were sent. Short/Volkov/other-setting/custom
calendar live generation, semantic quality and real-model gameplay remain required
before claiming production stability.
