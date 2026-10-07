# Context Builder v2: final implementation report

Measured 2026-10-07 on local CPU with two embedding threads. Raw model weights were cached before model-comparison timing. No live Narrative provider was called. PR #47 remains draft for repeat live QA.

## Russian semantic benchmark

The selected E5 model retrieves all 8 expected entities across three positive queries and returns no result for the unrelated space-engine query. MiniLM retrieves 6/8 and returns one result for the negative query. E5 favors recall but is less precise for the relationship query. These four tiny cases informed threshold choice and are not an independent evaluation set.

| Model | Cached load ms | Warm query median ms | Process peak RSS MiB | Model cache MiB |
|---|---:|---:|---:|---:|
| intfloat/multilingual-e5-small | 4997.89 | 29.073 | 883.61 | 470.44 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | 4491.71 | 19.982 | 1100.82 | 457.51 |

RSS includes Python, PyTorch and benchmark execution; model-cache size includes the files actually cached, not only weights. First download is excluded above. Latency depends on CPU, input size and concurrent load.

| Query | E5 expected found / expected | E5 extras | MiniLM expected found / expected | MiniLM extras |
|---|---:|---:|---:|---:|
| serious | 2/2 | 5 | 2/2 | 3 |
| cottage | 3/3 | 2 | 1/3 | 0 |
| jealous | 3/3 | 0 | 3/3 | 0 |
| negative | 0/0 | 0 | 0/0 | 1 |

E5 extra matches for the serious-relationship query: Katya character/fact/event and two cottage facts (5 extras, precision 2/7). For the cottage query: station and report thread (2 extras, precision 3/5). The jealousy query is 3/3 without extras. Reporting only negative-prefixed documents would hide the first five errors; the benchmark now reports all extra IDs and precision.

## Same-world context benchmark

Baseline: `663c2e82c0a37b566b5c7ba2f1059915c2b1f92f`. The exact same synthetic world is fed to both builders. Estimates are the project UTF-8 heuristic, not provider usage. The baseline reaches its budget by dropping all six scenes; the new builder retains six.

| Mode | Before estimated tokens | After estimated tokens | Before scenes | After scenes |
|---|---:|---:|---:|---:|
| Narrative | 123,329 | 17,018 | 0 | 6 |
| Extraction | 123,710 | 8,007 | 0 | 0 |
| ActiveNarrative | 123,349 | 16,450 | 0 | 6 |

ActiveNarrative requests reading Sonya’s message and includes one ACTIVE_REFERENCED behavioral profile. It does not turn the author into a physical or remote participant.

| Entity | World total | Old Narrative included | Narrative selected / included | Extraction selected / included | ActiveNarrative selected / included |
|---|---:|---:|---:|---:|---:|
| locations | 56 | 56 | 5 / 5 | 1 / 1 | 4 / 4 |
| facts | 221 | 167 | 12 / 12 | 1 / 1 | 12 / 12 |
| knowledge | 442 | 168 | 13 / 13 | 2 / 2 | 13 / 13 |
| relationships | 141 | 16 | 6 / 6 | 4 / 4 | 12 / 12 |
| threads | 36 | 36 | 4 / 4 | 1 / 1 | 4 / 4 |
| scheduled_events | 56 | 56 | 2 / 2 | 1 / 1 | 1 / 1 |
| history_events | 551 | 31 | 8 / 8 | 0 / 0 | 2 / 2 |

| Character mode | Narrative selected / included | Extraction selected / included | ActiveNarrative selected / included |
|---|---:|---:|---:|
| FULL_PRESENT | 2 / 2 | 2 / 2 | 2 / 2 |
| FULL_REMOTE | 0 / 0 | 0 / 0 | 0 / 0 |
| ACTIVE_REFERENCED | 0 / 0 | 0 / 0 | 1 / 1 |
| COMPACT_REFERENCED | 11 / 11 | 1 / 1 | 11 / 11 |
| INDEX | 22 / 22 | 32 / 0 | 21 / 21 |

Extraction mode counts describe its affected canonical actors; it contains no behavioral cards or identity index.

