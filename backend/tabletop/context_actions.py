"""Availability derives from current state and declared requirements."""

from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model, Named, Id, Ability


class ActionRequirements(Model):
    attributes: dict[Ability, int] = {}
    skills: list[Id] = []
    backgrounds: list[Id] = []
    archetypes: list[Id] = []
    features: list[Id] = []
    items: list[Id] = []
    equipment: list[Id] = []
    knowledge: list[Id] = []
    conditions: list[Id] = []
    without_conditions: list[Id] = []
    relationship_minimum: int | None = Field(default=None, ge=-100, le=100)


class ContextAction(Named):
    location_id: Id
    object_id: str = ""
    actor_id: str = ""
    requirements: ActionRequirements = Field(default_factory=ActionRequirements)
    check_id: str = ""
    feature_id: str = ""
    interaction: bool = False

    @model_validator(mode="after")
    def one_operation(self):
        if sum((bool(self.check_id), bool(self.feature_id), self.interaction)) != 1:
            raise ValueError("Context action must select exactly one operation")
        return self


class ObjectCapability(Model):
    capacity: int | None = Field(default=None, ge=1, le=1000)
    type: Literal[
        "interactable",
        "container",
        "lockable",
        "breakable",
        "terminal",
        "hazard",
        "trap",
        "cover",
        "environment",
    ]
    action_ids: list[Id] = []
    hit_points: int = Field(default=1, ge=1, le=1000)
    defence: int = Field(default=10, ge=1, le=30)
    damage_expression: str = ""
    damage_type: str = ""
    feature_id: str = ""


def eligible(state, actor, action):
    if actor.location != action.location_id:
        return False
    if action.object_id and (
        action.object_id not in state.objects
        or not state.objects[action.object_id].revealed
    ):
        return False
    if action.actor_id and (
        action.actor_id not in state.actors()
        or state.actor(action.actor_id).location != actor.location
    ):
        return False
    return requirements_met(state, actor, action.requirements, action.actor_id)


def requirements_met(state, actor, r, target_id=""):
    if any(actor.abilities[k] < v for k, v in r.attributes.items()):
        return False
    if r.backgrounds and actor.background not in r.backgrounds:
        return False
    if r.archetypes and actor.character_class not in r.archetypes:
        return False
    for required, available in (
        (r.skills, actor.skill_proficiencies),
        (r.features, actor.features),
        (r.items, [e.item_id for e in actor.inventory]),
        (r.equipment, [e.item_id for e in actor.inventory if e.equipped]),
        (r.knowledge, set(actor.knowledge) | set(state.player_knowledge)),
        (r.conditions, actor.conditions),
    ):
        if not set(required) <= set(available):
            return False
    if set(r.without_conditions) & set(actor.conditions):
        return False
    if r.relationship_minimum is not None and (
        not target_id
        or state.actor(target_id).relationships.get(actor.id, 0)
        < r.relationship_minimum
    ):
        return False
    return True


class ContextActionService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, command, aid, events):
        from .commands import Command

        action = next(
            (a for a in state.definition.context_actions if a.id == command.action_id),
            None,
        )
        if not action or not eligible(state, state.actor(aid), action):
            raise ValueError("Контекстное действие недоступно")
        if action.check_id:
            check = next(c for c in state.definition.checks if c.id == action.check_id)
            c = Command(
                type="save" if check.save else "check", check_id=check.id, actor_id=aid
            )
        elif action.feature_id:
            c = Command(
                type="use_feature",
                feature_id=action.feature_id,
                target=action.actor_id or aid,
                actor_id=aid,
            )
        else:
            c = Command(type="interact", target=action.object_id, actor_id=aid)
        if action.feature_id:
            return self.runtime.features_service.execute(
                state, c, aid, events, granted=True
            )
        self.runtime.apply(state, c, aid, events)
