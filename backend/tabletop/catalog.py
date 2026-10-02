"""Trusted declarative rules, independent of campaign content and React."""

import json
from pathlib import Path
from .models import Ruleset


def load_ruleset(ruleset_id="d20-basic-v2"):
    paths = {p.stem: p for p in Path(__file__).with_name("catalog").glob("*.json")}
    if ruleset_id not in paths:
        raise ValueError("Неподдерживаемый ruleset")
    rules = Ruleset.model_validate(json.loads(paths[ruleset_id].read_text()))
    items = {item.id for item in rules.items}
    from .dice import DiceEngine

    for feature in rules.features.values():
        for effect in feature.effects:
            if effect.type == "heal_dice":
                DiceEngine.parse(effect.expression)
    for spell in rules.spells.values():
        if not set(spell.effects) <= set(rules.condition_definitions):
            raise ValueError("Заклинание ссылается на неизвестное состояние")
        for expression in (spell.damage, spell.healing):
            if expression:
                DiceEngine.parse(expression)
    for level in rules.levels.values():
        if any(
            fid not in rules.features for ids in level.features.values() for fid in ids
        ):
            raise ValueError("Неизвестная особенность развития")
    if not set(rules.feats) <= set(rules.features):
        raise ValueError("Неизвестная черта")
    for cls, casting in rules.spellcasting.items():
        if cls not in rules.classes or not set(casting.defaults) <= set(rules.spells):
            raise ValueError("Некорректный каталог магического класса")
    for group in (rules.classes, rules.species, rules.backgrounds):
        for entry in group.values():
            if not set(
                entry.get("features", []) + entry.get("feature_choices", [])
            ) <= set(rules.features):
                raise ValueError("Каталог ссылается на неизвестную особенность")
            if (
                not set(entry.get("skills", [])) <= set(rules.skills)
                or not set(entry.get("equipment", [])) <= items
            ):
                raise ValueError("Некорректные навыки или предметы каталога")
    return rules
