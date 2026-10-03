"""Execute catalog-owned features through the same atomic runtime as attacks."""

from ..encounter import event


class FeatureService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, command, aid, events, validate_only=False, granted=False):
        actor = state.actor(aid)
        feature = state.ruleset.features.get(command.feature_id)
        if (
            not feature
            or (feature.id not in actor.features and not granted)
            or feature.level > actor.level
        ):
            raise ValueError("Особенность недоступна персонажу")
        if feature.activation == "PASSIVE":
            raise ValueError("Пассивную особенность нельзя активировать")
        target = state.actor(command.target) if command.target else actor
        from ..context_actions import requirements_met

        if not requirements_met(state, actor, feature.requirements, target.id):
            raise ValueError("Не выполнены требования способности")
        if (
            target.location != actor.location
            or "dead" in target.conditions
            or abs(target.position - actor.position) > feature.reach
        ):
            raise ValueError("Цель особенности недоступна")
        if feature.target == "self" and target.id != actor.id:
            raise ValueError("Особенность применяется только к себе")
        if (
            feature.target == "ally"
            and state.relation(actor.faction, target.faction) != "ALLY"
        ):
            raise ValueError("Нужна союзная цель")
        if feature.target == "enemy" and not state.hostile(aid, target.id):
            raise ValueError("Нужна враждебная цель")
        costs = dict(feature.resource_cost)
        if feature.resource:
            costs[feature.resource] = costs.get(feature.resource, 0) + 1
        for rid, cost in costs.items():
            if cost < 0 or actor.resources.get(rid, 0) < cost:
                raise ValueError("Недостаточно ресурса: " + rid)
        if (
            any(
                effect.type in ("dash", "disengage", "condition")
                for effect in feature.effects
            )
            and not state.encounter
        ):
            raise ValueError("Эта особенность применяется в бою")
        from ..effects import EffectsEngine

        for effect in feature.effects:
            if effect.type in EffectsEngine.ACTIVE:
                EffectsEngine.validate(state, actor, target, effect)
            if effect.type == "restore_slot" and (
                effect.key not in actor.spell_slots
                or actor.spell_slots[effect.key].remaining
                >= actor.spell_slots[effect.key].maximum
            ):
                raise ValueError("Нет потраченной ячейки для восстановления")
            if effect.type == "condition" and effect.key in target.conditions:
                raise ValueError("Эффект уже действует")
        area_targets = [target]
        if feature.area:
            if any(
                effect.type not in EffectsEngine.ACTIVE for effect in feature.effects
            ):
                raise ValueError(
                    "Область поддерживает только объявленные универсальные эффекты"
                )
            area_targets = [
                other
                for other in state.actors().values()
                if other.location == target.location
                and other.hp > 0
                and abs(other.position - target.position) <= feature.area
                and (
                    state.hostile(actor.id, other.id)
                    if feature.target == "enemy"
                    else state.relation(actor.faction, other.faction) == "ALLY"
                )
            ]
            for other in area_targets:
                for effect in feature.effects:
                    EffectsEngine.validate(state, actor, other, effect)
        if feature.activation == "REACTION":
            if not state.encounter or not state.encounter.reaction.get(aid):
                raise ValueError("Реакция недоступна")
            if validate_only:
                return
            state.encounter.reaction[aid] = False
        else:
            if validate_only:
                self.runtime.spend(
                    state.encounter.model_copy(deep=True) if state.encounter else None,
                    (
                        "bonus_action"
                        if feature.activation == "BONUS_ACTION"
                        else "action"
                    ),
                )
                return
            self.runtime.spend(
                state.encounter,
                "bonus_action" if feature.activation == "BONUS_ACTION" else "action",
            )
        for rid, cost in costs.items():
            actor.resources[rid] = actor.resources.get(rid, 0) - cost
        for effect in feature.effects:
            if effect.type in EffectsEngine.ACTIVE:
                for other in area_targets:
                    EffectsEngine.apply(
                        self.runtime, state, actor, other, effect, events
                    )
            elif effect.type == "heal_dice":
                modifier = effect.value + (actor.level if effect.add_level else 0)
                if state.controllers[aid].controller == "PLAYER":
                    self.runtime.pending(
                        state,
                        "feature_healing",
                        aid,
                        expression=effect.expression,
                        modifier=modifier,
                        target=target.id,
                        reason=feature.name,
                    )
                else:
                    roll = self.runtime.combat.roll(
                        events,
                        effect.expression,
                        modifier=modifier,
                        purpose="feature_healing",
                        actor=aid,
                    )
                    self.resolve_healing(state, target.id, roll, events)
            elif effect.type == "restore_slot":
                slot = actor.spell_slots[effect.key]
                slot.remaining = min(slot.maximum, slot.remaining + effect.value)
            elif effect.type == "heal":
                before = target.hp
                healed = self.runtime.rules.heal(target, effect.value + actor.level)
                event(
                    events,
                    f"{target.name}: восстановлено {healed} HP.",
                    kind="healing",
                    hp_before=before,
                    hp_after=target.hp,
                    maximum=target.max_hp,
                    amount=healed,
                    target=target.id,
                )
            elif effect.type == "condition":
                if effect.key not in state.ruleset.condition_definitions:
                    raise ValueError("Неизвестный эффект каталога")
                target.conditions.append(effect.key)
            elif effect.type == "dash":
                state.encounter.movement += self.runtime.rules.speed(
                    actor, state.ruleset
                )
            elif effect.type == "disengage":
                state.encounter.disengaged = True
            else:
                raise ValueError("Неподдерживаемый активный эффект")
        event(
            events,
            f"{actor.name}: {feature.name}.",
            kind="feature",
            actor=aid,
            feature_id=feature.id,
            target=target.id,
        )

    def resolve_healing(self, state, target_id, roll, events):
        target = state.actor(target_id)
        before = target.hp
        healed = self.runtime.rules.heal(target, roll.total)
        event(
            events,
            f"{target.name}: восстановлено {healed} HP.",
            kind="healing",
            target=target_id,
            amount=healed,
            hp_before=before,
            hp_after=target.hp,
            maximum=target.max_hp,
        )

    @staticmethod
    def recharge(actor, rules, rest):
        for fid in actor.features:
            f = rules.features.get(fid)
            if (
                f
                and f.resource
                and f.recharge != "none"
                and (rest == "long" or f.recharge == "short")
            ):
                actor.resources[f.resource] = f.uses
