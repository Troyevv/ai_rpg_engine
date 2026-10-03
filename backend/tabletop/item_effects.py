"""Equipment grants are reversible; toggling equipment never replenishes a resource."""


class ItemEffects:
    @staticmethod
    def sync(actor, items, rules):
        old = set(actor.equipment_grants)
        intrinsic = [fid for fid in actor.features if fid not in old]
        for key, amount in actor.equipment_effect_bonuses.items():
            actor.bonuses[key] = actor.bonuses.get(key, 0) - amount
        actor.max_hp -= actor.equipment_hp_bonus
        actor.speed -= actor.equipment_speed_bonus
        actor.equipment_hp_bonus = actor.equipment_speed_bonus = 0
        actor.equipment_effect_bonuses = {}
        grants = list(
            dict.fromkeys(
                fid
                for entry in actor.inventory
                if entry.equipped
                for fid in items[entry.item_id].features
                if fid not in intrinsic
            )
        )
        actor.equipment_grants = grants
        actor.features = intrinsic + grants
        for fid in grants:
            feature = rules.features[fid]
            if feature.resource and fid not in actor.initialized_item_features:
                actor.resources.setdefault(feature.resource, feature.uses)
            if feature.activation == "PASSIVE":
                for effect in feature.effects:
                    if effect.type == "max_hp":
                        actor.equipment_hp_bonus += effect.value
                    elif effect.type == "speed":
                        actor.equipment_speed_bonus += effect.value
                    elif effect.type == "resource":
                        if fid not in actor.initialized_item_features:
                            actor.resources.setdefault(effect.key, effect.value)
                    else:
                        key = effect.type + (":" + effect.key if effect.key else "")
                        actor.equipment_effect_bonuses[key] = (
                            actor.equipment_effect_bonuses.get(key, 0)
                            + (
                                1
                                if effect.type == "skill_proficiency"
                                else effect.value
                            )
                        )
            if fid not in actor.initialized_item_features:
                actor.initialized_item_features.append(fid)
        actor.max_hp = max(1, actor.max_hp + actor.equipment_hp_bonus)
        actor.hp = min(actor.hp, actor.max_hp)
        actor.speed += actor.equipment_speed_bonus
        for key, amount in actor.equipment_effect_bonuses.items():
            actor.bonuses[key] = actor.bonuses.get(key, 0) + amount
