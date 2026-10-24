"""Lossless authoring adaptation, never a Runtime/save migration."""
from copy import deepcopy
import logging

from backend.runtime_v3.appearance import KINDS


log = logging.getLogger(__name__)

CATEGORIES = {kind: category for category, kinds in KINDS.items() for kind in kinds}
# These labels do not establish canonical traits (hair_color may be dyed).
PROSE_KINDS = {'hair_color', 'hair', 'style', 'clothing', 'clothes', 'outfit', 'appearance'}


def normalize_batch(payload):
    value = deepcopy(payload)
    if not isinstance(value, dict) or not isinstance(value.get('characters'), dict):
        return value
    for actor in value['characters'].values():
        if not isinstance(actor, dict):
            continue
        profile = actor.get('appearance')
        if not isinstance(profile, dict) or not isinstance(profile.get('items'), dict):
            continue
        for key, item in list(profile['items'].items()):
            if not isinstance(item, dict) or not isinstance(item.get('kind'), str):
                continue
            kind = item['kind']
            # Do not repair condition projections or historical/evidence-bearing rows.
            baseline = (not any(item.get(k) for k in ('condition_id', 'source_event_id', 'fact_id', 'evidence'))
                        and item.get('revision', 1) == 1)
            if not baseline or profile.get('applied'):
                continue
            if kind in CATEGORIES and kind != 'condition':
                if item.get('category') != CATEGORIES[kind]:
                    log.info('generated_appearance: category normalized for canonical kind %s', kind)
                item['category'] = CATEGORIES[kind]
            elif kind in PROSE_KINDS:
                allowed = {'category', 'kind', 'text', 'revision', 'condition_id', 'source_event_id', 'fact_id', 'evidence'}
                text = item.get('text')
                legacy = profile.get('legacy_text', '')
                if set(item) <= allowed and isinstance(text, str) and text.strip() and isinstance(legacy, str):
                    profile['legacy_text'] = legacy + ('\n' if legacy else '') + text
                    del profile['items'][key]
                    log.info('generated_appearance: unclassified baseline preserved as prose (%s)', kind)
    return value


def character_schema(model):
    schema = model.model_json_schema()
    # JSON Schema cannot derive this cross-field invariant from Pydantic's validator.
    schema['$defs']['AppearanceFeature']['allOf'] = [{'anyOf':[
        {'properties': {'category': {'const': category}, 'kind': {'enum': sorted(kinds)}}}
        for category, kinds in KINDS.items()]}]
    return schema


INSTRUCTIONS = '''Appearance: category/kind pairs are mandatory: intrinsic = eye_color,
natural_hair_color, skin, face; body = build, height; modification = scar, tattoo,
piercing, cosmetic; presentation = hairstyle, facial_hair; condition = condition.
Only explicitly natural hair color belongs to natural_hair_color. Hairstyle is
presentation. Keep clothing, outfits, dyed/unspecified hair color and mixed or
unclassified visual prose verbatim in appearance.legacy_text; do not invent a
clothing/style kind or classify clothes as cosmetic, skin or body. Structured
items require nonempty text (at most 600 characters). Condition projections need
condition_id and empty text; never invent a condition to describe appearance.
Initial baseline traits use revision 1, no source_event_id/fact_id/evidence and no
applied operations. Preserve useful visual detail without forcing classification.
'''
