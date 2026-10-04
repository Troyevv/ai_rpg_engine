"""Bounded model-facing intent, deliberately independent of executable domain models."""

from typing import Annotated, Literal
from pydantic import ConfigDict, Field, model_validator
from .contracts import Model

Text = Annotated[str, Field(max_length=2000)]
Name = Annotated[str, Field(min_length=1, max_length=120)]
Names = Annotated[list[Name], Field(max_length=20)]
Power = Literal["low", "medium", "high"]
Role = Literal[
    "minion",
    "skirmisher",
    "brute",
    "defender",
    "controller",
    "ranged",
    "caster",
    "boss",
    "support",
]
Affinity = Literal[
    "physical", "precision", "endurance", "reasoning", "awareness", "social"
]


class SemanticModel(Model):
    model_config = ConfigDict(extra="forbid", strict=True)


class Concept(SemanticModel):
    name: Name
    description: Text = ""
    tags: Names = []


class SemanticFeature(Concept):
    intent: Literal[
        "damage",
        "healing",
        "durability",
        "defense",
        "mobility",
        "expertise",
        "temporary_offensive_buff",
        "control",
        "unsupported",
    ] = "unsupported"
    power: Power = "low"
    trigger: Literal["active", "passive"] = "active"
    damage_concept: str = Field(default="", max_length=120)
    condition_concept: str = Field(default="", max_length=120)
    expertise: str = Field(default="", max_length=120)
    tradeoff: Literal["none", "reduced_defense"] = "none"


class SemanticSkill(Concept):
    affinity: Affinity = "reasoning"


class SemanticSpecies(Concept):
    size: Literal["small", "medium", "large"] = "medium"
    movement: Literal["slow", "normal", "fast"] = "normal"
    strengths: Names = []
    weaknesses: Names = []
    traits: list[SemanticFeature] = Field(default_factory=list, max_length=3)


class SemanticResource(Concept):
    model: Literal[
        "reserve",
        "charges",
        "ammunition",
        "battery",
        "stamina",
        "focus",
        "rage",
        "stability",
    ] = "reserve"
    recovery: Literal["consumable", "rest", "daily"] = "rest"
    abundance: Power = "medium"


class SemanticProfession(Concept):
    role: Role = "skirmisher"
    tactics: Text = ""
    strengths: Names = []
    weaknesses: Names = []
    expertise: Names = []
    equipment: Names = []
    power_source: Text = ""
    progression_identity: Text = ""
    resource: SemanticResource | None = None
    casting: Literal["none", "prepared_slots"] = "none"
    abilities: list[SemanticFeature] = Field(default_factory=list, max_length=4)


class SemanticBackground(Concept):
    expertise: Names = []
    contacts: Names = []
    knowledge: Names = []
    equipment: Names = []


class SemanticItem(Concept):
    category: Literal[
        "weapon",
        "armor",
        "medical",
        "tool",
        "artifact",
        "key",
        "currency",
        "quest",
        "container",
        "ammo",
        "device",
    ]
    purpose: Text = ""
    usage: Text = ""
    supply: Literal["none", "ammunition"] = "none"
    supply_concept: str = Field(default="", max_length=120)
    rarity: Literal["common", "uncommon", "rare"] = "common"
    power: Power = "low"
    weight: Literal["light", "medium", "heavy"] = "medium"
    style: Literal["melee", "ranged"] = "melee"
    speed: Literal["fast", "normal", "slow"] = "normal"
    hands: Literal["one", "two"] = "one"
    approach: Literal["precision", "power"] = "power"
    reach: Literal["close", "near", "far"] = "near"
    damage_concept: str = Field(default="", max_length=120)
    expertise: str = Field(default="", max_length=120)
    protection: Power = "medium"
    mobility: Literal["restricted", "normal", "free"] = "normal"
    capabilities: list[SemanticFeature] = Field(default_factory=list, max_length=2)


class SemanticCreature(Concept):
    role: Role = "minion"
    threat: Power = "low"
    size: Literal["small", "medium", "large"] = "medium"
    behavior: Text = ""
    attack: Text = ""
    defense: Literal["fragile", "normal", "armored"] = "normal"
    damage_concept: str = Field(default="", max_length=120)
    habitats: Names = []
    resistances: Names = []
    weaknesses: Names = []
    abilities: list[SemanticFeature] = Field(default_factory=list, max_length=3)


