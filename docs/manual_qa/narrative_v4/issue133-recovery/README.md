# PR #133 — recoverable call extraction

Base inspected: `912ad608c613f5b4d376d929c7d6a18f900c7976`.
Existing branch: `codex/issue122-phone-scenes-commitments`. Root AGENTS.md applies.

## Behavior

Optional presentation no longer decides whether a valid call turn commits. Missing,
invalid or overlapping physical projections fall back to validated Event.text; an
unambiguous reference can be recovered from exact evidence. No Event is invented.
Text-only camera changes do not invalidate physical choice applicability. Missing
suggestions retain applicable prior choices or allow a real free-input turn from
the current world, without replaying earlier effects/time.

Unconfirmed optional arrivals and rejected physical Events stay noncanonical.
Identifiable rejected spans are removed from committed display; a localized notice
and persisted diagnostic make reconciliation explicit. Context and memory use the
reconciled view, while original narrative and snapshots remain auditable. Independent
validated character situation updates are preserved. Critical lifecycle, canonical
IDs, agency, consent, POV/Knowledge and atomicity retain their existing guards.
Repair may drop unaccepted optional hints, but cannot delete or invalidate an already
accepted physical Event to pass validation. No required Extraction field or migration.

## Executed user scenarios

`tests/test_call_continuity.py` exercises real FastAPI jobs, engine provider stages,
Resolver, SQLite atomic save and reload, rather than only direct Resolver calls:

- ordinary call with no physical transition; situation-only paraphrase;
- absent/malformed projection, bad evidence/reference, partial/missing choices;
- accepted Event fallback and unsupported optional arrival/rejected Event notice;
- actual next physical action with current choices, one application of prior time/events;
- NPC hangup, proposal/assent in both orders, calendar anchoring, reschedule/cancel;
- extraction outage + retry, variants, rollback/sibling lineage, save/reload;
- repair removing unaccepted Events, and atomic rejection of deleting/invalidating accepted ones;
- context excludes identifiable rejected prose while preserving valid phone speech.

Browser `call-continuity` scenarios use the existing office fixture via the real
API/jobs server. Desktop/mobile cover the full call and both recovery/rejection
variants, main-story fallback, no stale choices, free input, reload, NPC hangup and
calendar persistence. No retries, deadlines or skips were relaxed.

## Validation

- `python -m pytest tests/test_call_continuity.py tests/test_phone122.py tests/test_remote_communication.py tests/test_memory* tests/test_pov_documents.py tests/test_pov_transitions.py -q`: 91 passed in 124.53s.
- Final scene-only follow-up: `python -m pytest tests/test_call_continuity.py -q`: **29 passed in 49.71s**, including explicit reconciliation when a scene-only claim appears in narrative without an Event/evidence field.
- `npm test`: 34 passed.
- `npm run build`: passed.
- `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/issue133-browser/chrome-headless-shell-linux64/chrome-headless-shell npx playwright test call-continuity --reporter=line`: 8 passed (desktop/mobile).

## Limits

These are variable controlled-provider outputs through the actual application, not
live DeepSeek calls. No live API credentials are available in this environment, so
live-model user acceptance remains unverified. Arbitrary significant claims omitted
entirely from Extraction cannot be semantically detected by deterministic span
matching. Unmatched rejected claims receive an explicit notice/context annotation;
WorldState remains authoritative. Provisional streaming is not a committed fact.
The PR is not merged and issue acceptance is not inferred from CI alone.
