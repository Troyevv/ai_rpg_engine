"""Canonical state v2. Definitions are compiled, never accepted as runtime patches."""

from typing import Literal
from .settings import DMSettings
from .commands import ChoiceOption
from .features import FeatureDefinition
from .progression import LevelRule, SubclassDefinition
from .spells import (
    SpellDefinition,
    SpellcastingFeature,
    SpellSlotState,
    ActiveConcentration,
    SpellCastState,
)
from .conditions import ConditionDefinition, default_conditions
from pydantic import Field, model_validator
from .definitions import (
    Model,
    Ability,
    Difficulty,
    ControllerType,
    CharacterBuild,
    CampaignDefinition,
    InventoryEntry,
    ItemDefinition,
    Setting,
)

ABILITIES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)


class Ruleset(Model):
    id: str
    name: str
    version: Literal[2, 3, 4] = 2
    capabilities: list[str]
    abilities: list[Ability]
    ability_array: list[int]
    allocation: dict[str, int] = {}
    starting_gold: int = Field(default=0, ge=0)
    equipment_slots: dict[str, str] = {}
    point_buy: dict[str, int | dict[str, int]] = {}
    features: dict[str, FeatureDefinition] = {}
    spells: dict[str, SpellDefinition] = {}
    spellcasting: dict[str, SpellcastingFeature] = {}
    condition_definitions: dict[str, ConditionDefinition] = Field(
        default_factory=default_conditions
    )
    skills: dict[str, Ability]
    difficulty: dict[Difficulty, int]
    check_die: Literal[20] = 20
    critical: Literal["double_dice", "max_dice"] = "double_dice"
    short_rest_minutes: int
    long_rest_minutes: int
    conditions: list[str]
    progression: dict[str, int]
    levels: dict[str, LevelRule] = {}
    subclasses: dict[str, dict[str, SubclassDefinition]] = {}
    feats: list[str] = []
    classes: dict[str, dict]
    species: dict[str, dict]
    backgrounds: dict[str, dict]
    items: list[ItemDefinition]


class Attack(Model):
    name: str
    ability: Ability = "strength"
    die: Literal[4, 6, 8, 10, 12] = 6
    proficient: bool = True
    reach: int = 5


class ActorControl(Model):
    actor_id: str
    controller: ControllerType
    player_id: str | None = None


class CharacterSheet(Model):
    gold: int = Field(default=0, ge=0)
    equipment_slots: dict[str, str] = {}
    languages: list[str] = []
    tool_proficiencies: list[str] = []
    background_tags: list[str] = []
    equipment_bonuses: dict[str, int] = {}
    id: str
    name: str
    level: int = Field(default=1, ge=1, le=20)
    xp: int = Field(default=0, ge=0)
    milestones: int = Field(default=0, ge=0)
    subclass: str = ""
    feats: list[str] = []
    proficiency_bonus: int = 2
    bonuses: dict[str, int] = {}
    proficiencies: list[str] = []
    campaign_hooks: list[str] = []
    concept: str = ""
    character_class: str
    species: str
    background: str = ""
    biography: str = ""
    appearance: str = ""
    personality: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""
    abilities: dict[Ability, int]
    skill_proficiencies: list[str] = []
    save_proficiencies: list[Ability] = []
    hp: int
    max_hp: int
    armor_class: int
    speed: int
    position: int = 0
    attacks: dict[str, Attack] = {}
    inventory: list[InventoryEntry] = []
    features: list[str] = []
    spells: list[str] = []
    prepared_spells: list[str] = []
    spell_slots: dict[str, SpellSlotState] = {}
    concentration: ActiveConcentration | None = None
    condition_expiry: dict[str, int] = {}
    resources: dict[str, int] = {}
    conditions: list[str] = []
    condition_sources: dict[str, str] = {}
    death_successes: int = 0
    death_failures: int = 0
    faction: str
    location: str
    goals: list[str] = []
    traits: list[str] = []
    knowledge: list[str] = []
    public_lore: list[str] = []
    relationships: dict[str, int] = {}
    attitude: str = "neutral"
    current_intent: str = ""
    morale: float = 0.5

    @model_validator(mode="after")
    def valid(self):
        if set(self.abilities) != set(ABILITIES) or not 0 <= self.hp <= self.max_hp:
            raise ValueError("Некорректный лист персонажа")
        return self


