"""Bounded declarative effects. No path mutation or setting-specific code."""

from uuid import uuid4
from .encounter import event


class EffectsEngine:
    ACTIVE = {
        "damage",
        "remove_condition",
        "modify_check",
        "modify_attack",
        "modify_damage",
        "grant_advantage",
        "grant_disadvantage",
        "move",
        "push",
        "pull",
        "spend_resource",
        "restore_resource",
        "reveal_knowledge",
        "modify_relationship",
        "spawn_object",
        "interact",
    }

    @staticmethod
    def validate(state, actor, target, effect):
        if effect.type == "damage":
            from .dice import DiceEngine

            DiceEngine.parse(effect.expression)
            if effect.key not in state.ruleset.damage_types:
                raise ValueError("Неизвестный тип урона")
        if effect.type in ("spend_resource", "restore_resource"):
            definition = state.ruleset.resource_definitions.get(effect.key)
            if not definition or effect.key not in target.resources:
                raise ValueError("Ресурс недоступен")
            if effect.value < 0:
                raise ValueError("Стоимость ресурса не может быть отрицательной")
            if (
                effect.type == "spend_resource"
                and target.resources[effect.key] < effect.value
            ):
                raise ValueError("Недостаточно ресурса")
        if (
            effect.type == "remove_condition"
            and effect.key not in state.ruleset.condition_definitions
        ):
            raise ValueError("Неизвестное состояние")
        if effect.type in ("move", "push", "pull") and not state.encounter:
            raise ValueError("Перемещение эффектом доступно в бою")
        if effect.type == "reveal_knowledge":
            secret = next(
                (s for s in state.definition.secrets if s.id == effect.key), None
            )
            if (
                not secret
                or secret.location_id != actor.location
                or secret.disclosure == "never"
            ):
                raise ValueError("Сведения нельзя раскрыть")
        if (
            effect.type == "modify_relationship"
            and state.controllers[target.id].controller == "PLAYER"
        ):
            raise ValueError("Нельзя управлять чувствами игрока")
        if effect.type == "spawn_object" and effect.key not in state.items:
            raise ValueError("Предмет не зарегистрирован")
        if effect.type == "interact":
            obj = next(
                (o for o in state.definition.objects if o.id == effect.key), None
            )
            if (
                not obj
                or obj.location_id != actor.location
                or not state.objects[obj.id].revealed
            ):
                raise ValueError("Объект недоступен")

    @classmethod
    def apply(cls, runtime, state, actor, target, effect, events):
        cls.validate(state, actor, target, effect)
        t = effect.type
        if t == "damage":
            roll = runtime.combat.roll(
                events,
                effect.expression,
                modifier=effect.value,
                purpose="damage",
                actor=actor.id,
            )
            runtime.combat.damage(state, target, roll.total, False, events, effect.key)
        elif t == "remove_condition":
            target.conditions = [c for c in target.conditions if c != effect.key]
        elif t in (
            "modify_check",
            "modify_attack",
            "modify_damage",
            "grant_advantage",
            "grant_disadvantage",
        ):
            key = {
                "modify_check": "check_bonus",
                "modify_attack": "attack_bonus",
                "modify_damage": "damage_bonus",
                "grant_advantage": "advantage",
                "grant_disadvantage": "disadvantage",
            }[t]
            target.active_effects.append(
                dict(
                    id=uuid4().hex,
                    key=key,
                    scope=effect.key,
                    value=effect.value if t.startswith("modify") else 1,
                    expires=state.game_time + effect.duration,
                )
            )
        elif t in ("move", "push", "pull"):
            distance = min(120, abs(effect.value))
            direction = 1 if target.position >= actor.position else -1
            if t == "pull":
                direction *= -1
            if t == "move":
                direction = 1 if effect.value >= 0 else -1
            target.position = max(
                -1000, min(1000, target.position + direction * distance)
            )
        elif t == "spend_resource":
            target.resources[effect.key] -= effect.value
        elif t == "restore_resource":
            target.resources[effect.key] = min(
                state.ruleset.resource_definitions[effect.key].maximum,
                target.resources[effect.key] + effect.value,
            )
        elif t == "reveal_knowledge":
            if effect.key not in state.player_knowledge:
                state.player_knowledge[effect.key] = next(
                    s.description
                    for s in state.definition.secrets
                    if s.id == effect.key
                )
        elif t == "modify_relationship":
            target.relationships[actor.id] = max(
                -100, min(100, target.relationships.get(actor.id, 0) + effect.value)
            )
        elif t == "spawn_object":
            from .definitions import WorldObject, InventoryEntry
            from .models import ObjectState

            id = "created_" + uuid4().hex
            obj = WorldObject(
                id=id,
                name=state.items[effect.key].name,
                location_id=actor.location,
                check_skill="",
                contents=[
                    InventoryEntry(item_id=effect.key, quantity=max(1, effect.value))
                ],
            )
            state.definition.objects.append(obj)
            state.objects[id] = ObjectState(
                revealed=True, opened=True, contents=obj.contents
            )
        elif t == "interact":
            runtime.interact(state, actor, effect.key, events)
        event(
            events,
            f"{target.name}: эффект {t}.",
            kind="effect",
            target=target.id,
            effect=t,
        )

    @staticmethod
    def expire(state):
        for actor in state.actors().values():
            actor.active_effects = [
                e for e in actor.active_effects if e["expires"] > state.game_time
            ]

    @staticmethod
    def bonus(actor, key, scope=""):
        return sum(
            e["value"]
            for e in actor.active_effects
            if e["key"] == key and (not e["scope"] or e["scope"] == scope)
        )
