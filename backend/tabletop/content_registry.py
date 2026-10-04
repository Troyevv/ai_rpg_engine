"""Registry validation and explicit compatibility adapters; no semantic repairs."""

from math import floor
from pydantic import ValidationError
from .content import SettingDefinition, ContentItem
from .dice import DiceEngine
from .validation import ValidationIssue, CampaignValidationError


def average(expression):
    return sum(
        sign * count * ((sides + 1) / 2 if sides else 1)
        for sign, count, sides in DiceEngine.parse(expression)
    )


def creature_threat(creature, registry):
    """Comparable encounter points, not a claim of official CR or perfect balance."""
    attacks = creature.attacks
    damage = max(
        [
            average(a.damage_expression)
            * max(0.05, min(0.95, (21 + a.accuracy - 13) / 20))
            for a in attacks
        ]
        or [0]
    )
    features = [
        registry.features[f] for f in creature.features if f in registry.features
    ]
    control = sum(
        e.type in ("condition", "check_bonus", "attack_bonus")
        for f in features
        for e in f.effects
    )
    healing = sum(
        (
            max(0, e.value)
            if e.type == "heal"
            else max(0, average(e.expression))
            if e.type == "heal_dice"
            else 0
        )
        for f in features
        for e in f.effects
    )
    damage += sum(
        max(0, average(e.expression)) * (2 if f.area else 1)
        for f in features
        for e in f.effects
        if e.type == "damage"
    )
    extra = sum(
        max(0, e.value) for f in features for e in f.effects if e.type == "extra_attack"
    )
    bonus = sum(f.activation in ("BONUS_ACTION", "REACTION") for f in features)
    defence = 1 + sum(1 - m for m in creature.damage_modifiers.values() if m < 1) * 0.25
    return round(
        max(
            1,
            (
                creature.base_hp
                * max(0.5, 1 + (creature.base_armor - 10) * 0.06)
                * defence
                + damage * 4 * (1 + extra)
                + control * 5
                + healing * 2
                + bonus * 4
            )
            * (1 + max(0, creature.movement - 30) / 150),
        ),
        2,
    )


