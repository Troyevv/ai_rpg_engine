"""Read-only combat forecasts using the same hit and modifier rules as resolution."""

from itertools import product
from types import SimpleNamespace

from .rules import RulesEngine
from .encounter import EncounterEngine
from .dice import DiceEngine


def attack_previews(state, actor):
    rules = RulesEngine()
    combat = EncounterEngine(DiceEngine(), rules)
    encounter = state.encounter
    if not encounter:
        return []
    result = []
    for weapon, attack in actor.attacks.items():
        for target_id in encounter.order:
            target = state.actor(target_id)
            if not state.hostile(actor.id, target_id) or target.hp <= 0:
                continue
            reason = ""
            try:
                combat.validate_attack(state, actor.id, target_id, weapon)
                if encounter.order[encounter.index] != actor.id:
                    raise ValueError("Сейчас ход другого участника")
                if not encounter.action and not encounter.attacks_remaining:
                    raise ValueError("Доступные атаки закончились")
                if rules.conditions.blocked(actor, state.ruleset):
                    raise ValueError("Состояние не позволяет атаковать")
                if (
                    state.session_state.pending
                    or state.session_state.choice
                    or state.session_state.reaction
                ):
                    raise ValueError("Сначала заверши ожидающее действие")
            except ValueError as exc:
                reason = str(exc)
            distance = abs(actor.position - target.position)
            advantage, sources = rules.conditions.advantage(
                actor, state.ruleset, "attack", target, distance=distance
            )
            modifier = rules.attack_modifier(actor, weapon)
            outcomes = list(product(range(1, 21), repeat=2 if advantage else 1))
            selected = [max(v) if advantage > 0 else min(v) for v in outcomes]
            hits = sum(
                rules.hit(
                    SimpleNamespace(selected=v, total=v + modifier), target.armor_class
                )
                for v in selected
            )
            damage_modifier = rules.damage_modifier(actor, weapon, state.ruleset)
            low, high = max(0, 1 + damage_modifier), max(
                0, attack.die + damage_modifier
            )
            critical_low = max(
                0,
                (attack.die + 1 if state.ruleset.critical == "max_dice" else 2)
                + damage_modifier,
            )
            critical_high = max(0, attack.die * 2 + damage_modifier)
            result.append(
                dict(
                    weapon=weapon,
                    name=attack.name,
                    target=target_id,
                    target_name=target.name,
                    available=not reason,
                    reason=reason,
                    distance=distance,
                    reach=attack.reach,
                    hit_percent=round(100 * hits / len(selected), 2),
                    advantage=advantage,
                    sources=sources,
                    target_ac=target.armor_class,
                    modifier=modifier,
                    damage_modifier=damage_modifier,
                    die=attack.die,
                    damage=[low, high],
                    critical_damage=[critical_low, critical_high],
                    damage_note="До защиты и сопротивления цели",
                    cost="Действие / оставшаяся атака",
                    breakdown={
                        "Характеристика": rules.modifier(
                            actor.abilities[attack.ability]
                        ),
                        "Владение": (
                            rules.proficiency(actor) if attack.proficient else 0
                        ),
                        "Способности": actor.bonuses.get("attack_bonus", 0),
                        "Состояния": rules.conditions.bonus(actor, "attack_bonus"),
                    },
                )
            )
    return result


