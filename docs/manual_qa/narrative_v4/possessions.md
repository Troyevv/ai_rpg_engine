# #77 — Significant possessions QA

Use the existing #78 isolated developer database/server. Each load creates a new,
reproducible save; resetting means rerunning the command, never wiping a user save.

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint possessions
```

The unchanged `base` is extended with three canonical objects:

| ID | Owner | Holder | Location | Knowledge |
| --- | --- | --- | --- | --- |
| qa_ring | Kirill | Kirill | home | Kirill, Vera, Timur |
| qa_camera | Timur | Vera | home | Kirill, Vera, Timur |
| qa_letter | Oleg | Oleg | workshop | Oleg only |

Inspect canonical state through saved `world_state.possessions` and existing job
context/Extraction diagnostics. In the UI, existing Knowledge/Milestone views show
established facts and meaningful events; no general inventory panel is added.

1. Start, take an ordinary turn, save, reload, take another turn. All three identities
   and owner/holder/location remain unchanged. Moving Kirill does not move his ring
   automatically. The private letter must not appear in Kirill's context/knowledge.
2. Ask Vera to return Timur's camera; establish an actual completed return. Expected:
   `return`, owner stays Timur, holder becomes Timur, location explicitly established
   or null, revision increments once. Asking/planning alone changes nothing.
3. Explicitly sell Kirill's ring to Vera, then establish completion. Expected: same
   `qa_ring`, owner Vera, holder/place explicitly established (unknown allowed).
   No cost, currency or account is created. Regenerate this turn; select the original
   variant; identity/provenance must not duplicate. Roll back: original title restored.
4. Without Kirill's input, try having the narrator voluntarily sell/gift/discard his
   ring. Expect a rejected delta and unchanged state. Merely observing an NPC must
   not change who is EXTERNAL. Autonomous Timur can gift his own camera causally.
5. Have Vera gift the acquired ring to Timur. Ownership changes on the same ID;
   later references must not restore it to Kirill. Returning physical custody to
   the owner is distinct from reacquiring legal ownership from another owner.
6. Establish an involuntary loss: status lost, holder null, location null (or explicitly
   established place), owner unchanged. A plan to look for it is not recovery. An
   actual discovery changes lost → available and establishes holder/place. An actual
   return changes holder to owner. A sold object requires acquisition to restore title.
7. Establish destruction: status destroyed, holder null, explicit place/null. Further
   ordinary turns/time skip must not restore it. Attempts to recover/transfer/rename
   that destroyed ID are rejected; a replacement is a genuinely distinct object.
8. Secretly move the camera off-camera. World Truth changes; uninformed Kirill's old
   knowledge remains unchanged. He must not receive the new holder/place from context,
   History or Milestones. A later witnessed explanation/observation can acquire its
   fact and correct an exclusive old claim via #76. Vera's knowledge is independent.
9. Replay the same extraction with renamed event or item IDs: no duplicate introduction
   or operation. Try two transitions without event order: both rejected; supply a
   distinct order and correct successive revisions: chronology is preserved.
10. Branch from before a sale; change only one branch. The sibling still has its own
    ownership/history. Compare after reload, regenerate and rollback. Each transition
    retains Event/Fact, before/after and source record provenance.
11. Load a legacy save without possessions: empty map, normal start/turn/reload/turn;
    rings/phones in descriptive prose do not become canonical entities automatically.
12. For a large map, inspect context: at most 12 selected objects / 6000 JSON characters,
    explicit named object prioritized, no ledger/full history. Hidden objects must
    not become visible just because their actual holder or place matches the scene.
13. Switch to Tabletop and exercise existing inventory/equipment. No Narrative item
    data appears and server-authoritative equipment behavior is unchanged.

Automated: `.venv/bin/python -m pytest -q tests/test_possessions.py`.
Real provider manual checks are exploratory; automated regressions use deterministic
provider fixtures and do not require paid calls. Verify Russian diegetic text stays
Russian; identifiers and delta enum values are language-neutral.
