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
