# Universal Tabletop 2.0 — acceptance status

PR #33 continues on `codex/universal-tabletop-2`, stacked on PR #32. No merge or deployment is included. Automated acceptance uses fixture authoring responses; **live-provider acceptance remains open**.

## Authoring boundary

The new-world flow is Setting → Campaign → Character. Generation uses the model configured for the generator. Existing saves, imported definitions and legacy drafts remain supported.

LLM output crosses strict Authoring DTO → deterministic AuthoringCompiler → domain definitions → reference and semantic validation. Item forms use named component fields; containers use a positive integer `container_capacity`; contextual actions use one explicit operation and reference. Invalid strings, unknown fields, conflicting references and incompatible capability fields are rejected, never coerced or removed. A regression covers four actions and four objects, including precise field/entity diagnostics and the two-attempt retry bound.

Targeted schema audit:

| Content | Authoring representation |
| --- | --- |
| Context actions | Explicit operation/reference DTO; compiler selects the domain operation |
| Item components | Named optional component forms, no discriminator union in LLM output |
| Objects | Explicit capabilities and mechanical fields; compiler builds typed components |
| Effects, resources, creature templates, checks, powers | Existing flat typed definitions; strict validation, no redundant DTO layer |
| Encounters | Flat requests; deterministic template selection and threat budget, no generated runtime stats |

Late setting stages receive complete editable sections and an ID/name index for the other sections. They no longer resend full advancement tables and unrelated definitions. Campaign authoring omits default item fields and receives creature selection metadata. The complete registry remains unchanged and is used by validators. Token estimates are conservative estimates, not provider tokenizer measurements; model context limits still apply.

SQLite checkpoints retain each validated stage, frozen source snapshot, current stage and structured issues. Resume after a process restart revalidates cached DTOs and calls the model only for unfinished stages. Completed requests are idempotent; changed input requires a new job. Credentials are excluded from persisted job requests. The editor displays saved stage progress and resume. Execution locking follows the application's single-process server model.

## Runtime and UI coverage

| Area | Implemented path and evidence |
| --- | --- |
| Setting snapshot | Versioned worlds, selected-world creator and immutable campaign content; independent-world fixtures survive SQLite reload |
| Items | Weapon/armor/tool/ammunition/magazine behavior, consumable and medical features, finite energy sources, carried/world containers with capacity and explicit store/unpack UI |
| Energy sources | One inventory unit restores up to its declared capacity, bounded by the resource maximum; the unit is consumed, preventing refill through transfer/reload |
| Item effects | Equipped items grant active/passive features; bonuses reverse on unequip; resource initialization cannot refill through toggling; feature-ID requirements are validated |
| Equipment | Profile-based slots and hand conflicts in runtime, creator shop and equipment UI; purchasing remains separate from equipping |
| Objects | Open/unlock, capacity, break attack/damage rolls, cover, terminal/environment features and typed hazard damage; local visibility and encounter-loot gates remain enforced |
| Context actions | Conditions and references select a declared check, interaction or granted feature; arbitrary feature execution remains forbidden |
| Firing modes | Separate ammo costs, accuracy modifiers, damage expression/bonus; preview and player/NPC resolution share mode data |
| Powers | Custom damage type and resource costs pass through attack, automatic, save and area resolution; immunity/resistance/vulnerability and NPC resolution regressions |
| Background | Equipment, skills, resources, hooks and proficiencies plus contacts/knowledge in the character UI, known facts and initial faction reputation |
| Creatures | Template stats remain independent of class progression; AI profile influences tactical utility weights |
| Gameplay | Browser scenario generates a setting and campaign, creates a character, performs checks, fights template creatures, takes loot, changes equipment and restarts the actual server |
| Choice UI | Shared choices throughout Narrative/Tabletop; native select/option/datalist AST guard remains in the build |

## Dice presentation

Three.js controlled 3D motion precedes the existing result card. The backend owns every result; animation never rolls or determines game mechanics. Supported solids: d4/d6/d8/d10/d12/d20; d100 uses two correctly labeled percentile dice. Compound rolls render their actual dice, advantage/disadvantage dims the unselected result, modifiers remain in the breakdown. Visual pools stop at 12 dice while retaining the full canonical result.

Motion lasts about 1.5 seconds plus a short resting pause. Skip, reduced motion, WebGL fallback and a completion timeout preserve interaction. Changing tabs finishes the visual wait, so spell/inventory navigation cannot strand a server-resolved roll. GPU resources are disposed. Desktop/mobile tests cover rendering, percentile labels, compound pools, selection, skip, reduced motion and width; resting faces were visually reviewed. This is mobile emulation, not a physical-device benchmark.

## Verification record

- Initial full backend run: 697 passed, one reputation regression found. The fix and related world/content regressions then passed (30 tests).
- Final related authoring/content/object/world regressions: 70 passed.
- Frontend production build and native-choice guard passed.
- Full browser run: 90 passed, 10 intentionally skipped duplicate layout cases, two mobile failures. One was caused by rebuilding the served frontend during the run; the other exposed a late roll response overriding tab navigation and was fixed.
- Both failed scenarios plus dice checks were rerun on desktop/mobile: 10 passed. The spellbook regression now deliberately delays the roll response until after tab navigation. CI status is recorded separately in the PR.

## Remaining external acceptance

- Real model generation smoke tests for unrelated user-created settings. No DeepSeek/OpenAI credentials or configured local model endpoint were available; fixtures do not establish real model compliance, story quality or encounter balance.
- Physical-phone performance and final user playtesting. Responsive browser emulation and WebGL checks do not establish frame rates on the user's phone.

Keep this distinction when reviewing acceptance; do not describe fixture generation as a successful real-provider test.
