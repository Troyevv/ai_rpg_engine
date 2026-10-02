# Universal Tabletop 2.0 — implementation checkpoint

This branch is a work in progress stacked on PR #32. It is **not full acceptance of the specification** and must stay draft.

## Implemented

- Separate, versioned SettingDefinition and ContentRegistry persistence; campaigns contain a fixed setting snapshot.
- Six-stage setting and campaign authors, strict schemas, dependency validation, structured semantic issues and at most two attempts per failed stage.
- Setting editor, section regeneration, saved world selection, campaign and character flow using the selected snapshot.
- Core-only rules catalog and explicit old catalog import. Three independent content fixtures compile, use resources and survive SQLite reload without importing fantasy content.
- Creature templates/instances and deterministic threat/budget selection.
- Custom skills, alternate abilities, damage modifiers, resource costs, magazines, reload and server-validated single/burst/automatic mode costs.
- Declarative effects, contextual action requirements, ability requirements and temporary effect expiry. Runtime transactions validate before committing state.
- Profile-driven equipment slots, armor placement and hand conflicts; starting purchases remain unequipped; unavailable starting items are rejected by the server.
- Application-wide shared choice popup/sheet, search, keyboard/focus support, mobile Back handling and AST guard against native select/option/datalist controls.
- Regression fixes: preserve catalog when regenerating foundation; aggregate duplicate resource costs; retain template combat statistics during inventory changes; preserve protection-ring AC during import; validate character builds against the campaign snapshot.

## Verification

The final response/PR records exact test counts for its commit. Verification includes backend regressions, frontend build, the native-choice guard and browser runs. The new mobile scenario covers setting generation/edit/save, campaign generation, character allocation, shop purchase/equip, game creation and browser reload at 360×800, 390×844 and 412×915.

All authoring responses in tests are fixtures. These tests do **not** establish real model quality, world coherence, encounter balance or live provider reliability.

## Remaining acceptance work

- Make the setting-first staged flow the default and remove the legacy one-shot generation path from new-campaign UX, while retaining old saves/drafts.
- Persist failed generation stage checkpoints, support resuming, and expose actual per-stage progress in the editor.
- Complete runtime behavior for all declared item components (including energy/container capacity and item-granted effects/requirements), all object capabilities, and creature AI profiles. Some declarations currently validate/store metadata without a complete runtime/UI path.
- Complete generic equipment handling in the starting shop UI (runtime handles custom slot profiles, but its conflict preview still contains legacy hand IDs).
- Integrate background contacts/knowledge/reputation fully into campaign creation and runtime presentation.
- Finish custom damage types in every power path and mode-specific firing mechanics beyond ammunition costs.
- Audit generated-world context size, semantic cross-references and all declarative effects against the complete specification.
- Add one new-setting end-to-end scenario including checks, template-based combat, loot and an actual server restart; the current new-setting scenario stops after game/browser reload. Legacy gameplay tests cover combat/restart separately.
- Run real LLM smoke tests for at least three unrelated user-created universes. No provider credentials or running local model were available in this environment.
- Complete visual review of the new authoring editor and comprehensive acceptance traceability.

No merge or deployment is part of this checkpoint.
