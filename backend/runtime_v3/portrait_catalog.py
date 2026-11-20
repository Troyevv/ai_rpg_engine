"""Curated public art vocabulary shared with the TypeScript renderer."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'shared/portrait-catalog.json').read_text(encoding='utf-8'))
STYLES = {key: tuple(labels) for key, labels in CATALOG['styles'].items()}

ILLUSTRATION = json.loads((Path(__file__).resolve().parents[2] / 'shared/portrait-illustration.json').read_text(encoding='utf-8'))
ILLUSTRATION_STYLES = {**ILLUSTRATION['styles'], 'trim': ILLUSTRATION['styles']['clothing_color']}


def art_version(style):
    return 4 if style in ('anime', 'semi_realistic') else 3
