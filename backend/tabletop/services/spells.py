"""Canonical casting queue: costs once, rolls in DiceEngine, resumable per target."""

import re
from ..spells import SpellCastState, ActiveConcentration, SpellSlotState
from ..encounter import event


class SpellService:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def choices(build, rules):
        casting = rules.spellcasting.get(build.character_class)
        if not casting:
            if build.spells or build.prepared_spells:
                raise ValueError("Класс не владеет магией")
            return [], []
        known = build.spells if build.spells is not None else casting.defaults
        if len(known) != len(set(known)) or len(known) > casting.known:
            raise ValueError("Неверное число известных заклинаний")
        if any(
            i not in rules.spells
            or build.character_class not in rules.spells[i].classes
            or rules.spells[i].level > 1
            for i in known
        ):
            raise ValueError("Заклинание недоступно на первом уровне")
        prepared = (
            build.prepared_spells
            if build.prepared_spells is not None
            else [i for i in known if rules.spells[i].level > 0][: casting.prepared]
        )
        if (
            len(prepared) != len(set(prepared))
            or len(prepared) > casting.prepared
            or not set(prepared) <= set(known)
        ):
            raise ValueError("Некорректные подготовленные заклинания")
        return list(known), list(prepared)

    @staticmethod
    def initialize(actor, build, rules):
        actor.spells, actor.prepared_spells = SpellService.choices(build, rules)
        casting = rules.spellcasting.get(actor.character_class)
        if casting:
            actor.spell_slots = {
                level: SpellSlotState(maximum=count, remaining=count)
                for level, count in casting.slots.items()
            }

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        casting = state.ruleset.spellcasting.get(a.character_class)
        if not casting:
            raise ValueError("Персонаж не владеет магией")
        if c.type == "prepare_spells":
            if (
                state.encounter
                or len(c.spells) > casting.prepared + (a.level - 1)
                or len(c.spells) != len(set(c.spells))
                or not set(c.spells) <= set(a.spells)
            ):
                raise ValueError(
                    "Подготовить заклинания можно вне боя в допустимом количестве"
                )
            a.prepared_spells = list(c.spells)
            state.game_time += 60
            event(events, "Заклинания подготовлены.", kind="prepare_spells")
            return
        spell = state.ruleset.spells.get(c.spell_id)
        if (
            not spell
            or spell.id not in a.spells
            or (spell.level and spell.id not in a.prepared_spells)
        ):
            raise ValueError("Заклинание не известно или не подготовлено")
        level = c.slot_level or spell.level
        if spell.level == 0 and level != 0:
            raise ValueError("Заговор не расходует ячейку")
        if level < spell.level or (
            level
            and (
                str(level) not in a.spell_slots
                or a.spell_slots[str(level)].remaining <= 0
            )
        ):
            raise ValueError("Подходящая ячейка недоступна")
        target = state.actor(c.target) if c.target else a
        if (
            target.location != a.location
            or "dead" in target.conditions
            or abs(target.position - a.position) > spell.range
        ):
            raise ValueError("Цель заклинания вне досягаемости")
        if spell.target_type == "self" and target.id != aid:
            raise ValueError("Нужна цель: сам заклинатель")
        if (
            spell.target_type == "ally"
            and state.relation(a.faction, target.faction) != "ALLY"
        ):
            raise ValueError("Нужна союзная цель")
        if spell.target_type in ("enemy", "area") and (
            not state.encounter
            or target.id not in state.encounter.order
            or target.hp <= 0
        ):
            raise ValueError("Боевому заклинанию нужна цель в столкновении")
        if spell.target_type == "enemy" and not state.hostile(aid, target.id):
            raise ValueError("Нужна враждебная цель")
        targets = [target.id]
        if spell.target_type == "area":
            targets = [
                i
                for i in state.encounter.order
                if state.actor(i).hp > 0
                and abs(state.actor(i).position - target.position) <= spell.area
            ]
        self.runtime.spend(
            state.encounter,
            "bonus_action" if spell.casting_time == "BONUS_ACTION" else "action",
        )
        if level:
            a.spell_slots[str(level)].remaining -= 1
        if spell.concentration:
            self.end_concentration(state, aid, events)
            a.concentration = ActiveConcentration(
                spell_id=spell.id,
                targets=targets,
                expires_at=state.game_time + spell.duration * 6,
            )
        state.session_state.spell_cast = SpellCastState(
            caster=aid, spell_id=spell.id, slot_level=level, targets=targets
        )
        event(
            events,
            f"{a.name}: {spell.name}.",
            kind="cast_spell",
            actor=aid,
            spell_id=spell.id,
            slot_level=level,
            targets=targets,
        )
        self.resume(state, events)

    def end_concentration(self, state, aid, events):
        actor = state.actor(aid)
        active = actor.concentration
        if not active:
            return
        spell = state.ruleset.spells[active.spell_id]
        for target_id in active.targets:
            target = state.actor(target_id)
            for condition in spell.effects:
                if target.condition_sources.get(condition) == aid:
                    target.conditions = [c for c in target.conditions if c != condition]
                    target.condition_sources.pop(condition, None)
                    target.condition_expiry.pop(condition, None)
        actor.concentration = None
        event(
            events,
            actor.name + ": концентрация завершена.",
            kind="concentration_end",
            actor=aid,
        )

    def expire(self, state, events):
        for a in state.actors().values():
            if a.concentration and (
                a.concentration.expires_at <= state.game_time
                or a.hp <= 0
                or self.runtime.rules.conditions.blocked(a, state.ruleset)
            ):
                self.end_concentration(state, a.id, events)
            for condition, end in list(a.condition_expiry.items()):
                if end <= state.game_time:
                    a.conditions = [c for c in a.conditions if c != condition]
                    a.condition_expiry.pop(condition, None)
                    a.condition_sources.pop(condition, None)

    def modifier(self, state, actor):
        return self.runtime.rules.modifier(
            actor.abilities[state.ruleset.spellcasting[actor.character_class].ability]
        )

    def roll_or_pending(self, state, events, purpose, aid, **kwargs):
        if state.controllers[aid].controller == "PLAYER":
            self.runtime.pending(state, purpose, aid, **kwargs)
            event(events, "Магия требует броска.", kind="pending")
            return None
        return self.runtime.combat.roll(
            events,
            kwargs.get("expression", "1d20"),
            modifier=kwargs.get("modifier", 0),
            advantage=kwargs.get("advantage", 0),
            critical=kwargs.get("critical", False),
            critical_rule=state.ruleset.critical,
            purpose=purpose,
            actor=aid,
        )

    def resume(self, state, events):
        self.expire(state, events)
        session = state.session_state
        while not session.pending:
            if session.concentration_checks:
                check = session.concentration_checks.pop(0)
                a = state.actor(check["actor"])
                if not a.concentration:
                    continue
                advantage, sources = self.runtime.rules.conditions.advantage(
                    a, state.ruleset, "save", ability="constitution"
                )
                roll = self.roll_or_pending(
                    state,
                    events,
                    "concentration",
                    a.id,
                    ability="constitution",
                    modifier=self.runtime.rules.save_modifier(a, "constitution"),
                    dc=check["dc"],
                    advantage=advantage,
                    advantage_sources=sources,
                )
                if roll is None:
                    return
                if roll.total < check["dc"]:
                    self.end_concentration(state, a.id, events)
                continue
            cast = session.spell_cast
            if not cast:
                return
            if cast.index >= len(cast.targets):
                session.spell_cast = None
                event(events, "Заклинание разрешено.", kind="spell_complete")
                continue
            a, target = state.actor(cast.caster), state.actor(cast.targets[cast.index])
            spell = state.ruleset.spells[cast.spell_id]
            if "dead" in target.conditions:
                cast.index += 1
                cast.stage = "target"
                continue
            if cast.stage == "target":
                cast.saved = cast.critical = False
                if spell.attack_roll:
                    adv, sources = self.runtime.rules.conditions.advantage(
                        a,
                        state.ruleset,
                        "attack",
                        target,
                        distance=abs(a.position - target.position),
                    )
                    self.runtime.rules.conditions.expire(a, state.ruleset, "attack")
                    roll = self.roll_or_pending(
                        state,
                        events,
                        "spell_attack",
                        a.id,
                        modifier=self.modifier(state, a)
                        + a.proficiency_bonus
                        + self.runtime.rules.conditions.bonus(a, "attack_bonus"),
                        dc=target.armor_class,
                        target=target.id,
                        advantage=adv,
                        advantage_sources=sources,
                    )
                    if roll is None:
                        return
                    self.resolve(
                        state, "spell_attack", a.id, roll, target.armor_class, events
                    )
                    continue
                if spell.save:
                    adv, sources = self.runtime.rules.conditions.advantage(
                        target, state.ruleset, "save", ability=spell.save
                    )
                    dc = 8 + a.proficiency_bonus + self.modifier(state, a)
                    roll = self.roll_or_pending(
                        state,
                        events,
                        "spell_save",
                        target.id,
                        modifier=self.runtime.rules.save_modifier(target, spell.save),
                        dc=dc,
                        ability=spell.save,
                        target=a.id,
                        advantage=adv,
                        advantage_sources=sources,
                    )
                    if roll is None:
                        return
                    self.resolve(state, "spell_save", target.id, roll, dc, events)
                    continue
                cast.stage = "effect"
            expression = spell.damage or spell.healing
            if expression:
                match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", expression)
                dice = int(match[1]) + spell.upcast * max(
                    0, cast.slot_level - spell.level
                )
                if spell.level == 0:
                    dice *= 1 + (a.level >= 5) + (a.level >= 11) + (a.level >= 17)
                expression = f"{dice}d{match[2]}{match[3] or ''}"
                purpose = "spell_damage" if spell.damage else "spell_healing"
                roll = self.roll_or_pending(
                    state,
                    events,
                    purpose,
                    a.id,
                    expression=expression,
                    modifier=self.modifier(state, a) if spell.healing else 0,
                    critical=cast.critical,
                    target=target.id,
                )
                if roll is None:
                    return
                self.resolve(state, purpose, a.id, roll, 0, events)
            else:
                self.apply_effects(state, events)

    def resolve(self, state, purpose, aid, roll, dc, events):
        if purpose == "concentration":
            if roll.total < dc:
                self.end_concentration(state, aid, events)
            return
        cast = state.session_state.spell_cast
        if not cast:
            raise ValueError("Нет ожидающего заклинания")
        spell = state.ruleset.spells[cast.spell_id]
        target = state.actor(cast.targets[cast.index])
        if purpose == "spell_attack":
            if not self.runtime.rules.hit(roll, target.armor_class):
                event(events, "Заклинание промахнулось.", kind="miss")
                cast.index += 1
            else:
                cast.critical = roll.selected == 20
                cast.stage = "effect"
        elif purpose == "spell_save":
            cast.saved = roll.total >= dc
            event(
                events,
                "Спасбросок успешен." if cast.saved else "Спасбросок провален.",
                kind="spell_save",
                target=target.id,
                success=cast.saved,
            )
            if cast.saved and not spell.half_on_save:
                cast.index += 1
            else:
                cast.stage = "effect"
        else:
            if purpose == "spell_damage":
                self.runtime.combat.damage(
                    state,
                    target,
                    roll.total // 2 if cast.saved else roll.total,
                    cast.critical,
                    events,
                )
            elif purpose == "spell_healing":
                healed = self.runtime.rules.heal(target, roll.total)
                event(
                    events,
                    f"{target.name}: восстановлено {healed} HP.",
                    kind="healing",
                    amount=healed,
                    target=target.id,
                )
            self.apply_effects(state, events)

    def apply_effects(self, state, events):
        cast = state.session_state.spell_cast
        spell = state.ruleset.spells[cast.spell_id]
        target = state.actor(cast.targets[cast.index])
        if not cast.saved:
            for condition in spell.effects:
                if condition not in target.conditions:
                    target.conditions.append(condition)
                target.condition_sources[condition] = cast.caster
                target.condition_expiry[condition] = (
                    state.game_time + spell.duration * 6
                )
        cast.index += 1
        cast.stage = "target"