class Campaign(Model):
    progression_mode: Literal["xp", "milestone"] = "xp"
    source_draft: str = ""
    name: str
    setting_id: str
    starting_location: str


class Encounter(Model):
    definition_id: str = ""
    order: list[str] = []
    initiative: dict[str, int] = {}
    index: int = 0
    round: int = 1
    action: bool = True
    bonus_action: bool = True
    free_interaction: bool = True
    attacks_remaining: int = Field(default=0, ge=0)
    ready: dict[str, str] = {}
    reaction: dict[str, bool] = {}
    movement: int = 0
    disengaged: bool = False
    outcome: str = ""


class PendingRoll(Model):
    check_id: str = ""
    id: str
    reason: str = ""
    purpose: Literal[
        "check",
        "save",
        "initiative",
        "attack",
        "damage",
        "death",
        "spell_attack",
        "spell_save",
        "spell_damage",
        "spell_healing",
        "feature_healing",
        "concentration",
    ]
    actor: str
    controller: ControllerType = "PLAYER"
    player_id: str | None = "local"
    expression: str = "1d20"
    modifier: int = 0
    advantage: Literal[-1, 0, 1] = 0
    advantage_sources: list[dict[str, str | int]] = []
    dc: int = 10
    target: str = ""
    ability: Ability = "wisdom"
    skill: str = ""
    weapon: str = ""
    critical: bool = False
    outcome: Literal[
        "check",
        "search",
        "unlock",
        "persuade",
        "trap",
        "attack",
        "reaction",
        "hide",
        "grapple",
        "shove",
        "escape",
    ] = "check"
    resume: Literal["EXPLORATION", "DIALOGUE", "ENCOUNTER"] = "EXPLORATION"


class PendingChoice(Model):
    id: str
    actor: str
    player_id: str | None = "local"
    kind: Literal["action", "target"] = "action"
    prompt: str
    options: list[ChoiceOption] = Field(min_length=2, max_length=6)


class SessionState(Model):
    mode: Literal["EXPLORATION", "DIALOGUE", "ENCOUNTER", "AWAITING_ROLL"] = (
        "EXPLORATION"
    )
    controlled_actor: str
    pending: PendingRoll | None = None
    choice: PendingChoice | None = None
    spell_cast: SpellCastState | None = None
    concentration_checks: list[dict[str, str | int]] = []
    dialogue_actor: str | None = None
    initiative_waiting: list[str] = []
    initiative_results: dict[str, int] = {}
    encounter_definition: str = ""
    turn_started: bool = False
    reaction: dict | None = None

    @property
    def mechanical_resolution_complete(self):
        return not (
            self.pending
            or self.choice
            or self.reaction
            or self.initiative_waiting
            or self.spell_cast
            or self.concentration_checks
        )


class ObjectState(Model):
    revealed: bool = True
    opened: bool = False
    unlocked: bool = False
    trap_triggered: bool = False
    contents: list[InventoryEntry] = []


