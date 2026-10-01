"""Execute catalog-owned features through the same atomic runtime as attacks."""

from ..encounter import event


class FeatureService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, command, aid, events):
        actor = state.actor(aid)
        feature = state.ruleset.features.get(command.feature_id)
        if (
            not feature
            or feature.id not in actor.features
            or feature.level > actor.level
        ):
            raise ValueError("Особенность недоступна персонажу")
        if feature.activation == "PASSIVE":
            raise ValueError("Пассивную особенность нельзя активировать")
        target = state.actor(command.target) if command.target else actor
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
        if feature.resource and actor.resources.get(feature.resource, 0) <= 0:
            raise ValueError("Ресурс особенности исчерпан")
        if (
            any(
                effect.type in ("dash", "disengage", "condition")
                for effect in feature.effects
            )
            and not state.encounter
        ):
            raise ValueError("Эта особенность применяется в бою")
        for effect in feature.effects:
            if effect.type == "condition" and effect.key in target.conditions:
                raise ValueError("Эффект уже действует")
        if feature.activation == "REACTION":
            if not state.encounter or not state.encounter.reaction.get(aid):
                raise ValueError("Реакция недоступна")
            state.encounter.reaction[aid] = False
        else:
            self.runtime.spend(
                state.encounter,
                "bonus_action" if feature.activation == "BONUS_ACTION" else "action",
            )
        if feature.resource:
            actor.resources[feature.resource] -= 1
        for effect in feature.effects:
            if effect.type == "heal":
                healed = self.runtime.rules.heal(target, effect.value + actor.level)
                event(
                    events,
                    f"{target.name}: восстановлено {healed} HP.",
                    kind="healing",
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
