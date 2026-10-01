"""Trusted per-level rules; runtime accepts choices rather than stat patches."""

from pydantic import Field
from .definitions import Model


class LevelRule(Model):
    xp: int = Field(ge=0)
    proficiency: int = Field(ge=2, le=6)
    asi: bool = False
    subclass: bool = False
    features: dict[str, list[str]] = {}
    spell_slots: dict[str, dict[str, int]] = {}
    learn_spells: int = Field(default=0, ge=0, le=5)


class SubclassDefinition(Model):
    id: str
    name: str
    description: str
    features: list[str]
