"""EncounterService domain behavior."""

from ..encounter import event


class EncounterService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "start_encounter":
            if e:
                raise ValueError("Бой уже идёт")
            candidates = [
                x
                for x in state.definition.encounters
                if x.location_id == a.location
                and x.id not in state.completed_encounters
            ]
            definition = (
                next((x for x in candidates if x.id == c.target), None)
                if c.target
                else next(iter(candidates), None)
            )
            if not definition:
                raise ValueError("Здесь нет доступного столкновения")
            ids = list(
                dict.fromkeys(
                    [i for i in state.party if state.actor(i).location == a.location]
                    + definition.participants
                )
            )
            ids = [
                i
                for i in ids
                if state.actor(i).hp > 0 and "fled" not in state.actor(i).conditions
            ]
            if not any((state.hostile(i, j) for i in ids for j in ids)):
                raise ValueError("Между участниками нет вражды")
            state.session_state.initiative_waiting = ids
            state.session_state.initiative_results = {}
            state.session_state.encounter_definition = definition.id
            self.runtime.initiative(state, events)
        if t == "attack":
            if not e:
                raise ValueError("Сначала начни столкновение")
            if e.action:
                self.runtime.spend(e)
                e.attacks_remaining = a.bonuses.get("extra_attack", 0)
            elif e.attacks_remaining > 0:
                e.attacks_remaining -= 1
            else:
                raise ValueError("Доступные атаки закончились")
            self.runtime.attack(
                state, aid, c.target, c.weapon or next(iter(a.attacks)), events
            )
        if t == "end_turn":
            if not e:
                raise ValueError("Сейчас нет боя")
            self.runtime.combat.advance(state)
        if t in ("dodge", "dash", "disengage", "help", "guard", "recover", "flee"):
            if not e:
                raise ValueError("Действие доступно только в бою")
            if t == "guard":
                if not e.reaction.get(aid):
                    raise ValueError("Реакция уже использована")
                e.reaction[aid] = False
                a.conditions.append("guard")
                event(events, "Защитная реакция подготовлена: −2 к следующему урону.")
            elif t == "recover":
                self.runtime.spend(e, "bonus_action")
                if a.resources.get("recovery", 0) <= 0:
                    raise ValueError("Восстановление уже использовано до отдыха")
                a.resources["recovery"] -= 1
                self.runtime.rules.heal(a, 4)
                event(events, "Бонусное действие: восстановлено до 4 HP.")
            elif t == "flee":
                distance = max(5, a.speed // 2)
                if e.movement < distance:
                    raise ValueError("Недостаточно перемещения для бегства")
                if not e.disengaged:
                    self.runtime.spend(e)
                a.conditions.append("fled")
                e.movement -= distance
                event(events, a.name + " покидает бой.", kind="flee")
                if not self.runtime.combat.ended(state, events):
                    self.runtime.combat.advance(state)
            else:
                self.runtime.spend(e)
                if t == "dodge":
                    a.conditions.append("dodge")
                elif t == "dash":
                    e.movement += self.runtime.rules.speed(a, state.ruleset)
                elif t == "disengage":
                    e.disengaged = True
                else:
                    ally = state.actor(c.target)
                    if (
                        state.relation(a.faction, ally.faction) != "ALLY"
                        or ally.id == aid
                        or ally.location != a.location
                        or (ally.hp <= 0)
                        or (abs(a.position - ally.position) > 5)
                    ):
                        raise ValueError("Нет союзника рядом")
                    if "helped" not in ally.conditions:
                        ally.conditions.append("helped")
                event(
                    events,
                    {
                        "dodge": "Уклонение до следующего хода.",
                        "dash": "Рывок: добавлено перемещение.",
                        "disengage": "Отход без атак реакцией.",
                        "help": "Помощь: преимущество следующей атаки союзника.",
                    }[t],
                )

    def attack(self, state, aid, target, weapon, events, reaction=False):
        a, t = self.runtime.combat.validate_attack(state, aid, target, weapon)
        if state.controllers[aid].controller == "PLAYER":
            advantage, sources = self.runtime.rules.conditions.advantage(
                a, state.ruleset, "attack", t, distance=abs(a.position - t.position)
            )
            self.runtime.rules.conditions.expire(a, state.ruleset, "attack")
            self.runtime.pending(
                state,
                "attack",
                aid,
                ability=a.attacks[weapon].ability,
                modifier=self.runtime.rules.attack_modifier(a, weapon),
                target=target,
                dc=t.armor_class,
                weapon=weapon,
                advantage=advantage,
                advantage_sources=sources,
                outcome="reaction" if reaction else "attack",
            )
            event(events, f"{a.name} атакует {t.name}. Брось кубик.", kind="pending")
        else:
            self.runtime.combat.npc_attack(state, aid, target, weapon, events)

    def initiative(self, state, events):
        s = state.session_state
        while s.initiative_waiting:
            aid = s.initiative_waiting.pop(0)
            a = state.actor(aid)
            modifier = self.runtime.rules.modifier(a.abilities["dexterity"])
            if state.controllers[aid].controller == "PLAYER":
                self.runtime.pending(
                    state, "initiative", aid, modifier=modifier, ability="dexterity"
                )
                event(events, a.name + ": брось инициативу.", kind="pending")
                return
            s.initiative_results[aid] = self.runtime.combat.roll(
                events, "1d20", modifier=modifier, purpose="initiative", actor=aid
            ).total
        definition = next(
            (x for x in state.definition.encounters if x.id == s.encounter_definition)
        )
        self.runtime.combat.start(
            state, definition, s.initiative_results.copy(), events
        )
        self.runtime.drive(state, events)

    def move(self, state, aid, distance, events):
        e = state.encounter
        a = state.actor(aid)
        if (
            not distance
            or abs(distance) > e.movement
            or self.runtime.rules.speed(a, state.ruleset) == 0
        ):
            raise ValueError("Недостаточно перемещения")
        new_position = a.position + distance
        if not e.disengaged:
            for oid in e.order:
                other = state.actor(oid)
                weapon = next(iter(other.attacks), "")
                if (
                    not state.hostile(aid, oid)
                    or not weapon
                    or other.hp <= 0
                    or self.runtime.rules.conditions.blocked(other, state.ruleset)
                    or (not e.reaction.get(oid))
                ):
                    continue
                reach = other.attacks[weapon].reach
                if reach > 5 or not abs(other.position - a.position) <= reach < abs(
                    other.position - new_position
                ):
                    continue
                if state.controllers[oid].controller == "PLAYER":
                    state.session_state.reaction = {
                        "actor": oid,
                        "mover": aid,
                        "distance": distance,
                        "weapon": weapon,
                    }
                    event(
                        events,
                        other.name + ": доступна атака реакцией.",
                        kind="reaction",
                    )
                    return
                e.reaction[oid] = False
                self.runtime.combat.npc_attack(state, oid, aid, weapon, events)
                if a.hp <= 0:
                    return
        for other in state.actors().values():
            if (
                other.condition_sources.get("grappled") == aid
                and abs(other.position - new_position) > 5
            ):
                other.conditions = [c for c in other.conditions if c != "grappled"]
                other.condition_sources.pop("grappled", None)
        a.position = new_position
        e.movement -= abs(distance)
        event(events, f"{a.name}: перемещение {distance} футов.", kind="move")

    def resume_reaction(self, state, events):
        r = state.session_state.reaction
        state.session_state.reaction = None
        if r and state.encounter:
            mover = state.actor(r["mover"])
            if mover.hp > 0:
                mover.position += r["distance"]
                state.encounter.movement -= abs(r["distance"])
                event(events, mover.name + " завершает перемещение.", kind="move")
            if not self.runtime.combat.ended(state, events):
                self.runtime.drive(state, events)

    def drive(self, state, events):
        for _ in range(250):
            self.runtime.spells_service.resume(state, events)
            if (
                not state.encounter
                or state.session_state.pending
                or state.session_state.reaction
                or self.runtime.combat.ended(state, events)
            ):
                return
            e = state.encounter
            aid = e.order[e.index]
            a = state.actor(aid)
            control = state.controllers[aid]
            if self.runtime.tactics_service.trigger_ready(state, events):
                return
            if a.hp > 0 and self.runtime.rules.conditions.blocked(a, state.ruleset):
                self.runtime.combat.advance(state)
                continue
            if set(a.conditions) & {"dead", "stable", "fled"}:
                self.runtime.combat.advance(state)
                continue
            if a.hp <= 0:
                if control.controller == "PLAYER":
                    self.runtime.pending(state, "death", aid, dc=10)
                    event(events, a.name + ": спасбросок от смерти.", kind="pending")
                    return
                roll = self.runtime.combat.roll(
                    events, "1d20", purpose="death", actor=aid
                )
                self.runtime.rules.death_save(a, roll)
                self.runtime.combat.advance(state)
                continue
            if control.controller == "PLAYER":
                return
            decision = self.runtime.ai.decision(state, aid)
            event(
                events,
                a.name
                + ": "
                + {
                    "Attack": "атака",
                    "EndTurn": "завершает ход",
                    "UseFeature": "применяет способность",
                    "CastSpell": "применяет магию",
                    "Move": "перемещается",
                    "Flee": "отступает",
                    "Heal": "лечится",
                }.get(decision.behavior, decision.behavior),
                kind="ai_decision",
                actor=aid,
                behavior=decision.behavior,
            )
            command = decision.command
            self.runtime.apply(state, command, aid, events)
        raise ValueError(
            "Превышен предел автоматических действий; состояние не изменено"
        )
