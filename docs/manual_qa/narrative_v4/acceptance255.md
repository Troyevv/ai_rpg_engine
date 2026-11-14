# Issue #255 — engineering record

Baseline: PR #248 `cace6ed35ede13666142e55875b71f2a38c99ae8`.
Master inspected: `ee343deee65f627932c5a4f13aedbb41fa06be8f`.
Both AGENTS.md read. Work continues in the existing PR; no merge.

## Evidence boundary

The 43-line `diary-notes.md` uploaded 2026-11-14 was read in full.
It reports 16 ordinary inputs, 9 saved (one after manual Retry), 7 rejected,
8 manual Retries, 6 abandons and two separate phone exchanges. Four attempts
to leave the cafe failed. This is player observation, not captured provider IO.
No original SQLite/requests from THAT session were found in the available
workspace or the targeted Library search. Its execution SHA is not established.
The available acceptance252 archive belongs to an earlier session and cannot
substitute for these missing originals. No historical replay of the seven
latest failures is claimed. New controls are explicitly authored.

| Diary episode | Observed failure | Proven cause in that job |
|---|---|---|
| 1, 12 retry | Duplicate fact | Unknown: exact repeat vs ID/privacy conflict needs original JSON |
| 2, 10, 12 initial | RawTurnResult/final_scene | Unknown: envelope/null/truncation needs original response |
| 7 | Input action source | Unknown: exact input/action needed |
| 8 | Controlled actor missing | Unknown: actual route and camera needed |
| 11, 18 | Presence / rejected relocation | Unknown: original steps/order needed |

Confirmed code causes: legacy parse requires final_scene before compilation;
the model separately supplies routes, action provenance and final membership;
repair requests a whole replacement proposal. These are interface properties,
not a claim that one cause explains every historical failure.

Paid provider smoke and ordinary 30–50-turn UI playtest: **NOT RUN**.
No paid budget is authorized by this issue. Engineering controls cannot prove
model understanding or satisfy the live acceptance gate.
