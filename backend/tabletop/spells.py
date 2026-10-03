"""Trusted spell definitions and serializable casting state, independent of LLM prose."""

from typing import Literal
from pydantic import Field
from .contracts import Model, Ability


class SpellDefinition(Model):
    damage_type: str = ""
    resource_cost: dict[str, int] = {}
    id: str
    name: str
    level: int = Field(ge=0, le=9)
    school: str
    classes: list[str]
    casting_time: Literal["ACTION", "BONUS_ACTION"] = "ACTION"
    range: int = Field(default=60, ge=0, le=300)
    target_type: Literal["enemy", "ally", "self", "area"] = "enemy"
    area: int = Field(default=0, ge=0, le=60)
    duration: int = Field(default=0, ge=0, le=600)  # rounds
    concentration: bool = False
    components: list[Literal["V", "S", "M"]] = ["V", "S"]
    damage: str = ""
    healing: str = ""
    save: Ability | None = None
    attack_roll: bool = False
    half_on_save: bool = False
    effects: list[str] = []
    upcast: int = Field(default=0, ge=0, le=5)  # extra dice per slot level
    description: str


class SpellcastingFeature(Model):
    ability: Ability
    known: int = Field(default=4, ge=1, le=30)
    prepared: int = Field(default=2, ge=1, le=30)
    defaults: list[str]
    slots: dict[str, int]


class SpellSlotState(Model):
    maximum: int = Field(ge=0, le=20)
    remaining: int = Field(ge=0, le=20)


class ActiveConcentration(Model):
    spell_id: str
    targets: list[str]
    expires_at: int


class SpellCastState(Model):
    caster: str
    spell_id: str
    slot_level: int
    targets: list[str]
    index: int = 0
    saved: bool = False
    critical: bool = False
    stage: Literal["target", "effect"] = "target"
