# Protagonist transition (#42)

Use the existing isolated #78 loader, never a personal database:

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint protagonist
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint protagonist-infant
```

Each command creates a fresh save. `base` is unchanged. `protagonist` establishes
Asya's tenth birthday and existing family relations. `protagonist-infant` replays
the existing accepted #41 birth and selects that same newborn Character ID.

## Existing characters and children

1. Start `protagonist`, perform an ordinary turn, reload, perform another turn.
2. Open **Сменить главного героя**, select Asya, preview and confirm.
   Current protagonist and controlled actor become Asya; Kirill remains alive,
   with unchanged identity, personality, relations, possessions and Knowledge.
   Asya has her own Knowledge and capabilities, not Kirill's private information.
3. Use **Камера мира → Временно управлять** for Vera. Asya remains protagonist;
   no protagonist period is added. **Наблюдать** sets control to null and an
   explicit subject/POV. These selection operations make no model requests.
4. Permanently switch back. The original characters and development profiles
   remain intact. Inspect the existing Milestones surface for permanent periods.
5. In `protagonist-infant`, verify null control, no action choices, no adult actions,
   working observation and **Пропуск времени**. **Продолжить наблюдать** retains
   the newborn subject; it does not silently switch POV to a caregiver.
6. Establish incapacity through a deterministic life-state fixture or ordinary
   accepted transition: permanent identity is unchanged. Observe or temporarily
   control another character, resolve the condition, explicitly resume control.

## Death

The pre-#68 policy rejects autonomous death proposals for the current protagonist.
The automated policy fixture permits one to exercise the complete resolver path.
An explicit confirmed/system-established death retains all canonical identity
and consequences, releases control, closes the open period and sets
`protagonist_required`. Further generation is blocked before provider invocation.
The UI requests a living successor or a new character, never Game Over. Selection
uses the same transition service as a manual permanent switch.

## New character

1. Open **Создать нового**. Enter name, card fields, canonical appearance,
   personality, motivations and capabilities as needed. Choose an initial place
   and enter **Стартовая сцена / Обстоятельства появления**.
2. Keep connections, Knowledge and secrets empty. Preview, cancel: no revision,
   Character, History, Milestone or Knowledge changes.
3. Reopen, create a newcomer, preview and confirm. Exactly one new ID and a
   permanent transition commit together, at unchanged world time.
4. Generate a whole draft with the configured provider (DeepSeek supported),
   edit fields, regenerate one field. Neighbouring edits remain unchanged.
   Generations are optional paid requests; deterministic automated tests use stubs.
5. In integrated mode, add a typed proposed relation/role/location/organization.
   Select existing reference targets. Approve each proposal separately and choose who knows it. Verify
   unknown IDs, cycles, duplicate identities, invalid dates and changes to existing
   NPCs are rejected with the draft retained.
6. Choose an explicitly authorized existing secret only from the current POV's
   known facts, with a source who knows it and an authored acquisition basis.
   Add a personal biographical secret with explicit holders. Other characters do
   not receive it; separate acquisition events preserve holder boundaries.
7. Confirm twice with the same request: one character, one transition. A stale
   revision or failing transaction leaves no orphan/partially applied state.

## History and regression

After each kind of switch or creation: ordinary turn → reload → ordinary turn;
rollback restores the recorded before snapshot, regeneration uses its original
context/control, selecting variants restores that lineage. Branch to a saved
variant and verify no sibling character/Knowledge/operation receipt leaks.
Rollback before creation removes its canonical additions, preserving the archived
historical record. Control changes between turns never rewrite older variants.
Tabletop creation, inventory and gameplay must remain unaffected.
