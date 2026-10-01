"""Declarative authoring contracts: no runtime HP, dice results or state patches."""

from typing import Annotated, Literal, Union
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


class InventoryEntry(Model):
    item_id: Id
    quantity: int = Field(default=1, ge=1, le=10000)
    equipped: bool = False


class ItemDefinition(Named):
    type: Literal["weapon", "armor", "consumable", "quest", "miscellaneous"] = (
        "miscellaneous"
    )
    weight: float = Field(default=0, ge=0, le=1000)
    value: int = Field(default=0, ge=0, le=100000)
    properties: list[str] = Field(default_factory=list, max_length=12)
    weapon_category: Literal["simple", "martial", "finesse"] = "simple"
    armor_category: Literal["light", "medium", "heavy", "shield"] = "light"
    weapon_die: Literal[4, 6, 8, 10, 12] = 6
    weapon_ability: Ability = "strength"
    reach: int = Field(default=5, ge=5, le=120)
    armor_base: int = Field(default=10, ge=10, le=18)
    dex_cap: int = Field(default=5, ge=0, le=5)
    healing: int = Field(default=0, ge=0, le=30)


class Region(Named):
    pass


class Location(Named):
    region_id: Id
    connections: list[Id] = Field(default_factory=list, max_length=50)
    travel_minutes: dict[Id, Annotated[int, Field(ge=1, le=1440)]] = {}


class Faction(Named):
    public_goal: str = Field(default="", max_length=1000)


class FactionRelation(Model):
    first: Id
    second: Id
    relation: Literal["ALLY", "NEUTRAL", "HOSTILE"]


class CharacterBuild(Model):
    name: str = Field(default="Искатель", min_length=1, max_length=120)
    species: str = "human"
    character_class: str = "fighter"
    background: str = "wanderer"
    ability_method: Literal["standard_array", "point_buy"] = "standard_array"
    spells: list[str] | None = Field(default=None, max_length=30)
    prepared_spells: list[str] | None = Field(default=None, max_length=30)
    concept: str = Field(default="", max_length=2000)
    feature_choices: list[str] = Field(default_factory=list, max_length=10)
    abilities: dict[Ability, int] = {
        "strength": 15,
        "dexterity": 13,
        "constitution": 14,
        "intelligence": 10,
        "wisdom": 12,
        "charisma": 8,
    }
    skills: list[str] = ["athletics", "perception"]
    equipment: list[str] = ["sword", "leather", "potion"]
    appearance: str = Field(default="", max_length=2000)
    biography: str = Field(default="", max_length=3000)
    personality: str = Field(default="", max_length=1000)
    ideals: str = Field(default="", max_length=1000)
    bonds: str = Field(default="", max_length=1000)
    flaws: str = Field(default="", max_length=1000)


class CharacterDefinition(Named):
    location_id: Id
    faction_id: Id
    build: CharacterBuild = Field(default_factory=CharacterBuild)
    controller: ControllerType = "AI"
    player_id: str | None = None
    goals: list[str] = Field(default_factory=list, max_length=10)
    personality: str = Field(default="", max_length=1500)
    attitude: Literal["friendly", "neutral", "hostile"] = "neutral"
    current_intent: str = Field(default="", max_length=1000)
    knowledge: list[Id] = Field(default_factory=list, max_length=30)
    public_lore: list[str] = Field(default_factory=list, max_length=20)
    relationships: dict[str, int] = Field(default_factory=dict, max_length=30)
    morale: float = Field(default=0.5, ge=0, le=1)
    position: int = Field(default=0, ge=-1000, le=1000)
    inventory: list[InventoryEntry] = Field(default_factory=list, max_length=30)


class Secret(Named):
    location_id: Id
    # Engine grants disclosure via search or an explicit, bounded social check.
    disclosure: Literal["search", "persuasion", "never"] = "search"
    difficulty: Difficulty = "MEDIUM"


class WorldObject(Named):
    location_id: Id
    hidden: bool = False
    locked: bool = False
    difficulty: Difficulty = "MEDIUM"
    dc: int | None = Field(default=None, ge=5, le=30)
    check_ability: Ability = "wisdom"
    check_skill: str = "perception"
    contents: list[InventoryEntry] = Field(default_factory=list, max_length=30)
    secrets: list[Id] = Field(default_factory=list, max_length=20)
    trap_damage: int = Field(default=0, ge=0, le=20)


class Quest(Named):
    giver_id: Id | None = None
    location_id: Id
    required_item: Id | None = None
    reward: list[InventoryEntry] = Field(default_factory=list, max_length=10)


class EncounterDefinition(Named):
    location_id: Id
    participants: list[Id] = Field(min_length=1, max_length=30)
    loot_object: Id | None = None
    quest_id: Id | None = None


class Setting(Named):
    genre: str = "Фэнтези"
    tone: str = "Приключение"
    technology: str = "Средневековье"
    magic: str = "Низкая"


