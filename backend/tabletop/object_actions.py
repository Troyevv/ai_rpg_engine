"""Capability-driven object actions execute through canonical pending rolls."""

from .encounter import event
from .commands import Command
from .resources import ResourceEngine


class ObjectActions:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def definition(state, actor, id):
        obj = next(
            (
                o
                for o in state.definition.objects
                if o.id == id and o.location_id == actor.location
            ),
            None,
        )
        if not obj or not state.objects[id].revealed:
            raise ValueError("Объект недоступен")
        if any(
            e.loot_object == id and e.id not in state.completed_encounters
            for e in state.definition.encounters
        ):
            raise ValueError("Сначала заверши столкновение")
        return obj

    def execute(self, state, command, aid, events):
        actor = state.actor(aid)
        obj = self.definition(state, actor, command.target)
        capabilities = {c.type: c for c in obj.components}
        status = state.objects[obj.id]
        if command.operation == "break":
            part = capabilities.get("breakable")
            if not part or status.hit_points == 0:
                raise ValueError("Объект нельзя разрушить")
            weapon = command.weapon or next(iter(actor.attacks))
            if weapon not in actor.attacks:
                raise ValueError("Оружие недоступно")
            ResourceEngine.spend_attack(actor, actor.attacks[weapon])
            self.runtime.spend(state.encounter)
            self.runtime.pending(
                state,
                "object_attack",
                aid,
                object_id=obj.id,
                weapon=weapon,
                modifier=self.runtime.rules.attack_modifier(actor, weapon),
                dc=part.defence,
                reason=obj.name,
            )
        elif command.operation == "cover":
            if "cover" not in capabilities:
                raise ValueError("Объект не является укрытием")
            self.runtime.apply(
                state, Command(type="seek_cover", actor_id=aid), aid, events
            )
        else:
            parts = [
                c
                for c in obj.components
                if c.type in ("terminal", "environment", "interactable")
                and c.feature_id
            ]
            if not parts:
                raise ValueError("У объекта нет активируемой способности")
            for part in parts:
                self.runtime.features_service.execute(
                    state,
                    Command(type="use_feature", feature_id=part.feature_id, target=aid),
                    aid,
                    events,
                    granted=True,
                )
        event(
            events,
            obj.name + ": " + command.operation,
            kind="object_action",
            target=obj.id,
        )

    def resolve(self, state, p, roll, events):
        actor = state.actor(p.actor)
        obj = self.definition(state, actor, p.object_id)
        status = state.objects[obj.id]
        if p.purpose == "object_attack":
            if self.runtime.rules.hit(roll, p.dc):
                attack = actor.attacks[p.weapon]
                self.runtime.pending(
                    state,
                    "object_damage",
                    actor.id,
                    object_id=obj.id,
                    weapon=p.weapon,
                    expression=attack.expression or f"1d{attack.die}",
                    modifier=self.runtime.rules.damage_modifier(
                        actor, p.weapon, state.ruleset
                    ),
                    critical=roll.selected == 20,
                )
            else:
                event(events, "Промах по объекту.", kind="miss")
        elif p.purpose == "object_damage":
            part = next(c for c in obj.components if c.type == "breakable")
            before = (
                status.hit_points if status.hit_points is not None else part.hit_points
            )
            status.hit_points = max(0, before - max(0, roll.total))
            if status.hit_points == 0:
                status.unlocked = status.opened = True
                self.runtime.reveal_object(state, obj, events)
            event(
                events,
                f"{obj.name}: прочность {status.hit_points}.",
                kind="object_damage",
                target=obj.id,
                amount=before - status.hit_points,
            )
        else:
            part = next(
                c
                for c in obj.components
                if c.type in ("hazard", "trap") and c.damage_expression
            )
            self.runtime.combat.damage(
                state, actor, roll.total, False, events, part.damage_type
            )
