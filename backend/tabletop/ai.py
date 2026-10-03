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
            and (c.encounter.action or c.encounter.attacks_remaining)
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


class UseFeature(Behavior):
    def candidates(self, c):
        options = []
        for fid in c.actor.features:
            f = c.state.ruleset.features.get(fid)
            if (
                not f
                or f.activation not in ("ACTION", "BONUS_ACTION")
                or (f.resource and c.actor.resources.get(f.resource, 0) <= 0)
            ):
                continue
            if not (
                c.encounter.action
                if f.activation == "ACTION"
                else c.encounter.bonus_action
            ):
                continue
            healing = any(e.type == "heal" for e in f.effects)
            if healing:
                targets = [c.actor] + (c.allies if f.target == "ally" else [])
                targets = [
                    a
                    for a in targets
                    if a.hp < a.max_hp and abs(a.position - c.actor.position) <= f.reach
                ]
                if not targets:
                    continue
                target = min(targets, key=lambda a: a.hp / a.max_hp)
                score = 1.4 if target.hp / target.max_hp < 0.6 else 0.2
            else:
                if not any(
                    e.type == "condition" and e.key not in c.actor.conditions
                    for e in f.effects
                ):
                    continue
                target, score = c.actor, 0.8
            options.append(
                Decision(
                    "UseFeature",
                    score,
                    Command(type="use_feature", feature_id=fid, target=target.id),
                )
            )
        return options


class SeekCover(Behavior):
    def candidates(self, c):
        if (
            c.encounter.action
            and c.target
            and c.danger > 0.5
            and abs(c.target.position - c.actor.position) > 5
        ):
            return [Decision("SeekCover", 0.6, Command(type="seek_cover"))]
        return []


class Surrender(Behavior):
    def candidates(self, c):
        if c.danger > 0.8 and c.actor.morale < 0.25 and not c.encounter.movement:
            return [Decision("Surrender", 2, Command(type="surrender"))]
        return []


class CastSpell(Behavior):
    def candidates(self, c):
        casting = c.state.ruleset.spellcasting.get(c.actor.character_class)
        if not casting:
            return []
        options = []
        for sid in c.actor.spells:
            spell = c.state.ruleset.spells[sid]
            if not (
                c.encounter.bonus_action
                if spell.casting_time == "BONUS_ACTION"
                else c.encounter.action
            ):
                continue
            if spell.level and (
                sid not in c.actor.prepared_spells
                or str(spell.level) not in c.actor.spell_slots
                or not c.actor.spell_slots[str(spell.level)].remaining
            ):
                continue
            if spell.healing:
                targets = [
                    a
                    for a in [c.actor, *c.allies]
                    if a.hp / a.max_hp < 0.5
                    and abs(a.position - c.actor.position) <= spell.range
                ]
                score = 1.5
            elif spell.damage and spell.target_type != "area":
                targets = [
                    a
                    for a in c.enemies
                    if abs(a.position - c.actor.position) <= spell.range
                ]
                score = 0.75
            else:
                continue
            if targets:
                options.append(
                    Decision(
                        "CastSpell",
                        score,
                        Command(type="cast_spell", spell_id=sid, target=targets[0].id),
                    )
                )
        return options


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
            UseFeature(),
            CastSpell(),
            SeekCover(),
            Surrender(),
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
