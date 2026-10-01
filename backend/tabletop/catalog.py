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
