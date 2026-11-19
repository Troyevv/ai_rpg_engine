# Life248: recovery before lifecycle gameplay

PR #248; original evidence HEAD `dfc872c305233dd49ad8e60afde5f9c31bb3bdd1`.
This change repairs world preparation. It does **not** certify Narrative gameplay,
character lifecycle, or Stage C. No paid request was made during implementation.

## Original evidence and reproduction

The supplied archives were extracted into separate directories outside git.
Original archives, provider replies and SQLite files were not edited.

| Archive | SHA256 |
| --- | --- |
| `life248-dfc872c-blocked-evidence-20261108.tar.gz` | `e6c9e89af34fa0e88681a9582b77367970f4eb8d7d34ba629f309523948f725b` |
| `life248-thinking-low-evidence-20261108.tar.gz` | `00c160301c30ba473b02364ccf09c2c17af175da8b6615768e60f084520a0421` |

Before changes, the original Off candidate reproduced five conflicting Knowledge
records. Applying its saved local repair revealed unsupported portrait hint
`char_tamara / clothing=dress`, outside that repair's scope. The original Low
journal rejected a changed 32,000-token output policy before provider dispatch.
The initial regression run failed six tests covering these defects (three control
cases already passed).

Confirmed causes and changes:

1. `initialize_authored_secrets` tested the dictionary key instead of the
   `(actor_id, fact_id)` identity. A valid model-generated key was missed and a
   second record with empty evidence was added. Initialization now reuses the
   existing pair without overwriting evidence, revisions or provenance. A
   contradictory belief is still rejected; real conflicting duplicates are not
   silently merged or discarded.
2. Portrait validation happened after earlier canonical preparation. An
   independent invalid hint was hidden until Knowledge repair, which could not
   edit it. Validation now reports the affected `/characters/<index>/portrait_traits`
   object together with earlier structural errors. A bounded repair can omit an
   unsupported optional hint; it cannot alter valid sibling hints, invent new
   hints, change literary appearance, or weaken canonical checks. All hints are
   validated before any are consumed, avoiding partial mutation on rejection.
3. Draft transport raised a saved empty-response failure before evaluating a
   changed request policy. A known terminal LENGTH can now enter an existing
   response-retry slot when effective provider/model/thinking/output parameters
   differ. The failed slot and usage remain intact; any visible JSON prefix is
   retained. Logical stage identity survives redirection, preserving the world
   output ceiling and assembly schema. Same-policy, ineffective context/sampling
   changes, A→B→A failed-policy reuse, unknown outcomes and exhausted total budgets
   remain blocked. No automatic retry loop or extra LLM stage was added.
4. Separately, the **QA harness** left a full reserve after LENGTH even when it
   received authoritative usage. Existing `Budget.settle` now handles that terminal
   exception. Missing usage still retains the reserve. Its output validation ceiling
   now matches the existing production Resume DTO (65,536); it does not increase
   any actual request's configured limit. No new ledger tables or authorization
   subsystem were added.

There is no SQL migration, historical snapshot rewrite, or change to ordinary
Narrative/Extraction defaults.

## Free verification versus Live verification

`tests/test_life248_recovery.py` covers changed/unchanged effective policies,
partial visible JSON, preserved old response records, pending unknown outcomes,
aggregate token budgets, Knowledge identity/provenance/conflicts, mixed repair
scope, atomic portrait rejection, production FastAPI Resume/confirm/SQLite reload,
and the real SDK wire contract through `httpx.MockTransport`.
`tests/test_live99_budget.py` checks LENGTH with and without authoritative usage
and the existing Resume output ceiling.

Two additional integration runs used **copies of the supplied SQLite databases**:

| Source | Controlled calls after Resume | Result |
| --- | --- | --- |
| Original Off candidate | repair → creative → semantic review; **no new draft_world** | saved; 11 original characters; confirm and Repository reload pass |
| Original Low failed job | draft_world with changed ceiling → creative → semantic review | saved; confirm and Repository reload pass |

Both retained prior provider response records and document versions. For Off,
the controlled repair used the saved Knowledge corrections plus omission of the
unsupported cosmetic hint. Creative/review replies were controlled fixtures.
For Low, the newly returned world was a test fixture because the original Low
response contains **no JSON**. These runs verify recovery, validation and
persistence; they are **not real DeepSeek creation or semantic PASS**. The original
Off biography/kinship inconsistencies still require a real semantic review.
Raw source and controlled-test evidence stay outside git.

Final owner-suite result: **550 passed, 1 skipped in 246.50s**. The skip is the
existing opt-in private-export test. Command (provider key removed from the test
environment; transports controlled):

```sh
env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest -q \
  tests/test_draft*.py tests/test_initial_draft_v4.py \
  tests/test_review170.py tests/test_review_protocol.py \
  tests/test_story_secrets*.py tests/test_secrets183.py \
  tests/test_secret_handoff181.py tests/test_editor_portrait_traits.py \
  tests/test_workshop_portraits.py tests/test_portrait_visual_age.py \
  tests/test_live99*.py tests/test_life248_recovery.py tests/test_providers.py
```

