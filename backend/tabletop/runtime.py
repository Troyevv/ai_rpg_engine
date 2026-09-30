"""Validated commands are the only path to a new canonical snapshot."""

from uuid import uuid4
from .models import GameState, Command, PendingRoll, ObjectState
from .definitions import InventoryEntry, WorldObject
from .dice import DiceEngine
from .rules import RulesEngine, DifficultyResolver
from .encounter import EncounterEngine, event
from .ai import GameAI


class TabletopRuntime:
    def __init__(self, dice=None):
        self.dice = dice or DiceEngine()
        self.rules = RulesEngine()
        self.combat = EncounterEngine(self.dice, self.rules)
        self.ai = GameAI()

    @staticmethod
    def validate(state):
        return GameState.model_validate(state.model_dump())

    @staticmethod
    def spend(e, slot="action"):
        if e:
            if not getattr(e, slot):
                raise ValueError("Это действие уже использовано")
            setattr(e, slot, False)

    @staticmethod
    def owned(state, actor_id, player_id="local"):
        if actor_id not in state.controllers:
            raise ValueError("Участник не найден")
        c = state.controllers[actor_id]
        if c.controller != "PLAYER" or c.player_id != player_id:
            raise ValueError("Этот персонаж не принадлежит твоему контроллеру")
        return state.actor(actor_id)

    def pending(self, state, purpose, actor, **kwargs):
        c = state.controllers[actor]
        state.session_state.pending = PendingRoll(
            id=uuid4().hex,
            purpose=purpose,
            actor=actor,
            controller=c.controller,
            player_id=c.player_id,
            resume=(
                "ENCOUNTER"
                if state.encounter
                else (
                    "DIALOGUE"
                    if state.session_state.mode == "DIALOGUE"
                    else "EXPLORATION"
                )
            ),
            **kwargs,
        )
        state.session_state.mode = "AWAITING_ROLL"

    def execute(self, original, command, player_id="local"):
        state = original.model_copy(deep=True)
        events = []
        aid = command.actor_id or state.session_state.controlled_actor
        self.owned(state, aid, player_id)
        if state.session_state.pending:
            raise ValueError("Сначала выполни ожидающий бросок")
        if state.session_state.reaction:
            if command.type not in ("reaction_attack", "decline_reaction"):
                raise ValueError("Сначала реши, использовать ли реакцию")
            reaction = state.session_state.reaction
            if reaction["actor"] != aid:
                raise ValueError("Реакция принадлежит другому участнику")
            state.encounter.reaction[aid] = False
            if command.type == "decline_reaction":
                self.resume_reaction(state, events)
            else:
                self.attack(
                    state,
                    aid,
                    reaction["mover"],
                    reaction["weapon"],
                    events,
                    reaction=True,
                )
        else:
            self.apply(state, command, aid, events)
            if state.encounter and not state.session_state.pending:
                self.drive(state, events)
        return self.validate(state), events

    def apply(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "select_actor":
            self.owned(state, c.target)
            state.session_state.controlled_actor = c.target
            event(events, "Выбран персонаж: " + state.actor(c.target).name)
            return
        if (
            a.hp <= 0 and not (t == "rest" and "stable" in a.conditions and not e)
        ) or set(a.conditions) & {"dead", "fled"}:
            raise ValueError("Персонаж сейчас не может действовать")
        if e and t != "guard" and e.order[e.index] != aid:
            raise ValueError("Сейчас ход другого участника")
        if t == "look":
            location = next(x for x in state.definition.locations if x.id == a.location)
            event(events, location.description or location.name, kind="look")
            state.game_time += 6
        elif t == "start_encounter":
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
            if not any(state.hostile(i, j) for i in ids for j in ids):
                raise ValueError("Между участниками нет вражды")
            state.session_state.initiative_waiting = ids
            state.session_state.initiative_results = {}
            state.session_state.encounter_definition = definition.id
            self.initiative(state, events)
        elif t == "attack":
            if not e:
                raise ValueError("Сначала начни столкновение")
            self.spend(e)
            self.attack(state, aid, c.target, c.weapon or next(iter(a.attacks)), events)
        elif t == "move":
            if e:
                self.move(state, aid, c.distance, events)
            else:
                loc = next(x for x in state.definition.locations if x.id == a.location)
                if c.target not in loc.connections:
                    raise ValueError("Нет пути в эту локацию")
                source = a.location
                for i in state.party:
                    if state.actor(i).location == source:
                        state.actor(i).location = c.target
                        state.actor(i).position = 0
                if c.target not in state.known_locations:
                    state.known_locations.append(c.target)
                state.session_state.mode = "EXPLORATION"
                state.session_state.dialogue_actor = None
                state.game_time += 300
                event(events, "Переход: " + state.locations[c.target], kind="travel")
        elif t in ("check", "save"):
            self.check(state, c, a, events)
        elif t == "interact":
            self.interact(state, a, c.target, events)
        elif t == "dialogue":
            npc = state.actor(c.target)
            if npc.id == a.id or npc.location != a.location or npc.hp <= 0:
                raise ValueError("Собеседник недоступен")
            if e and state.hostile(a.id, npc.id):
                raise ValueError("Противник сейчас ведёт бой")
            state.session_state.dialogue_actor = npc.id
            if not e:
                state.session_state.mode = "DIALOGUE"
            event(
                events,
                f"{a.name} обращается к {npc.name}.",
                kind="dialogue",
                speaker=npc.id,
            )
            for lore in npc.public_lore:
                if lore not in state.player_knowledge.values():
                    state.player_knowledge["lore_" + uuid4().hex] = lore
                    event(events, lore, kind="discovery")
            for q in state.definition.quests:
                if q.giver_id == npc.id:
                    if state.quests[q.id] == "available":
                        state.quests[q.id] = "active"
                        event(events, "Получено задание: " + q.name, kind="quest")
                    elif (
                        state.quests[q.id] == "active"
                        and q.required_item
                        and self.entry(a, q.required_item)
                    ):
                        self.remove(a.inventory, q.required_item, 1)
                        state.quests[q.id] = "completed"
                        for reward in q.reward:
                            self.add(a.inventory, reward.item_id, reward.quantity)
                        event(
                            events,
                            "Задание выполнено: " + q.name,
                            kind="quest_complete",
                        )
            state.game_time += 60
        elif t in ("take_item", "drop_item", "equip", "unequip", "use_item"):
            self.inventory(state, c, a, events)
        elif t == "end_turn":
            if not e:
                raise ValueError("Сейчас нет боя")
            self.combat.advance(state)
        elif t in ("dodge", "dash", "disengage", "help", "guard", "recover", "flee"):
            if not e:
                raise ValueError("Действие доступно только в бою")
            if t == "guard":
                if not e.reaction.get(aid):
                    raise ValueError("Реакция уже использована")
                e.reaction[aid] = False
                a.conditions.append("guard")
                event(events, "Защитная реакция подготовлена: −2 к следующему урону.")
            elif t == "recover":
                self.spend(e, "bonus_action")
                if a.resources.get("recovery", 0) <= 0:
                    raise ValueError("Восстановление уже использовано до отдыха")
                a.resources["recovery"] -= 1
                self.rules.heal(a, 4)
                event(events, "Бонусное действие: восстановлено до 4 HP.")
            elif t == "flee":
                distance = max(5, a.speed // 2)
                if e.movement < distance:
                    raise ValueError("Недостаточно перемещения для бегства")
                if not e.disengaged:
                    self.spend(e)
                a.conditions.append("fled")
                e.movement -= distance
                event(events, a.name + " покидает бой.", kind="flee")
                if not self.combat.ended(state, events):
                    self.combat.advance(state)
            else:
                self.spend(e)
                if t == "dodge":
                    a.conditions.append("dodge")
                elif t == "dash":
                    e.movement += a.speed
                elif t == "disengage":
                    e.disengaged = True
                else:
                    ally = state.actor(c.target)
                    if (
                        state.relation(a.faction, ally.faction) != "ALLY"
                        or ally.id == aid
                        or ally.location != a.location
                        or ally.hp <= 0
                        or abs(a.position - ally.position) > 5
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
        elif t == "rest":
            if e:
                raise ValueError("Во время боя отдых невозможен")
            if c.rest == "short":
                if a.resources.get("hit_dice", 0) <= 0:
                    raise ValueError("Кости здоровья закончились")
                a.resources["hit_dice"] -= 1
                self.rules.heal(
                    a, max(1, 5 + self.rules.modifier(a.abilities["constitution"]))
                )
            else:
                for i in state.party:
                    ally = state.actor(i)
                    if ally.location == a.location and "dead" not in ally.conditions:
                        self.rules.heal(ally, ally.max_hp)
                        ally.resources.update(hit_dice=ally.level, recovery=1)
            state.game_time += (
                state.ruleset.short_rest_minutes
                if c.rest == "short"
                else state.ruleset.long_rest_minutes
            ) * 60
            event(events, "Отдых завершён.", kind="rest")
        else:
            raise ValueError("Команда требует отдельного обработчика")

    def check(self, state, c, a, events):
        if c.type == "check":
            self.spend(state.encounter)
        dc = DifficultyResolver.resolve(state.ruleset, c.difficulty)
        target = c.target
        outcome = "check"
        ability = c.ability
        skill = c.skill
        if c.purpose in ("search", "unlock"):
            candidates = [
                o
                for o in state.definition.objects
                if o.location_id == a.location and (not target or o.id == target)
            ]
            candidates = [
                o
                for o in candidates
                if not any(
                    e.loot_object == o.id and e.id not in state.completed_encounters
                    for e in state.definition.encounters
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
                state.game_time += 60
                return
            obj = candidates[0]
            target = obj.id
            outcome = "unlock" if c.purpose == "unlock" else "search"
            if c.purpose == "unlock" and not state.objects[obj.id].revealed:
                raise ValueError("Объект ещё не обнаружен")
            ability, skill = obj.check_ability, obj.check_skill
            dc = DifficultyResolver.resolve(state.ruleset, obj.difficulty, obj.dc)
        elif c.purpose == "persuade":
            npc = state.actor(target)
            if npc.location != a.location or npc.hp <= 0:
                raise ValueError("Собеседник недоступен")
            secrets = [
                s
                for s in state.definition.secrets
                if s.id in npc.knowledge
                and s.disclosure == "persuasion"
                and s.location_id == a.location
                and s.id not in state.player_knowledge
            ]
            if npc.attitude == "hostile" or state.hostile(a.id, npc.id) or not secrets:
                event(
                    events,
                    "Собеседник не согласен на это требование. Бросок не может изменить его принципиальное решение.",
                    kind="refusal",
                )
                return
            ability, skill = "charisma", "persuasion"
            outcome = "persuade"
            dc = DifficultyResolver.resolve(state.ruleset, secrets[0].difficulty)
        elif target:
            raise ValueError("Для цели проверки укажи допустимое назначение")
        if c.type == "save" and (skill or c.purpose != "general"):
            raise ValueError("У спасброска нет навыка или произвольного последствия")
        modifier = (
            self.rules.save_modifier(a, ability)
            if c.type == "save"
            else self.rules.check_modifier(a, ability, skill, state.ruleset)
        )
        self.pending(
            state,
            "save" if c.type == "save" else "check",
            a.id,
            ability=ability,
            skill=skill,
            modifier=modifier,
            dc=dc,
            target=target,
            outcome=outcome,
        )
        event(events, "Требуется проверка. Выполни бросок.", kind="pending")

    def interact(self, state, a, target, events):
        obj = next(
            (
                o
                for o in state.definition.objects
                if o.id == target and o.location_id == a.location
            ),
            None,
        )
        if obj and any(
            e.loot_object == obj.id and e.id not in state.completed_encounters
            for e in state.definition.encounters
        ):
            raise ValueError("Сначала заверши столкновение")
        if not obj or not state.objects[obj.id].revealed:
            raise ValueError("Объект недоступен")
        status = state.objects[obj.id]
        if obj.locked and not status.unlocked:
            raise ValueError("Объект заперт. Нужна проверка взаимодействия")
        self.spend(state.encounter)
        if obj.trap_damage and not status.trap_triggered:
            self.pending(
                state,
                "save",
                a.id,
                ability="dexterity",
                modifier=self.rules.save_modifier(a, "dexterity"),
                dc=DifficultyResolver.resolve(state.ruleset, obj.difficulty, obj.dc),
                target=obj.id,
                outcome="trap",
            )
            event(events, "Сработала ловушка. Нужен спасбросок.", kind="trap")
            return
        status.opened = True
        self.reveal_object(state, obj, events)
        event(events, obj.description or ("Открыто: " + obj.name), kind="interact")

    @staticmethod
    def reveal_object(state, obj, events):
        for secret in state.definition.secrets:
            if (
                secret.id in obj.secrets
                and secret.disclosure == "search"
                and secret.id not in state.player_knowledge
            ):
                state.player_knowledge[secret.id] = secret.description
                event(events, secret.description, kind="discovery")

    @staticmethod
    def entry(actor, item_id):
        return next((e for e in actor.inventory if e.item_id == item_id), None)

    @staticmethod
    def add(entries, item_id, quantity):
        entry = next(
            (x for x in entries if x.item_id == item_id and not x.equipped), None
        )
        if entry:
            entry.quantity += quantity
        else:
            entries.append(InventoryEntry(item_id=item_id, quantity=quantity))

    @staticmethod
    def remove(entries, item_id, quantity):
        total = sum(x.quantity for x in entries if x.item_id == item_id)
        if total < quantity:
            raise ValueError("Недостаточно предметов")
        remaining = quantity
        for x in entries[:]:
            if x.item_id == item_id and remaining:
                take = min(x.quantity, remaining)
                remaining -= take
                if take == x.quantity:
                    entries.remove(x)
                else:
                    x.quantity -= take

    def inventory(self, state, c, a, events):
        if c.item_id not in state.items:
            raise ValueError("Предмет не найден")
        item = state.items[c.item_id]
        if c.type == "take_item":
            if any(
                e.loot_object == c.target and e.id not in state.completed_encounters
                for e in state.definition.encounters
            ):
                raise ValueError("Сначала победи в столкновении")
            obj = next(
                (
                    o
                    for o in state.definition.objects
                    if o.id == c.target and o.location_id == a.location
                ),
                None,
            )
            if (
                not obj
                or not state.objects[obj.id].revealed
                or not state.objects[obj.id].opened
            ):
                raise ValueError("Контейнер недоступен или закрыт")
            self.remove(state.objects[obj.id].contents, c.item_id, c.quantity)
            self.add(a.inventory, c.item_id, c.quantity)
        else:
            entry = self.entry(a, c.item_id)
            if not entry:
                raise ValueError("Предмета нет в инвентаре")
            if c.type == "use_item":
                if item.type != "consumable" or not item.healing:
                    raise ValueError(
                        "У предмета нет поддерживаемого эффекта использования"
                    )
                recipient = state.actor(c.target) if c.target else a
                if (
                    recipient.location != a.location
                    or abs(recipient.position - a.position) > 5
                    or state.relation(a.faction, recipient.faction) != "ALLY"
                ):
                    raise ValueError("Цель лечения недоступна")
                self.rules.heal(recipient, item.healing)
                self.remove(a.inventory, c.item_id, 1)
                event(
                    events,
                    f"{recipient.name}: лечение до {item.healing} HP.",
                    kind="healing",
                )
            elif c.type == "drop_item":
                self.remove(a.inventory, c.item_id, c.quantity)
                obj = WorldObject(
                    id="dropped_" + uuid4().hex, name=item.name, location_id=a.location
                )
                state.definition.objects.append(obj)
                state.objects[obj.id] = ObjectState(
                    opened=True,
                    contents=[InventoryEntry(item_id=c.item_id, quantity=c.quantity)],
                )
            elif c.type == "equip":
                if item.type not in ("weapon", "armor"):
                    raise ValueError("Предмет нельзя экипировать")
                if item.type == "armor":
                    for x in a.inventory:
                        if state.items[x.item_id].type == "armor":
                            x.equipped = False
                entry.equipped = True
            else:
                entry.equipped = False
        self.spend(state.encounter)
        self.rules.equipment_stats(a, state.items)
        event(
            events,
            {
                "take_item": "Предмет получен: ",
                "drop_item": "Предмет оставлен: ",
                "use_item": "Предмет использован: ",
                "equip": "Экипировано: ",
                "unequip": "Снято: ",
            }[c.type]
            + item.name,
            kind=c.type,
            item_id=item.id,
            quantity=c.quantity,
        )

    def attack(self, state, aid, target, weapon, events, reaction=False):
        a, t = self.combat.validate_attack(state, aid, target, weapon)
        if state.controllers[aid].controller == "PLAYER":
            advantage = (1 if "helped" in a.conditions else 0) - (
                1 if "dodge" in t.conditions else 0
            )
            a.conditions = [x for x in a.conditions if x != "helped"]
            self.pending(
                state,
                "attack",
                aid,
                modifier=self.rules.attack_modifier(a, weapon),
                target=target,
                dc=t.armor_class,
                weapon=weapon,
                advantage=advantage,
                outcome="reaction" if reaction else "attack",
            )
            event(events, f"{a.name} атакует {t.name}. Брось кубик.", kind="pending")
        else:
            self.combat.npc_attack(state, aid, target, weapon, events)

    def initiative(self, state, events):
        s = state.session_state
        while s.initiative_waiting:
            aid = s.initiative_waiting.pop(0)
            a = state.actor(aid)
            modifier = self.rules.modifier(a.abilities["dexterity"])
            if state.controllers[aid].controller == "PLAYER":
                self.pending(state, "initiative", aid, modifier=modifier)
                event(events, a.name + ": брось инициативу.", kind="pending")
                return
            s.initiative_results[aid] = self.combat.roll(
                events, "1d20", modifier=modifier, purpose="initiative", actor=aid
            ).total
        definition = next(
            x for x in state.definition.encounters if x.id == s.encounter_definition
        )
        self.combat.start(state, definition, s.initiative_results.copy(), events)
        self.drive(state, events)

    def move(self, state, aid, distance, events):
        e = state.encounter
        a = state.actor(aid)
        if not distance or abs(distance) > e.movement:
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
                    or "fled" in other.conditions
                    or not e.reaction.get(oid)
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
                self.combat.npc_attack(state, oid, aid, weapon, events)
                if a.hp <= 0:
                    return
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
            if not self.combat.ended(state, events):
                self.drive(state, events)

    def drive(self, state, events):
        for _ in range(250):
            if (
                not state.encounter
                or state.session_state.pending
                or state.session_state.reaction
                or self.combat.ended(state, events)
            ):
                return
            e = state.encounter
            aid = e.order[e.index]
            a = state.actor(aid)
            control = state.controllers[aid]
            if set(a.conditions) & {"dead", "stable", "fled"}:
                self.combat.advance(state)
                continue
            if a.hp <= 0:
                if control.controller == "PLAYER":
                    self.pending(state, "death", aid, dc=10)
                    event(events, a.name + ": спасбросок от смерти.", kind="pending")
                    return
                roll = self.combat.roll(events, "1d20", purpose="death", actor=aid)
                self.rules.death_save(a, roll)
                self.combat.advance(state)
                continue
            if control.controller == "PLAYER":
                return
            command = self.ai.decide(state, aid)
            self.apply(state, command, aid, events)
        raise ValueError(
            "Превышен предел автоматических действий; состояние не изменено"
        )

    def resolve_roll(self, original, pending_id, player_id="local"):
        state = original.model_copy(deep=True)
        events = []
        p = state.session_state.pending
        if not p or p.id != pending_id:
            raise ValueError("Бросок уже выполнен или устарел")
        self.owned(state, p.actor, player_id)
        a = state.actor(p.actor)
        roll = self.combat.roll(
            events,
            p.expression,
            modifier=p.modifier,
            advantage=p.advantage,
            purpose=p.purpose,
            actor=p.actor,
            critical=p.critical,
            critical_rule=state.ruleset.critical,
        )
        state.session_state.pending = None
        state.session_state.mode = p.resume
        if p.purpose == "initiative":
            state.session_state.initiative_results[p.actor] = roll.total
            self.initiative(state, events)
        elif p.purpose in ("check", "save"):
            success = roll.total >= p.dc
            event(
                events,
                "Успех." if success else "Проверка не пройдена.",
                kind="check",
                success=success,
            )
            if p.outcome in ("search", "unlock"):
                obj = next(o for o in state.definition.objects if o.id == p.target)
                if success:
                    state.objects[obj.id].revealed = True
                    if p.outcome == "unlock":
                        state.objects[obj.id].unlocked = True
                    self.reveal_object(state, obj, events)
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
                        and s.location_id == a.location
                        and s.id not in state.player_knowledge
                    ),
                    None,
                )
                if secret:
                    state.player_knowledge[secret.id] = secret.description
                    event(events, secret.description, kind="discovery")
            elif p.outcome == "trap":
                obj = next(o for o in state.definition.objects if o.id == p.target)
                status = state.objects[obj.id]
                status.trap_triggered = True
                status.opened = True
                if not success:
                    self.combat.damage(state, a, obj.trap_damage, False, events)
                self.reveal_object(state, obj, events)
            state.game_time += 60
        elif p.purpose == "attack":
            if self.rules.hit(roll, state.actor(p.target).armor_class):
                w = a.attacks[p.weapon]
                self.pending(
                    state,
                    "damage",
                    p.actor,
                    expression=f"1d{w.die}",
                    modifier=self.rules.modifier(a.abilities[w.ability]),
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
                    self.resume_reaction(state, events)
        elif p.purpose == "damage":
            self.combat.damage(
                state, state.actor(p.target), roll.total, p.critical, events
            )
            if state.encounter:
                self.combat.ended(state, events)
            if p.outcome == "reaction":
                self.resume_reaction(state, events)
        elif p.purpose == "death":
            self.rules.death_save(a, roll)
            event(
                events,
                f"{a.name}: {a.death_successes} успехов / {a.death_failures} провалов.",
                kind="death",
            )
            if a.hp == 0 and state.encounter:
                self.combat.advance(state)
        if state.encounter and not state.session_state.pending:
            self.drive(state, events)
        if not state.encounter and not state.session_state.pending:
            for aid in state.party:
                actor = state.actor(aid)
                if (
                    actor.hp == 0
                    and not set(actor.conditions) & {"dead", "stable"}
                    and state.controllers[aid].controller == "PLAYER"
                ):
                    self.pending(state, "death", aid, dc=10)
                    event(
                        events, actor.name + ": спасбросок от смерти.", kind="pending"
                    )
                    break
        return self.validate(state), events
