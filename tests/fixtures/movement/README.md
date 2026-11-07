# Issue #223: synthetic Phone examples

These hand-written Narratives and responses reproduce the semantics described
publicly in Issue #223. They contain no original private QA archive data.
The location IDs, player input and bad movement shapes are public issue examples.

- `phone006.json`: departure with an unknown destination; initial and repair
  responses incorrectly emit a null completed-arrival endpoint.
- `phone001.json`: future film/photo plans plus departure; Extraction incorrectly
  emits arrival at an existing workshop.

Tests run the real Context Builder, jobs, StateResolver, History and SQLite with
scripted provider responses. Removing only the false Movement retains the
Event and leaves the actor's location unknown. A valid-ID false arrival still
passes Runtime intentionally: Python does not interpret literary meaning.

Original Phone/006 and Phone/001 payloads were also replayed separately against
private copies of the archived SQLite; see the PR report for those results.
Neither these synthetic tests nor the archived-response replay is a live model
accuracy evaluation. No paid DeepSeek calls are made.
