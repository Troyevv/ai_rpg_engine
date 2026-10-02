"""Lossless source catalog import. The existing catalog is content, never an engine branch."""

from .content import (
    SettingDefinition,
    ContentRegistry,
    ContentItem,
    SkillDefinition,
    DamageTypeDefinition,
    ResourceDefinition,
    EquipmentProfile,
    EquipmentSlot,
    Archetype,
    SpeciesDefinition,
    BackgroundDefinition,
)
from .content_registry import SettingValidator


def import_catalog(rules):
    registry = ContentRegistry(
        skills={
            key: SkillDefinition(
                id=key,
                name=key,
                default_ability=value,
                tags={
                    "perception": ["PASSIVE_PERCEPTION"],
                    "insight": ["PASSIVE_INSIGHT"],
                }.get(key, []),
            )
            for key, value in rules.skills.items()
        },
        archetypes={
            key: Archetype(id=key, **value) for key, value in rules.classes.items()
        },
        species={
            key: SpeciesDefinition(id=key, **value)
            for key, value in rules.species.items()
        },
        backgrounds={
            key: BackgroundDefinition(id=key, **value)
            for key, value in rules.backgrounds.items()
        },
        features=rules.features,
        powers=rules.spells,
        spellcasting=rules.spellcasting,
        levels=rules.levels,
        subclasses=rules.subclasses,
        feats=rules.feats,
        damage_types={
            "physical": DamageTypeDefinition(id="physical", name="Физический")
        },
        equipment_profiles={
            "humanoid": EquipmentProfile(
                id="humanoid",
                name="Обычное телосложение",
                slots=[
                    EquipmentSlot(
                        id=key,
                        name=value,
                        position={
                            "HEAD": "head",
                            "NECK": "neck",
                            "TORSO": "body",
                            "MAIN_HAND": "left",
                            "OFF_HAND": "right",
                            "LEGS": "legs",
                            "FEET": "feet",
                        }.get(key, "extra"),
                    )
                    for key, value in rules.equipment_slots.items()
                ],
            )
        },
    )
    for feature in rules.features.values():
        if feature.resource:
            registry.resources[feature.resource] = ResourceDefinition(
                id=feature.resource,
                name=feature.resource,
                maximum=max(1, feature.uses),
                initial=feature.uses,
                recovery=feature.recharge,
                recovery_amount=feature.uses,
            )
        for effect in feature.effects:
            if effect.type == "resource":
                registry.resources[effect.key] = ResourceDefinition(
                    id=effect.key,
                    name=effect.key,
                    maximum=max(1, effect.value),
                    initial=max(0, effect.value),
                )
    for item in rules.items:
        components = []
        if item.type == "weapon":
            components.append(
                dict(
                    type="weapon",
                    damage_expression=f"1d{item.weapon_die}",
                    damage_type="physical",
                    attack_ability=item.weapon_ability,
                    range=item.reach,
                    hands=item.hands,
                    proficiency=item.weapon_category,
                    properties=item.properties,
                )
            )
        if item.type == "armor":
            components.append(
                dict(
                    type="armor",
                    base=item.armor_base,
                    bonus=item.ac_bonus,
                    dex_cap=item.dex_cap,
                    proficiency=item.armor_category,
                    stealth_disadvantage=item.stealth_disadvantage,
                )
            )
        if item.type == "consumable":
            components.append(dict(type="consumable", fixed_healing=item.healing))
        if item.type == "quest":
            components.append(dict(type="quest"))
        if item.ac_bonus and item.type != "armor":
            components.append(dict(type="artifact", armor_bonus=item.ac_bonus))
        registry.items[item.id] = ContentItem(
            id=item.id,
            name=item.name,
            description=item.description,
            category=item.type,
            weight=item.weight,
            value=item.value,
            equipment_slots=item.slots,
            components=components,
            effects=item.features,
        )
    return SettingValidator().validate(
        SettingDefinition(
            id=rules.id,
            name=rules.name,
            description="Импорт существующего каталога",
            starting_currency=rules.starting_gold,
            content=registry,
        )
    )
