"""Expand authored concept families into bounded variants without new genre assumptions."""

from .semantic import SemanticItem, SemanticFeature, SemanticCreature
from .generation_config import GeneratorContext


def world_coverage(blueprint, config):
    dto = blueprint.model_copy(deep=True)
    targets = config.targets
    rng = GeneratorContext(config.seed)

    # Species count follows the fiction (a human-only world stays human-only).
    # Secondary content is variants of authored concepts, not a preset world.
    def grow(values, target, kind, change=None):
        originals = values[:]
        while len(values) < target and originals:
            index = len(values)
            source = originals[index % len(originals)]
            variant = source.model_copy(deep=True)
            variant.name = f"{source.name[:95]} · {index // len(originals) + 1}"
            if change:
                change(variant, rng.rng(kind, variant.name))
            values.append(variant)

    grow(dto.skills, targets["skills"], "skills")
    grow(dto.backgrounds, targets["backgrounds"], "backgrounds")
    grow(dto.professions, targets["professions"], "professions")
    for v in dto.professions:
        if not v.abilities:
            v.abilities = [
                SemanticFeature(
                    name=f"{v.name[:90]}: подготовка",
                    intent={
                        "defender": "defense",
                        "brute": "durability",
                        "skirmisher": "mobility",
                        "ranged": "expertise",
                        "caster": "damage",
                        "controller": "control",
                        "support": "healing",
                    }.get(v.role, "expertise"),
                )
            ]
    categories = {
        "weapons": "weapon",
        "armor": "armor",
        "medical": "medical",
        "utility": "tool",
    }
    items = []
    for group, category in categories.items():
        values = [v for v in dto.items if v.category == category]
        if not values:
            # Generic starter capabilities receive the world's terminology through the blueprint.
            names = {
                "weapon": "Базовое оружие",
                "armor": "Защитное снаряжение",
                "medical": "Средство восстановления",
                "tool": "Рабочий инструмент",
            }
            values = [
                SemanticItem(
                    name=names[category],
                    category=category,
                    description="Базовое снаряжение этого мира.",
                )
            ]

        def vary(v, r):
            v.power = r.choice(["low", "medium", "high"])
            if category == "armor":
                v.weight = r.choice(["light", "medium", "heavy"])

        grow(values, targets[group], group, vary)
        items.extend(values)
    items.extend(v for v in dto.items if v.category not in categories.values())
    dto.items = items
    if not dto.creatures:
        dto.creatures = [
            SemanticCreature(
                name=dto.species[0].name + " — противник",
                description=dto.species[0].description,
                role="minion",
            )
        ]

    def vary_creature(v, r):
        v.threat = r.choice(["low", "medium", "high"])
        v.defense = r.choice(["fragile", "normal", "armored"])

    grow(dto.creatures, targets["creatures"], "creatures", vary_creature)
    return dto


def campaign_coverage(blueprint, setting, config):
    from .semantic import (
        SemanticNPC,
        SemanticQuest,
        SemanticEncounter,
        SemanticSecret,
        SemanticObject,
        SemanticLoot,
    )

    dto = blueprint.model_copy(deep=True)
    context = GeneratorContext(config.seed)
    targets = config.targets
    original_locations = dto.locations[:]
    while len(dto.locations) < targets["locations"]:
        n = len(dto.locations)
        parent = original_locations[n % len(original_locations)]
        location = parent.model_copy(deep=True)
        location.name = f"{parent.name[:90]} · участок {n + 1}"
        location.connections = [parent.name]
        parent.connections.append(location.name)
        dto.locations.append(location)
    for group, model in [
        ("npcs", SemanticNPC),
        ("quests", SemanticQuest),
        ("encounters", SemanticEncounter),
        ("secrets", SemanticSecret),
        ("objects", SemanticObject),
    ]:
        values = getattr(dto, group)
        originals = values[:]
        while len(values) < targets[group]:
            n = len(values)
            location = context.rng(group, str(n)).choice(dto.locations)
            if originals:
                value = originals[n % len(originals)].model_copy(deep=True)
                value.name = f"{value.name[:90]} · {n + 1}"
                if group == "npcs":
                    value.companion = False
            else:
                name = (
                    {
                        "npcs": "Житель",
                        "quests": "Исследование",
                        "encounters": "Встреча",
                        "secrets": "Сведения",
                        "objects": "Тайник",
                    }[group]
                    + " · "
                    + str(n + 1)
                )
                fields = dict(name=name, location=location.name)
                if group in ("npcs", "encounters"):
                    fields["faction"] = dto.factions[0].name
                if group == "npcs":
                    fields["profession"] = list(setting.content.archetypes.values())[
                        n % len(setting.content.archetypes)
                    ].name
                if group == "quests":
                    fields["description"] = (
                        "Исследовать доступные возможности: " + location.description
                    )
                if group == "objects":
                    fields.update(
                        capabilities=["container"],
                        loot=[SemanticLoot(category="medical")],
                    )
                if group == "secrets":
                    fields["description"] = (
                        location.description or "Следы недавнего присутствия."
                    )
                value = model(**fields)
            values.append(value)
    return dto
