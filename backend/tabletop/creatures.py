"""Compile instance identity against its immutable, validated setting template."""

from .models import CharacterSheet, Attack
from .definitions import InventoryEntry
from .features import FeatureEngine


def build_creature(instance, setting):
    template = setting.content.creatures[instance.template_id]
    actor = CharacterSheet(
        id=instance.id,
        name=instance.name,
        template_id=template.id,
        character_class="",
        species=template.id,
        abilities=template.attributes.copy(),
        hp=template.base_hp if instance.current_hp is None else instance.current_hp,
        max_hp=template.base_hp,
        armor_class=template.base_armor,
        speed=template.movement,
        faction=instance.faction_id,
        location=instance.location_id,
        skill_proficiencies=template.skills,
        save_proficiencies=template.saves,
        conditions=instance.conditions,
        resources={
            rid: setting.content.resources[rid].initial for rid in template.resources
        },
        inventory=[
            InventoryEntry(item_id=id, quantity=n)
            for id, n in instance.inventory.items()
        ],
        knowledge=instance.knowledge,
        relationships=instance.relationships,
        attitude=instance.attitude,
        morale=instance.morale,
        features=template.features,
        damage_modifiers=template.damage_modifiers,
        attacks={
            attack.id: Attack(
                name=attack.name,
                ability=attack.ability,
                expression=attack.damage_expression,
                damage_type=attack.damage_type,
                accuracy=attack.accuracy,
                reach=attack.range,
            )
            for attack in template.attacks
        },
    )
    FeatureEngine.apply_passives(
        actor, [setting.content.features[fid] for fid in template.features]
    )
    actor.resources.update(instance.resources)
    return actor
