# Berezovsk #251 original-response fixture

Source: user-provided `berezovsk248-part-00.gz` through `-03.gz`, concatenated in
that order. Combined SHA256:
`831161494259cd7e207ec1ad63745a16759ce10cea79f8506b291a9b27c3086a`.
All 573 manifest entries and all 36 SQLite files (6 roots + 30 checkpoints) were
verified; SQLite opened read-only. Originals were never modified.

`berezovsk.json.xz` is a lossless JSON selection, compressed with standard-library
LZMA to avoid storing repeated snapshots (88,460 bytes instead of 1,989,414 gzip).
SHA256: `c1af17eef034d33b6e293cb2a0a3cd60b5aabc73f3a48b80b4003c5eadc41a9b`.
It contains cases 001, 002/002r, 005, 006, 008, 009/009r, 016/016r, 017,
020/020r, 024/024r and 025r:

- `snapshot`, `player_input`, `narrative`: original job `before_json`, input and
  immutable Narrative. No reauthoring or generated replacement world.
- `responses`: original request IDs, stages, and literal extraction/repair response
  strings from `requests.json.gz`, including repetitions across retry attempts.
- `original_messages`: actual archived Narrative messages for 016/017.
- `views`: original last eight prior turn records, with snapshots projected only
  to meta/calendar, camera and character situations for isolated context tests.
- `previous_turn`: full original immediately preceding turn, used to seed the
  small CI database. The CI fixture resets its History head; it is NOT a complete
  archive or a claim to replay full historical lineage.

`test_playability251.control()` contains explicitly labelled human JSON controls;
none replaces a recorded response or changes Narrative. These demonstrate Retry
mechanics, not the probability of DeepSeek repairing itself.

Full-lineage replay uses `python -m devtools.live99.replay251 ARCHIVE_ROOT OUTPUT`.
It validates the original manifest, makes SQLite backups, restores successful
checkpoints through ordinary rollback, and runs production jobs with only provider
IO scripted. Missing archived responses fail explicitly; no paid/network calls.
Output includes actual engine→provider messages, diagnostics, integrity and input
hash checks. Do not commit the raw archive, databases or bulky traces.