def usable_actions(state, actor):
    from .runtime import TabletopRuntime
    from .commands import Command

    runtime = TabletopRuntime()
    encounter = state.encounter
    if (
        actor.hp <= 0
        or state.controllers[actor.id].controller != "PLAYER"
        or runtime.rules.conditions.blocked(actor, state.ruleset)
        or state.session_state.pending
        or state.session_state.choice
        or state.session_state.reaction
        or encounter
        and encounter.order[encounter.index] != actor.id
    ):
        return []
    actions = []
    for kind, definitions in (
        (
            "feature",
            [
                state.ruleset.features[f]
                for f in actor.features
                if f in state.ruleset.features
            ],
        ),
        ("spell", [state.ruleset.spells[s] for s in actor.spells]),
    ):
        for definition in definitions:
            if kind == "feature" and definition.activation == "PASSIVE":
                continue
            levels = (
                [0]
                if kind == "feature" or not definition.level
                else [
                    int(k)
                    for k, slot in actor.spell_slots.items()
                    if int(k) >= definition.level and slot.remaining
                ]
            )
            for level in levels:
                targets = []
                for target in state.actors().values():
                    command = Command(
                        type="use_feature" if kind == "feature" else "cast_spell",
                        **(
                            {"feature_id": definition.id}
                            if kind == "feature"
                            else {"spell_id": definition.id, "slot_level": level}
                        ),
                        target=target.id
                    )
                    try:
                        service = (
                            runtime.features_service
                            if kind == "feature"
                            else runtime.spells_service
                        )
                        service.execute(
                            state, command, actor.id, [], validate_only=True
                        )
                        forecast = {}
                        if kind == "spell":
                            spell_modifier = runtime.spells_service.modifier(
                                state, actor
                            )
                            if definition.attack_roll:
                                modifier = (
                                    spell_modifier
                                    + actor.proficiency_bonus
                                    + runtime.rules.conditions.bonus(
                                        actor, "attack_bonus"
                                    )
                                    + actor.bonuses.get("attack_bonus", 0)
                                )
                                adv, sources = runtime.rules.conditions.advantage(
                                    actor,
                                    state.ruleset,
                                    "attack",
                                    target,
                                    distance=abs(actor.position - target.position),
                                )
                                values = [
                                    (max(v) if adv > 0 else min(v))
                                    for v in product(
                                        range(1, 21), repeat=2 if adv else 1
                                    )
                                ]
                                forecast.update(
                                    hit_percent=round(
                                        100
                                        * sum(
                                            runtime.rules.hit(
                                                SimpleNamespace(
                                                    selected=v, total=v + modifier
                                                ),
                                                target.armor_class,
                                            )
                                            for v in values
                                        )
                                        / len(values),
                                        2,
                                    ),
                                    modifier=modifier,
                                    sources=sources,
                                    target_ac=target.armor_class,
                                )
                            if definition.save:
                                forecast.update(
                                    save=definition.save,
                                    save_dc=8
                                    + actor.proficiency_bonus
                                    + spell_modifier,
                                    half_on_save=definition.half_on_save,
                                )
                            if definition.damage or definition.healing:
                                expression = runtime.spells_service.expression(
                                    definition, level, actor.level
                                )
                                forecast.update(
                                    expression=expression,
                                    healing_modifier=(
                                        spell_modifier if definition.healing else 0
                                    ),
                                )
                        targets.append(
                            {
                                "id": target.id,
                                "name": target.name,
                                "distance": abs(actor.position - target.position),
                                **forecast,
                            }
                        )
                    except ValueError:
                        continue
                if targets:
                    actions.append(
                        {
                            "kind": kind,
                            "id": definition.id,
                            "name": definition.name,
                            "description": definition.description,
                            "cost": (
                                definition.activation
                                if kind == "feature"
                                else definition.casting_time
                            ),
                            "slot_level": level,
                            "targets": targets,
                        }
                    )
    return actions


def build_impact(actor, rules):
    engine = RulesEngine()
    return {
        "sheet": actor.model_dump(),
        "attacks": {k: engine.attack_modifier(actor, k) for k in actor.attacks},
        "damage": {k: engine.damage_modifier(actor, k, rules) for k in actor.attacks},
        "initiative": engine.modifier(actor.abilities["dexterity"]),
        "valid": True,
        "points_remaining": None,
        "gold_remaining": actor.gold,
        "modifiers": {a: engine.modifier(v) for a, v in actor.abilities.items()},
        "skills": {
            s: engine.check_modifier(actor, a, s, rules)
            for s, a in rules.skills.items()
        },
        "saves": {a: engine.save_modifier(actor, a) for a in actor.abilities},
    }
