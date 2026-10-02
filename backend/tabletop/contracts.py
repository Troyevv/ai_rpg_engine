"""Shared strict authoring primitives, independent of state and content."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Ability = Literal[
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
]
Difficulty = Literal["TRIVIAL", "EASY", "MEDIUM", "HARD", "VERY_HARD", "EXTREME"]
ControllerType = Literal["PLAYER", "AI", "DM"]
Id = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Named(Model):
    id: Id
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
