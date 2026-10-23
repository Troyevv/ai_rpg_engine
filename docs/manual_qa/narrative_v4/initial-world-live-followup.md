# Issue #44 — second bounded live assessment

This continues PR #105 on the existing branch. The user authorized a **new $2
allowance, at most three new full generations, at most two retries per failed
unit, sequential paid calls**. Repeated credential/continue messages did not reset
this allowance. The first assessment remains documented separately.

## Actual result and blocker

One new short Ilya/Moscow/research-institute scenario was started. Six requests
completed with provider usage: interpretation, setting, places, two core character
batches and a secondary batch. Deterministic interpretation assembly also completed.
All seven accepted checkpoint versions survived recovery unchanged.

The seventh attempt, `life_ties`, was interrupted. The execution tool returned:

> Network access to "https://api.deepseek.com:443" was blocked by policy.

No usage or response was received for this attempt. It is **uncertain**, not
recorded as free or successfully completed. The live harness is no longer running;
normal repository recovery marked the unit uncertain and retained all accepted
artifacts. No blind retry, network-policy workaround, fourth scenario or budget
reset was attempted. The medium and complex scenarios were not started under this
new allowance. The short scenario did not reach canonical publication/Start Game.

In the accepted short-world batch, Ilya has an empty goals list. Core NPCs have
different research, career and laboratory-management motives. This is limited
positive evidence about character generation, not proof of an entire playable
world, privacy under future POVs, or all explicit user constraints.

## Usage and cost

- **6 completed, usage-confirmed chat requests + 1 uncertain attempt.**
- Confirmed input: **29,081 tokens**; output: **13,047 tokens**; total **42,128**.
- Confirmed estimated cost: **$0.010722702** using returned usage and the tariff
  documented in the first assessment. This is not a billing statement.
- Conservative cumulative reservations, including the uncertain attempt:
  **$0.1564458**, below the $2 cap. Reservations were not released.
- Only **one of three** permitted new full generations was started. No failed unit
  was retried during this follow-up. Model: `deepseek-flash`, thinking off.
- Credential supplied via echo-disabled stdin and held only in process memory;
  no credential in repository files, reports, prompts or committed diagnostics.

The uncertain request prevents an exact final billed-cost claim. Do not subtract
it from accounting or replay it without explicit uncertainty handling. A future
continuation of this allowance must keep its existing usage/attempt ledger.

## Changes and regression evidence

Request guidance now explicitly separates adoption truth, a private disclosure and
parental marriage plans into facts with potentially different Knowledge holders.
Knowing a family secret does not imply knowing a later private conversation, and
kinship/marriage/co-residence do not transmit knowledge. Backstory must retain the
source's chronological precision and accepted organizational business areas.
Protagonist goals/intentions/obligations remain empty unless explicitly supplied;
moving or beginning employment is not authorization to invent personal goals.

These are focused generation instructions, **not a claim of deterministic semantic
protection**. No source quotes/spans, new persistent schemas, mandatory semantic
retry loops or Runtime-validator changes were introduced. Background/Knowledge
instructions were not reached before the network block and remain live-unverified.

Extended the existing canonical author-edit regression to create then remove an
imposed protagonist goal and repair an overprecise adoption description. Combined
with existing organization/family/Knowledge/opening edits, confirmation and fresh
repository reload preserve the repairs. Invalid Knowledge references still reject
atomically. This proves the API repair path; it is not an exhaustive new browser
usability assessment of all narrative errors.

Final local verification after the changes:

- `python -m pytest tests -q`: **1619 passed in 216.79s**.
- Frontend `npm run build`: passed in **3.45s**, existing bundle-size advisory.
- Frontend `npm run test:e2e`: **204 passed, 10 skipped in 11.4m**. The skips
  are existing mobile-project exclusions; no test or timeout was weakened.
- Expanded author-repair regression also passed individually before the full suite.
- `git diff --check` and credential-pattern check of changed files: passed.

These are local results, not a claim that a new GitHub Actions run has completed.

## Remaining blockers

1. Network policy currently blocks real DeepSeek calls; the in-flight ties attempt
   has unknown usage/outcome and must not be retried implicitly.
2. Complete the short world through assembly/editor/Start Game.
3. Run medium and complex cases against the final context fixes; verify all five
   Apex subsidiaries and accepted parent relationships survive assembly/reload.
4. Live-check protagonist agency, adoption precision, discovery chronology and
   per-fact Knowledge, including the new guidance. Earlier assessment failures
   remain unresolved until observed corrected behavior is verified.
5. Complete real three-scenario acceptance. Passing deterministic suites alone
   cannot close these quality criteria.

**PR #105 stays Draft; Issue #44 is not complete.**
