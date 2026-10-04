"""Code-owned generation scale and reproducible, per-entity random streams."""

import hashlib
import random
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model

WORLD_PROFILES = {
    "SMALL": dict(
        professions=4,
        backgrounds=4,
        skills=6,
        weapons=6,
        armor=3,
        medical=3,
        utility=4,
        creatures=6,
    ),
    "NORMAL": dict(
        professions=6,
        backgrounds=6,
        skills=10,
        weapons=9,
        armor=6,
        medical=4,
        utility=6,
        creatures=12,
    ),
    "LARGE": dict(
        professions=10,
        backgrounds=10,
        skills=16,
        weapons=15,
        armor=9,
        medical=6,
        utility=10,
        creatures=20,
    ),
}
CAMPAIGN_PROFILES = {
    "SHORT": dict(locations=3, npcs=3, quests=2, encounters=2, secrets=3, objects=3),
    "NORMAL": dict(locations=6, npcs=6, quests=4, encounters=4, secrets=6, objects=6),
    "LONG": dict(locations=10, npcs=10, quests=8, encounters=8, secrets=10, objects=12),
}


class GenerationConfig(Model):
    seed: int = Field(default=0, ge=0, le=2**63 - 1)
    profile: Literal["SMALL", "NORMAL", "LARGE"] = "NORMAL"
    economy: Literal["scarce", "standard", "abundant"] = "standard"
    counts: dict[str, int] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def bounds(self):
        if not set(self.counts) <= set(WORLD_PROFILES["NORMAL"]):
            raise ValueError("Unknown generation count")
        maxima = dict(
            professions=10,
            backgrounds=10,
            skills=20,
            weapons=18,
            armor=9,
            medical=6,
            utility=10,
            creatures=20,
        )
        if any(
            n < WORLD_PROFILES["SMALL"][k] or n > maxima[k]
            for k, n in self.counts.items()
        ):
            raise ValueError("Count outside playable coverage range")
        return self

    @property
    def targets(self):
        return {**WORLD_PROFILES[self.profile], **self.counts}


class CampaignGenerationConfig(Model):
    seed: int = Field(default=0, ge=0, le=2**63 - 1)
    profile: Literal["SHORT", "NORMAL", "LONG"] = "NORMAL"
    party_level: int = Field(default=1, ge=1, le=20)

    @property
    def targets(self):
        return CAMPAIGN_PROFILES[self.profile]


class GeneratorContext:
    def __init__(self, seed):
        self.seed = seed

    def rng(self, kind, name):
        digest = hashlib.sha256(f"{self.seed}:{kind}:{name}".encode()).digest()
        return random.Random(int.from_bytes(digest, "big"))

    def order(self, values, kind):
        return sorted(values, key=lambda v: self.rng(kind, str(v)).random())
