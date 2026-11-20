"""Curated public art vocabulary shared with the TypeScript renderer."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'shared/portrait-catalog.json').read_text(encoding='utf-8'))
STYLES = {key: tuple(labels) for key, labels in CATALOG['styles'].items()}
