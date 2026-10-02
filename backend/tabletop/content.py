"""Setting-owned content contracts. Settings cannot redefine attributes or turns."""

from typing import Annotated, Literal
from pydantic import Field, model_validator
from .contracts import Model, Named, Id, Ability
from .features import FeatureDefinition
from .spells import SpellDefinition, SpellcastingFeature
from .progression import LevelRule, SubclassDefinition


class SkillDefinition(Named):
    default_ability: Ability
    alternate_abilities: list[Ability] = []
    tags: list[str] = []


class DamageTypeDefinition(Named):
    tags: list[str] = []


class ResourceDefinition(Named):
    maximum: int = Field(ge=1, le=10000)
    initial: int = Field(default=0, ge=0, le=10000)
    recovery: Literal["none", "short", "long"] = "none"
    recovery_amount: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def bounds(self):
        if self.initial > self.maximum:
            raise ValueError("Resource initial exceeds maximum")
        return self


class ResourceCost(Model):
    resource_id: Id
    amount: int = Field(default=1, ge=1, le=10000)


class WeaponComponent(Model):
    type: Literal["weapon"] = "weapon"
    damage_expression: str
    damage_type: Id
    attack_ability: Ability = "strength"
    range: int = Field(default=5, ge=1, le=1000)
    hands: Literal[1, 2] = 1
    proficiency: str = "simple"
    properties: list[str] = []
    resource_usage: list[ResourceCost] = []
    features: list[Id] = []


class ArmorComponent(Model):
    type: Literal["armor"] = "armor"
    base: int = Field(default=10, ge=0, le=22)
    bonus: int = Field(default=0, ge=0, le=5)
    dex_cap: int = Field(default=5, ge=0, le=10)
    proficiency: str = "light"
    stealth_disadvantage: bool = False


class AmmoComponent(Model):
    type: Literal["ammo"] = "ammo"
    ammo_type: Id


class MagazineComponent(Model):
    type: Literal["magazine"] = "magazine"
    ammo_type: Id
    capacity: int = Field(ge=1, le=1000)
    initial: int = Field(default=0, ge=0, le=1000)
    modes: dict[
        Literal["single", "burst", "automatic"], Annotated[int, Field(ge=1, le=1000)]
    ] = {"single": 1}
    reload_cost: Literal["ACTION", "BONUS_ACTION"] = "ACTION"

    @model_validator(mode="after")
    def bounds(self):
        if self.initial > self.capacity or any(
            v > self.capacity for v in self.modes.values()
        ):
            raise ValueError("Magazine capacity exceeded")
        return self


class EnergyComponent(Model):
    type: Literal["energy"] = "energy"
    resource_id: Id
    capacity: int = Field(ge=1, le=10000)


class ToolComponent(Model):
    type: Literal["tool"] = "tool"
    skill_id: Id
    modifier: int = Field(default=1, ge=-5, le=5)
    requires_equipped: bool = True


class ConsumableComponent(Model):
    type: Literal["consumable", "medical"]
    fixed_healing: int = Field(default=0, ge=0, le=100)
    healing: str = ""
    feature_id: str = ""
    action_cost: Literal["ACTION", "BONUS_ACTION"] = "ACTION"


class ContainerComponent(Model):
    type: Literal["container"] = "container"
    capacity: int = Field(ge=1, le=1000)


class IdentityComponent(Model):
    armor_bonus: int = Field(default=0, ge=0, le=5)
    type: Literal["artifact", "key", "currency", "quest"]
    tags: list[str] = []
    feature_ids: list[Id] = []


ItemComponent = Annotated[
    WeaponComponent
    | ArmorComponent
    | AmmoComponent
    | MagazineComponent
    | EnergyComponent
    | ToolComponent
    | ConsumableComponent
    | ContainerComponent
    | IdentityComponent,
    Field(discriminator="type"),
]


class ContentItem(Named):
    category: str = ""
    tags: list[str] = []
    weight: float = Field(default=0, ge=0, le=1000)
    value: int = Field(default=0, ge=0, le=100000)
    equipment_slots: list[Id] = []
    components: list[ItemComponent] = Field(default_factory=list, max_length=20)
    effects: list[Id] = []
    starting_available: bool = True
    requirements: list[Id] = []

    @model_validator(mode="after")
    def unique_components(self):
        kinds = [c.type for c in self.components]
        if len(kinds) != len(set(kinds)):
            raise ValueError("Duplicate item component")
        if "magazine" in kinds and "weapon" not in kinds:
            raise ValueError("Magazine requires weapon")
        return self


class EquipmentSlot(Named):
    group: str = "accessory"
    position: Literal[
        "head", "neck", "body", "left", "right", "legs", "feet", "extra"
    ] = "extra"


