# Extraction 136 semantic corpus

23 public synthetic cases. Expected records, forbidden records, scene identity and time
are scored directly on the provider response, before Resolver. The synthetic reply is
a replay fixture, not a prediction or a live DeepSeek result. Narrative/API tests use the
existing E5 export and import pipeline; only the external provider is substituted.

`python -m pytest -q tests/test_extraction_corpus136.py` checks actual assembled prompts,
JSON Schema, raw semantic labels and API/jobs/Runtime/SQLite application. It does not
measure model recall. `python -m devtools.evaluate_extraction136 --output /tmp/report.json`
records NOT RUN by default. See the linked acceptance report for bounded live opt-in.

Cases cover death/rumor/hypothesis/negation, entry/doorway/closed door/future arrival,
remote contact, offered/declined/agreed/rescheduled plans, injury/recovery, route with
multiple events, new place/NPC, historical wording, initiative, marriage, resignation,
and subjective rumor Knowledge. Exact duration annotations are fixture expectations;
real model differences need review, since literary durations may be underdetermined.

Live before/after semantic quality and repair effectiveness are NOT RUN. The full-stack
phone continuation/reload sequence is covered separately by the #78 integration and
Playwright suite; the corpus phone case tests remote classification only.
