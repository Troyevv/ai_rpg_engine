"""Slot equipment validates compatibility and recomputes derived effects from scratch."""

from .models import Attack


class EquipmentEngine:
    @staticmethod
    def hand_slots(actor):
        if actor.equipment_layout:
            return {
                slot
                for slot, layout in actor.equipment_layout.items()
                if layout["group"] == "hand" or layout["position"] in ("left", "right")
            }
        return {"MAIN_HAND", "OFF_HAND"}

    @staticmethod
    def body_slots(actor):
        if actor.equipment_layout:
            return {
                slot
                for slot, layout in actor.equipment_layout.items()
                if layout["position"] == "body"
            }
        return {"TORSO"}

    @staticmethod
    def equip(actor, items, entry, slot=""):
        item = items[entry.item_id]
        if not set(item.requirements) <= set(actor.features) - set(
            actor.equipment_grants
        ):
            raise ValueError("Не выполнены требования предмета")
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
                or (item.hands == 2 and other.slot in EquipmentEngine.hand_slots(actor))
                or (
                    slot in EquipmentEngine.hand_slots(actor)
                    and items[other.item_id].hands == 2
                )
            )
            if conflict:
                other.equipped = False
                other.slot = ""
        entry.container_id = ""
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
            if entry.container_id:
                raise ValueError("Предмет в контейнере нельзя экипировать")
            if not set(item.requirements) <= set(actor.features) - set(
                actor.equipment_grants
            ):
                raise ValueError("Не выполнены требования предмета")
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
        hands = EquipmentEngine.hand_slots(actor)
        if (
            any(i.hands == 2 for slot, i in occupied.items() if slot in hands)
            and len(set(occupied) & hands) > 1
        ):
            raise ValueError("Двуручное оружие занимает обе руки")
        actor.attacks = {}
        dex = rules.modifier(actor.abilities["dexterity"])
        actor.armor_class = 10 + dex
        actor.equipment_bonuses = {}
        for slot, item in occupied.items():
            if item.type == "armor":
                if item.armor_category not in actor.proficiencies:
                    raise ValueError("Нет владения этим типом брони")
                if slot in EquipmentEngine.body_slots(actor):
                    actor.armor_class = item.armor_base + min(item.dex_cap, dex)
            if item.type == "weapon":
                actor.attacks[item.id] = Attack(
                    name=item.name,
                    ability=item.weapon_ability,
                    die=item.weapon_die,
                    reach=item.reach,
                    proficient=item.weapon_category in actor.proficiencies,
                )
            for component in item.components:
                if component.type == "weapon":
                    attack = actor.attacks[item.id]
                    attack.item_id = item.id
                    attack.expression = component.damage_expression
                    attack.damage_type = component.damage_type
                    attack.resource_usage = component.resource_usage
                elif component.type == "magazine":
                    actor.attacks[item.id].magazine = component
                    actor.item_resources.setdefault(item.id, component.initial)
                elif component.type == "tool":
                    actor.equipment_bonuses["check:" + component.skill_id] = (
                        actor.equipment_bonuses.get("check:" + component.skill_id, 0)
                        + component.modifier
                    )
            if item.stealth_disadvantage:
                actor.equipment_bonuses["stealth_disadvantage"] = 1
        for entry in actor.inventory:
            if entry.equipped or entry.container_id:
                continue
            for component in items[entry.item_id].components:
                if component.type == "tool" and not component.requires_equipped:
                    key = "check:" + component.skill_id
                    actor.equipment_bonuses[key] = (
                        actor.equipment_bonuses.get(key, 0) + component.modifier
                    )
        if not set(occupied) & EquipmentEngine.body_slots(actor):
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
