# Initial World State v2 — #44 / #78

Use a separate test database. Provider-dependent automated cases use fixture
responses; they do not establish live-provider narrative quality.

## Entry paths and source integrity

1. In Quick Creation select Family Saga, a secondary genre and Expressive NPCs.
   Change the genre: descriptions must update without a provider call. A fourth
   secondary genre, duplicate primary/secondary or empty Custom description must
   be rejected. Pacing and risk remain independently selectable.
2. Enter the rich Volkov family brief from `tests/test_initial_world_rich_brief.py`.
   Inspect its author interpretation: seven named people, adoption, parental
   marriage intention, five subsidiaries, discovery yesterday and Friday 06:00
   station walk. Unknown country remains unknown; legal qualification has an
   author warning. Plans do not become marriages, pregnancy or protagonist goals.
3. Repeat using Scenario's existing hand-off into World Workshop. Verify source
   and settings are captured once. JSON and structured Markdown imports must
   normalize without creative provider calls.

## Hybrid editing and recovery

1. Pause during a character request. Observe the pausing state, one safe commit,
   then no further dispatch. Read-only inspection while running does not pause.
2. Edit a completed character, location, life record, Knowledge record and opening
   through canonical forms. Inspect impact before saving; independent versions
   remain intact. Lock/edit, regenerate and unlock explicitly; provider attempts
   cannot silently overwrite accepted locks.
3. Revise a source claim with acknowledgement. Original brief/quotes/IDs remain
   in history. Change a core NPC to secondary: locks follow its stable identity,
   obsolete batches remain in audit history and no duplicate NPC appears.
4. Close the browser context, restart the backend with the same SQLite DB, reopen
   and resume. Completed checkpoints must not trigger repeated requests. Missing
   credentials and interrupted billing uncertainty require explicit recovery.
5. A semantic review conflict pauses before publication. Only author inspection
   exposes its explanation/evidence. Repair the originating stage or explicitly
   revise the source; retry must preserve accepted unrelated work.

## Ready world and regressions

Confirm only current, complete, canonically valid and semantically reviewed data.
Change a reviewed opening in Author World: Start Game must require revalidation.
Use "Проверить изменённый мир": only affected semantic reviews rerun, edited
content remains intact and successful validation allows Start Game. A conflict
keeps the edited draft; cancel the review to correct it in Author World.
Play an ordinary turn, reload the save, regenerate/rollback and create sibling
branches. Verify hidden adoption knowledge does not spread, opening history stays
unchanged and player agency/expressiveness policy survive. Repeat legacy imports
and a Tabletop campaign using their existing flows.

Automation: `test_initial_world_v2.py`, `test_initial_world_rich_brief.py`,
`test_generation_edits.py`, `test_generation_semantics.py`,
`world-generation.spec.ts`, `world-generation-recovery.spec.ts` and the existing
parity/import/Runtime/Tabletop suites. Record exact commands, tree and results in
PR #105; do not mark manual/live-provider checks passed merely from mock tests.

## Temporal guard integration (#112)

After generated Start Game, retain the specified initial clock/calendar and a
nearby pending commitment. An ordinary turn may reach its due minute, never cross
it without accepted resolution. A rejected long regenerate preserves active
variant/snapshot; valid regenerate, variant selection, reload and rollback remain
available. The automated generated-world case is
`test_generated_world_obeys_merged_temporal_guard_through_history`; the broader
#78 matrix remains in `commitments.md` and `test_temporal_guard.py`.