class SettingValidator:
    def validate(self, value, *, complete=True):
        try:
            s = SettingDefinition.model_validate(
                value.model_dump() if isinstance(value, SettingDefinition) else value
            )
        except ValidationError as exc:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code=e["type"],
                        stage="schema",
                        entity_type="setting",
                        entity_id="",
                        field=".".join(map(str, e["loc"])),
                        message=e["msg"],
                    )
                    for e in exc.errors(include_input=False)
                ],
                stage="schema",
            ) from None
        c = s.content
        issues = []

        def issue(code, kind, id, field, message, target=""):
            issues.append(
                ValidationIssue(
                    code=code,
                    stage="content",
                    entity_type=kind,
                    entity_id=id,
                    source_id=id,
                    field=field,
                    target_id=target,
                    reference=target,
                    message=message,
                )
            )

        def refs(kind, entry, field, values, targets):
            for target in values:
                if target not in targets:
                    issue(
                        "missing_content_reference",
                        kind,
                        entry.id,
                        field,
                        f"{entry.name}: {field} ссылается на отсутствующий контент {target}",
                        target,
                    )

        def dice(kind, entry, field, expression):
            try:
                DiceEngine.parse(expression)
            except ValueError as exc:
                issue("invalid_dice", kind, entry.id, field, str(exc))

        for group in (
            "conditions",
            "skills",
            "species",
            "archetypes",
            "backgrounds",
            "features",
            "powers",
            "creatures",
            "items",
            "damage_types",
            "resources",
            "equipment_profiles",
            "world_mechanics",
        ):
            for key, entry in getattr(c, group).items():
                if key != entry.id:
                    issue(
                        "content_id_mismatch",
                        group,
                        entry.id,
                        "id",
                        "Ключ реестра должен совпадать с ID",
                        key,
                    )
        for group in (
            "species",
            "archetypes",
            "backgrounds",
            "skills",
            "equipment_profiles",
        ):
            if complete and not getattr(c, group):
                issue(
                    "empty_required_content",
                    "setting",
                    s.id,
                    group,
                    f"Нужен непустой раздел {group}",
                )
        slots = {
            slot.id
            for profile in c.equipment_profiles.values()
            for slot in profile.slots
        }
        for species in c.species.values():
            refs("species", species, "features", species.features, c.features)
            refs(
                "species",
                species,
                "equipment_profile",
                [species.equipment_profile],
                c.equipment_profiles,
            )
        for kind, entries in [
            ("archetype", c.archetypes),
            ("background", c.backgrounds),
        ]:
            for entry in entries.values():
                refs(kind, entry, "skills", entry.skills, c.skills)
                refs(kind, entry, "features", entry.features, c.features)
                refs(kind, entry, "equipment", entry.equipment, c.items)
                refs(kind, entry, "resources", entry.resources, c.resources)
                if kind == "archetype":
                    refs(
                        kind,
                        entry,
                        "feature_choices",
                        entry.feature_choices,
                        c.features,
                    )
                    for group in entry.equipment_choices:
                        refs(kind, entry, "equipment_choices", group, c.items)
                    if entry.skill_count > len(
                        set(entry.skills)
                    ) or entry.feature_choice_count > len(set(entry.feature_choices)):
                        issue(
                            "invalid_choice_count",
                            kind,
                            entry.id,
                            "skills",
                            "Недостаточно доступных вариантов",
                        )
        for item in c.items.values():
            refs("item", item, "equipment_slots", item.equipment_slots, slots)
            refs("item", item, "effects", item.effects, c.features)
            refs("item", item, "requirements", item.requirements, c.features)
            for comp in item.components:
                if comp.type == "weapon":
                    dice("item", item, "damage_expression", comp.damage_expression)
                    refs(
                        "item", item, "damage_type", [comp.damage_type], c.damage_types
                    )
                    refs(
                        "item",
                        item,
                        "resource_usage",
                        [r.resource_id for r in comp.resource_usage],
                        c.resources,
                    )
                    refs("item", item, "features", comp.features, c.features)
                elif comp.type == "tool":
                    refs("item", item, "skill_id", [comp.skill_id], c.skills)
                elif comp.type == "energy":
                    refs("item", item, "resource_id", [comp.resource_id], c.resources)
                elif comp.type in ("medical", "consumable"):
                    if comp.healing:
                        dice("item", item, "healing", comp.healing)
                    if comp.feature_id:
                        refs("item", item, "feature_id", [comp.feature_id], c.features)
                        feature = c.features.get(comp.feature_id)
                        if feature and feature.activation != comp.action_cost:
                            issue(
                                "incompatible_item_action",
                                "item",
                                item.id,
                                "components.feature_id",
                                "Стоимость способности должна совпадать с действием предмета",
                            )
                    if (
                        sum(
                            bool(v)
                            for v in (comp.fixed_healing, comp.healing, comp.feature_id)
                        )
                        != 1
                    ):
                        issue(
                            "ambiguous_consumable",
                            "item",
                            item.id,
                            "components",
                            "Выбери один эффект предмета: фиксированное лечение, кубики или способность",
                        )
                elif comp.type in ("artifact", "key", "currency", "quest"):
                    refs("item", item, "feature_ids", comp.feature_ids, c.features)
                elif comp.type == "magazine":
                    for mode, effect in comp.mode_effects.items():
                        if effect.damage_expression:
                            dice(
                                "item",
                                item,
                                "mode_effects." + mode + ".damage_expression",
                                effect.damage_expression,
                            )
                    ammunition = {
                        a.ammo_type
                        for i in c.items.values()
                        for a in i.components
                        if a.type == "ammo"
                    }
                    refs("item", item, "ammo_type", [comp.ammo_type], ammunition)
        for creature in c.creatures.values():
            refs("creature", creature, "features", creature.features, c.features)
            refs("creature", creature, "skills", creature.skills, c.skills)
            refs("creature", creature, "resources", creature.resources, c.resources)
            refs(
                "creature",
                creature,
                "damage_modifiers",
                creature.damage_modifiers,
                c.damage_types,
            )
            for attack in creature.attacks:
                dice(
                    "creature",
                    creature,
                    "attacks.damage_expression",
                    attack.damage_expression,
                )
                refs(
                    "creature",
                    creature,
                    "attacks.damage_type",
                    [attack.damage_type],
                    c.damage_types,
                )
        for feature in list(c.features.values()) + list(c.world_mechanics.values()):
            from .effects import EffectsEngine

            for field, registry in (
                ("skills", c.skills),
                ("backgrounds", c.backgrounds),
                ("archetypes", c.archetypes),
                ("features", c.features),
                ("items", c.items),
                ("equipment", c.items),
            ):
                refs(
                    "feature",
                    feature,
                    "requirements." + field,
                    getattr(feature.requirements, field),
                    registry,
                )

            if feature.area and any(
                e.type not in EffectsEngine.ACTIVE for e in feature.effects
            ):
                issue(
                    "invalid_area_effect",
                    "feature",
                    feature.id,
                    "area",
                    "Эффект не поддерживает область",
                )
            passive = {
                "unarmed_die",
                "unarmored_ability",
                "max_hp",
                "armor_class",
                "speed",
                "skill_proficiency",
                "resource",
                "check_bonus",
                "save_bonus",
                "attack_bonus",
                "damage_bonus",
                "extra_attack",
            }
            active = EffectsEngine.ACTIVE | {
                "heal_dice",
                "restore_slot",
                "heal",
                "condition",
                "dash",
                "disengage",
            }
            if any(
                e.type not in (passive if feature.activation == "PASSIVE" else active)
                for e in feature.effects
            ):
                issue(
                    "invalid_passive_effect",
                    "feature",
                    feature.id,
                    "activation",
                    "Тип эффекта не соответствует способу активации",
                )
            refs(
                "feature", feature, "resource_cost", feature.resource_cost, c.resources
            )
            if any(cost < 0 for cost in feature.resource_cost.values()):
                issue(
                    "invalid_resource_cost",
                    "feature",
                    feature.id,
                    "resource_cost",
                    "Стоимость ресурса не может быть отрицательной",
                )
            if feature.resource:
                refs("feature", feature, "resource", [feature.resource], c.resources)
            for effect in feature.effects:
                if effect.type in ("heal_dice", "damage"):
                    dice("feature", feature, "effects.expression", effect.expression)
                if effect.type == "skill_proficiency":
                    refs("feature", feature, "effects.key", [effect.key], c.skills)
                if effect.type == "damage":
                    refs(
                        "feature", feature, "effects.key", [effect.key], c.damage_types
                    )
                if effect.type in ("resource", "spend_resource", "restore_resource"):
                    refs("feature", feature, "effects.key", [effect.key], c.resources)
        from .conditions import default_conditions

        conditions = {**default_conditions(), **c.conditions}
        for feature in list(c.features.values()) + list(c.world_mechanics.values()):
            for effect in feature.effects:
                if effect.type in ("condition", "remove_condition"):
                    refs("feature", feature, "effects.key", [effect.key], conditions)
                if effect.type in ("check_bonus", "modify_check") and effect.key:
                    refs(
                        "feature",
                        feature,
                        "effects.key",
                        [effect.key],
                        set(c.skills)
                        | {
                            "strength",
                            "dexterity",
                            "constitution",
                            "intelligence",
                            "wisdom",
                            "charisma",
                        },
                    )
        for power in c.powers.values():
            refs("power", power, "effects", power.effects, conditions)
            if power.damage_type:
                refs("power", power, "damage_type", [power.damage_type], c.damage_types)
            refs("power", power, "resource_cost", power.resource_cost, c.resources)
            if any(v < 0 for v in power.resource_cost.values()):
                issue(
                    "invalid_resource_cost",
                    "power",
                    power.id,
                    "resource_cost",
                    "Стоимость не может быть отрицательной",
                )
            refs("power", power, "classes", power.classes, c.archetypes)
            for field in ("damage", "healing"):
                if getattr(power, field):
                    dice("power", power, field, getattr(power, field))
        for cls, casting in c.spellcasting.items():
            if cls not in c.archetypes:
                issue(
                    "missing_content_reference",
                    "setting",
                    s.id,
                    "spellcasting",
                    "Неизвестный архетип",
                    cls,
                )
            refs("setting", s, "spellcasting.defaults", casting.defaults, c.powers)
        refs("setting", s, "feats", c.feats, c.features)
        for level in c.levels.values():
            for cls, features in level.features.items():
                refs("setting", s, "levels.features", features, c.features)
                refs("setting", s, "levels.classes", [cls], c.archetypes)
        if issues:
            raise CampaignValidationError(issues, stage="content")
        # Derived threat is explicitly calculated by the engine at the authoring boundary.
        for creature in c.creatures.values():
            creature.threat = creature_threat(creature, c)
        return s


