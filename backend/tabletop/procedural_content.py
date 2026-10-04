"""Deterministic semantic → existing ContentRegistry compiler. All numbers are code-owned."""

import hashlib
from .semantic import SemanticSettingDTO
from .content import (
    ContentRegistry,
    SettingDefinition,
    SkillDefinition,
    DamageTypeDefinition,
    EquipmentProfile,
    EquipmentSlot,
    SpeciesDefinition,
    Archetype,
    BackgroundDefinition,
    ResourceDefinition,
    ContentItem,
    WeaponComponent,
    ArmorComponent,
    CreatureTemplate,
    CreatureAttack,
)
from .features import FeatureDefinition, FeatureEffect
from .spells import SpellDefinition, SpellcastingFeature
from .content_registry import SettingValidator, average
from .validation import ValidationIssue, CampaignValidationError

VERSION = "procedural-2"
ABILITIES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)
AFFINITIES = dict(
    zip(
        ("physical", "precision", "endurance", "reasoning", "awareness", "social"),
        ABILITIES,
    )
)
PRIMARY = {
    "minion": "dexterity",
    "skirmisher": "dexterity",
    "brute": "strength",
    "defender": "strength",
    "controller": "intelligence",
    "ranged": "dexterity",
    "caster": "intelligence",
    "boss": "strength",
    "support": "wisdom",
}


def stable_id(kind, name):
    return (
        kind + "_" + hashlib.sha256(name.strip().casefold().encode()).hexdigest()[:16]
    )


def diagnostic(code, name, message):
    return dict(code=code, entity=name, message=message)


def concept_key(value):
    return value.key or value.name


def pick(registry, name="", diagnostics=None):
    if name in registry:
        return name
    matches = [
        key
        for key, value in registry.items()
        if value.name.casefold() == name.casefold()
    ]
    if len(matches) == 1:
        return matches[0]  # Compatibility for old semantic snapshots only.
    if name:
        raise ValueError("Unknown or ambiguous registry reference: " + name)
    if diagnostics is not None:
        diagnostics.append(
            diagnostic(
                "default_selection",
                "",
                "Не задан вариант; выбран допустимый базовый вариант.",
            )
        )
    return next(iter(sorted(registry)), "")


class BalanceEngine:
    """Level-one budgets shared across every setting; no genre branches."""

    tier = {"low": 0, "medium": 1, "high": 2}
    dice = ("1d4", "1d6", "1d8")
    dc = {"low": 10, "medium": 15, "high": 20}

    @staticmethod
    def encounter_budget(party_size, party_level, difficulty, environment=1):
        factor = {
            "TRIVIAL": 0.25,
            "EASY": 0.5,
            "MEDIUM": 1,
            "HARD": 1.5,
            "VERY_HARD": 2,
            "EXTREME": 3,
        }[difficulty]
        return party_size * (18 + party_level * 12) * factor / environment

    @staticmethod
    def loot_budget(difficulty):
        return {
            "TRIVIAL": 150,
            "EASY": 100,
            "MEDIUM": 75,
            "HARD": 50,
            "VERY_HARD": 40,
            "EXTREME": 25,
        }[difficulty]

    @classmethod
    def validate(cls, setting):
        c = setting.content
        problems = []
        for item in c.items.values():
            for comp in item.components:
                if comp.type == "weapon" and average(comp.damage_expression) > 7:
                    problems.append(item.id)
                if comp.type == "armor" and comp.base + comp.bonus > 18:
                    problems.append(item.id)
        for creature in c.creatures.values():
            if creature.base_hp > 100 or creature.base_armor > 18:
                problems.append(creature.id)
        if problems:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code="balance_warning",
                        stage="balance",
                        entity_type="content",
                        entity_id=i,
                        field="budget",
                        message="Compiler exceeded level-one budget",
                    )
                    for i in problems
                ],
                stage="balance",
            )
        return setting


