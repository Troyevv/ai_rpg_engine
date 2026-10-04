"""Compile adventure intent into the existing campaign/runtime contracts."""

from .semantic import SemanticCampaignDTO
from .procedural_content import (
    stable_id,
    pick,
    PRIMARY,
    ABILITIES,
    BalanceEngine,
    VERSION,
    diagnostic,
)
from .content_registry import setting_rules, SettingValidator
from .definitions import (
    CampaignDefinition,
    PlayerPlaceholder,
    CharacterBuild,
    CharacterDefinition,
    Region,
    Location,
    Faction,
    FactionRelation,
    Secret,
    Quest,
    SceneCheck,
    CheckEffect,
    WorldObject,
    InventoryEntry,
    Setting,
)
from .rules import RulesEngine
from .compiler import CampaignCompiler

DIFFICULTY = {"low": "EASY", "medium": "MEDIUM", "high": "HARD"}


class NPCBuildFactory:
    def build(self, concept, setting, diagnostics, seed=0):
        rules = setting_rules(setting)
        cls = pick(setting.content.archetypes, concept.profession, diagnostics)
        if not concept.profession:
            cls = min(
                rules.classes,
                key=lambda k: (
                    PRIMARY[concept.role] not in rules.classes[k]["primary_abilities"],
                    k,
                ),
            )
        from .generation_config import GeneratorContext

        random = GeneratorContext(seed)
        entry = rules.classes[cls]
        order = list(
            dict.fromkeys(
                entry.get("primary_abilities", [])
                + [PRIMARY[concept.role], "constitution"]
                + random.order(ABILITIES, concept.name)
            )
        )
        abilities = dict(zip(order, sorted(rules.ability_array, reverse=True)))
        build = CharacterBuild(
            name=concept.name,
            character_class=cls,
            species=pick(setting.content.species, concept.species, diagnostics),
            background=pick(
                setting.content.backgrounds, concept.background, diagnostics
            ),
            abilities=abilities,
            skills=random.order(entry["skills"], concept.name + "skills")[
                : entry["skill_count"]
            ],
            equipment=(entry.get("equipment_choices") or [entry["equipment"]])[0],
            feature_choices=entry.get("feature_choices", [])[
                : entry.get("feature_choice_count", 0)
            ],
            personality=concept.personality[:1000],
            concept=concept.description,
        )
        casting = rules.spellcasting.get(cls)
        if casting:
            build.spells = casting.defaults[: casting.known]
            build.prepared_spells = [
                p for p in build.spells if rules.spells[p].level > 0
            ][: casting.prepared]
        return RulesEngine().validate_build(build, rules)


class LootBuilder:
    def build(self, intents, setting, diagnostics, difficulty="MEDIUM"):
        result = {}
        cap = BalanceEngine.loot_budget(difficulty)
        remaining = cap
        for intent in intents:
            candidates = {
                k: v
                for k, v in setting.content.items.items()
                if v.category == intent.category and v.value <= remaining
            }
            if not candidates:
                diagnostics.append(
                    diagnostic(
                        "loot_unavailable",
                        intent.purpose,
                        "Нет предмета нужной категории в бюджете; добыча не добавлена.",
                    )
                )
                continue
            key = pick(candidates, intent.item, diagnostics)
            result[key] = result.get(key, 0) + 1
            remaining -= candidates[key].value
        return [
            InventoryEntry(item_id=k, quantity=n) for k, n in sorted(result.items())
        ]


class ObjectBuilder:
    def build(self, v, setting, diagnostics, difficulty):
        c = setting.content
        skill = pick(c.skills, v.expertise, diagnostics)
        mapping = {
            "openable": "interactable",
            "lockable": "lockable",
            "destructible": "breakable",
            "hackable": "terminal",
            "flammable": "hazard",
            "explosive": "trap",
            "activatable": "interactable",
            "container": "container",
            "cover": "cover",
        }
        kinds = list(dict.fromkeys(mapping[k] for k in v.capabilities))
        if v.loot and "container" not in kinds:
            kinds.append("container")
        components = []
        for kind in kinds:
            comp = dict(type=kind)
            if kind == "container":
                comp["capacity"] = 10
            if kind == "breakable":
                comp.update(hit_points=10, defence=12)
            if kind in ("hazard", "trap"):
                comp.update(
                    damage_expression="1d4",
                    damage_type=next(iter(c.damage_types), "physical"),
                )
            components.append(comp)
        return WorldObject(
            id=stable_id("object", v.name),
            name=v.name,
            description=v.description,
            location_id=stable_id("location", v.location),
            components=components,
            hidden=v.hidden,
            locked="lockable" in v.capabilities,
            difficulty=DIFFICULTY[v.difficulty],
            dc=BalanceEngine.dc[v.difficulty],
            check_skill=skill,
            check_ability=c.skills[skill].default_ability,
            contents=LootBuilder().build(v.loot, setting, diagnostics, difficulty),
            secrets=[stable_id("secret", n) for n in v.secrets],
        )


