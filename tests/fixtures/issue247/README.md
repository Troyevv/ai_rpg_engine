# Original QA #245 inputs for #247 / #246

Source archive: `live99-postfix-evidence-20261107.tar.gz`, 30,262,307 bytes,
SHA256 `e19a0b07ea8a76223c16c6b5805f3e7c9b85733aea0a5828719d0522e5176a36`.
QA revision: `42df4c0048ae2f089a70d701130848703e609c54`.

Each JSON preserves the original `before` WorldState, player input, Narrative,
job ID and the first/last original parsed Extraction responses used by the tests. Cases: Family/001,
Knowledge/002, Phone/001, Crisis/001, Social/001, Campaign/000. Campaign's
last response is the already successful targeted recovery. These files contain
no provider configuration, credentials or full SQLite/ledger.
Unused intermediate responses for Knowledge/Campaign were removed during review;
the original archive still contains them. No checkpoint fields or selected
response fields were trimmed: exact snapshots are needed for regression/reload.
The six readable fixtures total about 560 KiB; no screenshots, logs or databases
are committed. Keeping exact states avoids a second fixture reconstruction format.

`tests/test_integrated_repair247.py::corrected` contains explicitly test-authored
controls. They are not DeepSeek output and must not be presented as live success.
The ordinary automated tests import checkpoints into a fixture lineage. The
separate `tests/replay_issue247_sqlite.py` command exercises the **original**
History/variants on copies of the full source SQLite; see the QA report.
