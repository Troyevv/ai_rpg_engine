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
            (x for x in entries if x.item_id == item_id and (not x.equipped)), None
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
                before = recipient.hp
                self.runtime.rules.heal(recipient, item.healing)
                self.runtime.remove(a.inventory, c.item_id, 1)
                event(
                    events,
                    f"{recipient.name}: лечение до {item.healing} HP.",
                    kind="healing",
                    target=recipient.id,
                    hp_before=before,
                    hp_after=recipient.hp,
                    maximum=recipient.max_hp,
                )
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
                self.runtime.rules.equipment_stats(recipient, state.items)
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
            self.runtime.spend(state.encounter)
        else:
            self.runtime.interaction(state)
        self.runtime.rules.equipment_stats(a, state.items)
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
