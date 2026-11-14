# Issue #255 — real provider smoke

**End-to-end result: FAIL. The 30–50-turn playtest remains BLOCKED / NOT RUN.**

The user separately authorized at most six new DeepSeek calls and $0.50.
The smoke used DeepSeek Flash, thinking off, the production FastAPI job path,
the complete Context Builder schema and the existing shared Budget/ledger.
There was one new Narrative, two manual Extraction retries after reproduced
code defects, and one automatic bounded repair. No Narrative was regenerated,
no model response was edited, and no successful control JSON entered the save.

## Save and provenance

The original last player-session SQLite was available in this workspace at
`/workspace/work/berezovsk-player-session/game.sqlite`. This updates the earlier
engineering record's environment-specific evidence limitation; the prior
seven failures have not thereby been individually investigated or fixed.
The smoke ran on an isolated SQLite backup, save 1, revision 43. Its initial
SHA256 was `319a3181d52eddcacf9ecc05b5524ee28ff9f92f780b7dbc4a29200497180765`.
Only one server used the working database at a time; startup recovery remained
enabled. The original failed legacy job was abandoned through the production
endpoint on the copy. A new job recorded Extraction/6 rather than silently
changing the old job's contract.

Player input:

> «До завтра, дед. Тамара Ильинична, спасибо за вечер». Убираю камеру в сумку, прощаюсь и иду домой к маме на Лесную.

The real Narrative describes the farewell, Tamara's invitation to return,
Alexey's walk and arrival at his mother's door. The same complete prose was
retained for both subsequent recovery attempts.

## Actual outcomes

| Attempt | Code | Provider result | Persistence |
|---|---|---|---|
| New turn | `533e747` | Full Responses schema accepted; completed Extraction. `departure` incorrectly carried a destination before a separate arrival. Compiler marked the error non-repairable. | Rejected, no repair |
| Manual Retry 1 | `2f6a469` | Completed Extraction. An observer-only location was supplied in actor mode; this error was also non-repairable. | Rejected, no repair |
| Manual Retry 2 | `f61dafe` | First Extraction again included both errors. One real bounded repair corrected the departure endpoint to null but retained the observer override. | Rejected after the single repair |

The recorded transport was `responses_json_schema`. The actual 26,908-byte wire
schema equals the full Context Builder schema after the existing wire projection;
it was not replaced with a minimal demo schema. Its SHA256 was
`1b6be139263b2b139a2b0592706219fe75a04ce83700432c09ffa827bce839d1`.
The Responses streams completed with actual usage receipts. This demonstrates
transport acceptance, **not** complete schema/semantic compliance: the initial
answer also supplied null in two optional `choices[].speech` fields whose schema
requires strings. Those annotations did not cause the observed job rejection.

## Confirmed narrow fixes

1. `scene_steps.py` called `fatal` for a departure endpoint without
   `repairable=True`; its default is false. The analogous existing Movement
   validation allows repair. The new compiler now also allows the one existing
   repair, while still rejecting the invalid route.
2. An observer override in actor mode had the same repair-eligibility problem.
   Additionally, the targeted scene patch merges fields, so omission could not
   clear the override and the schema-permitted null still triggered the error.
   Null now means no observer override in non-observer mode; a non-null override
   remains invalid and repairable. Observer-mode semantics and camera ownership
   remain unchanged.

Both failures were first reproduced on unmodified stored provider replies.
Reduced integration controls failed before the respective changes. They cover
production repair dispatch, successful corrected controls, a repeated invalid
repair with no additional retry, atomic rejection, retained independent Facts,
unchanged camera mode and SQLite reload. These controls are authored tests, not
claimed live model repairs.

Final focused command:

```sh
python -m pytest -q tests/test_scene_steps255.py tests/test_structured_extraction255.py tests/test_movement_semantics223.py
```

Result: **88 passed in 37.17s**. The initial free provider suite was 11 passed;
the first-fix focused suite was 86 passed. No full CI was manually rerun, and
the prior green CI #516 applies to `533e747`, not these new commits.

## Remaining blocker and next work

The compiler exits at the first error. In the final attempt it reported the
departure endpoint to repair; the already-present independent observer error
became visible only after that repair. The real repair preserved the override.
No second automatic repair was attempted, and no unsupported override committed.

The next focused change should collect these independently checkable scene and
step errors before the single repair, and explicitly describe clearing the
observer-only field in actor mode. Preserve the route, input authority and
independent outcomes. Reproduce using this original candidate, test combined
feedback/scopes for one repair, then perform a separately scoped live recovery.
The two fixes above do not establish successful recovery or general playability.

## Accounting and reload

| Request | Input tokens | Output tokens | Provider-call seconds |
|---|---:|---:|---:|
| Narrative | 21,880 | 555 | 4.072 |
| Initial Extraction | 29,158 | 977 | 5.182 |
| Retry 1 Extraction | 29,158 | 624 | 3.823 |
| Retry 2 Extraction | 29,158 | 720 | 4.454 |
| Retry 2 bounded repair | 24,410 | 861 | 3.967 |

**5 calls; 133,764 input / 3,737 output tokens; $0.0446136 conservative cost.**
Rates follow the existing ledger: $0.30/M input and $1.20/M output, with no cache
discount. All receipts settled; no unknown costs were zeroed. The final
Extraction plus repair took 8.421 seconds of provider calls, excluding local
validation and the intervening engineering investigation.

The entire canonical snapshot, History, existing variants and revision 43
remained unchanged. A cold Repository reload after shutting down the server
confirmed the same snapshot. There is **no newly saved turn** to count as PASS.

Raw Narrative, all first answers, repair, actual schemas, request diagnostics,
provider streams, usage receipts, before/after/reload snapshots and the final
SQLite are retained outside Git at `/workspace/work/issue255-live/`. Paid servers
were stopped. The unused allowance was not spent on further attempts. PR #248
remains unmerged; #255 is not accepted.
