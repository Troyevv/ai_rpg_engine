"""Code-owned role variants; no numeric clones and no invented creature species."""

from .semantic import SemanticItem, SemanticFeature
import hashlib
from .generation_config import GeneratorContext

PROFESSIONS = [
    ("разведка", "skirmisher", "mobility"),
    ("защита", "defender", "defense"),
    ("помощь", "support", "healing"),
    ("контроль", "controller", "control"),
    ("точность", "ranged", "expertise"),
    ("натиск", "brute", "durability"),
    ("эвакуация", "support", "mobility"),
    ("наблюдение", "ranged", "expertise"),
    ("сдерживание", "defender", "control"),
    ("восстановление", "support", "healing"),
]
SKILLS = [
    ("анализ", "reasoning"),
    ("практика", "precision"),
    ("наблюдение", "awareness"),
    ("переговоры", "social"),
    ("усилие", "physical"),
    ("выдержка", "endurance"),
]
ORIGINS = [
    "полевой опыт",
    "обучение",
    "ремесло",
    "служба",
    "изгнание",
    "наследие",
    "экспедиция",
    "торговля",
    "потеря",
    "восстановление",
]
WEAPONS = [
    ("компактный", "low", "light", "fast", "one", "precision", "close"),
    ("служебный", "medium", "medium", "normal", "one", "power", "near"),
    ("точный", "medium", "light", "normal", "two", "precision", "far"),
    ("тяжёлый", "high", "heavy", "slow", "two", "power", "far"),
    ("мобильный", "low", "light", "fast", "one", "precision", "near"),
    ("штурмовой", "high", "heavy", "normal", "two", "power", "close"),
]
ARMOR = [
    ("подвижная", "light", "low", "free"),
    ("усиленная", "medium", "medium", "normal"),
    ("барьерная", "heavy", "high", "restricted"),
]
MEDICAL = [
    ("первая помощь", "low"),
    ("стабилизация", "medium"),
    ("восстановление", "high"),
]
CONTEXTS = ["полевой", "стационарный", "экспедиционный", "аварийный"]


def world_coverage(blueprint, config):
    dto = blueprint.model_copy(deep=True)
    context = GeneratorContext(config.seed)

    def grow(values, target, kind, variants, apply):
        originals = values[:]
        if not originals:
            return values
        candidates = [
            (i, j, k)
            for k in range(4)
            for j in range(len(variants))
            for i in range(len(originals))
        ]
        # Per-role ordering is seeded; authored entries stay untouched.
        candidates = sorted(
            candidates, key=lambda x: (x[2], context.rng(kind, str(x)).random())
        )
        names = {v.name for v in values}
        for i, j, k in candidates:
            if len(values) >= target:
                break
            source = originals[i]
            v = source.model_copy(deep=True)
            label = variants[j][0] if isinstance(variants[j], tuple) else variants[j]
            v.name = f"{source.name[:65]}: {label} ({CONTEXTS[k]})"[:120]
            if v.name in names:
                continue
            names.add(v.name)
            v.key = f"{source.key or kind + '/' + str(i)}/{j}/{k}"
            v.description = f"{source.description[:1200]} Специализация: {label}; применение: {CONTEXTS[k]}."
            apply(v, variants[j], i, k)
            values.append(v)
        return values

    grow(
        dto.skills,
        config.targets["skills"],
        "skill",
        SKILLS,
        lambda v, spec, i, k: setattr(v, "affinity", spec[1]),
    )
    skill_keys = [
        "skill_"
        + hashlib.sha256((v.key or v.name).strip().casefold().encode()).hexdigest()[:16]
        for v in dto.skills
    ]

    def origin(v, spec, i, k):
        v.expertise = [skill_keys[(i + k + ORIGINS.index(spec)) % len(skill_keys)]]
        v.knowledge = [f"{spec}: {dto.name}"]
        v.contacts = [f"{dto.name}: {spec}"]

    grow(dto.backgrounds, config.targets["backgrounds"], "origin", ORIGINS, origin)

    def profession(v, spec, i, k):
        v.role = spec[1]
        v.expertise = [skill_keys[(i + k) % len(skill_keys)]]
        v.equipment = []  # Legal loadout selected by compiler for the new role.
        v.casting = "none"
        v.abilities = [SemanticFeature(name=f"{v.name[:85]}: приём", intent=spec[2])]
        v.tactics = f"{spec[0]}: {CONTEXTS[k]} контекст"

    grow(
        dto.professions,
        config.targets["professions"],
        "profession",
        PROFESSIONS,
        profession,
    )
    for v in dto.professions:
        if not v.abilities:
            v.abilities = [
                SemanticFeature(name=v.name[:90] + ": подготовка", intent="expertise")
            ]

    def weapon(v, spec, i, k):
        _, v.power, v.weight, v.speed, v.hands, v.approach, v.reach = spec

    def armor(v, spec, i, k):
        _, v.weight, v.protection, v.mobility = spec

    def medical(v, spec, i, k):
        v.power = spec[1]

    def tool(v, spec, i, k):
        v.expertise = skill_keys[(i + k + SKILLS.index(spec)) % len(skill_keys)]

    for group, category, name, specs, apply in [
        ("weapons", "weapon", "Средство защиты", WEAPONS, weapon),
        ("armor", "armor", "Защитное снаряжение", ARMOR, armor),
        ("medical", "medical", "Средство восстановления", MEDICAL, medical),
        ("utility", "tool", "Рабочий инструмент", SKILLS, tool),
    ]:
        values = [v for v in dto.items if v.category == category]
        if not values:
            values = [
                SemanticItem(
                    key="base/" + category,
                    name=f"{dto.name[:65]}: {name}",
                    category=category,
                )
            ]
            dto.items.extend(values)
        before = len(values)
        grow(values, config.targets[group], group, specs, apply)
        dto.items.extend(values[before:])

    def creature(v, spec, i, k):
        v.role = spec[1]
        v.threat = ("low", "medium", "high")[k % 3]
        v.defense = ("fragile", "normal", "armored")[k % 3]
        v.behavior = f"{spec[0]}: {v.description}"

    # Empty means no creature threats in this fiction. Never derive enemies from species.
    grow(dto.creatures, config.targets["creatures"], "threat", PROFESSIONS, creature)
    return dto
