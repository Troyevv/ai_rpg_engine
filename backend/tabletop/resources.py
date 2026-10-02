"""ID-based costs and magazines. Validation never spends resources."""


class ResourceEngine:
    @staticmethod
    def attack_costs(attack):
        costs = {}
        for cost in attack.resource_usage:
            costs[cost.resource_id] = costs.get(cost.resource_id, 0) + cost.amount
        return costs

    @staticmethod
    def validate_attack(actor, attack, mode="single"):
        for resource_id, amount in ResourceEngine.attack_costs(attack).items():
            if actor.resources.get(resource_id, 0) < amount:
                raise ValueError("Недостаточно ресурса: " + resource_id)
        if attack.magazine:
            if mode not in attack.magazine.modes:
                raise ValueError("Режим оружия недоступен")
            if (
                actor.item_resources.get(attack.item_id, 0)
                < attack.magazine.modes[mode]
            ):
                raise ValueError("Нужна перезарядка")
        elif mode != "single":
            raise ValueError("Оружие не поддерживает этот режим")

    @classmethod
    def spend_attack(cls, actor, attack, mode="single"):
        cls.validate_attack(actor, attack, mode)
        for resource_id, amount in cls.attack_costs(attack).items():
            actor.resources[resource_id] -= amount
        if attack.magazine:
            actor.item_resources[attack.item_id] -= attack.magazine.modes[mode]

    @staticmethod
    def reload(actor, items, item_id):
        attack = actor.attacks.get(item_id)
        if not attack or not attack.magazine:
            raise ValueError("Оружие с магазином не экипировано")
        mag = attack.magazine
        need = mag.capacity - actor.item_resources.get(item_id, 0)
        if need <= 0:
            raise ValueError("Магазин уже полон")
        ammo = [
            e
            for e in actor.inventory
            if not e.equipped
            and any(
                c.type == "ammo" and c.ammo_type == mag.ammo_type
                for c in items[e.item_id].components
            )
        ]
        if not ammo:
            raise ValueError("Нет подходящих боеприпасов")
        loaded = 0
        for entry in ammo:
            count = min(need - loaded, entry.quantity)
            entry.quantity -= count
            loaded += count
            if loaded == need:
                break
        actor.inventory = [e for e in actor.inventory if e.quantity]
        actor.item_resources[item_id] = actor.item_resources.get(item_id, 0) + loaded
        return loaded

    @staticmethod
    def recover(actor, rules, kind):
        for id, definition in rules.resource_definitions.items():
            if (
                definition.recovery == kind
                or kind == "long"
                and definition.recovery == "short"
            ):
                if id in actor.resources:
                    actor.resources[id] = min(
                        definition.maximum,
                        actor.resources[id] + definition.recovery_amount,
                    )