class EffectFactory:
    @staticmethod
    def build(value, content, diagnostics):
        n = BalanceEngine.tier[value.power] + 1
        damage = pick(content.damage_types, value.damage_concept, diagnostics)
        skill = pick(content.skills, value.expertise, diagnostics)
        # Activation is selected together with the primitive, never independently.
        if value.intent == "damage":
            return (
                "ACTION",
                "enemy",
                [
                    FeatureEffect(
                        type="damage", expression=BalanceEngine.dice[n - 1], key=damage
                    )
                ],
            )
        if value.intent == "healing":
            return (
                "ACTION",
                "ally",
                [FeatureEffect(type="heal_dice", expression=BalanceEngine.dice[n - 1])],
            )
        if value.intent == "mobility" and value.trigger == "active":
            return "BONUS_ACTION", "self", [FeatureEffect(type="dash")]
        if value.intent in ("durability", "defense", "mobility", "expertise"):
            kind, amount, key = {
                "durability": ("max_hp", n, ""),
                "defense": ("armor_class", 1, ""),
                "mobility": ("speed", 5, ""),
                "expertise": ("check_bonus", 1, skill),
            }[value.intent]
            return "PASSIVE", "self", [FeatureEffect(type=kind, value=amount, key=key)]
        if value.intent == "temporary_offensive_buff":
            effects = [FeatureEffect(type="modify_damage", value=n, duration=18)]
            if value.tradeoff != "none":
                diagnostics.append(
                    diagnostic(
                        "capability_limitation",
                        value.name,
                        "Снижение AC временным эффектом не поддерживается; вместо этого снижается точность.",
                    )
                )
                effects.append(
                    FeatureEffect(type="modify_attack", value=-1, duration=18)
                )
            return "BONUS_ACTION", "self", effects
        if value.intent == "control" and value.condition_concept:
            condition = pick(content.conditions, value.condition_concept, diagnostics)
            if condition:
                return (
                    "ACTION",
                    "enemy",
                    [FeatureEffect(type="condition", key=condition)],
                )
        if value.intent == "control":
            return (
                "ACTION",
                "enemy",
                [FeatureEffect(type="grant_disadvantage", duration=6)],
            )
        diagnostics.append(
            diagnostic(
                "narrative_only",
                value.name,
                "Способность сохранена как описание без исполняемого эффекта.",
            )
        )
        return "PASSIVE", "self", []


class FeatureFactory:
    @staticmethod
    def build(value, owner, content, diagnostics, source="CLASS"):
        activation, target, effects = EffectFactory.build(value, content, diagnostics)
        owner = source + "/" + owner
        rid = ""
        if activation != "PASSIVE":
            rid = stable_id("uses", owner + "/" + value.name)
            content.resources[rid] = ResourceDefinition(
                id=rid,
                name=value.name,
                maximum=2,
                initial=2,
                recovery="short",
                recovery_amount=2,
            )
        feature = FeatureDefinition(
            id=stable_id("feature", owner + "/" + value.name),
            name=value.name,
            description=value.description,
            source=source,
            activation=activation,
            target=target,
            reach=30 if target != "self" else 5,
            effects=effects,
            resource=rid,
            uses=2 if rid else 0,
            recharge="short",
        )
        content.features[feature.id] = feature
        return feature.id


class WeaponFactory:
    @staticmethod
    def build(v, c, diagnostics):
        tier = BalanceEngine.tier[v.power]
        # Heavy/two-handed has a bounded gain; fast weapons trade damage for finesse.
        tier = min(2, max(0, tier + (v.hands == "two") - (v.speed == "fast")))
        return WeaponComponent(
            damage_expression=BalanceEngine.dice[tier],
            damage_type=pick(c.damage_types, v.damage_concept, diagnostics),
            attack_ability="dexterity"
            if v.approach == "precision" or v.style == "ranged"
            else "strength",
            range={"close": 20, "near": 60, "far": 120}[v.reach]
            if v.style == "ranged"
            else 5,
            hands=2 if v.hands == "two" else 1,
            proficiency="martial" if v.weight == "heavy" else "simple",
            properties=["ranged"]
            if v.style == "ranged"
            else ["finesse"]
            if v.approach == "precision"
            else [],
        )


class ArmorFactory:
    @staticmethod
    def build(v):
        base, cap = {"light": (11, 5), "medium": (13, 2), "heavy": (15, 0)}[v.weight]
        return ArmorComponent(
            base=base + (v.protection == "high"),
            dex_cap=cap,
            proficiency=v.weight,
            stealth_disadvantage=v.mobility == "restricted",
        )


class EconomyGenerator:
    @staticmethod
    def price(value, config, rng):
        category = {
            "weapon": 3,
            "armor": 4,
            "medical": 1,
            "tool": 2,
            "artifact": 5,
            "key": 1,
            "currency": 1,
            "quest": 1,
            "container": 1,
            "ammo": 1,
            "device": 3,
        }[value.category]
        rarity = {"common": 1, "uncommon": 2, "rare": 4}[value.rarity]
        economy = {"scarce": 1.25, "standard": 1, "abundant": 0.8}[config.economy]
        return max(
            1,
            round(
                (8 + 8 * BalanceEngine.tier[value.power])
                * category
                * rarity
                * economy
                * rng.uniform(0.9, 1.1)
            ),
        )


