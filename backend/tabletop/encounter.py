"""Faction-agnostic encounter queue and combat primitives."""

from .models import Encounter


def event(events, text, **details):
    events.append({"text": text, **details})


class EncounterEngine:
    def __init__(self, dice, rules):
        self.dice, self.rules = dice, rules

    def roll(self, events, expression, **kwargs):
        roll = self.dice.roll(expression, **kwargs)
        event(events, f"Бросок: {roll.total}", roll=roll.as_dict())
        return roll

    def start(self, state, definition, results, events):
        order = sorted(
            results,
            key=lambda i: (-results[i], -state.actor(i).abilities["dexterity"], i),
        )
        state.encounters[definition.id] = Encounter(
            definition_id=definition.id,
            order=order,
            initiative=results,
            reaction={i: True for i in order},
        )
        state.active_encounter = definition.id
        state.session_state.mode = "ENCOUNTER"
        state.session_state.turn_started = False
        self.reset_turn(state)
        event(events, "Столкновение началось. Определена инициатива.", kind="encounter")

    @staticmethod
    def reset_turn(state):
        from .effects import EffectsEngine

        EffectsEngine.expire(state)
        e = state.encounter
        a = state.actor(e.order[e.index])
        e.action = e.bonus_action = e.free_interaction = True
        e.ready.pop(a.id, None)
        e.attacks_remaining = 0
        e.disengaged = False
        from .conditions import ConditionEngine

        for condition, until in list(a.condition_expiry.items()):
            if until <= state.game_time:
                a.conditions = [c for c in a.conditions if c != condition]
                a.condition_expiry.pop(condition, None)
                a.condition_sources.pop(condition, None)
        e.movement = ConditionEngine.speed(a, state.ruleset)
        e.reaction[a.id] = True
        ConditionEngine.expire(a, state.ruleset, "turn_start")
        state.session_state.turn_started = False

    def advance(self, state):
        e = state.encounter
        e.index = (e.index + 1) % len(e.order)
        if e.index == 0:
            e.round += 1
            state.game_time += 6
        self.reset_turn(state)

    def ended(self, state, events):
        e = state.encounter
        if not e:
            return True
        active = [
            i
            for i in e.order
            if (
                state.actor(i).hp > 0
                or state.controllers[i].controller == "PLAYER"
                and "stable" not in state.actor(i).conditions
            )
            and not set(state.actor(i).conditions) & {"dead", "fled", "surrendered"}
        ]
        if any(state.hostile(a, b) for a in active for b in active):
            return False
        party_here = set(state.party) & set(e.order)
        surviving = set(active) & party_here
        escaped = {i for i in party_here if "fled" in state.actor(i).conditions}
        e.outcome = "victory" if surviving else "flee" if escaped else "defeat"
        state.active_encounter = None
        state.session_state.mode = "EXPLORATION"
        state.session_state.reaction = None
        state.session_state.pending = None
        if e.outcome == "victory" and e.definition_id not in state.completed_encounters:
            state.completed_encounters.append(e.definition_id)
        for aid in e.order:
            self.rules.conditions.expire(state.actor(aid), state.ruleset, "encounter")
            state.actor(aid).conditions = [
                c for c in state.actor(aid).conditions if c != "fled"
            ]
        definition = next(
            x for x in state.definition.encounters if x.id == e.definition_id
        )
        if e.outcome == "victory":
            if definition.loot_object:
                state.objects[definition.loot_object].revealed = True
            if definition.quest_id:
                state.quests[definition.quest_id] = "completed"
        event(
            events,
            {
                "victory": "Победа. Можно осмотреть добычу.",
                "flee": "Участники покинули бой.",
                "defeat": "Партия выведена из боя.",
            }[e.outcome],
            kind="encounter_end",
            outcome=e.outcome,
        )
        return True

    def validate_attack(self, state, actor_id, target_id, weapon, mode="single"):
        a, t = state.actor(actor_id), state.actor(target_id)
        self.rules.attack_modifier(a, weapon)
        if (
            not state.hostile(a.id, t.id)
            or t.hp <= 0
            or "fled" in t.conditions
            or a.location != t.location
        ):
            raise ValueError("Цель атаки недоступна")
        if not state.encounter or t.id not in state.encounter.order:
            raise ValueError("Цель не участвует в бою")
        if abs(a.position - t.position) > a.attacks[weapon].reach:
            raise ValueError("Цель вне досягаемости")
        from .resources import ResourceEngine

        ResourceEngine.validate_attack(a, a.attacks[weapon], mode)
        return a, t

    def damage(self, state, target, amount, critical, events, damage_type=""):
        if "guard" in target.conditions:
            amount = max(0, amount - 2)
            target.conditions.remove("guard")
            event(events, "Защитная реакция поглощает 2 урона.")
        if any(
            c.resistance
            for c in self.rules.conditions.definitions(target, state.ruleset)
        ):
            amount //= 2
        from math import floor

        amount = max(0, floor(amount * target.damage_modifiers.get(damage_type, 1)))
        before = target.hp
        dealt = self.rules.damage(target, amount, critical)
        if dealt and target.concentration:
            state.session_state.concentration_checks.append(
                {"actor": target.id, "dc": max(10, amount // 2)}
            )
        for actor in [
            state.actor(i)
            for i in (state.encounter.order if state.encounter else state.party)
        ]:
            if actor.condition_sources.get("grappled") == target.id and target.hp <= 0:
                actor.conditions = [c for c in actor.conditions if c != "grappled"]
                actor.condition_sources.pop("grappled", None)
        event(
            events,
            f"{target.name}: получено {dealt} урона.",
            kind="damage",
            target=target.id,
            amount=dealt,
            hp_before=before,
            hp_after=target.hp,
            maximum=target.max_hp,
            critical=critical,
        )
        return dealt

    def npc_attack(self, state, actor_id, target_id, weapon, events, mode="single"):
        a, t = self.validate_attack(state, actor_id, target_id, weapon, mode)
        from .resources import ResourceEngine

        ResourceEngine.spend_attack(a, a.attacks[weapon], mode)
        advantage, sources = self.rules.conditions.advantage(
            a, state.ruleset, "attack", t, distance=abs(a.position - t.position)
        )
        self.rules.conditions.expire(a, state.ruleset, "attack")
        if sources:
            event(
                events,
                "Источники преимущества/помехи.",
                kind="advantage",
                sources=sources,
            )
        roll = self.roll(
            events,
            "1d20",
            modifier=self.rules.attack_modifier(a, weapon)
            + ResourceEngine.mode_effect(a.attacks[weapon], mode).attack_bonus,
            advantage=advantage,
            purpose="attack",
            actor=a.id,
        )
        if self.rules.hit(roll, t.armor_class):
            w = a.attacks[weapon]
            damage = self.roll(
                events,
                ResourceEngine.mode_effect(w, mode).damage_expression
                or w.expression
                or f"1d{w.die}",
                modifier=self.rules.damage_modifier(a, weapon, state.ruleset)
                + ResourceEngine.mode_effect(w, mode).damage_bonus,
                critical=roll.selected == 20,
                critical_rule=state.ruleset.critical,
                purpose="damage",
                actor=a.id,
            )
            self.damage(
                state, t, damage.total, roll.selected == 20, events, w.damage_type
            )
        else:
            event(events, f"{a.name} промахивается.", kind="miss")
