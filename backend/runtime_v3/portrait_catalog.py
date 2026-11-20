"""Curated public art vocabulary shared with the TypeScript renderer."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'shared/portrait-catalog.json').read_text(encoding='utf-8'))
STYLES = {key: tuple(labels) for key, labels in CATALOG['styles'].items()}

# Old descriptors use numeric indices into the original palettes.
LEGACY_STYLES = {**STYLES, 'face':STYLES['face'][:7], 'hair':STYLES['hair'][:16],
                 'clothing':STYLES['clothing'][:15], 'hair_color':STYLES['hair_color'][:7],
                 'clothing_color':STYLES['clothing_color'][:7], 'facial_hair':STYLES['facial_hair'][:5]}
CLASSIC_OPTIONS = {**STYLES, 'accent_color':STYLES['clothing_color'], **{key: tuple(options) for key, options in CATALOG['features'].items()}}

# Read descriptors already saved with the archived draft renderer.
ILLUSTRATION = json.loads((Path(__file__).resolve().parents[2] / 'shared/portrait-illustration.json').read_text(encoding='utf-8'))
ILLUSTRATION_STYLES = {**ILLUSTRATION['styles'], 'trim': ILLUSTRATION['styles']['clothing_color']}