class ItemFactory:
    @staticmethod
    def build(v, c, diagnostics):
        slots, components = [], []
        if v.category == "weapon":
            components = [WeaponFactory.build(v, c, diagnostics)]
            slots = ["MAIN_HAND"]
            if v.supply == "ammunition":
                ammo_name = v.supply_concept or v.name[:100] + " · боеприпасы"
                ammo_type = stable_id("ammunition", ammo_name)
                ammo_id = stable_id("item", ammo_name)
                c.items.setdefault(
                    ammo_id,
                    ContentItem(
                        id=ammo_id,
                        name=ammo_name,
                        category="ammo",
                        value=2,
                        components=[dict(type="ammo", ammo_type=ammo_type)],
                    ),
                )
                components.append(
                    dict(
                        type="magazine",
                        ammo_type=ammo_type,
                        capacity=6,
                        initial=6,
                        modes={"single": 1},
                    )
                )
        elif v.category == "armor":
            components = [ArmorFactory.build(v)]
            slots = ["TORSO"]
        elif v.category == "medical":
            components = [
                dict(type="medical", fixed_healing=4 + 2 * BalanceEngine.tier[v.power])
            ]
        elif v.category == "tool":
            components = [
                dict(
                    type="tool",
                    skill_id=pick(c.skills, v.expertise, diagnostics),
                    modifier=1,
                    requires_equipped=False,
                )
            ]
        elif v.category == "ammo":
            components = [
                dict(
                    type="ammo",
                    ammo_type=stable_id("ammunition", v.supply_concept or v.name),
                )
            ]
        elif v.category == "device":
            components = [dict(type="artifact")]
        elif v.category == "container":
            components = [dict(type="container", capacity=10)]
        else:
            components = [dict(type=v.category)]
        features = [
            FeatureFactory.build(f, v.name, c, diagnostics, "ITEM")
            for f in v.capabilities
        ]
        return ContentItem(
            id=stable_id("item", concept_key(v)),
            name=v.name,
            description=v.description,
            category=v.category,
            tags=v.tags,
            value=(10, 30, 75)[BalanceEngine.tier[v.power]]
            * {"common": 1, "uncommon": 2, "rare": 4}[v.rarity],
            weight={"light": 1, "medium": 3, "heavy": 6}[v.weight],
            equipment_slots=slots,
            components=components,
            effects=features,
            starting_available=v.rarity != "rare" and v.category != "quest",
        )


class CreatureFactory:
    @staticmethod
    def build(v, c, diagnostics):
        tier = BalanceEngine.tier[v.threat]
        hp = (6, 16, 28)[tier] + {
            "minion": 0,
            "brute": 8,
            "boss": 16,
            "defender": 6,
        }.get(v.role, 0)
        stats = {a: 10 for a in ABILITIES}
        stats[PRIMARY[v.role]] = 12 + tier * 2
        stats["constitution"] = 12
        return CreatureTemplate(
            id=stable_id("creature", concept_key(v)),
            name=v.name,
            description=v.description,
            category=v.role,
            tags=v.tags,
            attributes=stats,
            base_hp=hp,
            base_armor={"fragile": 10, "normal": 12, "armored": 14}[v.defense],
            attacks=[
                CreatureAttack(
                    id=stable_id("attack", concept_key(v)),
                    name=v.attack[:120] or v.name,
                    damage_type=pick(c.damage_types, v.damage_concept, diagnostics),
                    damage_expression=BalanceEngine.dice[tier],
                    accuracy=2 + tier,
                    range=60 if v.role in ("ranged", "caster") else 5,
                )
            ],
            features=[
                FeatureFactory.build(f, v.name, c, diagnostics) for f in v.abilities
            ],
            damage_modifiers={
                **{pick(c.damage_types, n, diagnostics): 0.5 for n in v.resistances},
                **{pick(c.damage_types, n, diagnostics): 2 for n in v.weaknesses},
            },
            ai_profile={
                "defender": "defensive",
                "support": "support",
                "controller": "cautious",
            }.get(v.role, "aggressive"),
            habitats=v.habitats,
        )