No full CI or new live browser/gameplay run was started. The production API tests
cover Resume, confirmation and reload; real Start Game/UI checks remain part of
the proposed paid retest.

## DeepSeek contract and generation budgets

Official documentation checked on 2026-11-08:

- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)

The documented `max_tokens` range is 1–393,216; default output is 8K without
thinking and 64K with thinking (128K for max effort). These provider capabilities
are not application defaults. The existing application knows a 1,048,576-token
provider context, but sends only its explicitly configured smaller context.

There are three different quantities:

- **Input budget:** all messages, schemas, candidate and any visible continuation
  prefix. App preflight uses `estimate(messages)+512`; input plus generated tokens
  must fit the configured context. `context_length` is a total window, not a
  separate input allowance.
- **Reasoning usage:** included in completion tokens; `reasoning_effort=low`
  controls effort, not a guaranteed numeric token quota.
- **Visible JSON:** uses the same completion allowance. No documented Chat
  Completions parameter reserves a minimum number of visible tokens independently
  of reasoning. Do not send invented `reasoning_budget`/`json_reserve` parameters.

The original provider receipt is direct evidence: 24,000 completion tokens,
24,000 reasoning tokens, zero visible JSON, finish_reason LENGTH. Increasing the
cap can make room, but does not guarantee that the model will deliver JSON.
Without tool calls, prior `reasoning_content` is ignored by the API. A retry cannot
resume hidden reasoning. With visible partial JSON, the existing transport sends
that prefix in context and requests its suffix, validating the assembly. Without
visible content, changed-policy recovery is a fresh attempt of the same request.

Suggested **starting profiles**, not automatic defaults or quality guarantees:

| World | Conservative input planning envelope | Configured total context | max_tokens (reasoning + JSON) | Visible JSON planning range |
| --- | ---: | ---: | ---: | ---: |
| Small, 3–5 NPC | up to 16,000 | 65,536 | 32,000 | 4,000–12,000 |
| Medium, 8–12 NPC | up to 48,000 | 131,072 | 64,000 | 12,000–24,000 |
| Large, 20–30 NPC | up to 128,000 | 262,144 | 64,000 initially | 24,000–40,000 |

Only the medium-world figures have evidence from this campaign: the Off request
used 10,932 input and 23,479 output tokens; Low used 10,957 input and exhausted
24,000 completion tokens before JSON. Small/large ranges are planning estimates.
They must be measured on actual requests. In a large world the shared output cap
may still be insufficient; stop and review usage instead of automatically raising
caps or generating the world again. The larger context accommodates later creative
and review requests containing the entire candidate, not just the initial brief.

Current app boundaries: new-generation `ModelConfig.max_tokens` is capped at
32,000; existing draft Resume accepts up to 65,536. This patch does **not** widen
all model settings/UI limits. The proposed 64,000 medium/large profile can be used
for the retained job through production Resume. Offering it for initial generation
would require a separately scoped world-generation setting, not enlarging ordinary
game defaults. This remains an explicit settings limitation.

Use Low for world generation only. The existing semantic review enforces Off;
ordinary Narrative and Extraction remain Off. The archived Off candidate keeps its
pinned original configuration during its repair; it does not regenerate a world.

## Minimal paid retest proposal — awaiting permission

Do not start a new random world. Use independent SQLite copies of the two original
jobs, one server per database, sequential operations, normal startup recovery.

1. Resume the **same Off candidate**, retaining its original raw world response.
   Check the real addressed repair, creative processing and semantic review. Confirm
   only a technically valid candidate; inspect family relations, private knowledge,
   dates and agency independently of the saved status.
2. Resume the **same Low job** with context 131,072 and max_tokens 64,000. Confirm
   that an actual provider call occurs, collect reasoning/visible usage, and retain
   its first answer. Let the existing bounded pipeline finish; do not increase retry
   counts or repeat successful results.
3. For a successful real world, check Start Game, UI, canonical state and SQLite
   reload. One opening Narrative/Extraction pair is included if budget remains.
   The later 30–50-turn lifecycle campaign is a separate continuation after this
   creation gate, not a substitute test performed here.

Expected 8–10 provider attempts including existing bounded repairs; hard proposal:
**10 new calls / $1.00 conservative total**, whichever limit is reached first.
Estimate 0.25–0.60M input and 0.08–0.25M completion tokens (including reasoning),
about $0.17–$0.48 at the existing peak/cold rates ($0.30/M input, $1.20/M output).
The extra headroom allows the existing full-context reservation (about $0.3914
for a 64,000-token output ceiling). Unknown usage retains that reserve and stops
further dispatch. Generation can take several minutes; allow roughly 15–30 minutes
for the two resumptions and validation, longer if provider latency requires it.

Historical campaign spending remains **4 calls / $0.0661083** in the supplied
ledger. Implementation and free regressions add **zero** paid calls. Use the
existing Budget/ledger for the approved retest; do not reset historical spending.

Remaining risks: real Low may again exhaust its shared output allowance; semantic
review may find additional inconsistencies; a structurally valid save does not
establish playability, correct lifecycle events, agency or long-term continuity.
PR #248 and Stage C remain unmerged/uncompleted.
