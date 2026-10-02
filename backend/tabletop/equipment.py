"""Slot equipment validates compatibility and recomputes derived effects from scratch."""

from .models import Attack


class EquipmentEngine:
    @staticmethod
    def equip(actor, items, entry, slot=""):
        item = items[entry.item_id]
        allowed = [s for s in item.slots if s in actor.equipment_slots]
        slot = slot or next(
            (
                s
                for s in allowed
                if not any(e.equipped and e.slot == s for e in actor.inventory)
            ),
            allowed[0] if allowed else "",
        )
        if slot not in allowed:
            raise ValueError("Предмет не подходит для выбранного слота")
        if entry.quantity > 1:
            actor.inventory.append(
                entry.model_copy(
                    update={
                        "quantity": entry.quantity - 1,
                        "equipped": False,
                        "slot": "",
                    }
                )
            )
            entry.quantity = 1
        for other in actor.inventory:
            if other is entry or not other.equipped:
                continue
            conflict = (
                other.slot == slot
                or (item.hands == 2 and other.slot in ("MAIN_HAND", "OFF_HAND"))
                or (
                    slot in ("MAIN_HAND", "OFF_HAND")
                    and items[other.item_id].hands == 2
                )
            )
            if conflict:
                other.equipped = False
                other.slot = ""
        entry.slot = slot
        entry.equipped = True

    @staticmethod
    def calculate(actor, items, rules):
        occupied = {}
        for entry in actor.inventory:
            if not entry.equipped:
                entry.slot = ""
                continue
            item = items[entry.item_id]
            if not entry.slot:
                entry.slot = next((s for s in item.slots if s not in occupied), "")
            if (
                entry.quantity != 1
                or entry.slot not in item.slots
                or entry.slot not in actor.equipment_slots
                or entry.slot in occupied
            ):
                raise ValueError("Несовместимые предметы или занятый слот")
            occupied[entry.slot] = item
        if any(i.hands == 2 for i in occupied.values()) and "OFF_HAND" in occupied:
            raise ValueError("Двуручное оружие занимает обе руки")
        actor.attacks = {}
        dex = rules.modifier(actor.abilities["dexterity"])
        actor.armor_class = 10 + dex
        actor.equipment_bonuses = {}
        for slot, item in occupied.items():
            if item.type == "armor":
                if item.armor_category not in actor.proficiencies:
                    raise ValueError("Нет владения этим типом брони")
                if slot == "TORSO":
                    actor.armor_class = item.armor_base + min(item.dex_cap, dex)
            if item.type == "weapon":
                actor.attacks[item.id] = Attack(
                    name=item.name,
                    ability=item.weapon_ability,
                    die=item.weapon_die,
                    reach=item.reach,
                    proficient=item.weapon_category in actor.proficiencies,
                )
            if item.stealth_disadvantage:
                actor.equipment_bonuses["stealth_disadvantage"] = 1
        if "TORSO" not in occupied:
            for ability in actor.abilities:
                if "unarmored_ability:" + ability in actor.bonuses:
                    actor.armor_class += rules.modifier(actor.abilities[ability])
        actor.armor_class += sum(
            i.ac_bonus for i in occupied.values()
        ) + actor.bonuses.get("armor_class", 0)
        if not actor.attacks:
            actor.attacks["unarmed"] = Attack(
                name="Без оружия",
                die=actor.bonuses.get("unarmed_die", 4),
                ability="dexterity" if actor.bonuses.get("unarmed_die") else "strength",
            )
