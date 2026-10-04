"""Lazy generation uses the same factories and an atomic campaign content overlay."""

from .semantic import SemanticExpansionDTO
from .semantic_authoring import generate_semantic, compile_stage
from .setting_generation import StagedAuthor
from .content_registry import campaign_setting, campaign_rules, SettingValidator
from .procedural_content import (
    ItemFactory,
    CreatureFactory,
    EconomyGenerator,
    stable_id,
    VERSION,
)
from .semantic_campaign import NPCBuildFactory, ObjectBuilder
from .generation_config import GeneratorContext
from .definitions import (
    CampaignMutation,
    CreateLocation,
    ConnectLocations,
    CreateNPC,
    CreateObject,
    Location,
    CharacterDefinition,
)
from .compiler import CampaignCompiler
from .contracts import Model


class ExpansionResult(Model):
    operations: list = []
    registry_additions: list[str] = []


class LazyContentCompiler:
    def compile(self, dto, state):
        after = state.model_copy(deep=True)
        setting = campaign_setting(after.definition)
        old = setting.content.model_copy(deep=True)
        diagnostics = []
        seed = after.definition.generation_config.seed
        context = GeneratorContext(seed)
        for v in dto.items:
            item = ItemFactory.build(v, setting.content, diagnostics)
            if item.id in old.items:
                raise ValueError("New item name already exists")
            item.value = EconomyGenerator.price(
                v, setting.generation_config, context.rng("price", item.id)
            )
            setting.content.items[item.id] = item
        for v in dto.creatures:
            creature = CreatureFactory.build(v, setting.content, diagnostics)
            if creature.id in old.creatures:
                raise ValueError("New creature name already exists")
            creature.base_hp += context.rng("hp", creature.id).randint(0, 3)
            setting.content.creatures[creature.id] = creature
        setting = SettingValidator().validate(setting)
        additions = []
        for group in type(old).model_fields:
            values = getattr(setting.content, group)
            if not isinstance(values, dict):
                continue
            previous = getattr(old, group)
            for key, value in values.items():
                if key in previous:
                    if value != previous[key]:
                        raise ValueError("Lazy generation changed existing content")
                    continue
                getattr(after.definition.content_overlay, group)[key] = value
                additions.append(key)
                after.definition.entity_generation_metadata[key] = dict(
                    generated_by=group,
                    generator_version=VERSION,
                    seed=seed,
                    template=getattr(value, "category", group),
                    balance_tier="starter",
                )
        after.ruleset = campaign_rules(after.definition)
        after.items.update({v.id: v for v in after.ruleset.items})
        places = {v.name: v.id for v in after.definition.locations}
        factions = {v.name: v.id for v in after.definition.factions}
        here = after.actor(after.session_state.controlled_actor).location
        region = next(l.region_id for l in after.definition.locations if l.id == here)
        operations = []
        for v in dto.locations:
            if v.name in places:
                raise ValueError("New location name already exists")
            places[v.name] = stable_id("location", v.name)
            operations.append(
                CreateLocation(
                    type="CreateLocation",
                    value=Location(
                        id=places[v.name],
                        name=v.name,
                        description=v.description,
                        region_id=region,
                        environment_tags=v.environment,
                        danger_profile=v.danger,
                        mood=v.mood,
                    ),
                )
            )
        for v in dto.locations:
            links = v.connections or [
                next(l.name for l in after.definition.locations if l.id == here)
            ]
            for name in links:
                if name not in places:
                    raise ValueError("Unknown semantic location")
                operations.append(
                    ConnectLocations(
                        type="ConnectLocations",
                        first=places[v.name],
                        second=places[name],
                    )
                )
        for v in dto.npcs:
            if v.location not in places or v.faction not in factions:
                raise ValueError("Unknown NPC location/faction")
            if v.knowledge or v.relationships:
                raise ValueError(
                    "New NPC cannot acquire existing hidden knowledge/relationships"
                )
            operations.append(
                CreateNPC(
                    type="CreateNPC",
                    value=CharacterDefinition(
                        id=stable_id("npc", v.name),
                        name=v.name,
                        description=v.description,
                        location_id=places[v.location],
                        faction_id=factions[v.faction],
                        build=NPCBuildFactory().build(v, setting, diagnostics, seed),
                        personality=v.personality[:1500],
                        goals=[v.motivation] if v.motivation else [],
                        attitude=v.attitude,
                    ),
                )
            )
        for v in dto.objects:
            if v.location not in places or v.secrets:
                raise ValueError(
                    "New object cannot reference old secrets or missing location"
                )
            obj = ObjectBuilder().build(v, setting, diagnostics, "MEDIUM")
            obj.location_id = places[v.location]
            operations.append(CreateObject(type="CreateObject", value=obj))
        after.definition.expansion_blueprints.append(dto.model_dump())
        after.definition.diagnostics.extend(diagnostics)
        if operations:
            after = CampaignCompiler().extend(
                after, CampaignMutation(operations=operations)
            )
        else:
            CampaignCompiler().validate(after.definition)
        if not operations and not additions:
            raise ValueError("Expansion contains no new content")
        return after, ExpansionResult(
            operations=operations, registry_additions=additions
        )


def expand(dm, gid, state, topic):
    setting = campaign_setting(state.definition)
    context = {
        "request": topic,
        "world": {"name": setting.name, "description": setting.description},
        "current_location": next(
            l.name
            for l in state.definition.locations
            if l.id == state.actor(state.session_state.controlled_actor).location
        ),
        "locations": [l.name for l in state.definition.locations],
        "factions": [f.name for f in state.definition.factions],
        "catalog": {
            group: [v.name for v in getattr(setting.content, group).values()]
            for group in (
                "species",
                "archetypes",
                "backgrounds",
                "items",
                "skills",
                "damage_types",
            )
        },
    }
    author = StagedAuthor(dm)
    dto = generate_semantic(
        author, gid, "content_semantics", SemanticExpansionDTO, context
    )
    return compile_stage(
        author, "content_compile", lambda: LazyContentCompiler().compile(dto, state)
    )