class SemanticCondition(Concept):
    intent: Literal[
        "hindered", "disoriented", "exposed", "protected", "unsupported"
    ] = "unsupported"


class SemanticSettingDTO(Concept):
    genre: Text = ""
    tone: Text = ""
    themes: Names = []
    era: Text = ""
    technology: Text = ""
    supernatural: Text = ""
    cultures: list[Concept] = Field(default_factory=list, max_length=10)
    factions: list[Concept] = Field(default_factory=list, max_length=10)
    lore: list[Text] = Field(default_factory=list, max_length=20)
    species: list[SemanticSpecies] = Field(min_length=1, max_length=10)
    professions: list[SemanticProfession] = Field(min_length=1, max_length=10)
    backgrounds: list[SemanticBackground] = Field(min_length=1, max_length=10)
    skills: list[SemanticSkill] = Field(min_length=1, max_length=20)
    items: list[SemanticItem] = Field(default_factory=list, max_length=40)
    creatures: list[SemanticCreature] = Field(default_factory=list, max_length=20)
    damage_concepts: list[Concept] = Field(default_factory=list, max_length=12)
    conditions: list[SemanticCondition] = Field(default_factory=list, max_length=10)
    environments: list[Concept] = Field(default_factory=list, max_length=10)
    interactions: list[Concept] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def unique_names(self):
        for key in (
            "species",
            "professions",
            "backgrounds",
            "skills",
            "items",
            "creatures",
            "damage_concepts",
            "conditions",
        ):
            values = [v.name.casefold().strip() for v in getattr(self, key)]
            if len(set(values)) != len(values):
                raise ValueError("Duplicate semantic names: " + key)
        return self


class SemanticLocation(Concept):
    connections: Names = []
    environment: Names = []
    mood: Text = ""
    danger: Power = "low"


class SemanticFaction(Concept):
    goals: Names = []
    allies: Names = []
    enemies: Names = []


class SemanticNPC(Concept):
    location: Name
    faction: Name
    species: str = Field(default="", max_length=120)
    profession: str = Field(default="", max_length=120)
    background: str = Field(default="", max_length=120)
    role: Role = "support"
    personality: Text = ""
    motivation: Text = ""
    knowledge: Names = []
    relationships: dict[Name, Literal["friendly", "neutral", "hostile"]] = Field(
        default_factory=dict, max_length=20
    )
    equipment_intent: Text = ""
    importance: Literal["minor", "major", "central"] = "minor"
    companion: bool = False
    attitude: Literal["friendly", "neutral", "hostile"] = "neutral"


class SemanticSecret(Concept):
    location: Name
    disclosure: Literal["search", "persuasion", "never"] = "search"


class SemanticLoot(SemanticModel):
    purpose: Text = ""
    item: str = Field(default="", max_length=120)
    category: Literal[
        "weapon",
        "armor",
        "medical",
        "tool",
        "artifact",
        "key",
        "currency",
        "quest",
        "container",
        "ammo",
        "device",
    ] = "medical"
    value: Power = "low"


class SemanticObject(Concept):
    location: Name
    capabilities: list[
        Literal[
            "openable",
            "lockable",
            "destructible",
            "hackable",
            "flammable",
            "explosive",
            "activatable",
            "container",
            "cover",
        ]
    ] = Field(default_factory=list, max_length=9)
    hidden: bool = False
    difficulty: Power = "medium"
    expertise: str = Field(default="", max_length=120)
    secrets: Names = []
    loot: list[SemanticLoot] = Field(default_factory=list, max_length=5)


class SemanticQuest(Concept):
    location: Name
    giver: str = Field(default="", max_length=120)
    goals: Names = []
    conflicts: Names = []
    clues: Names = []
    dependencies: Names = []
    possible_outcomes: Names = []
    consequences: Names = []
    reward: list[SemanticLoot] = Field(default_factory=list, max_length=3)


class SemanticEncounter(Concept):
    location: Name
    faction: Name
    difficulty: Power = "medium"
    creatures: Names = []
    environment: Names = []