class ProceduralContentCompiler:
    version = VERSION

    def compile(self, id, value, revision=0, generation=None):
        dto = SemanticSettingDTO.model_validate(
            value.model_dump() if isinstance(value, SemanticSettingDTO) else value
        )
        from .generation_config import GenerationConfig, GeneratorContext
        from .generation_coverage import world_coverage

        config = (
            generation
            if isinstance(generation, GenerationConfig)
            else GenerationConfig.model_validate(generation or {})
        )
        source = dto.model_dump()
        dto = world_coverage(dto, config)
        context = GeneratorContext(config.seed)
        c, diagnostics = ContentRegistry(), []
        for v in dto.skills:
            key = stable_id("skill", concept_key(v))
            c.skills[key] = SkillDefinition(
                id=key,
                name=v.name,
                description=v.description,
                default_ability=AFFINITIES[v.affinity],
                tags=v.tags,
            )
        for v in dto.damage_concepts:
            key = stable_id("damage", concept_key(v))
            c.damage_types[key] = DamageTypeDefinition(
                id=key, name=v.name, description=v.description
            )
        if not c.damage_types:
            c.damage_types["physical"] = DamageTypeDefinition(
                id="physical", name="Физический"
            )
        c.equipment_profiles["standard"] = EquipmentProfile(
            id="standard",
            name="Базовое снаряжение",
            slots=[
                EquipmentSlot(
                    id="MAIN_HAND", name="Основной инструмент", position="left"
                ),
                EquipmentSlot(
                    id="OFF_HAND", name="Второй инструмент", position="right"
                ),
                EquipmentSlot(id="TORSO", name="Корпус", position="body"),
            ],
        )
        from .conditions import ConditionDefinition

        for v in dto.conditions:
            key = stable_id("condition", concept_key(v))
            effects = {
                "hindered": dict(speed_multiplier=0.5),
                "disoriented": dict(checks=-1),
                "exposed": dict(incoming_attack=1),
                "protected": dict(incoming_attack=-1),
                "unsupported": {},
            }[v.intent]
            if v.intent == "unsupported":
                diagnostics.append(
                    diagnostic(
                        "narrative_only",
                        v.name,
                        "Состояние не имеет поддерживаемого эффекта.",
                    )
                )
            c.conditions[key] = ConditionDefinition(
                id=key, name=v.name, expires="turn_start", **effects
            )
        for v in dto.species:
            key = stable_id("species", concept_key(v))
            c.species[key] = SpeciesDefinition(
                id=key,
                name=v.name,
                description=v.description,
                speed={"slow": 25, "normal": 30, "fast": 35}[v.movement],
                equipment_profile="standard",
                features=[
                    FeatureFactory.build(f, v.name, c, diagnostics, "SPECIES")
                    for f in v.traits
                ],
            )
        for v in dto.items:
            item = ItemFactory.build(v, c, diagnostics)
            item.value = EconomyGenerator.price(
                v, config, context.rng("price", item.id)
            )
            c.items[item.id] = item
        for v in dto.professions:
            key = stable_id("class", concept_key(v))
            primary = PRIMARY[v.role]
            skills = list(
                dict.fromkeys(pick(c.skills, n, diagnostics) for n in v.expertise)
            ) or sorted(
                c.skills, key=lambda k: (c.skills[k].default_ability != primary, k)
            )
            equipment = (
                list(dict.fromkeys(pick(c.items, n, diagnostics) for n in v.equipment))
                if c.items
                else []
            )
            # Only a compatible loadout is exposed to the existing build validator.
            armor = {
                "defender": ["light", "medium", "heavy"],
                "brute": ["light", "medium"],
            }.get(v.role, ["light"])
            weapons = (
                ["simple", "martial"]
                if v.role not in ("caster", "support", "controller")
                else ["simple"]
            )

            def legal(i):
                return all(
                    comp.type != "armor" or comp.proficiency in armor
                    for comp in c.items[i].components
                ) and all(
                    comp.type != "weapon" or comp.proficiency in weapons
                    for comp in c.items[i].components
                )

            if any(not legal(i) for i in equipment):
                diagnostics.append(
                    diagnostic(
                        "equipment_fallback",
                        v.name,
                        "Несовместимое снаряжение заменено допустимым.",
                    )
                )
            equipment = [i for i in equipment if legal(i)]
            if not equipment:
                equipment = [
                    i
                    for i in sorted(c.items)
                    if legal(i) and c.items[i].category == "weapon"
                ][:1]
            features = [
                FeatureFactory.build(f, v.name, c, diagnostics)
                for f in v.abilities
                if v.casting != "prepared_slots"
                or f.intent not in ("healing", "damage")
            ]
            resources = []
            if v.resource:
                r = v.resource
                rid = stable_id("resource", v.name + "/" + r.name)
                maximum = (2, 3, 4)[BalanceEngine.tier[r.abundance]]
                c.resources[rid] = ResourceDefinition(
                    id=rid,
                    name=r.name,
                    description=r.description,
                    maximum=maximum,
                    initial=maximum,
                    recovery={"consumable": "none", "rest": "short", "daily": "long"}[
                        r.recovery
                    ],
                    recovery_amount=maximum if r.recovery != "consumable" else 0,
                )
                resources.append(rid)
                for fid in features:
                    feature = c.features[fid]
                    if feature.activation != "PASSIVE":
                        c.resources.pop(feature.resource, None)
                        feature.resource = ""
                        feature.uses = 0
                        feature.resource_cost = {rid: 1}
            c.archetypes[key] = Archetype(
                id=key,
                name=v.name,
                description=v.description,
                primary_abilities=[primary, "constitution"],
                hit_die=10
                if v.role in ("brute", "defender", "boss")
                else 6
                if v.role == "caster"
                else 8,
                saves=[primary, "constitution"],
                skills=skills,
                skill_count=min(2, len(skills)),
                armor=armor,
                weapons=weapons,
                equipment=equipment,
                features=features,
                resources=resources,
            )
            if v.casting == "prepared_slots":
                powers = []
                for n, feature in enumerate(v.abilities or []):
                    pid = stable_id("power", v.name + "/" + feature.name)
                    healing = feature.intent == "healing"
                    if feature.intent not in ("healing", "damage"):
                        continue
                    level = 0 if not powers and not healing else 1
                    c.powers[pid] = SpellDefinition(
                        id=pid,
                        name=feature.name,
                        description=feature.description,
                        school=v.power_source[:120] or "power",
                        classes=[key],
                        level=level,
                        damage_type=pick(
                            c.damage_types, feature.damage_concept, diagnostics
                        ),
                        healing="1d6" if healing else "",
                        damage="" if healing else "1d6",
                        target_type="ally" if healing else "enemy",
                        attack_roll=not healing,
                    )
                    powers.append(pid)
                if not powers:
                    diagnostics.append(
                        diagnostic(
                            "capability_limitation",
                            v.name,
                            "Книга заклинаний пуста: нужны семантические способности урона или лечения.",
                        )
                    )
                c.spellcasting[key] = SpellcastingFeature(
                    ability=primary,
                    known=max(1, len(powers)),
                    prepared=max(1, len(powers)),
                    defaults=powers,
                    slots={"1": 2},
                )
        for v in dto.backgrounds:
            key = stable_id("background", concept_key(v))
            c.backgrounds[key] = BackgroundDefinition(
                id=key,
                name=v.name,
                description=v.description,
                skills=list(
                    dict.fromkeys(pick(c.skills, n, diagnostics) for n in v.expertise)
                )[:2]
                or [next(iter(c.skills))],
                contacts=v.contacts,
                knowledge=v.knowledge,
                tags=v.tags,
                equipment=list(
                    dict.fromkeys(pick(c.items, n, diagnostics) for n in v.equipment)
                )
                if c.items
                else [],
                starting_gold=10,
            )
        for v in dto.creatures:
            creature = CreatureFactory.build(v, c, diagnostics)
            creature.base_hp += context.rng("hp", creature.id).randint(0, 3)
            c.creatures[creature.id] = creature
        from .progression import LevelRule

        c.levels = {
            str(level): LevelRule(
                xp=100 * (level - 1) ** 3,
                proficiency=2 + (level - 1) // 4,
                asi=level in (4, 8, 12, 16, 19),
                spell_slots={
                    key: {"1": min(4, 2 + level // 2)} for key in c.spellcasting
                },
            )
            for level in range(1, 21)
        }
        affordable = max(
            (
                sum(c.items[i].value for i in cls.equipment)
                for cls in c.archetypes.values()
            ),
            default=150,
        )
        metadata = {
            entry.id: dict(
                generated_by=group,
                generator_version=VERSION,
                seed=config.seed,
                template=getattr(entry, "category", group),
                balance_tier="starter",
            )
            for group in (
                "species",
                "archetypes",
                "backgrounds",
                "skills",
                "items",
                "features",
                "creatures",
                "resources",
                "powers",
                "conditions",
            )
            for entry in getattr(c, group).values()
        }
        setting = SettingDefinition(
            id=id,
            name=dto.name,
            description=dto.description,
            genre=dto.genre,
            tone=dto.tone,
            themes=dto.themes,
            technology_description=dto.technology,
            supernatural_description=dto.supernatural,
            society_description="\n".join(v.description for v in dto.cultures),
            custom_lore=dto.lore,
            content=c,
            revision=revision,
            compiler_version=VERSION,
            semantic_source=source,
            generation_config=config,
            generation_metadata=metadata,
            starting_currency=max(150, affordable + 30),
            diagnostics=diagnostics,
        )
        return BalanceEngine.validate(SettingValidator().validate(setting))
