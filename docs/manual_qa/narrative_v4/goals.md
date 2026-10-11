# #75 — Goals, intentions and values

## Setup/reset

```bash
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint goals
```

Use the printed save in the existing isolated dev database/server. Repeating creates
another deterministic save; no real saves are deleted. The base and earlier #78
checkpoints are unchanged. This checkpoint is already started without a model call.
It adds Ilya/Sonya to the same Two Shores world immediately before their meeting.

| Actor | Intention ID | Starting state | Separate goal |
|---|---|---|---|
| Ilya (`qa_ilya`, EXTERNAL) | `intentions_4d05e847cba4c0a38a98` | active, meet Sonya after Critical Success | develop relationship |
| Sonya (`qa_sonya`) | `intentions_ef4ffaa2b77eac28626d` | active, offer cottage trip | spend weekend together |

Both have an imported explicit honesty value. The source sequence 50 preserves the
live-regression metadata; it is not used as an age-based completion timer.

## Actions and expected canonical state

1. Open Ilya's card: intention and long goal are current, value is distinct. Play
   meeting Sonya, talking and parting. When the narrative actually shows the meeting,
   Extraction must close the existing Ilya intention ID as completed, revision 1,
   with current quote and Event source when supplied. Merely saying “I will meet”
   must not close it. Inspect generation diagnostics if the model omits the update.
2. Have Sonya offer the cottage trip and explicitly agree. Accepted narrative/fact
   `fact_cottage_agreed` grounds completion of her offering intention. Her weekend
   goal remains active until the actual weekend outcome; Ilya's relationship goal
   is unchanged. No duplicate intention/second invitation should be generated from
   the closed record over several subsequent ordinary turns.
3. Open motivation history: completed text/ID remains, current intention list is
   empty. Reload and take another turn: same status, provenance and goal. Desktop
   and mobile should keep all controls usable without horizontal overflow.
4. Regenerate the meeting as a variant where Sonya did not arrive: original active
   intention returns. Select the completed variant: same completed ID/revision.
   Roll back: before-state and History head return. Create divergent continuation:
   no lifecycle/evidence from the other branch may leak.
5. Explicitly abandon/replace Ilya's remaining goal. It must require his player
   decision; Sonya's wishes or narrator speculation cannot cancel it. Switch control
   to Sonya and back: protections follow control, IDs/value provenance stay intact.
6. Advance time past a due date without achieving anything: no automatic completion.
7. With an explicitly linked target/role/organization, establish target death or
   organization/role closure. The linked item is marked for review and stops being
   actionable. Review may block, resolve or supersede with appropriate agency;
   unrelated goals/values remain unchanged. Graduation is a semantic outcome, not
   a rule that completes every goal mentioning university.
8. State an explicit durable principle as Ilya, with a narrated accepted statement;
   inspect the partial `value_delta`. Alternatively perform three distinct voluntary
   completed choices that consistently support refinement. Other values, personality,
   Emotion and timed commitments remain unchanged. One involuntary event or mood is
   insufficient; NPC-era experience cannot substitute for player-owned choices.
9. Verify a witness versus a non-witness: no Knowledge broadcast or access to secret
   value changes. Refine/retire a value, reload, regenerate and roll back; current
   projection and permitted chronological value history follow the selected branch.

Automated counterparts: `tests/test_goals_values.py`, existing lifecycle/agency suites,
and `frontend/e2e/goals.spec.ts`. E2E seeds a deterministic completed meeting through
normal turn execution. Model-backed narrative quality and extraction recall are manual
checks, not claimed as guaranteed by deterministic fixtures.