class SemanticCheck(Concept):
    location: Name
    expertise: str = Field(default="", max_length=120)
    difficulty: Power = "medium"
    reveals: Name


class SemanticCampaignDTO(Concept):
    premise: Text
    starting_situation: Annotated[str, Field(min_length=1, max_length=2000)]
    starting_location: Name
    player_hooks: Names = []
    compatibility: Names = []
    locations: list[SemanticLocation] = Field(min_length=1, max_length=20)
    factions: list[SemanticFaction] = Field(min_length=1, max_length=10)
    npcs: list[SemanticNPC] = Field(default_factory=list, max_length=30)
    secrets: list[SemanticSecret] = Field(default_factory=list, max_length=30)
    objects: list[SemanticObject] = Field(default_factory=list, max_length=30)
    quests: list[SemanticQuest] = Field(default_factory=list, max_length=15)
    encounters: list[SemanticEncounter] = Field(default_factory=list, max_length=10)
    checks: list[SemanticCheck] = Field(default_factory=list, max_length=15)
    developments: list[Text] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def references(self):
        groups = {
            k: {v.name for v in getattr(self, k)}
            for k in (
                "locations",
                "factions",
                "npcs",
                "secrets",
                "objects",
                "quests",
                "encounters",
                "checks",
            )
        }
        for k, names in groups.items():
            if len({name.strip().casefold() for name in names}) != len(
                getattr(self, k)
            ):
                raise ValueError("Duplicate semantic names: " + k)

        def ref(name, group):
            if name not in groups[group]:
                raise ValueError(f"Unknown {group} concept: {name}")

        ref(self.starting_location, "locations")
        for group in ("npcs", "secrets", "objects", "quests", "encounters", "checks"):
            for value in getattr(self, group):
                ref(value.location, "locations")
        for v in self.locations:
            for name in v.connections:
                ref(name, "locations")
        for v in self.npcs:
            ref(v.faction, "factions")
            for name in v.knowledge:
                ref(name, "secrets")
            for name in v.relationships:
                ref(name, "npcs")
        for v in self.factions:
            for name in v.allies + v.enemies:
                ref(name, "factions")
                if name == v.name or name in v.allies and name in v.enemies:
                    raise ValueError("Conflicting faction relationship")
        for v in self.objects:
            for name in v.secrets:
                ref(name, "secrets")
                if (
                    next(s.location for s in self.secrets if s.name == name)
                    != v.location
                ):
                    raise ValueError("Secret and object must share location")
        for v in self.quests:
            if v.giver:
                ref(v.giver, "npcs")
            for name in v.dependencies:
                ref(name, "quests")
        for v in self.encounters:
            ref(v.faction, "factions")
        for v in self.checks:
            ref(v.reveals, "secrets")
            secret = next(s for s in self.secrets if s.name == v.reveals)
            if secret.location != v.location or secret.disclosure == "never":
                raise ValueError("Challenge cannot reveal that secret")
        reached, todo = set(), [self.starting_location]
        while todo:
            name = todo.pop()
            if name not in reached:
                reached.add(name)
                todo.extend(
                    next(v.connections for v in self.locations if v.name == name)
                )
        if reached != groups["locations"]:
            raise ValueError("Locations must be reachable from starting location")
        return self


class SemanticExpansionDTO(SemanticModel):
    """New concepts only; existing entities are referenced by display name, never patched."""

    items: list[SemanticItem] = Field(default_factory=list, max_length=8)
    creatures: list[SemanticCreature] = Field(default_factory=list, max_length=4)
    locations: list[SemanticLocation] = Field(default_factory=list, max_length=4)
    npcs: list[SemanticNPC] = Field(default_factory=list, max_length=6)
    objects: list[SemanticObject] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def unique_new_concepts(self):
        for group in ("items", "creatures", "locations", "npcs", "objects"):
            entries = getattr(self, group)
            names = [v.name.strip().casefold() for v in entries]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate new concepts: " + group)
        return self


# Public architectural names; these are the same contracts, not parallel formats.
WorldBlueprint = SemanticSettingDTO
CampaignBlueprint = SemanticCampaignDTO
