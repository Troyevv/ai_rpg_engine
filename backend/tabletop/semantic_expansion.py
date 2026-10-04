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
    concept_key,
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

        def index(entries):
            result = {v.id: v.id for v in entries}
            # Compatibility aliases only when display names are unambiguous.
            for v in entries:
                if sum(x.name == v.name for x in entries) == 1:
                    result[v.name] = v.id
            return result

        places = index(after.definition.locations)
        factions = index(after.definition.factions)
        here = after.actor(after.session_state.controlled_actor).location
        region = next(l.region_id for l in after.definition.locations if l.id == here)
        operations = []
        for v in dto.locations:
            if concept_key(v) in places:
                raise ValueError("New location name already exists")
            places[concept_key(v)] = stable_id("location", concept_key(v))
            operations.append(
                CreateLocation(
                    type="CreateLocation",
                    value=Location(
                        id=places[concept_key(v)],
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
            links = v.connections or [here]
            for name in links:
                if name not in places:
                    raise ValueError("Unknown semantic location")
                operations.append(
                    ConnectLocations(
                        type="ConnectLocations",
                        first=places[concept_key(v)],
                        second=places[name],
                    )
                )
        for v in dto.npcs:
            if v.location not in places or (
                v.faction is not None and v.faction not in factions
            ):
                raise ValueError("Unknown NPC location/faction")
            if v.known_secrets or v.relationships:
                raise ValueError(
                    "New NPC cannot acquire existing hidden knowledge/relationships"
                )
            operations.append(
                CreateNPC(
                    type="CreateNPC",
                    value=CharacterDefinition(
                        id=stable_id("npc", concept_key(v)),
                        name=v.name,
                        description=v.description,
                        location_id=places[v.location],
                        faction_id=factions[v.faction] if v.faction else None,
                        public_lore=v.knowledge,
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


def expansion_semantics(blueprint, state, setting):
    """Attach local ideas to the current location; never ask the model for references."""
    from .semantic import (
        SemanticLocation,
        SemanticNPC,
        SemanticItem,
        SemanticCreature,
        SemanticObject,
    )

    here = state.actor(state.session_state.controlled_actor).location
    prefix = "expansion/" + str(len(state.definition.expansion_blueprints))

    def fields(v, kind, i):
        return dict(key=f"{prefix}/{kind}/{i}", name=v.name, description=v.description)

    locations = [
        SemanticLocation(**fields(v, "place", i), connections=[here])
        for i, v in enumerate(blueprint.locations)
    ]
    place = concept_key(locations[0]) if locations else here
    random = GeneratorContext(state.definition.generation_config.seed)
    classes = random.order(list(setting.content.archetypes), prefix)
    npcs = [
        SemanticNPC(
            **fields(v, "actor", i),
            location=place,
            profession=classes[i % len(classes)],
            knowledge=v.knowledge,
            motivation=v.motivation,
        )
        for i, v in enumerate(blueprint.actors)
    ]
    items = [
        SemanticItem(
            **fields(v, "item", i),
            category={"protection": "armor", "recovery": "medical"}.get(
                v.purpose, v.purpose
            ),
            style="melee" if v.medium == "contact" else "ranged",
            supply="ammunition"
            if v.medium == "projectile" and v.purpose == "weapon"
            else "none",
        )
        for i, v in enumerate(blueprint.equipment_families)
    ]
    creatures = [
        SemanticCreature(
            **fields(v, "threat", i), behavior=v.description, tags=[v.nature]
        )
        for i, v in enumerate(blueprint.threat_families)
        if v.nature != "phenomenon"
    ]
    objects = [
        SemanticObject(
            **fields(v, "object", i), location=place, capabilities=["openable"]
        )
        for i, v in enumerate(blueprint.objects)
    ]
    objects += [
        SemanticObject(
            **fields(v, "hazard", i), location=place, capabilities=["flammable"]
        )
        for i, v in enumerate(blueprint.threat_families)
        if v.nature == "phenomenon"
    ]
    return SemanticExpansionDTO(
        items=items,
        creatures=creatures,
        locations=locations,
        npcs=npcs,
        objects=objects,
    )


def expand(dm, gid, state, topic):
    from .blueprints import ExpansionBlueprint, world_context

    setting = campaign_setting(state.definition)
    here = next(
        l
        for l in state.definition.locations
        if l.id == state.actor(state.session_state.controlled_actor).location
    )
    context = {
        "request": topic,
        "world": world_context(setting),
        "current_location": {"name": here.name, "description": here.description[:2000]},
    }
    author = StagedAuthor(dm)
    blueprint = generate_semantic(
        author, gid, "content_blueprint", ExpansionBlueprint, context
    )

    def compile():
        after, result = LazyContentCompiler().compile(
            expansion_semantics(blueprint, state, setting), state
        )
        after.definition.expansion_blueprints[-1] = {
            "blueprint": blueprint.model_dump(),
            "compiler_version": VERSION,
        }
        return after, result

    return compile_stage(author, "content_compile", compile)
