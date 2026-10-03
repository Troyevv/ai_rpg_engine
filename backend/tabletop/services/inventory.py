"""InventoryService domain behavior."""

from uuid import uuid4
from ..models import ObjectState
from ..definitions import InventoryEntry, WorldObject
from ..encounter import event


class InventoryService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t in ("store_item", "unpack_item"):
            self.store(state, c, a, events)
            return
        if t in (
            "take_item",
            "drop_item",
            "transfer_item",
            "equip",
            "unequip",
            "use_item",
        ):
            self.runtime.inventory(state, c, a, events)

    @staticmethod
    def entry(actor, item_id):
        return next((e for e in actor.inventory if e.item_id == item_id), None)

    @staticmethod
    def add(entries, item_id, quantity):
        entry = next(
            (
                x
                for x in entries
                if x.item_id == item_id and (not x.equipped) and not x.container_id
            ),
            None,
        )
        if entry:
            entry.quantity += quantity
        else:
            entries.append(InventoryEntry(item_id=item_id, quantity=quantity))

    @staticmethod
    def remove(entries, item_id, quantity):
        total = sum((x.quantity for x in entries if x.item_id == item_id))
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
        if c.type in ("drop_item", "transfer_item", "use_item") and any(
            e.container_id == c.item_id for e in a.inventory
        ):
            raise ValueError("Сначала освободи контейнер")
        if c.type == "take_item":
            if any(
                (
                    e.loot_object == c.target and e.id not in state.completed_encounters
                    for e in state.definition.encounters
                )
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
                or (not state.objects[obj.id].opened)
            ):
                raise ValueError("Контейнер недоступен или закрыт")
            self.runtime.remove(
                state.objects[obj.id].contents, c.item_id, getattr(c, "quantity", 1)
            )
            self.runtime.add(a.inventory, c.item_id, getattr(c, "quantity", 1))
        else:
            entry = next(
                (
                    e
                    for e in a.inventory
                    if e.item_id == c.item_id
                    and (
                        not getattr(c, "slot", "")
                        or e.slot == c.slot
                        or c.type == "equip"
                    )
                ),
                None,
            )
            if not entry:
                raise ValueError("Предмета нет в инвентаре")
            if c.type == "use_item":
                if entry.container_id:
                    raise ValueError("Сначала достань предмет из контейнера")
                if not set(item.requirements) <= set(a.features) - set(
                    a.equipment_grants
                ):
                    raise ValueError("Не выполнены требования предмета")
                energy = next(
                    (part for part in item.components if part.type == "energy"), None
                )
                if energy:
                    if c.target and c.target != a.id:
                        raise ValueError(
                            "Источник энергии восстанавливает ресурс владельца"
                        )
                    definition = state.ruleset.resource_definitions[energy.resource_id]
                    amount = min(
                        energy.capacity,
                        definition.maximum - a.resources.get(energy.resource_id, 0),
                    )
                    if amount <= 0:
                        raise ValueError("Ресурс полон или источник энергии исчерпан")
                    self.runtime.spend(state.encounter)
                    self.runtime.remove(a.inventory, item.id, 1)
                    a.resources[energy.resource_id] = (
                        a.resources.get(energy.resource_id, 0) + amount
                    )
                    event(
                        events,
                        "Использован источник энергии: "
                        + item.name
                        + "; восстановлен ресурс: "
                        + definition.name,
                        kind="resource",
                        amount=amount,
                        target=a.id,
                    )
                    self.runtime.rules.equipment_stats(a, state.items, state.ruleset)
                    return
                consumable = next(
                    (
                        part
                        for part in item.components
                        if part.type in ("consumable", "medical")
                    ),
                    None,
                )
                if item.type != "consumable" or not (
                    item.healing
                    or consumable
                    and (consumable.healing or consumable.feature_id)
                ):
                    raise ValueError(
                        "У предмета нет поддерживаемого эффекта использования"
                    )
                recipient = state.actor(c.target) if c.target else a
                if consumable and consumable.feature_id:
                    from ..commands import Command

                    self.runtime.features_service.execute(
                        state,
                        Command(
                            type="use_feature",
                            feature_id=consumable.feature_id,
                            target=recipient.id,
                        ),
                        aid=a.id,
                        events=events,
                        granted=True,
                    )
                    self.runtime.remove(a.inventory, c.item_id, 1)
                    self.runtime.rules.equipment_stats(a, state.items, state.ruleset)
                    event(
                        events,
                        "Предмет использован: " + item.name,
                        kind="use_item",
                        item_id=item.id,
                        quantity=1,
                    )
                    return
                if (
                    recipient.location != a.location
                    or abs(recipient.position - a.position) > 5
                    or state.relation(a.faction, recipient.faction) != "ALLY"
                ):
                    raise ValueError("Цель лечения недоступна")
                if consumable and consumable.healing:
                    self.runtime.pending(
                        state,
                        "feature_healing",
                        a.id,
                        expression=consumable.healing,
                        target=recipient.id,
                        reason=item.name,
                    )
                else:
                    before = recipient.hp
                    self.runtime.rules.heal(recipient, item.healing)
                    event(
                        events,
                        f"{recipient.name}: лечение до {item.healing} HP.",
                        kind="healing",
                        target=recipient.id,
                        hp_before=before,
                        hp_after=recipient.hp,
                        maximum=recipient.max_hp,
                        amount=recipient.hp - before,
                    )
                self.runtime.remove(a.inventory, c.item_id, 1)
            elif c.type == "transfer_item":
                recipient = state.actor(c.target)
                if (
                    recipient.id == a.id
                    or recipient.id not in state.party
                    or recipient.location != a.location
                    or abs(recipient.position - a.position) > 5
                ):
                    raise ValueError("Получатель недоступен")
                self.runtime.remove(a.inventory, c.item_id, c.quantity)
                self.runtime.add(recipient.inventory, c.item_id, c.quantity)
                self.runtime.rules.equipment_stats(
                    recipient, state.items, state.ruleset
                )
            elif c.type == "drop_item":
                self.runtime.remove(a.inventory, c.item_id, getattr(c, "quantity", 1))
                obj = WorldObject(
                    id="dropped_" + uuid4().hex, name=item.name, location_id=a.location
                )
                state.definition.objects.append(obj)
                state.objects[obj.id] = ObjectState(
                    opened=True,
                    contents=[
                        InventoryEntry(
                            item_id=c.item_id, quantity=getattr(c, "quantity", 1)
                        )
                    ],
                )
            elif c.type == "equip" and a.template_id:
                raise ValueError("Шаблон существа не задаёт профиль экипировки")
            elif c.type == "equip" and a.equipment_slots:
                from ..equipment import EquipmentEngine

                EquipmentEngine.equip(a, state.items, entry, c.slot)
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
        if c.type == "use_item":
            self.runtime.spend(
                state.encounter,
                (
                    "bonus_action"
                    if consumable and consumable.action_cost == "BONUS_ACTION"
                    else "action"
                ),
            )
        else:
            self.runtime.interaction(state)
        self.runtime.rules.equipment_stats(a, state.items, state.ruleset)
        event(
            events,
            {
                "take_item": "Предмет получен: ",
                "drop_item": "Предмет оставлен: ",
                "transfer_item": "Предмет передан: ",
                "use_item": "Предмет использован: ",
                "equip": "Экипировано: ",
                "unequip": "Снято: ",
            }[c.type]
            + item.name,
            kind=c.type,
            item_id=item.id,
            quantity=getattr(c, "quantity", 1),
        )

    def store(self, state, c, a, events):
        if c.item_id not in state.items:
            raise ValueError("Неизвестный предмет")
        if any(e.container_id == c.item_id for e in a.inventory):
            raise ValueError("Вложенные заполненные контейнеры не поддерживаются")
        if c.type == "unpack_item":
            entries = [
                e
                for e in a.inventory
                if e.item_id == c.item_id and e.container_id == c.target
            ]
            destination = a.inventory
            container = ""
        else:
            entries = [
                e for e in a.inventory if e.item_id == c.item_id and not e.container_id
            ]
            bag = next(
                (
                    e
                    for e in a.inventory
                    if e.item_id == c.target and not e.container_id
                ),
                None,
            )
            if bag:
                part = next(
                    (
                        p
                        for p in state.items[bag.item_id].components
                        if p.type == "container"
                    ),
                    None,
                )
                if not part or c.item_id == c.target:
                    raise ValueError("Нужен другой контейнер")
                capacity = part.capacity
                used = sum(
                    e.quantity for e in a.inventory if e.container_id == c.target
                )
                destination = a.inventory
                container = c.target
            else:
                from ..object_actions import ObjectActions

                obj = ObjectActions.definition(state, a, c.target)
                part = next((p for p in obj.components if p.type == "container"), None)
                if (
                    not part
                    or part.capacity is None
                    or not state.objects[obj.id].opened
                ):
                    raise ValueError("Контейнер закрыт или недоступен")
                capacity = part.capacity
                destination = state.objects[obj.id].contents
                container = ""
                used = sum(e.quantity for e in destination)
            if used + c.quantity > capacity:
                raise ValueError("Недостаточно места в контейнере")
        if sum(e.quantity for e in entries) < c.quantity:
            raise ValueError("Недостаточно предметов")
        self.runtime.interaction(state)
        remaining = c.quantity
        for entry in entries:
            count = min(remaining, entry.quantity)
            entry.quantity -= count
            remaining -= count
            if not remaining:
                break
        a.inventory = [e for e in a.inventory if e.quantity]
        # For a carried container, destination is the newly filtered actor inventory.
        if c.type == "store_item" and container:
            destination = a.inventory
        elif c.type == "unpack_item":
            destination = a.inventory
        destination.append(
            InventoryEntry(
                item_id=c.item_id, quantity=c.quantity, container_id=container
            )
        )
        self.runtime.rules.equipment_stats(a, state.items, state.ruleset)
        event(
            events,
            "Предметы перемещены: " + state.items[c.item_id].name,
            kind="inventory",
            item_id=c.item_id,
            target=c.target,
        )
