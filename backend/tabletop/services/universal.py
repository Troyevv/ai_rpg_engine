"""Authored, reference-validated consequences; the DM selects checks, never outcomes."""

from ..encounter import event


class UniversalChecks:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def eligible(state, c, actor):
        return (
            c.location_id == actor.location
            and c.id not in state.resolved_checks
            and (
                not c.background_tags
                or bool(set(c.background_tags) & set(actor.background_tags))
            )
            and (not c.actor_id or state.actor(c.actor_id).location == actor.location)
        )

    def request(self, state, command, actor, events):
        c = next((c for c in state.definition.checks if c.id == command.check_id), None)
        if not c or not self.eligible(state, c, actor) or c.passive:
            raise ValueError("Проверка недоступна в текущей сцене")
        if c.save != (command.type == "save"):
            raise ValueError("Неверный тип проверки")
        self.runtime.spend(state.encounter)
        modifier = (
            self.runtime.rules.save_modifier(actor, c.ability)
            if c.save
            else self.runtime.rules.check_modifier(
                actor, c.ability, c.skill, state.ruleset
            )
        )
        advantage, sources = self.runtime.rules.conditions.advantage(
            actor,
            state.ruleset,
            "save" if c.save else "check",
            ability=c.ability,
            skill=c.skill,
        )
        dc = state.ruleset.difficulty[c.difficulty]
        if c.category == "stealth" and c.actor_id:
            enemy = state.actor(c.actor_id)
            dc = max(
                dc,
                10
                + self.runtime.rules.check_modifier(
                    enemy, "wisdom", "perception", state.ruleset
                ),
            )
        self.runtime.pending(
            state,
            "save" if c.save else "check",
            actor.id,
            check_id=c.id,
            ability=c.ability,
            skill=c.skill,
            dc=dc,
            modifier=modifier,
            reason=c.description or c.name,
            advantage=advantage,
            advantage_sources=sources,
        )
        event(events, c.name, kind="pending", check_id=c.id)

    def resolve(self, state, check_id, actor, roll, events, dc=None):
        c = next(c for c in state.definition.checks if c.id == check_id)
        target_dc = dc if dc is not None else state.ruleset.difficulty[c.difficulty]
        if dc is None and c.category == "stealth" and c.actor_id:
            enemy = state.actor(c.actor_id)
            target_dc = max(
                target_dc,
                10
                + self.runtime.rules.check_modifier(
                    enemy, "wisdom", "perception", state.ruleset
                ),
            )
        success = roll.total >= target_dc
        outcome = "SUCCESS" if success else "FAILURE"
        effects = c.success if success else c.failure
        if roll.selected == 20 and c.critical_success is not None:
            outcome = "CRITICAL_SUCCESS"
            effects = c.critical_success
        elif roll.selected == 1 and c.critical_failure is not None:
            outcome = "CRITICAL_FAILURE"
            effects = c.critical_failure
        elif (
            not success
            and c.partial_margin
            and roll.total >= target_dc - c.partial_margin
        ):
            outcome = "PARTIAL_SUCCESS"
            effects = c.partial
        for e in reversed(events):
            if e.get("roll"):
                e.update(
                    outcome=outcome,
                    success=outcome
                    in ("SUCCESS", "CRITICAL_SUCCESS", "PARTIAL_SUCCESS"),
                )
                break
        state.resolved_checks[c.id] = outcome
        for effect in effects:
            if effect.type == "reveal_secret":
                secret = next(
                    s for s in state.definition.secrets if s.id == effect.target
                )
                state.player_knowledge[secret.id] = secret.description
                event(events, secret.description, kind="discovery")
            elif effect.type == "reveal_object":
                state.objects[effect.target].revealed = True
            elif effect.type == "attitude":
                npc = state.actor(effect.target)
                before = npc.attitude
                npc.attitude = effect.attitude
                event(
                    events,
                    f"{npc.name}: отношение изменилось.",
                    kind="attitude",
                    target=npc.id,
                    before=before,
                    after=npc.attitude,
                )
            elif effect.type == "alert":
                if effect.target not in state.alerted_actors:
                    state.alerted_actors.append(effect.target)
                state.actor(effect.target).current_intent = "Ищет нарушителя"
                event(
                    events,
                    f"{state.actor(effect.target).name} насторожился.",
                    kind="alert",
                )
            elif effect.type == "move":
                for aid in state.party:
                    state.actor(aid).location = effect.target
                    state.actor(aid).position = 0
                if effect.target not in state.known_locations:
                    state.known_locations.append(effect.target)
            elif effect.type == "damage":
                self.runtime.combat.damage(state, actor, effect.amount, False, events)
            elif effect.type == "prone" and "prone" not in actor.conditions:
                actor.conditions.append("prone")
        event(
            events,
            c.name
            + ": "
            + {
                "SUCCESS": "успех",
                "FAILURE": "неудача",
                "CRITICAL_SUCCESS": "критический успех",
                "CRITICAL_FAILURE": "критическая неудача",
                "PARTIAL_SUCCESS": "частичный успех",
            }[outcome],
            kind="check_outcome",
            outcome=outcome,
            check_id=c.id,
            success=outcome in ("SUCCESS", "CRITICAL_SUCCESS", "PARTIAL_SUCCESS"),
        )

    def passive(self, state, events):
        from types import SimpleNamespace

        actor = state.actor(state.session_state.controlled_actor)
        for c in state.definition.checks:
            if c.passive and self.eligible(state, c, actor):
                total = 10 + self.runtime.rules.check_modifier(
                    actor, c.ability, c.skill, state.ruleset
                )
                self.resolve(
                    state,
                    c.id,
                    actor,
                    SimpleNamespace(total=total, selected=10),
                    events,
                )
