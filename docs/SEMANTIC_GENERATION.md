# Procedural world and campaign generation

This iteration continues PR #33 (`codex/universal-tabletop-2`).

## Authority boundary

`SemanticSettingDTO` / `WorldBlueprint` and `SemanticCampaignDTO` / `CampaignBlueprint` contain bounded concepts, display-name links and narrative intent. They do not import executable models. The provider cannot select IDs, dice, Effect trees, exact modifiers, prices, build attributes, equipment IDs, or player identity.

`ProceduralContentCompiler` builds the existing `ContentRegistry` and `SettingDefinition`. `SemanticCampaignCompiler` builds the existing `CampaignDefinition`. Existing RulesEngine, DiceEngine and runtime execute their output. No new genre-specific engine or preset worlds are introduced.

- Setting generation: one semantic request, at most one semantic/schema repair, then deterministic compilation.
- Campaign generation: one semantic request using a compact setting catalog, at most one repair, then deterministic compilation.
- Compiler/reference/mechanical failures never return to the provider for repair.
- Valid semantic output is checkpointed before compilation. Resume after a compiler failure reuses that output; API jobs also retain the frozen source setting.
- Provider, schema, semantic, compiler and mechanical diagnostics are distinct. Unsupported abilities have an explicit narrative-only fallback.

## World compiler

Factories own weapons, armor, items (including medical supplies, tools, devices and ammunition), features/effects, resources and creatures. Species, skills, professions, backgrounds, conditions and initial advancement tables are assembled in the same compiler. Prepared-slot casting retains known spells, prepared spells, cantrips and slots; it does not become generic mana.

`GenerationConfig` is the server-owned scale policy. SMALL/NORMAL/LARGE supply minimum starting coverage. Species count follows the fiction; secondary concepts expand into named variants of authored families. Missing basic equipment categories get generic starter capabilities. This guarantees usable coverage, not the narrative diversity of separately authored concepts.

`EconomyGenerator` prices category, power, rarity, availability profile and seeded variation. Starting wealth covers class loadouts. `BalanceEngine` shares damage/DC/tier, encounter and loot budgets and checks starter weapon/armor/creature bounds. These are approximate starter budgets, not official CR or extensive playtest balance.

## Campaign compiler

`CampaignGenerationConfig` supplies SHORT/NORMAL/LONG coverage, seed and party-level encounter context. Location semantics carry environment, mood and danger without combat coordinates. NPC builds use legal registry choices and seeded secondary allocation. Encounter composition uses derived threat, party context, difficulty and a seeded candidate order. Objects receive supported capabilities; checks and loot are built from the registry.

New campaigns have a `PlayerPlaceholder` and no player CharacterBuild. Campaign validation accepts it; game compilation requires a valid user-selected build. Optional AI companion slots are filled independently. Legacy embedded-player campaigns still load.

Quest goals, clues, dependencies, possible resolutions and consequences are retained, with stable prerequisite references. They remain open situation descriptions: the existing runtime's quest-resolution operations are not expanded into a universal arbitrary-goal solver in this change. Dependencies are authoring metadata, not automatic narrative scripting.

## Lazy generation and persistence

`SemanticExpansionDTO` replaces raw `CampaignMutation` model output. New locations, NPCs, objects, items and creature templates pass through the same factories and validators. Mechanical additions live in `CampaignDefinition.content_overlay`; the original setting snapshot remains unchanged. Existing entities cannot be overwritten, old secrets cannot be assigned to newly generated objects/NPCs, and failed compilation leaves the original state untouched.

World/campaign snapshots persist original blueprints, config/seed, compiled content, compiler version and per-entity provenance. Lazy blueprints and overlay content also persist. Loading existing games does not rerun generation. Existing versioned setting rows, campaign serialization and legacy import remain the persistence boundary.

Random streams use SHA-256 of seed, category and entity context instead of Python's process-dependent hash. Identical blueprint/config/seed/compiler version reproduces mechanics. IDs use normalized concept names. Different seeds vary prices, creature health, secondary content and encounter selection within budgets.

## Verification (2026-10-04)

- Final backend regression: **717 passed** (one dependency deprecation warning).
- Production frontend build and no-native-choice guard: passed.
- Added tests cover forbidden mechanical inputs, safe feature fallback, legal NPC casting/builds, same-seed reproducibility, different-seed variation, coverage, four unrelated thematic fixtures (including no-magic cyberpunk), immutable snapshots, compiler-failure resume, lazy overlay rollback/restart, ammunition/device components, and API world → campaign → creator validation → shop → game → restart.
- Generated encounters enter the existing combat runtime in integration tests.
- Browser E2E could not execute: no Chromium was installed; the download returned a truncated archive. Updated semantic browser fixtures are committed, but this is not a browser acceptance pass.
- No `CombatMapGenerator`/`generateCombatMap` implementation was found in the current tabletop sources. Its separate integration contract is therefore **not verified**; location/encounter semantics are retained for that boundary. The renderer was not modified.
- No configured provider credentials were found in the execution environment. **Zero real-provider calls** were made. Creative output quality and provider schema compliance remain unverified.

## Remaining acceptance / limitations

The full requested DoD is not claimed complete: browser and real-provider acceptance and the separate combat-map contract remain outstanding. Procedural coverage uses bounded family variants, not unlimited original lore. Unsupported mechanics stay narrative-only with diagnostics. Starter spell generation is limited to supported damage/healing spell forms and levels 0–1; advancement preserves compatibility but does not invent a complete twenty-level spell catalog. Broad freeform quest resolution still uses the pre-existing runtime operations.
