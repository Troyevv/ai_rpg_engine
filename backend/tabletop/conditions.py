"""Central catalog of mechanical conditions and explainable d20 modifiers."""

from typing import Literal
from pydantic import Field
from .definitions import Model


class ConditionDefinition(Model):
    id: str
    name: str
    blocks_action: bool = False
    speed_multiplier: float = Field(default=1, ge=0, le=2)
    attack: Literal[-1, 0, 1] = 0
    incoming_attack: Literal[-1, 0, 1] = 0
    checks: Literal[-1, 0, 1] = 0
    saves: dict[str, Literal[-1, 0, 1]] = {}
    damage_bonus: int = 0
    attack_bonus: int = 0
    save_bonus: int = 0
    resistance: bool = False
    expires: Literal["none", "turn_start", "attack", "encounter"] = "none"


def default_conditions():
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).with_name("catalog") / "shared" / "conditions.json").read_text()
    )
    return {
        key: ConditionDefinition.model_validate(value) for key, value in data.items()
    }


class ConditionEngine:
    @staticmethod
    def bonus(actor, field):
        definitions = default_conditions()
        return sum(
            getattr(definitions[c], field) for c in actor.conditions if c in definitions
        )

    @staticmethod
    def definitions(actor, rules):
        return [
            rules.condition_definitions[c]
            for c in actor.conditions
            if c in rules.condition_definitions
        ]

    @classmethod
    def blocked(cls, actor, rules):
        return any(c.blocks_action for c in cls.definitions(actor, rules))

    @classmethod
    def speed(cls, actor, rules):
        return int(
            actor.speed
            * min([1] + [c.speed_multiplier for c in cls.definitions(actor, rules)])
        )

    @classmethod
    def advantage(
        cls, actor, rules, purpose, target=None, ability="", distance=5, skill=""
    ):
        sources = []
        if skill == "stealth" and actor.equipment_bonuses.get("stealth_disadvantage"):
            sources.append({"name": "Тяжёлая броня", "value": -1})
        for c in cls.definitions(actor, rules):
            value = (
                c.attack
                if purpose == "attack"
                else c.saves.get(ability, 0) if purpose == "save" else c.checks
            )
            if value:
                sources.append({"name": c.name, "value": value})
        if purpose == "attack" and target:
            for c in cls.definitions(target, rules):
                value = (
                    (1 if distance <= 5 else -1)
                    if c.id == "prone"
                    else c.incoming_attack
                )
                if value:
                    sources.append({"name": f"Цель: {c.name}", "value": value})
        # Any advantage and any disadvantage cancel, irrespective of source count.
        values = {s["value"] for s in sources}
        return (0 if len(values) != 1 else next(iter(values))), sources

    @classmethod
    def expire(cls, actor, rules, boundary):
        actor.conditions = [
            c
            for c in actor.conditions
            if c not in rules.condition_definitions
            or rules.condition_definitions[c].expires != boundary
        ]
