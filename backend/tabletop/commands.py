"""Discriminated commands: each operation owns only its valid payload fields."""

from typing import Annotated, Literal, Union
from pydantic import Field, TypeAdapter
from .definitions import Model, Ability, Difficulty


class ActorCommand(Model):
    actor_id: str = Field(default="", max_length=80)


class LookCommand(ActorCommand):
    type: Literal["look"] = "look"


class MoveCommand(ActorCommand):
    type: Literal["move"] = "move"
    target: str = Field(default="", max_length=80)
    distance: int = Field(default=0, ge=-120, le=120)


class CheckCommand(ActorCommand):
    check_id: str = Field(default="", max_length=80)
    type: Literal["check"] = "check"
    ability: Ability = "wisdom"
    skill: str = Field(default="", max_length=80)
    difficulty: Difficulty = "MEDIUM"
    purpose: Literal["general", "search", "unlock", "persuade"] = "general"
    target: str = Field(default="", max_length=80)
    reason: str = Field(default="", max_length=500)


class SaveCommand(ActorCommand):
    check_id: str = Field(default="", max_length=80)
    type: Literal["save"] = "save"
    ability: Ability = "wisdom"
    difficulty: Difficulty = "MEDIUM"
    reason: str = Field(default="", max_length=500)


class AttackCommand(ActorCommand):
    mode: Literal["single", "burst", "automatic"] = "single"
    type: Literal["attack"] = "attack"
    target: str = Field(min_length=1, max_length=80)
    weapon: str = Field(default="", max_length=80)


class ContextActionCommand(ActorCommand):
    type: Literal["context_action"] = "context_action"
    action_id: str = Field(min_length=1, max_length=80)


class ReloadCommand(ActorCommand):
    type: Literal["reload"] = "reload"
    item_id: str = Field(min_length=1, max_length=80)


class LevelUpCommand(ActorCommand):
    type: Literal["level_up"] = "level_up"
    subclass: str = Field(default="", max_length=80)
    ability_increases: list[Ability] = Field(default_factory=list, max_length=2)
    feat_id: str = Field(default="", max_length=80)
    learn_spells: list[str] = Field(default_factory=list, max_length=2)


class CastSpellCommand(ActorCommand):
    type: Literal["cast_spell"] = "cast_spell"
    spell_id: str = Field(min_length=1, max_length=80)
    target: str = Field(default="", max_length=80)
    slot_level: int = Field(default=0, ge=0, le=9)


class PrepareSpellsCommand(ActorCommand):
    type: Literal["prepare_spells"] = "prepare_spells"
    spells: list[str] = Field(max_length=30)


class UseFeatureCommand(ActorCommand):
    type: Literal["use_feature"] = "use_feature"
    feature_id: str = Field(min_length=1, max_length=80)
    target: str = Field(default="", max_length=80)


class ManeuverCommand(ActorCommand):
    type: Literal["grapple", "shove", "ready"]
    target: str = Field(min_length=1, max_length=80)


class TacticalCommand(ActorCommand):
    type: Literal["hide", "search", "stand", "escape", "surrender", "seek_cover"]


class UseObjectCommand(ActorCommand):
    type: Literal["use_object"] = "use_object"
    target: str = Field(min_length=1, max_length=80)


class InteractCommand(ActorCommand):
    type: Literal["interact"] = "interact"
    target: str = Field(min_length=1, max_length=80)


class DialogueCommand(ActorCommand):
    type: Literal["dialogue"] = "dialogue"
    target: str = Field(min_length=1, max_length=80)


class UseItemCommand(ActorCommand):
    type: Literal["use_item"] = "use_item"
    item_id: str = Field(min_length=1, max_length=80)
    target: str = Field(default="", max_length=80)


class EquipmentCommand(ActorCommand):
    slot: str = Field(default="", max_length=40)
    type: Literal["equip", "unequip"]
    item_id: str = Field(min_length=1, max_length=80)


class TakeItemCommand(ActorCommand):
    type: Literal["take_item"] = "take_item"
    target: str = Field(min_length=1, max_length=80)
    item_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=100)


class DropItemCommand(ActorCommand):
    type: Literal["drop_item"] = "drop_item"
    item_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=100)


class TransferItemCommand(ActorCommand):
    type: Literal["transfer_item"] = "transfer_item"
    target: str = Field(min_length=1, max_length=80)
    item_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=100)


class RestCommand(ActorCommand):
    type: Literal["rest"] = "rest"
    rest: Literal["short", "long"] = "short"


class HelpCommand(ActorCommand):
    type: Literal["help"] = "help"
    target: str = Field(min_length=1, max_length=80)


class CombatActionCommand(ActorCommand):
    type: Literal["dodge", "dash", "disengage", "end_turn", "flee", "guard", "recover"]


class StartEncounterCommand(ActorCommand):
    type: Literal["start_encounter"] = "start_encounter"
    target: str = Field(default="", max_length=80)


class ReactionCommand(ActorCommand):
    type: Literal["reaction_attack", "decline_reaction"]


class SelectActorCommand(ActorCommand):
    type: Literal["select_actor"] = "select_actor"
    target: str = Field(min_length=1, max_length=80)


class ExpandCommand(ActorCommand):
    type: Literal["expand"] = "expand"
    topic: str = Field(min_length=3, max_length=1000)


ActionCommand = Annotated[
    Union[
        LookCommand,
        MoveCommand,
        CheckCommand,
        SaveCommand,
        AttackCommand,
        ReloadCommand,
        ContextActionCommand,
        UseFeatureCommand,
        CastSpellCommand,
        LevelUpCommand,
        PrepareSpellsCommand,
        ManeuverCommand,
        TacticalCommand,
        UseObjectCommand,
        InteractCommand,
        DialogueCommand,
        UseItemCommand,
        EquipmentCommand,
        TakeItemCommand,
        DropItemCommand,
        TransferItemCommand,
        RestCommand,
        HelpCommand,
        CombatActionCommand,
        StartEncounterCommand,
        ReactionCommand,
        SelectActorCommand,
    ],
    Field(discriminator="type"),
]


class ChoiceOption(Model):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    command: ActionCommand


class RequestChoiceCommand(ActorCommand):
    type: Literal["request_choice"] = "request_choice"
    kind: Literal["action", "target"] = "action"
    prompt: str = Field(min_length=1, max_length=500)
    options: list[ChoiceOption] = Field(min_length=2, max_length=6)


class ResolveChoiceCommand(ActorCommand):
    type: Literal["resolve_choice"] = "resolve_choice"
    pending_id: str = Field(min_length=1, max_length=80)
    option_id: str = Field(min_length=1, max_length=80)


CommandType = Annotated[
    Union[ActionCommand, ExpandCommand, RequestChoiceCommand, ResolveChoiceCommand],
    Field(discriminator="type"),
]
COMMAND_ADAPTER = TypeAdapter(CommandType)


class Command:
    """Compatibility constructor for internal callers; returns a typed operation."""

    def __new__(cls, **payload):
        return COMMAND_ADAPTER.validate_python(payload)

    model_validate = staticmethod(COMMAND_ADAPTER.validate_python)
    model_validate_json = staticmethod(COMMAND_ADAPTER.validate_json)
    model_json_schema = staticmethod(COMMAND_ADAPTER.json_schema)
