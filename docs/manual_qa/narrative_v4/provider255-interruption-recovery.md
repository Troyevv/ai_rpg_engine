# #255 — interrupted provider recovery: engineering follow-up

This follows the [player diary](playtest255-diary.md) and
[post-session analysis](playtest255-technical.md). No new paid call or game session
was run. The four accepted player turns remain the starting point for continuation.

## Confirmed cause and evidence boundary

Original reservation 665 has 679 text chunks / 2206 characters, an incomplete JSON
string, and `complete=false, usage=null`. The request log holds the same partial
response and no finish reason. No original exception or provider response ID was
retained. Therefore connection failure, provider failure, SDK/Responses parsing
failure and other local exceptions **cannot be distinguished retrospectively**.
An EOF replay deterministically rejects the prefix; it does not prove that EOF
was the original exception. We did not infer token usage from partial output or
account balance, nor issue another generation request to investigate.

Two concrete recovery defects were reproduced:

1. `tracked_stream` stored HTTP rejection details but no general original stream
   exception. `llm.chat_stream` translated non-Runtime SDK exceptions before the
   tracker could identify them. Retry replaced the single current job.error;
   neither request diagnostics nor the QA raw stream retained the original cause.
2. The ordinary Retry route accepted client revision/attempt_epoch but did not
   pass them to the storage transaction. A free API regression reproduced a 200
   for an explicitly stale revision. Canonical job/save revision checks existed,
   but the caller's stale attempt precondition was not enforced.

## Narrow changes

- Existing `llm_requests.diagnostics_json.provider_attempt` records request/job,
  epoch/revision, reservation when Budget is present, provider request/response IDs,
  phase, terminal status/reason, completion and original error classification.
  Request-scoped routing adds no model wire fields or LLM calls. Independent Retry
  rows retain their own errors; job.error remains the current UI error.
- Original exception class/causal chain and message digest are captured **before**
  translation. Parser failures have stable codes. Arbitrary SDK/provider exception
  text, bodies and headers are not copied: they can echo credentials or prompts.
  Existing safe HTTP rejection diagnostics remain available. Available usage and
  finish values stay in their existing request fields.
- Existing QA JSONL start/end records include request/epoch/reservation links and
  the sanitized failure metadata. Missing usage still remains unknown, never zero.
- Ordinary Retry validates supplied revision/epoch in the existing transaction;
  legacy callers omitting the optional preconditions remain compatible.
- No Extraction/6 or Runtime semantic changes, extra repair, altered model,
  mandatory call, hidden fallback or new production SQLite schema.

## Reservation 665: explicit conservative procedure

Exact usage cannot be recovered from the available archive: neither a receipt
nor provider response ID exists there. No claim is made that every provider
supports or forbids retrieval; this particular evidence cannot identify such a
retrieval request. Original stream SHA256:
`69bd259d380761d9e519aa20327babbcaad3ffa2e8b4d6526f330d3c037adbc4`.

The existing Budget now offers an **explicit offline** `charge_unknown` decision:

1. Stop the sole QA server. The method takes its existing server lock and refuses
   to act while that lock is held by another worker.
2. Identify the reservation and unchanged source JSONL by SHA256. Require an ended
   unsuccessful stream without usage. If a receipt exists, reconcile it instead.
3. Keep input/output reserves and the call count unchanged. Set `settled=2` to mean
   **full conservative charge, usage unknown**, distinct from `1=provider receipt`
   and `0=unknown/blocking`. Append the decision metadata in `resolution_json` on
   that existing reservation row: original reserve, reason, timestamp and evidence
   hash. This nullable column is added lazily to the QA ledger, not game SQLite.
4. The original JSONL and production request usage remain untouched. Repeated
   resolution or a late callback cannot erase this decision. The full charge
   continues to count against all existing money/token/call limits; no ceiling is
   renewed. A separate paid authorization is still required for this continuation.

This procedure was exercised **only on copies**. Real reservation 665 is still
`(1048576, 8192, settled=0)`, full reserve **$0.3244032**. The real ledger still ends
at 665, with no schema or balance changes. Proposed next approval covers this
explicit full-reserve decision separately from new generation spending.

## Free checks and limitations

Focused command:

```sh
python -m pytest -q tests/test_provider_recovery255.py tests/test_request_responses.py tests/test_structured_extraction255.py tests/test_scene_steps255.py tests/test_scene_error_collection255.py tests/test_live99_budget.py tests/test_live99_stage_b.py tests/test_live99_stage_c.py tests/test_live99_recovery.py tests/test_engine.py tests/test_continuation.py tests/test_runtime_handoff.py
```

**228 passed in 70.68s**. Coverage includes interrupted JSON, original failure after
Budget rejection/Retry, terminal status/usage, safe exception handling, conservative
charge preserving limits, stale revision/epoch, cancellation/abandon, same actual
provider input/schema/parameters and Narrative on Retry, atomic save, cold reload,
rollback and existing v6 behavior. An initial run exposed an unintended release of
reserve on an errored stream with a usage callback; that change was removed and
all existing assertions retained. The final run above passed.

Original-save replay at `/workspace/work/issue255-interruption-free-v2/` used
separate copies of the playtest SQLite/ledger. Original deltas were rejected,
unknown dispatch blocked, then the copied reservation was conservatively charged.
An explicitly authored control (not a DeepSeek answer) retained the Narrative,
recorded conversation/Knowledge, saved through production FastAPI, survived cold
reload and rolled back to the original before-state. Earlier snapshots/variants
and the original Narrative/context remained intact. The first offline script sent
internal config keys through the public DTO and received 422; filtering to the
existing public fields fixed the script, not the product.

Full CI result is recorded on this PR's exact code commit. Green tests do not
complete #255. The next live step is one UI Retry of the retained exhibition
Narrative, then ordinary play toward 30–50 total accepted turns, counting the four
already played. Proposed new ceiling: **220 calls / $2.50**, expected roughly
$0.70–$1.60, with the old $0.3244032 charge retained separately. No new calls until
explicit approval; a repeated blocker ends the session rather than triggering
unbounded retries. PR remains unmerged.