class NPCSchedule(Named):
    actor_id: Id
    destination_id: Id
    delay_minutes: int = Field(ge=1, le=10080)
    after_quest: Id | None = None


class CampaignDefinition(Model):
    schema_version: Literal[1] = 1
    id: Id
    name: str = Field(min_length=1, max_length=120)
    ruleset_id: str = "d20-basic-v2"
    ruleset_version: Literal[2, 3] = 2
    setting: Setting
    regions: list[Region] = Field(min_length=1, max_length=30)
    locations: list[Location] = Field(min_length=1, max_length=150)
    factions: list[Faction] = Field(min_length=1, max_length=30)
    faction_relations: list[FactionRelation] = []
    characters: list[CharacterDefinition] = Field(min_length=1, max_length=100)
    creatures: list[CharacterDefinition] = []
    items: list[ItemDefinition] = Field(default_factory=list, max_length=150)
    objects: list[WorldObject] = Field(default_factory=list, max_length=200)
    quests: list[Quest] = Field(default_factory=list, max_length=50)
    secrets: list[Secret] = Field(default_factory=list, max_length=100)
    encounters: list[EncounterDefinition] = Field(default_factory=list, max_length=50)
    initial_conflict: str = Field(default="", max_length=3000)
    schedules: list[NPCSchedule] = Field(default_factory=list, max_length=100)
    plot_hooks: list[str] = Field(default_factory=list, max_length=20)
    starting_party: list[Id] = Field(min_length=1, max_length=6)
    starting_location: Id
    starting_scene: str = Field(min_length=1, max_length=5000)
    generation_metadata: dict[str, str] = Field(default_factory=dict, max_length=10)


# Each extension operation carries a whole, typed definition, never a field path.
class CreateLocation(Model):
    type: Literal["CreateLocation"]
    value: Location


class CreateNPC(Model):
    type: Literal["CreateNPC"]
    value: CharacterDefinition


class CreateItem(Model):
    type: Literal["CreateItem"]
    value: ItemDefinition


class CreateQuest(Model):
    type: Literal["CreateQuest"]
    value: Quest


class CreateEncounter(Model):
    type: Literal["CreateEncounter"]
    value: EncounterDefinition


class CreateObject(Model):
    type: Literal["CreateObject"]
    value: WorldObject


class CreateFaction(Model):
    type: Literal["CreateFaction"]
    value: Faction


class CreateRegion(Model):
    type: Literal["CreateRegion"]
    value: Region


class CreateSecret(Model):
    type: Literal["CreateSecret"]
    value: Secret


class CreateSchedule(Model):
    type: Literal["CreateSchedule"]
    value: NPCSchedule


class DefineFactionRelation(Model):
    type: Literal["DefineFactionRelation"]
    value: FactionRelation


class ConnectLocations(Model):
    type: Literal["ConnectLocations"]
    first: Id
    second: Id


class RevealKnowledge(Model):
    type: Literal["RevealKnowledge"]
    secret_id: Id
    source_id: Id


Operation = Annotated[
    Union[
        CreateLocation,
        CreateNPC,
        CreateItem,
        CreateQuest,
        CreateEncounter,
        CreateObject,
        CreateFaction,
        CreateRegion,
        CreateSecret,
        CreateSchedule,
        DefineFactionRelation,
        ConnectLocations,
        RevealKnowledge,
    ],
    Field(discriminator="type"),
]


class CampaignMutation(Model):
    operations: list[Operation] = Field(min_length=1, max_length=40)


class GenerationOptions(Model):
    idea: str = Field(min_length=3, max_length=6000)
    title: str = Field(default="", max_length=120)
    genre: str = Field(default="Фэнтези", max_length=120)
    setting: str = Field(default="", max_length=2000)
    tone: str = Field(default="Приключение", max_length=120)
    technology: str = Field(default="Средневековье", max_length=120)
    magic: str = Field(default="Низкая", max_length=120)
    scale: str = Field(default="Город и окрестности", max_length=120)
    adventure_type: str = Field(default="Исследование и расследование", max_length=120)
    difficulty: Difficulty = "MEDIUM"
    party_size: int = Field(default=1, ge=1, le=4)
    starting_situation: str = Field(default="", max_length=2000)
    wishes: str = Field(default="", max_length=3000)


class CharacterRoleplay(Model):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    appearance: str | None = Field(default=None, min_length=1, max_length=2000)
    biography: str | None = Field(default=None, min_length=1, max_length=3000)
    personality: str | None = Field(default=None, min_length=1, max_length=1000)
    ideals: str | None = Field(default=None, min_length=1, max_length=1000)
    bonds: str | None = Field(default=None, min_length=1, max_length=1000)
    flaws: str | None = Field(default=None, min_length=1, max_length=1000)
