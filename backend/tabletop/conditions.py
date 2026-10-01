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
    resistance: bool = False
    expires: Literal["none", "turn_start", "attack", "encounter"] = "none"


def default_conditions():
    data = [
        dict(
            id="dodge",
            name="Уклонение",
            incoming_attack=-1,
            saves={"dexterity": 1},
            expires="turn_start",
        ),
        dict(id="helped", name="Помощь союзника", attack=1, expires="attack"),
        dict(
            id="hidden",
            name="Скрытность",
            attack=1,
            incoming_attack=-1,
            expires="attack",
        ),
        dict(id="poisoned", name="Отравление", attack=-1, checks=-1),
        dict(id="frightened", name="Испуг", attack=-1, checks=-1),
        dict(
            id="restrained",
            name="Опутан",
            speed_multiplier=0,
            attack=-1,
            incoming_attack=1,
            saves={"dexterity": -1},
        ),
        dict(id="grappled", name="Захват", speed_multiplier=0),
        dict(id="prone", name="Сбит с ног", speed_multiplier=0.5, attack=-1),
        dict(
            id="stunned",
            name="Оглушение",
            blocks_action=True,
            speed_multiplier=0,
            incoming_attack=1,
            saves={"strength": -1, "dexterity": -1},
        ),
        dict(
            id="unconscious",
            name="Без сознания",
            blocks_action=True,
            speed_multiplier=0,
            incoming_attack=1,
        ),
        dict(id="dead", name="Погиб", blocks_action=True, speed_multiplier=0),
        dict(id="fled", name="Покинул бой", blocks_action=True),
        dict(id="surrendered", name="Сдался", blocks_action=True, expires="encounter"),
        dict(
            id="rage",
            name="Ярость",
            damage_bonus=2,
            resistance=True,
            expires="encounter",
        ),
        dict(id="focused", name="Прицельная атака", attack=1, expires="attack"),
        dict(id="guard", name="Защитная реакция", expires="turn_start"),
        dict(id="stable", name="Стабилизирован"),
    ]
    return {x["id"]: ConditionDefinition(**x) for x in data}


class ConditionEngine:
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
    def advantage(cls, actor, rules, purpose, target=None, ability="", distance=5):
        sources = []
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