def item_adapter(item: ContentItem):
    from .definitions import ItemDefinition

    data = dict(
        id=item.id,
        name=item.name,
        description=item.description,
        weight=item.weight,
        value=item.value,
        slots=item.equipment_slots,
        components=item.components,
        features=item.effects,
        requirements=item.requirements,
        starting_available=item.starting_available,
    )
    for comp in item.components:
        if comp.type == "weapon":
            data.update(
                type="weapon",
                weapon_ability=comp.attack_ability,
                reach=comp.range,
                hands=comp.hands,
                weapon_category=comp.proficiency,
                properties=comp.properties,
            )
        elif comp.type == "armor":
            data.update(
                type="armor",
                armor_base=comp.base,
                ac_bonus=comp.bonus,
                dex_cap=comp.dex_cap,
                armor_category=comp.proficiency,
                stealth_disadvantage=comp.stealth_disadvantage,
            )
        elif comp.type == "quest":
            data["type"] = "quest"
        elif comp.type in ("medical", "consumable") and "type" not in data:
            data["type"] = "consumable"
            data["healing"] = comp.fixed_healing
    for comp in item.components:
        if comp.type in ("artifact", "key", "currency", "quest"):
            data["ac_bonus"] = data.get("ac_bonus", 0) + comp.armor_bonus
            data["features"] = list(dict.fromkeys(data["features"] + comp.feature_ids))
        elif comp.type == "weapon":
            data["features"] = list(dict.fromkeys(data["features"] + comp.features))
    return ItemDefinition.model_validate(data)


