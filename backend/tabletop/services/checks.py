"""CheckService domain behavior."""

from ..rules import DifficultyResolver
from ..encounter import event
from .world import WorldService


class CheckService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t in ("check", "save"):
            self.runtime.check(state, c, a, events)

    def check(self, state, c, a, events):
        if c.check_id:
            from .universal import UniversalChecks

            return UniversalChecks(self.runtime).request(state, c, a, events)
        if c.type == "check":
            self.runtime.spend(state.encounter)
        dc = DifficultyResolver.resolve(state.ruleset, c.difficulty)
        target = getattr(c, "target", "")
        outcome = "check"
        ability = c.ability
        skill = getattr(c, "skill", "")
        if getattr(c, "purpose", "general") in ("search", "unlock"):
            candidates = [
                o
                for o in state.definition.objects
                if o.location_id == a.location and (not target or o.id == target)
            ]
            candidates = [
                o
                for o in candidates
                if not any(
                    (
                        e.loot_object == o.id and e.id not in state.completed_encounters
                        for e in state.definition.encounters
                    )
                )
            ]
            if not target:
                candidates = [
                    o
                    for o in candidates
                    if not state.objects[o.id].revealed
                    or not state.objects[o.id].opened
                ]
            if not candidates:
                event(events, "Поиск не обнаружил ничего нового.")
                state.game_time += 6 if state.encounter else 60
                return
            obj = candidates[0]
            target = obj.id
            outcome = (
                "unlock" if getattr(c, "purpose", "general") == "unlock" else "search"
            )
            if getattr(c, "purpose", "general") == "unlock" and (
                not state.objects[obj.id].revealed
            ):
                raise ValueError("Объект ещё не обнаружен")
            ability, skill = (obj.check_ability, obj.check_skill)
            dc = DifficultyResolver.resolve(state.ruleset, obj.difficulty, obj.dc)
        elif getattr(c, "purpose", "general") == "persuade":
            npc = state.actor(target)
            if npc.location != a.location or npc.hp <= 0:
                raise ValueError("Собеседник недоступен")
            secrets = [
                s
                for s in state.definition.secrets
                if s.id in npc.knowledge
                and s.disclosure == "persuasion"
                and (s.location_id == a.location)
                and (s.id not in state.player_knowledge)
            ]
            if (
                npc.attitude == "hostile"
                or state.hostile(a.id, npc.id)
                or (not secrets)
            ):
                event(
                    events,
                    "Собеседник не согласен на это требование. Бросок не может изменить его принципиальное решение.",
                    kind="refusal",
                )
                return
            ability, skill = ("charisma", "persuasion")
            outcome = "persuade"
            dc = DifficultyResolver.resolve(state.ruleset, secrets[0].difficulty)
            dc -= min(2, max(0, state.faction_reputation.get(npc.faction, 0)) // 2)
        elif target:
            raise ValueError("Для цели проверки укажи допустимое назначение")
        if c.type == "save" and (
            skill or getattr(c, "purpose", "general") != "general"
        ):
            raise ValueError("У спасброска нет навыка или произвольного последствия")
        modifier = (
            self.runtime.rules.save_modifier(a, ability)
            if c.type == "save"
            else self.runtime.rules.check_modifier(a, ability, skill, state.ruleset)
        )
        advantage, sources = self.runtime.rules.conditions.advantage(
            a, state.ruleset, c.type, ability=ability, skill=skill
        )
        self.runtime.pending(
            state,
            "save" if c.type == "save" else "check",
            a.id,
            advantage=advantage,
            advantage_sources=sources,
            ability=ability,
            skill=skill,
            modifier=modifier,
            dc=dc,
            target=target,
            outcome=outcome,
            reason=c.reason,
        )
        event(events, "Требуется проверка. Выполни бросок.", kind="pending")

    def resolve_roll(self, original, pending_id, player_id="local"):
        state = original.model_copy(deep=True)
        events = []
        p = state.session_state.pending
        if not p or p.id != pending_id:
            raise ValueError("Бросок уже выполнен или устарел")
        self.runtime.owned(state, p.actor, player_id)
        a = state.actor(p.actor)
        roll = self.runtime.combat.roll(
            events,
            p.expression,
            modifier=p.modifier,
            advantage=p.advantage,
            purpose=p.purpose,
            actor=p.actor,
            critical=p.critical,
            critical_rule=state.ruleset.critical,
        )
        if p.purpose in ("check", "save", "spell_save", "concentration"):
            events[-1].update(
                dc=p.dc, success=roll.total >= p.dc, ability=p.ability, skill=p.skill
            )
        if p.advantage_sources:
            events[-1]["sources"] = p.advantage_sources
        state.session_state.pending = None
        state.session_state.mode = p.resume
        if p.purpose in ("object_attack", "object_damage", "hazard_damage"):
            from ..object_actions import ObjectActions

            ObjectActions(self.runtime).resolve(state, p, roll, events)
        elif p.check_id:
            from .universal import UniversalChecks

            UniversalChecks(self.runtime).resolve(
                state, p.check_id, a, roll, events, dc=p.dc
            )
        elif p.purpose == "feature_healing":
            self.runtime.features_service.resolve_healing(state, p.target, roll, events)
        elif p.purpose.startswith("spell_") or p.purpose == "concentration":
            self.runtime.spells_service.resolve(
                state, p.purpose, p.actor, roll, p.dc, events
            )
        elif p.purpose == "initiative":
            state.session_state.initiative_results[p.actor] = roll.total
            self.runtime.initiative(state, events)
        elif p.purpose in ("check", "save"):
            success = roll.total >= p.dc
            event(
                events,
                "Успех." if success else "Проверка не пройдена.",
                kind="check",
                success=success,
            )
            if p.outcome in ("hide", "grapple", "shove", "escape"):
                self.runtime.tactics_service.resolve(
                    state, p.actor, p.outcome, p.target, success, events
                )
            elif p.outcome in ("search", "unlock"):
                obj = next((o for o in state.definition.objects if o.id == p.target))
                if success:
                    state.objects[obj.id].revealed = True
                    if p.outcome == "unlock":
                        state.objects[obj.id].unlocked = True
                    self.runtime.reveal_object(state, obj, events)
                    event(events, "Обнаружено: " + obj.name, kind="discovery")
                    if obj.trap_damage:
                        event(
                            events,
                            "Обнаружена ловушка; при взаимодействии потребуется спасбросок.",
                        )
            elif p.outcome == "persuade" and success:
                npc = state.actor(p.target)
                secret = next(
                    (
                        s
                        for s in state.definition.secrets
                        if s.id in npc.knowledge
                        and s.disclosure == "persuasion"
                        and (s.location_id == a.location)
                        and (s.id not in state.player_knowledge)
                    ),
                    None,
                )
                if secret:
                    npc.relationships[a.id] = min(5, npc.relationships.get(a.id, 0) + 1)
                    state.player_knowledge[secret.id] = secret.description
                    event(events, secret.description, kind="discovery")
            elif p.outcome == "trap":
                obj = next((o for o in state.definition.objects if o.id == p.target))
                status = state.objects[obj.id]
                status.trap_triggered = True
                status.opened = True
                if not success:
                    hazard = next(
                        (
                            c
                            for c in obj.components
                            if c.type in ("hazard", "trap") and c.damage_expression
                        ),
                        None,
                    )
                    if hazard:
                        self.runtime.pending(
                            state,
                            "hazard_damage",
                            a.id,
                            object_id=obj.id,
                            expression=hazard.damage_expression,
                            reason=obj.name,
                        )
                    else:
                        self.runtime.combat.damage(
                            state, a, obj.trap_damage, False, events
                        )
                self.runtime.reveal_object(state, obj, events)
            state.game_time += 6 if state.encounter else 60
        elif p.purpose == "attack":
            if self.runtime.rules.hit(roll, state.actor(p.target).armor_class):
                w = a.attacks[p.weapon]
                from ..resources import ResourceEngine

                mode = ResourceEngine.mode_effect(w, p.firing_mode)
                self.runtime.pending(
                    state,
                    "damage",
                    p.actor,
                    expression=mode.damage_expression or w.expression or f"1d{w.die}",
                    modifier=self.runtime.rules.damage_modifier(
                        a, p.weapon, state.ruleset
                    )
                    + mode.damage_bonus,
                    target=p.target,
                    weapon=p.weapon,
                    critical=roll.selected == 20,
                    outcome=p.outcome,
                )
                event(
                    events,
                    (
                        "Критическое попадание! Брось урон."
                        if roll.selected == 20
                        else "Попадание! Брось урон."
                    ),
                    kind="hit",
                )
            else:
                event(events, "Промах.", kind="miss")
                if p.outcome == "reaction":
                    self.runtime.resume_reaction(state, events)
        elif p.purpose == "damage":
            self.runtime.combat.damage(
                state,
                state.actor(p.target),
                roll.total,
                p.critical,
                events,
                a.attacks[p.weapon].damage_type if p.weapon in a.attacks else "",
            )
            if state.encounter:
                self.runtime.combat.ended(state, events)
            if p.outcome == "reaction":
                self.runtime.resume_reaction(state, events)
        elif p.purpose == "death":
            self.runtime.rules.death_save(a, roll)
            event(
                events,
                f"{a.name}: {a.death_successes} успехов / {a.death_failures} провалов.",
                kind="death",
            )
            if a.hp == 0 and state.encounter:
                self.runtime.combat.advance(state)
        self.runtime.spells_service.resume(state, events)
        if state.encounter and (not state.session_state.pending):
            self.runtime.drive(state, events)
        if not state.encounter and (not state.session_state.pending):
            for aid in state.party:
                actor = state.actor(aid)
                if (
                    actor.hp == 0
                    and (not set(actor.conditions) & {"dead", "stable"})
                    and (state.controllers[aid].controller == "PLAYER")
                ):
                    self.runtime.pending(state, "death", aid, dc=10)
                    event(
                        events, actor.name + ": спасбросок от смерти.", kind="pending"
                    )
                    break
        self.runtime.progression_service.reconcile(state, events)
        WorldService.advance(state, events)
        from ..effects import EffectsEngine

        EffectsEngine.expire(state)
        from ..events import state_changes

        state_changes(original, state, events)
        return (self.runtime.validate(state), events)