class CheckBuilder:
    def build(self, v, setting, difficulty):
        skill = pick(setting.content.skills, v.expertise)
        # Difficulty labels resolve to the fixed core DC table at runtime.
        bands = ["EASY", "MEDIUM", "HARD"]
        n = min(
            2,
            max(
                0,
                BalanceEngine.tier[v.difficulty]
                + (
                    1
                    if difficulty in ("VERY_HARD", "EXTREME")
                    else -1
                    if difficulty == "TRIVIAL"
                    else 0
                ),
            ),
        )
        return SceneCheck(
            id=stable_id("check", v.name),
            name=v.name,
            description=v.description,
            location_id=stable_id("location", v.location),
            category="exploration",
            skill=skill,
            ability=setting.content.skills[skill].default_ability,
            difficulty=bands[n],
            success=[
                CheckEffect(type="reveal_secret", target=stable_id("secret", v.reveals))
            ],
        )


class SemanticCampaignCompiler:
    def compile(self, id, value, setting, options):
        from .campaign_generation import EncounterBuilder, EncounterRequest

        dto = SemanticCampaignDTO.model_validate(
            value.model_dump() if isinstance(value, SemanticCampaignDTO) else value
        )
        from .generation_coverage import campaign_coverage

        source = dto.model_dump()
        config = options.generation
        setting = SettingValidator().validate(setting)
        dto = campaign_coverage(dto, setting, config)
        rules = setting_rules(setting)
        diagnostics = []
        location = stable_id("location", dto.starting_location)
        faction = stable_id("faction", dto.factions[0].name)
        chars = []
        for v in dto.npcs:
            chars.append(
                CharacterDefinition(
                    id=stable_id("npc", v.name),
                    name=v.name,
                    description=v.description,
                    location_id=stable_id("location", v.location),
                    faction_id=stable_id("faction", v.faction),
                    build=NPCBuildFactory().build(v, setting, diagnostics, config.seed),
                    goals=[v.motivation] if v.motivation else [],
                    personality=v.personality[:1500],
                    attitude=v.attitude,
                    knowledge=[stable_id("secret", n) for n in v.knowledge],
                    relationships={
                        stable_id("npc", n): {
                            "friendly": 25,
                            "neutral": 0,
                            "hostile": -25,
                        }[a]
                        for n, a in v.relationships.items()
                    },
                )
            )
        companions = [a for a, v in zip(chars, dto.npcs) if v.companion][
            : options.party_size - 1
        ]
        for a in companions:
            a.location_id = location
        # Compiler fills unclaimed AI party slots from legal setting roles, never the player's slot.
        from .semantic import SemanticNPC

        for n in range(len(companions), options.party_size - 1):
            concept = SemanticNPC(
                name=f"Спутник {n + 1}",
                location=dto.starting_location,
                faction=dto.factions[0].name,
                role="support",
            )
            actor = CharacterDefinition(
                id=f"companion_{n + 1}",
                name=concept.name,
                location_id=location,
                faction_id=faction,
                build=NPCBuildFactory().build(
                    concept, setting, diagnostics, config.seed
                ),
            )
            chars.append(actor)
            companions.append(actor)
            diagnostics.append(
                diagnostic(
                    "companion_fallback",
                    actor.name,
                    "Свободный слот спутника заполнен допустимым AI-персонажем.",
                )
            )
        encounters, instances = [], []
        for v in dto.encounters:
            candidates = [
                k
                for k, c in setting.content.creatures.items()
                if not v.creatures or c.name in v.creatures
            ]
            if not candidates:
                candidates = list(setting.content.creatures)
            if not candidates:
                diagnostics.append(
                    diagnostic(
                        "narrative_only",
                        v.name,
                        "В мире нет шаблонов существ; столкновение сохранено как сюжетная возможность.",
                    )
                )
                continue
            request = EncounterRequest(
                id=stable_id("encounter", v.name),
                name=v.name,
                description=v.description,
                location_id=stable_id("location", v.location),
                faction_id=stable_id("faction", v.faction),
                available_creatures=candidates,
                difficulty=DIFFICULTY[v.difficulty],
            )
            # Both local danger and the user-selected campaign difficulty affect budget.
            request.environment_modifier = {
                "TRIVIAL": 2,
                "EASY": 1.5,
                "MEDIUM": 1,
                "HARD": 0.8,
                "VERY_HARD": 0.6,
                "EXTREME": 0.5,
            }[options.difficulty]
            from .validation import CampaignValidationError

            try:
                encounter, actors = EncounterBuilder().build(
                    request,
                    setting,
                    options.party_size,
                    config.party_level,
                    seed=config.seed,
                )
            except CampaignValidationError as exc:
                if not all(i.code == "encounter_budget_exceeded" for i in exc.issues):
                    raise
                diagnostics.append(
                    diagnostic(
                        "balance_warning",
                        v.name,
                        "Существа превышают бюджет; сцена оставлена потенциальной угрозой без обязательного боя.",
                    )
                )
                continue
            encounters.append(encounter)
            instances.extend(actors)
        relations = {}
        for v in dto.factions:
            for kind, names in [("ALLY", v.allies), ("HOSTILE", v.enemies)]:
                for name in names:
                    pair = tuple(
                        sorted(
                            (stable_id("faction", v.name), stable_id("faction", name))
                        )
                    )
                    if pair in relations and relations[pair] != kind:
                        diagnostics.append(
                            diagnostic(
                                "relationship_fallback",
                                v.name,
                                "Противоречивые отношения фракций сведены к HOSTILE.",
                            )
                        )
                        kind = "HOSTILE"
                    relations[pair] = kind
        d = CampaignDefinition(
            id=id,
            name=options.title or dto.name,
            ruleset_id=rules.id,
            ruleset_version=rules.version,
            setting_definition=setting,
            setting=Setting(
                id=setting.id,
                name=setting.name,
                description=setting.description,
                genre=setting.genre,
                tone=setting.tone,
                technology=setting.technology_description,
                magic=setting.supernatural_description,
            ),
            regions=[Region(id="region_main", name=dto.name)],
            locations=[
                Location(
                    id=stable_id("location", v.name),
                    name=v.name,
                    description=v.description,
                    region_id="region_main",
                    environment_tags=v.environment,
                    danger_profile=v.danger,
                    mood=v.mood,
                    connections=[stable_id("location", n) for n in v.connections],
                )
                for v in dto.locations
            ],
            factions=[
                Faction(
                    id=stable_id("faction", v.name),
                    name=v.name,
                    description=v.description,
                    public_goal="; ".join(v.goals)[:1000],
                )
                for v in dto.factions
            ],
            faction_relations=[
                FactionRelation(first=a, second=b, relation=r)
                for (a, b), r in sorted(relations.items())
            ],
            characters=chars,
            starting_party=[a.id for a in companions],
            creature_instances=instances,
            objects=[
                ObjectBuilder().build(v, setting, diagnostics, options.difficulty)
                for v in dto.objects
            ],
            secrets=[
                Secret(
                    id=stable_id("secret", v.name),
                    name=v.name,
                    description=v.description,
                    location_id=stable_id("location", v.location),
                    disclosure=v.disclosure,
                )
                for v in dto.secrets
            ],
            quests=[
                Quest(
                    id=stable_id("quest", v.name),
                    name=v.name,
                    description=v.description,
                    location_id=stable_id("location", v.location),
                    giver_id=stable_id("npc", v.giver) if v.giver else None,
                    goals=v.goals,
                    clues=v.clues,
                    prerequisites=[stable_id("quest", n) for n in v.dependencies],
                    possible_resolutions=v.possible_outcomes,
                    consequences=v.consequences,
                    reward=LootBuilder().build(
                        v.reward, setting, diagnostics, options.difficulty
                    ),
                )
                for v in dto.quests
            ],
            checks=[
                CheckBuilder().build(v, setting, options.difficulty) for v in dto.checks
            ],
            encounters=encounters,
            initial_conflict=dto.premise,
            plot_hooks=dto.player_hooks,
            starting_location=location,
            starting_scene=dto.starting_situation,
            player_slot=PlayerPlaceholder(
                starting_location=location,
                faction_id=faction,
                hooks=dto.player_hooks,
                compatibility=dto.compatibility,
            ),
            generation_metadata={
                "compiler_version": VERSION,
                "setting_revision": str(setting.revision),
            },
            semantic_source=source,
            generation_config=config,
            diagnostics=diagnostics,
        )
        d.entity_generation_metadata = {
            entry.id: dict(
                generated_by=group,
                generator_version=VERSION,
                seed=config.seed,
                template=group,
                balance_tier=options.difficulty,
            )
            for group in (
                "locations",
                "characters",
                "creature_instances",
                "quests",
                "objects",
                "checks",
                "encounters",
            )
            for entry in getattr(d, group)
        }
        return CampaignCompiler().validate(d)
