"""Trusted declarative rules, independent of campaign content and React."""

import json
from pathlib import Path
from .models import Ruleset


def load_ruleset(ruleset_id="d20-basic-v2"):
    paths = {p.stem: p for p in Path(__file__).with_name("catalog").glob("*.json")}
    if ruleset_id not in paths:
        raise ValueError("Неподдерживаемый ruleset")
    return Ruleset.model_validate(json.loads(paths[ruleset_id].read_text()))
