"""Typed, catalog-owned effects. Player/LLM input can select IDs, never edit effects."""

from typing import Literal
from pydantic import Field
from .contracts import Model
from .context_actions import ActionRequirements


class FeatureEffect(Model):
    type: Literal[
        "damage",
        "remove_condition",
        "modify_check",
        "modify_attack",
        "modify_damage",
        "grant_advantage",
        "grant_disadvantage",
        "move",
        "push",
        "pull",
        "spend_resource",
        "restore_resource",
        "reveal_knowledge",
        "modify_relationship",
        "spawn_object",
        "interact",
        "heal_dice",
        "restore_slot",
        "unarmed_die",
        "unarmored_ability",
        "max_hp",
        "armor_class",
        "speed",
        "skill_proficiency",
        "resource",
        "check_bonus",
        "save_bonus",
        "attack_bonus",
        "damage_bonus",
        "heal",
        "condition",
        "dash",
        "disengage",
        "extra_attack",
    ]
    duration: int = Field(default=60, ge=1, le=86400)
    expression: str = ""
    add_level: bool = False
    value: int = Field(default=0, ge=-20, le=100)
    key: str = ""


class FeatureDefinition(Model):
    requirements: ActionRequirements = Field(default_factory=ActionRequirements)
    source: Literal[
        "CLASS", "SUBCLASS", "SPECIES", "BACKGROUND", "FEAT", "ITEM", "CONDITION"
    ] = "CLASS"
    id: str
    name: str
    level: int = Field(default=1, ge=1, le=20)
    description: str
    activation: Literal["PASSIVE", "ACTION", "BONUS_ACTION", "REACTION"] = "PASSIVE"
    resource_cost: dict[str, int] = {}
    area: int = Field(default=0, ge=0, le=60)
    resource: str = ""
    uses: int = Field(default=0, ge=0, le=20)
    recharge: Literal["short", "long", "none"] = "long"
    target: Literal["self", "ally", "enemy"] = "self"
    reach: int = Field(default=5, ge=0, le=120)
    effects: list[FeatureEffect]


class FeatureEngine:
    @staticmethod
    def apply_passives(actor, definitions):
        for feature in definitions:
            if feature.resource:
                actor.resources[feature.resource] = feature.uses
            if feature.activation != "PASSIVE":
                continue
            for effect in feature.effects:
                if effect.type == "max_hp":
                    actor.max_hp += effect.value
                    actor.hp += effect.value
                elif effect.type == "speed":
                    actor.speed += effect.value
                elif effect.type == "skill_proficiency":
                    if effect.key not in actor.skill_proficiencies:
                        actor.skill_proficiencies.append(effect.key)
                elif effect.type == "resource":
                    actor.resources[effect.key] = effect.value
                else:
                    key = effect.type + (":" + effect.key if effect.key else "")
                    actor.bonuses[key] = actor.bonuses.get(key, 0) + effect.value
