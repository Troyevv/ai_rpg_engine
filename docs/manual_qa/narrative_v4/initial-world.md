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
3. Revise a source claim with acknowledgement. Original brief and IDs remain
   in history. Change a core NPC to secondary: locks follow its stable identity,
   obsolete batches remain in audit history and no duplicate NPC appears.
4. Close the browser context, restart the backend with the same SQLite DB, reopen
   and resume. Completed checkpoints must not trigger repeated requests. Missing
   credentials and interrupted billing uncertainty require explicit recovery.
5. A semantic conflict in a revision-6 job is an author-only warning, not a
   publication blocker. Accept or repair the interpretation in the author editor.
   A malformed technical payload still blocks its own unit. Exhaust its budget:
   Resume must disappear and an explicit bounded retry must preserve prior work.

## Ready world and regressions

Confirm only current, complete, canonically valid data. Open the full author
editor and correct family links, organizations, Knowledge, calendar/time and
opening. Invalid references must reject without losing the prior version.
Revision-6 semantic warnings do not block Start Game. Optional
"Проверить изменённый мир" reruns only affected reviews without overwriting edits.
Captured revision-5 jobs retain their strict semantic revalidation gate.
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


## Separate live-provider quality assessment (not completed by fixtures)

Use a real DeepSeek credential, a separate database and a small bounded budget.
Record provider/model, creation settings, actual token/cost usage and original
outputs; do not expose credentials or private world details in public reports.

1. Short: «Молодой парень Илья переезжает в Москву, устраивается в НИИ и пытается
   начать новую жизнь. Повседневность, романтика, юмор и драма».
2. Medium: several named people, two organizations, explicit social relationships,
   a move/job transition and a private fact with limited holders.
3. Complex: the Volkov/Apex brief above, including five subsidiaries, adoption,
   parental marriage plans, discovery chronology and Friday 06:00 opening.

For each inspect whether missing surroundings were creatively developed, core
NPCs have distinct voices/motives/backstories, secondary detail is sufficient,
explicit circumstances are retained, private knowledge does not leak, and the
opening offers possibilities without prescribing the player's next action or a
future plot. Record disagreements as warnings and try correcting them in the UI.
Continue through Start Game, an ordinary turn and reload. Automated fixtures do
not count as this assessment; leave untested quality dimensions explicitly open.

## Single-response creation regression (2026-10-24)

The current default captures `world-single-1`. Historical staged/checkpoint QA
above still applies to captured old jobs, not new creation. Use an isolated dev DB.

1. Quick Creation: enter the Moscow/institute premise, select existing genre,
   cast, geography, expressiveness and pacing/risk controls, create once.
2. Repeat via Scenario hand-off. Check the combined original idea reaches the
   provider intact. No analysis, plan, pages, pair enumeration or review calls.
3. With a separately authorized test key/budget, repeat with the **complete**
   `tests/fixtures/world_authoring/volkov_user_brief.txt`, including Friday 08:00,
   Ilya and Liza outside court. Review all eight named people, five subsidiaries,
   adoption vs biological ties, parental marriage intentions vs actual marriage,
   Ilya's discovery yesterday, restricted Knowledge and unchanged starting action.
4. Editor: change a biography, relationship, Knowledge, location and start time;
   save/reload, confirm, Start Game, ordinary turn, reload and another turn.
   Use existing #78 History/branch/rollback checks for the resulting save.
5. Inject a bad reference: the repair request contains the original response and
   path report. Correct biographies survive; a repair rewriting them fails safely.
   At most initial + two repairs; output truncation is never a schema retry.
6. Pause after a validation failure, restart/reopen and resume: original raw output
   and technical report survive; no fresh creative generation replaces them.
7. Context 8192 currently rejects the full contract before a provider request;
   32768 is the tested offline budget. Oversized input/repair reports estimates,
   never clips the source or falls back to planning. A blocked first submission
   has no job; the form retains the text. Failed received output stays author-only.

Automated lifecycle fixtures are not semantic evidence for the complete Volkov
brief, and this checklist is not a completed live test. Paid acceptance remains
blocked until a test key and separate budget authorization are supplied.
