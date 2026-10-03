# Tabletop Gameplay 1.0 — acceptance record

Base: PR #31, `825442f02f251a2429804b0d1e5adb2e6d48c1ef`.

## Scope

The new default `d20-fantasy-v2` (schema version 4) adds the twelve main class archetypes, twelve species and fourteen backgrounds. The older scout remains for compatibility. These are custom simplified rules, not a claim of complete official D&D implementation. Existing campaigns retain their original ruleset.

New characters start with six scores of 5 and distribute 42 linear points (5–18), with server-derived before/after changes. A priced starting shop preserves unspent gold. Twelve equipment slots enforce compatibility, hands and armor proficiency; equipment recalculates attacks, armor and stealth disadvantage. Inventory supports inspection, equipment changes, use, transfer and dropping.

Scene checks contain validated success/failure consequences. Exploration, social, knowledge, environmental, stealth and travel requests use the same server dice engine as combat, including authored critical/partial outcomes and passive perception/insight. The DM selects requests, never dice results or direct state patches. Generated and expanded content crosses reference and semantic validation before use.

Combat previews enumerate the d20 outcomes with the same hit rule and condition modifiers as combat resolution. Spell/feature targets reuse execution validation without spending resources. The timeline shows rolls and consequences before narration; pending controls sit above the composer. Request status reports observed server stages rather than invented percentages.

## Separate step-by-step UI acceptance

Performed through a local Chromium browser driven interactively, separately from the Playwright assertions. The world and model replies were deterministic fixtures; live external-model quality was **not** verified.

Character: Александр, human paladin, soldier background. Allocation: STR 15, DEX 13, CON 14, INT 10, WIS 12, CHA 8. This deliberately weak spellcasting score also exposed negative-modifier presentation.

1. Opened the creator, verified all six scores at 5 and 42 remaining points. Increased and decreased Dexterity, inspected the derived armor, initiative, save and skill deltas.
2. Selected class/background, purchased leather armor, dagger and healing potion. Started with 115 gold; checked equipment and class resources in play.
3. Searched for traces (Investigation), spoke with the archivist, lied about being sent by the captain (Deception), and examined a rune (Arcana). Verified discoveries and the NPC attitude event.
4. Failed the climb (Athletics): HP 12 → 9 and prone. Moved to the vault and failed Stealth: the guard became alerted.
5. Started combat, rolled initiative, stood up, used Lay Hands with its healing roll, ended the turn and observed the opponent's attack.
6. Cast Healing Word from the combat panel: a server d4 result, negative Charisma modifier, HP 8 → 11, and spell slots 2 → 1. Used the potion and guard reaction, then inspected weapon hit/damage previews.
7. Rolled attacks and critical damage, observed actual HP events and enemy healing, and fought through to victory. Opened the guard's bag and took three coins.
8. Inspected the paper doll and item actions. Removed/re-equipped leather armor and inspected the common impact preview.
9. Restarted the Python server against the same SQLite database. Revision 41 and the complete character projection matched before/after. Continued with Look at revision 42; gold remained 115.
10. Checked the inventory at 393 × 851 and inspected screenshots of abilities, impact changes, shop, pending check, combat and equipment.

## UX findings and fixes

| Finding during review | Fix |
| --- | --- |
| The impact table was squeezed into a narrow creator column; headings ran together. | Widened the desktop creator, spaced table columns, retained a single-column phone layout. |
| Ability scores did not explain their practical purpose. | Added concise descriptions next to each score; kept the server-derived deltas. |
| A mobile action drawer could hide an outstanding roll. | Pending roll/choice/reaction forces the timeline to remain visible. |
| Combat controls were duplicated in the center and right rail. | New-rule combat uses the central action bar; the side rail keeps the character summary. |
| Other controls appeared between the pending roll and composer. | Moved action selection before pending controls. |
| HP animation reused a rotating dice transform. | Replaced it with a short fade/vertical transition and reduced-motion support. |
| Healing features displayed an internal purpose ID; negative spell modifiers rendered as `+ -1`. | Added the localized healing label and signed modifier formatting. |
| Attack cards inherited an unrelated default ability label. | Pending weapon attacks now carry the weapon ability; non-ability damage/healing cards omit it. |
| Inventory actions were permanently expanded. | Each grid item now exposes its inspection/action panel on demand. |
| A two-handed purchase could conflict with the off-hand item. | Shop and runtime unequip conflicting hand slots; changing class removes incompatible armor from equipped slots. |

## Automated checks

Local verification: **644 backend tests passed**, production frontend build passed, and **12 desktop/mobile tabletop browser scenarios passed**. The strengthened armor-swap/restart scenario then passed again on both viewports. The full browser suite is also configured as a PR CI gate.

- Backend regression suite, including allocation/shop validation, all twelve class builds, compound dice, canonical check consequences, healing rolls, passive discovery, critical outcomes, exact advantage probability and read-only target validation.
- Desktop/mobile browser scenarios cover the creator, five check domains, combat preview/rolls/healing, loot and real server restart.
- The equipment scenario also buys chain armor, starts in leather, then swaps to chain, verifies armor/stealth changes and old armor returning to inventory, and restarts the server.
- Existing creator, spellbook, choice/check persistence and legacy campaign scenarios remain covered.

## Known boundaries

- UI and mechanics acceptance uses a mocked provider; a real local/remote model still needs a user-side campaign smoke test. No provider credential was available in this workspace.
- Class/subclass content is intentionally a custom first catalog and is not claimed to be balance-tested over a long campaign.
- Runtime progress is a bounded in-process registry for the current single-worker application. Mechanical state/history is persisted in SQLite; progress labels themselves are transient.
- Damage previews show the rolled range before target guard/resistance, and label that limitation. Hit forecasts include the actual condition-based defense rules.
- No tactical map was added: distance remains the existing scalar position model.