def setting_rules(setting):
    from .catalog import load_ruleset

    s = SettingValidator().validate(setting)
    c = s.content
    rules = load_ruleset("d20-core-v1")
    rules.skills = {key: v.default_ability for key, v in c.skills.items()}
    rules.skill_definitions = c.skills
    rules.classes = {
        key: v.model_dump(exclude={"id"}) for key, v in c.archetypes.items()
    }
    for entry in rules.classes.values():
        if not entry["equipment_choices"]:
            entry["equipment_choices"] = [entry["equipment"]]
    rules.species = {key: v.model_dump(exclude={"id"}) for key, v in c.species.items()}
    rules.backgrounds = {
        key: v.model_dump(exclude={"id"}) for key, v in c.backgrounds.items()
    }
    rules.condition_definitions.update(c.conditions)
    rules.conditions = list(dict.fromkeys(rules.conditions + list(c.conditions)))
    rules.features = {**c.features, **c.world_mechanics}
    rules.world_features = list(c.world_mechanics)
    rules.spells = c.powers
    rules.spellcasting = c.spellcasting
    rules.levels = c.levels
    rules.subclasses = c.subclasses
    rules.feats = c.feats
    rules.items = [item_adapter(i) for i in c.items.values()]
    rules.resource_definitions = c.resources
    rules.damage_types = c.damage_types
    rules.starting_gold = s.starting_currency
    rules.currency_label = s.currency_label
    rules.equipment_slots = {
        slot.id: slot.name for p in c.equipment_profiles.values() for slot in p.slots
    }
    rules.equipment_profiles = c.equipment_profiles
    return rules


def campaign_setting(definition):
    """Return a validated detached content view; never mutate the bound world snapshot."""
    from .catalog import load_ruleset
    from .content_migration import import_catalog

    setting = (
        definition.setting_definition.model_copy(deep=True)
        if definition.setting_definition
        else import_catalog(load_ruleset(definition.ruleset_id))
    )
    for group in type(definition.content_overlay).model_fields:
        additions = getattr(definition.content_overlay, group)
        target = getattr(setting.content, group)
        if isinstance(target, dict):
            overlap = set(additions) & set(target)
            if overlap:
                raise ValueError(
                    "Runtime content cannot overwrite setting IDs: "
                    + ",".join(sorted(overlap))
                )
            target.update(additions)
        elif additions:
            setattr(setting.content, group, list(dict.fromkeys(target + additions)))
    return SettingValidator().validate(setting)


def campaign_rules(definition):
    from .catalog import load_ruleset

    if not any(
        getattr(definition.content_overlay, k)
        for k in type(definition.content_overlay).model_fields
    ):
        return (
            setting_rules(definition.setting_definition)
            if definition.setting_definition
            else load_ruleset(definition.ruleset_id)
        )
    patched = setting_rules(campaign_setting(definition))
    if definition.setting_definition:
        return patched
    # Old saves keep their core rules. Only registered content is extended.
    rules = load_ruleset(definition.ruleset_id)
    for field in (
        "skills",
        "skill_definitions",
        "classes",
        "species",
        "backgrounds",
        "features",
        "world_features",
        "spells",
        "spellcasting",
        "levels",
        "subclasses",
        "feats",
        "items",
        "resource_definitions",
        "damage_types",
        "equipment_slots",
        "equipment_profiles",
        "condition_definitions",
    ):
        setattr(rules, field, getattr(patched, field))
    return rules
