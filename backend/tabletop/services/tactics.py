"""Concrete combat maneuvers; their outcomes are resolved by engine rolls."""

from ..commands import Command
from ..encounter import event


class TacticalService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a, e = state.actor(aid), state.encounter
        if c.type == "search":
            return self.runtime.check(
                state,
                Command(
                    type="check", purpose="search", reason="Поиск объектов в сцене"
                ),
                a,
                events,
            )
        if c.type == "use_object":
            return self.runtime.exploration_service.interact(
                state, a, c.target, events, action=True
            )
        if not e:
            raise ValueError("Манёвр доступен только в бою")
        if c.type == "stand":
            if "prone" not in a.conditions or e.movement < a.speed // 2:
                raise ValueError("Нельзя встать: нет состояния или перемещения")
            e.movement -= a.speed // 2
            a.conditions.remove("prone")
            event(events, a.name + " встаёт на ноги.", kind="stand")
            return
        if c.type == "surrender":
            a.conditions.append("surrendered")
            event(events, a.name + " сдаётся.", kind="surrender")
            if not self.runtime.combat.ended(state, events):
                self.runtime.combat.advance(state)
            return
        if c.type == "seek_cover":
            self.runtime.spend(e)
            if "dodge" not in a.conditions:
                a.conditions.append("dodge")
            event(events, a.name + " занимает защитную позицию.", kind="cover")
            return
        if c.type == "ready":
            self.runtime.combat.validate_attack(
                state, aid, c.target, next(iter(a.attacks))
            )
            if not e.reaction.get(aid):
                raise ValueError("Для подготовки нужна свободная реакция")
            self.runtime.spend(e)
            e.ready[aid] = c.target
            event(
                events,
                "Подготовлена атака при начале хода цели в досягаемости.",
                kind="ready",
            )
            return
        target = None
        if c.type in ("grapple", "shove"):
            target = state.actor(c.target)
            if (
                not state.hostile(aid, target.id)
                or target.id not in e.order
                or target.hp <= 0
                or target.location != a.location
                or abs(target.position - a.position) > 5
            ):
                raise ValueError("Нужна враждебная цель рядом")
            if c.type == "grapple" and "grappled" in target.conditions:
                raise ValueError("Цель уже захвачена")
        if c.type == "escape":
            source = a.condition_sources.get("grappled")
            if not source or "grappled" not in a.conditions:
                raise ValueError("Нет захвата для освобождения")
            target = state.actor(source)
        self.runtime.spend(e)
        if c.type == "hide":
            enemies = [
                state.actor(i)
                for i in e.order
                if state.hostile(aid, i) and state.actor(i).hp > 0
            ]
            if any(abs(t.position - a.position) <= 5 for t in enemies):
                raise ValueError("Нельзя скрыться вплотную к противнику")
            dc = max(
                [10]
                + [
                    10
                    + self.runtime.rules.check_modifier(
                        t, "wisdom", "perception", state.ruleset
                    )
                    for t in enemies
                ]
            )
            ability, skill = "dexterity", "stealth"
        else:
            dc = 10 + max(
                self.runtime.rules.check_modifier(
                    target, "strength", "athletics", state.ruleset
                ),
                (
                    self.runtime.rules.check_modifier(
                        target, "dexterity", "acrobatics", state.ruleset
                    )
                    if "acrobatics" in state.ruleset.skills
                    else self.runtime.rules.modifier(target.abilities["dexterity"])
                ),
            )
            ability, skill = "strength", "athletics"
        modifier = self.runtime.rules.check_modifier(a, ability, skill, state.ruleset)
        advantage, sources = self.runtime.rules.conditions.advantage(
            a, state.ruleset, "check"
        )
        payload = dict(
            ability=ability,
            skill=skill,
            dc=dc,
            modifier=modifier,
            target=target.id if target else "",
            outcome=c.type,
            advantage=advantage,
            advantage_sources=sources,
        )
        if state.controllers[aid].controller == "PLAYER":
            self.runtime.pending(
                state,
                "check",
                aid,
                reason={
                    "hide": "Попытка скрыться",
                    "grapple": "Захват противника",
                    "shove": "Сбить противника с ног",
                    "escape": "Освободиться из захвата",
                }[c.type],
                **payload
            )
            event(events, "Манёвр требует броска.", kind="pending")
        else:
            roll = self.runtime.combat.roll(
                events,
                "1d20",
                modifier=modifier,
                advantage=advantage,
                purpose="check",
                actor=aid,
            )
            self.resolve(
                state,
                aid,
                c.type,
                target.id if target else "",
                roll.total >= dc,
                events,
            )

    def resolve(self, state, aid, outcome, target_id, success, events):
        a = state.actor(aid)
        if success:
            if outcome == "hide" and "hidden" not in a.conditions:
                a.conditions.append("hidden")
            elif outcome in ("grapple", "shove"):
                target = state.actor(target_id)
                condition = "grappled" if outcome == "grapple" else "prone"
                if condition not in target.conditions:
                    target.conditions.append(condition)
                if condition == "grappled":
                    target.condition_sources[condition] = aid
            elif outcome == "escape":
                a.conditions.remove("grappled")
                a.condition_sources.pop("grappled", None)
        event(
            events,
            "Манёвр удался." if success else "Манёвр не удался.",
            kind=outcome,
            success=success,
            actor=aid,
            target=target_id,
        )

    def trigger_ready(self, state, events):
        e = state.encounter
        current = e.order[e.index]
        for aid, target_id in list(e.ready.items()):
            if target_id != current:
                continue
            del e.ready[aid]
            a, target = state.actor(aid), state.actor(target_id)
            weapon = next(iter(a.attacks), "")
            if (
                not e.reaction.get(aid)
                or a.hp <= 0
                or target.hp <= 0
                or self.runtime.rules.conditions.blocked(a, state.ruleset)
                or not weapon
                or abs(a.position - target.position) > a.attacks[weapon].reach
            ):
                continue
            if state.controllers[aid].controller == "PLAYER":
                state.session_state.reaction = {
                    "actor": aid,
                    "mover": target_id,
                    "distance": 0,
                    "weapon": weapon,
                }
                event(
                    events,
                    "Подготовленная атака: использовать реакцию?",
                    kind="reaction",
                )
                return True
            e.reaction[aid] = False
            self.runtime.combat.npc_attack(state, aid, target_id, weapon, events)
        return False