class EquipmentProfile(Named):
    slots: list[EquipmentSlot]


class Archetype(Named):
    primary_abilities: list[Ability] = []
    hit_die: Literal[6, 8, 10, 12] = 8
    saves: list[Ability] = []
    skill_count: int = Field(default=2, ge=0, le=6)
    skills: list[Id] = []
    armor: list[str] = []
    weapons: list[str] = []
    features: list[Id] = []
    feature_choices: list[Id] = []
    feature_choice_count: int = Field(default=0, ge=0, le=6)
    equipment: list[Id] = []
    equipment_choices: list[list[Id]] = []
    starting_gold: int = Field(default=0, ge=0, le=10000)
    resources: list[Id] = []


class SpeciesDefinition(Named):
    speed: int = Field(default=30, ge=5, le=100)
    features: list[Id] = []
    equipment_profile: Id = "humanoid"


class BackgroundDefinition(Named):
    skills: list[Id] = []
    proficiencies: list[str] = []
    languages: list[str] = []
    tools: list[str] = []
    tags: list[str] = []
    hooks: list[str] = []
    knowledge: list[str] = []
    contacts: list[str] = []
    reputation: dict[str, int] = {}
    features: list[Id] = []
    equipment: list[Id] = []
    starting_gold: int = Field(default=0, ge=0, le=10000)
    resources: list[Id] = []


class CreatureAttack(Named):
    damage_expression: str = "1d6"
    damage_type: Id
    ability: Ability = "strength"
    accuracy: int = Field(default=2, ge=-5, le=15)
    range: int = Field(default=5, ge=1, le=1000)


class CreatureTemplate(Named):
    category: str = ""
    tags: list[str] = []
    attributes: dict[Ability, Annotated[int, Field(ge=1, le=30)]]
    base_hp: int = Field(ge=1, le=1000)
    base_armor: int = Field(default=10, ge=5, le=25)
    movement: int = Field(default=30, ge=0, le=150)
    skills: list[Id] = []
    saves: list[Ability] = []
    attacks: list[CreatureAttack] = Field(default_factory=list, max_length=10)
    features: list[Id] = []
    damage_modifiers: dict[Id, Annotated[float, Field(ge=0, le=3)]] = {}
    resources: list[Id] = []
    ai_profile: Literal["aggressive", "defensive", "support", "cautious"] = "aggressive"
    habitats: list[str] = []
    rarity: int = Field(default=1, ge=1, le=100)
    threat: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def six_attributes(self):
        if set(self.attributes) != {
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        }:
            raise ValueError("Creature requires six core attributes")
        return self


class CreatureInstance(Named):
    @property
    def controller(self):
        return "AI"

    @property
    def player_id(self):
        return None

    template_id: Id
    location_id: Id
    faction_id: Id
    current_hp: int | None = Field(default=None, ge=0, le=1000)
    conditions: list[str] = []
    resources: dict[Id, int] = {}
    inventory: dict[Id, Annotated[int, Field(ge=1, le=10000)]] = {}
    knowledge: list[Id] = []
    relationships: dict[Id, Annotated[int, Field(ge=-100, le=100)]] = {}
    attitude: Literal["friendly", "neutral", "hostile"] = "neutral"
    morale: float = Field(default=0.5, ge=0, le=1)


class ContentRegistry(Model):
    skills: dict[Id, SkillDefinition] = {}
    species: dict[Id, SpeciesDefinition] = {}
    archetypes: dict[Id, Archetype] = {}
    backgrounds: dict[Id, BackgroundDefinition] = {}
    features: dict[Id, FeatureDefinition] = {}
    powers: dict[Id, SpellDefinition] = {}
    spellcasting: dict[Id, SpellcastingFeature] = {}
    levels: dict[str, LevelRule] = {}
    subclasses: dict[Id, dict[Id, SubclassDefinition]] = {}
    feats: list[Id] = []
    creatures: dict[Id, CreatureTemplate] = {}
    items: dict[Id, ContentItem] = {}
    damage_types: dict[Id, DamageTypeDefinition] = {}
    resources: dict[Id, ResourceDefinition] = {}
    equipment_profiles: dict[Id, EquipmentProfile] = {}
    world_mechanics: dict[Id, FeatureDefinition] = {}


class SettingFoundation(Named):
    genre: str = ""
    tone: str = ""
    world_rules: list[str] = []
    themes: list[str] = []
    technology_description: str = ""
    supernatural_description: str = ""
    society_description: str = ""
    conflict_description: str = ""
    custom_lore: list[str] = []


class SettingDefinition(SettingFoundation):
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    archetype_label: str = "Профессия / роль"
    currency_label: str = "монеты"
    starting_currency: int = Field(default=150, ge=0, le=100000)
    content: ContentRegistry