| Prompt part (includes message framing) | Old Narrative | Narrative | ActiveNarrative | Extraction |
|---|---:|---:|---:|---:|
| Постоянные правила | 2325 | 2529 | 2529 | 3019 |
| Кампания / GM-only | 85 | 74 | 74 | 0 |
| Текущее состояние / GM-only | 77600 | 5807 | 5575 | 1101 |
| Карточки присутствующих / GM-only | 2762 | 3260 | 3261 | 0 |
| Индекс персонажей | 596 | 593 | 569 | 0 |
| Знания POV | 37035 | 367 | 368 | 0 |
| Память | 62 | 62 | 62 | 0 |
| Недавняя история / GM-only | 2264 | 632 | 206 | 0 |
| Director / GM-only | 269 | 389 | 358 | 0 |
| Текущий ввод | 75 | 75 | 95 | 75 |
| ContextScope / GM-only | 0 | 226 | 219 | 0 |
| Поведенческие профили / GM-only | 0 | 59 | 189 | 0 |
| Знания действующих персонажей / GM-only | 0 | 93 | 93 | 0 |
| Реплика игрока 0 | 0 | 47 | 47 | 0 |
| Реплика игрока 1 | 0 | 47 | 47 | 0 |
| Реплика игрока 2 | 0 | 47 | 47 | 0 |
| Реплика игрока 3 | 0 | 47 | 47 | 0 |
| Реплика игрока 4 | 0 | 47 | 47 | 0 |
| Реплика игрока 5 | 0 | 47 | 47 | 0 |
| Entity IDs | 0 | 0 | 0 | 102 |
| JSON Schema | 0 | 0 | 0 | 3382 |
| completed_narrative | 0 | 0 | 0 | 72 |
| Assistant continuity | 0 | 2314 | 2314 | 0 |
| One-time estimator overhead | 256 | 256 | 256 | 256 |

The benchmark includes previous player inputs separately. Narrative Facts are serialized once; POV and acting-actor Knowledge rows reference their IDs. Selected/included ownership counts: `{"selected": 13, "POV": 12, "FULL_PRESENT": 1, "FULL_REMOTE": 0, "ACTIVE_REFERENCED": 0}`.

### Cache and index

The long-world index contains 955 documents. Cold build/model initialization: 18781.644 ms; query: 79.382 ms. First build encodes 955 documents. Warm repeat: 955 hits, 0 misses, 0 rebuilds, 84.358 ms query / 89.22 ms retrieval total. This long-world query is longer than the microbenchmark and has higher latency.

Cache tests cover edits, deletion, rollback, stable ordering and failure cooldown. 100/1,000/10,000-fact prompt tests retain the same capped payload. Every request still scans/hash-checks active documents; this is not a sublinear vector index.

## Validation and boundaries

- Full Python suite: **766 passed**, Python 3.12 (one existing Starlette/httpx deprecation warning).
- Focused participation/semantic suite: **26 passed**, including two-turn Yura with and without name, distinct author voices, ownership, directed relationships, soft/hard overflow and semantic-only overdue schedules.
- Frontend: `npm run build` passed; existing Vite bundle-size warning remains.
- General tests use injected embeddings or disable retrieval. The model benchmarks above use real sentence-transformers on CPU.
- Existing suites cover save/load/import, POV, observer worlds, regeneration, variants, rollback, background/time skip, lifecycle, relationships and diagnostics. Tabletop code is unchanged.
- Live generated prose and extraction accuracy still require user QA. No quality claim is inferred from deterministic tests.
- Explicit authored-output detection handles common Russian/English forms, not arbitrary natural-language instructions. Ambiguous authors should be established by structured Event metadata; old-message pronouns beyond the short continuity window may require a name.
- Thresholds can yield irrelevant candidates; per-type caps and non-expanding neighborhoods bound the damage. No semantic result becomes truth, knowledge, physical presence or behavioral participation on its own.
- Missing local model weights use visible structural fallback. Weights must be provisioned once; runtime does not download them.

## Changed files in this continuation

| Files | Change |
|---|---|
| `backend/runtime_v3/semantic.py` | Local encoder, content-addressed bounded cache, deterministic retrieval and fallback |
| `backend/runtime_v3/participation.py` | Structured authors/background actors and explicit personalized-output requests |
| `backend/runtime_v3/scope.py` | Hybrid candidates, ACTIVE_REFERENCED, bounded neighborhood and selection reasons |
| `backend/runtime_v3/context.py` | Behavioral projection, ownership blocks, compact references, trimming and diagnostics |
| `backend/runtime_v3/context_contract.py` | Truth/Knowledge boundaries and author extraction instructions |
| `backend/runtime_v3/raw.py`, `backend/runtime_v3/resolver.py` | Additive validated message author_id |
| `backend/runtime_v3/history_selector.py`, `backend/runtime_v3/director.py` | Shared semantic scope and structurally justified acting actors |
| `frontend/src/Diagnostics.tsx` | Selected/included counts, ownership and semantic details |
| `requirements.txt` | sentence-transformers and CPU wheel source |
| `scripts/benchmark_context_v2.py`, `scripts/benchmark_semantic_v2.py` | Real-model quality/performance, active profile, prompt breakdown |
| `tests/conftest.py`, `tests/test_semantic_participation.py` | Reproducible tests without weights and new regressions |
| `tests/test_canonical_runtime.py`, `tests/test_context_builder_v2.py` | Updated intentional context projection expectations |
| `docs/context-builder-v2.md`, `docs/context-builder-v2-results.md` | Architecture, setup, reproducible measurements and limitations |
