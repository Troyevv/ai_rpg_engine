# Issue #238 original QA extracts

The JSON files preserve the original World State immediately before each job,
player input, Narrative, initial Extraction and failed repair from QA #239:

- Social/001: `5592529ee31b47578745db1c05f2afb8`.
- Knowledge/001: `5b4fbd26cfc746db91ea7b33b5f1d339`.
- Campaign/011 (after one-year LTA): `df90fbfbb25c4018911b4ba13c2d8f77`.

Source: `live99-campaign-evidence-20261107.tar.gz`, SHA256
`3979c8b87ce923ccf21737c8a7cd17718f218b36535997b752c5118d4d15a277`.
Values come from `<case>/<step>/before.json.gz`, `intent.json`, and
`diagnostics.json.gz`. They have not been reduced to synthetic reproducers.
Corrected replies are explicitly test-authored in `test_action_provenance_repair.py`.

The tests import the archived World State into isolated fixture lineage. Separate
validation against copies of the archive's original `game.sqlite` also exercises
its complete History, turns and sibling variants; see the PR verification report.
No production database, previous snapshot or History record is rewritten.
