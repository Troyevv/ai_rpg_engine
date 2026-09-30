"""Composable tactical behaviors. Evaluations never mutate canonical state."""

from dataclasses import dataclass
from .models import Command


@dataclass(frozen=True)
class Decision:
    behavior: str
    score: float
    command: Command


class Considerations:
    def __init__(self, state, actor):
        self.state = state
        self.actor = state.actor(actor)
        self.encounter = state.encounter
        self.enemies = [
            state.actor(i)
            for i in self.encounter.order
            if state.hostile(actor, i)
            and state.actor(i).hp > 0
            and "fled" not in state.actor(i).conditions
        ]
        self.allies = [
            state.actor(i)
            for i in self.encounter.order
            if i != actor
            and state.relation(self.actor.faction, state.actor(i).faction) == "ALLY"
            and state.actor(i).hp > 0
        ]
        self.danger = 1 - self.actor.hp / self.actor.max_hp
        self.target = min(
            self.enemies,
            key=lambda a: (abs(a.position - self.actor.position), a.hp, a.id),
            default=None,
        )
        self.weapon = next(iter(self.actor.attacks), "")


class Behavior:
    def candidates(self, c):
        return []


class Attack(Behavior):
    def candidates(self, c):
        if (
            c.weapon
            and c.encounter.action
            and c.target
            and abs(c.target.position - c.actor.position)
            <= c.actor.attacks[c.weapon].reach
        ):
            return [
                Decision(
                    "Attack",
                    0.65,
                    Command(type="attack", target=c.target.id, weapon=c.weapon),
                )
            ]
        return []


class MoveToTarget(Behavior):
    def candidates(self, c):
        if (
            c.weapon
            and c.target
            and c.encounter.movement
            and abs(c.target.position - c.actor.position)
            > c.actor.attacks[c.weapon].reach
        ):
            delta = c.target.position - c.actor.position
            distance = min(abs(delta), c.encounter.movement)
            return [
                Decision(
                    "MoveToTarget",
                    0.45,
                    Command(type="move", distance=distance if delta > 0 else -distance),
                )
            ]
        return []


class Flee(Behavior):
    def candidates(self, c):
        if (
            (c.encounter.action or c.encounter.disengaged)
            and c.danger > 0.7
            and c.actor.morale < 0.6
            and c.encounter.movement >= max(5, c.actor.speed // 2)
        ):
            return [
                Decision(
                    "Flee", 0.7 + c.danger * (1 - c.actor.morale), Command(type="flee")
                )
            ]
        return []


class Dodge(Behavior):
    def candidates(self, c):
        return (
            [Decision("Dodge", 0.15 + c.danger * 0.2, Command(type="dodge"))]
            if c.encounter.action
            else []
        )


class Help(Behavior):
    def candidates(self, c):
        near = [
            a
            for a in c.allies
            if abs(a.position - c.actor.position) <= 5 and "helped" not in a.conditions
        ]
        return (
            [Decision("Help", 0.3, Command(type="help", target=near[0].id))]
            if c.encounter.action and near
            else []
        )


class UseItem(Behavior):
    def candidates(self, c):
        potions = [e for e in c.actor.inventory if c.state.items[e.item_id].healing]
        return (
            [
                Decision(
                    "UseItem", 1.3, Command(type="use_item", item_id=potions[0].item_id)
                )
            ]
            if c.encounter.action and c.danger > 0.4 and potions
            else []
        )


class ProtectAlly(Behavior):
    def candidates(self, c):
        hurt = [
            a
            for a in c.allies
            if a.hp / a.max_hp < 0.5
            and abs(a.position - c.actor.position) <= 5
            and "helped" not in a.conditions
        ]
        return (
            [
                Decision(
                    "ProtectAlly",
                    0.7 if c.actor.morale > 0.7 else 0.2,
                    Command(type="help", target=hurt[0].id),
                )
            ]
            if c.encounter.action and hurt
            else []
        )


class Disengage(Behavior):
    def candidates(self, c):
        near = any(abs(e.position - c.actor.position) <= 5 for e in c.enemies)
        return (
            [Decision("Disengage", 1.7, Command(type="disengage"))]
            if c.danger > 0.7
            and c.actor.morale < 0.6
            and near
            and c.encounter.action
            and not c.encounter.disengaged
            else []
        )


class Dash(Behavior):
    def candidates(self, c):
        return (
            [Decision("Dash", 0.5, Command(type="dash"))]
            if c.weapon
            and c.target
            and c.encounter.action
            and not c.encounter.movement
            and abs(c.target.position - c.actor.position)
            > c.actor.attacks[c.weapon].reach
            else []
        )


class BehaviorRegistry:
    def __init__(self, behaviors=None):
        self.behaviors = behaviors or [
            Attack(),
            MoveToTarget(),
            Flee(),
            Dodge(),
            Help(),
            UseItem(),
            ProtectAlly(),
            Disengage(),
            Dash(),
        ]

    def options(self, context):
        return [d for behavior in self.behaviors for d in behavior.candidates(context)]


class UtilityScorer:
    @staticmethod
    def choose(options):
        return (
            max(options, key=lambda d: d.score)
            if options
            else Decision("EndTurn", 0, Command(type="end_turn"))
        )


class GameAI:
    def __init__(self, registry=None):
        self.registry = registry or BehaviorRegistry()

    def decision(self, state, actor_id):
        return UtilityScorer.choose(
            self.registry.options(Considerations(state, actor_id))
        )

    def decide(self, state, actor_id):
        return self.decision(state, actor_id).command