class GameState(Model):
    dm_settings: DMSettings = Field(default_factory=DMSettings)
    schema_version: Literal[2] = 2
    definition: CampaignDefinition
    campaign: Campaign
    ruleset: Ruleset
    world: Setting
    party: list[str]
    characters: dict[str, CharacterSheet]
    npcs: dict[str, CharacterSheet]
    controllers: dict[str, ActorControl]
    locations: dict[str, str]
    objects: dict[str, ObjectState] = {}
    items: dict[str, ItemDefinition] = {}
    encounters: dict[str, Encounter] = {}
    active_encounter: str | None = None
    completed_encounters: list[str] = []
    rewarded_progression: list[str] = []
    schedule_due: dict[str, int] = {}
    completed_schedules: list[str] = []
    resolved_checks: dict[str, str] = {}
    alerted_actors: list[str] = []
    world_events: list[dict[str, str | int]] = []
    faction_reputation: dict[str, int] = {}
    reputation_rewards: list[str] = []
    quests: dict[str, Literal["available", "active", "completed"]] = {}
    player_knowledge: dict[str, str] = {}
    known_locations: list[str] = []
    game_time: int = 0
    session_state: SessionState

    def actors(self):
        return {**self.characters, **self.npcs}

    def actor(self, actor_id):
        if actor_id not in self.actors():
            raise ValueError("Участник не найден")
        return self.actors()[actor_id]

    def relation(self, first, second):
        if first == second:
            return "ALLY"
        for r in self.definition.faction_relations:
            if {first, second} == {r.first, r.second}:
                return r.relation
        return "NEUTRAL"

    def hostile(self, a, b):
        return self.relation(self.actor(a).faction, self.actor(b).faction) == "HOSTILE"

    @property
    def encounter(self):
        return self.encounters.get(self.active_encounter)

    @model_validator(mode="after")
    def invariants(self):
        actors = self.actors()
        if set(self.characters) & set(self.npcs) or set(self.controllers) != set(
            actors
        ):
            raise ValueError("Некорректные участники или контроллеры")
        if self.session_state.controlled_actor not in actors or not set(
            self.party
        ) <= set(actors):
            raise ValueError("Некорректная партия")
        for key, a in actors.items():
            if (
                key != a.id
                or a.location not in self.locations
                or self.controllers[key].actor_id != key
            ):
                raise ValueError("Некорректная ссылка участника")
            if any(slot.remaining > slot.maximum for slot in a.spell_slots.values()):
                raise ValueError("Число ячеек превышает максимум")
            if not set(a.spells) <= set(self.ruleset.spells) or not set(
                a.prepared_spells
            ) <= set(a.spells):
                raise ValueError("Некорректные известные заклинания")
            if any(value < 0 for value in a.resources.values()):
                raise ValueError("Ресурс не может быть отрицательным")
            if any(source not in actors for source in a.condition_sources.values()):
                raise ValueError("Источник состояния не найден")
            if any(x.item_id not in self.items for x in a.inventory):
                raise ValueError("Неизвестный предмет")
        p = self.session_state.pending
        if (self.session_state.mode == "AWAITING_ROLL") != (p is not None):
            raise ValueError("Некорректный ожидающий бросок")
        if p and (
            p.actor not in actors
            or p.controller != self.controllers[p.actor].controller
            or p.player_id != self.controllers[p.actor].player_id
        ):
            raise ValueError("Контроллер броска не соответствует участнику")
        choice = self.session_state.choice
        if choice:
            if p or self.session_state.reaction or choice.actor not in actors:
                raise ValueError("Несовместимые ожидающие действия")
            owner = self.controllers[choice.actor]
            if owner.controller != "PLAYER" or owner.player_id != choice.player_id:
                raise ValueError("Контроллер выбора не соответствует участнику")
            if len({o.id for o in choice.options}) != len(choice.options):
                raise ValueError("Повтор ID варианта выбора")
        e = self.encounter
        if self.active_encounter and (
            not e
            or not e.order
            or not set(e.order) <= set(actors)
            or not 0 <= e.index < len(e.order)
        ):
            raise ValueError("Некорректная очередь")
        if self.session_state.mode == "ENCOUNTER" and not e:
            raise ValueError("Отсутствует бой")
        return self


# Backwards compatible import; HTTP uses the discriminated CommandType union.
from .commands import Command


class NewGame(Model):
    progression_mode: Literal["xp", "milestone"] = "xp"
    draft_id: str
    draft_revision: int = Field(ge=0)
    character: CharacterBuild
