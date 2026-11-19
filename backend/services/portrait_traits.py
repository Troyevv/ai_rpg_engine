"""Finite vocabulary for PUBLIC portrait styling; never interpret literary prose."""
from typing import get_args
from backend.runtime_v3.models import FacialHair

FACIAL_HAIR = get_args(FacialHair)
STYLES = {
    'facial_hair': FACIAL_HAIR,
    'face': ('oval', 'narrow', 'angular', 'broad', 'long', 'round', 'soft'),
    'hair': ('short', 'long', 'bob', 'curly', 'medium', 'wavy', 'fringe', 'bald'),
    'hair_color': ('black', 'brown', 'blond', 'dark_blond', 'red', 'grey', 'white'),
    'skin': ('light', 'warm', 'beige', 'deep', 'olive', 'peach', 'sand'),
    'eyes': ('hazel', 'green', 'grey', 'brown', 'grey_green', 'blue', 'light_green', 'grey_blue'),
    'clothing': ('plain', 'tshirt', 'shirt', 'blazer', 'jacket', 'cardigan', 'jumper', 'sweater'),
    'clothing_color': ('dark', 'light', 'blue', 'green', 'brown', 'red', 'sand'),
}


def input_diagnostics(cards):
    """Address unsupported cosmetic hints before later canonical preparation.

    The optional hint object is the repair unit: unsupported features can be
    omitted without inventing a replacement or changing literary appearance.
    """
    options = dict(STYLES, form=('human', 'neutral'))
    errors = []
    for index, card in enumerate(cards if isinstance(cards, list) else []):
        if not isinstance(card, dict) or 'portrait_traits' not in card:
            continue
        hints = card['portrait_traits']
        if hints is None:  # Legacy optional null was always equivalent to absent.
            continue
        invalid = [k for k, v in hints.items() if k not in options or v not in options[k]] if isinstance(hints, dict) else None
        if invalid or invalid is None:
            errors.append(dict(path=f'/characters/{index}/portrait_traits', category='portrait_traits',
                message='portrait_traits: используйте только поддерживаемые признаки из схемы. '
                        'Неподдерживаемые признаки можно опустить; корректные признаки и Внешность сохраните.',
                invalid_fields=invalid, allowed={k:list(v) for k,v in options.items()}))
    return errors
# Exact, unambiguous values of a *typed* initial feature, never substrings of
# sentences, names, legacy_text, biographies or derived identity characteristics.
_TYPED = {
    'facial_hair': ('facial_hair', {
        'гладко выбрит':'clean_shaven', 'гладко выбритое лицо':'clean_shaven', 'щетина':'stubble',
        'усы':'mustache', 'короткая борода':'short_beard', 'полная борода':'full_beard'}),
    'natural_hair_color': ('hair_color', {
        'чёрные':'black', 'черные':'black', 'тёмные':'black', 'темные':'black', 'каштановые':'brown',
        'светлые':'blond', 'блонд':'blond', 'русые':'dark_blond', 'рыжие':'red',
        'седые':'grey', 'белые':'white'}),
    'hairstyle': ('hair', {
        'короткие':'short', 'длинные':'long', 'каре':'bob', 'кудрявые':'curly',
        'средние':'medium', 'волнистые':'wavy', 'чёлка':'fringe', 'без волос':'bald'}),
    'skin': ('skin', {'светлая':'light','смуглая':'deep','оливковая':'olive'}),
    'eye_color': ('eyes', {
        'ореховые':'hazel', 'зелёные':'green', 'зеленые':'green', 'серые':'grey',
        'карие':'brown', 'серо-зелёные':'grey_green', 'голубые':'blue', 'синие':'blue',
        'светло-зелёные':'light_green'}),
}


def input_schema():
    return {'type':'object', 'properties':{'form':{'enum':['human','neutral']},
            **{k:{'enum':list(v)} for k,v in STYLES.items()}}, 'additionalProperties':False}


def graphic_choices(actor, hints=None, *, facial_hair=False):
    approved = {}
    if isinstance(hints,dict):
        for field, options in STYLES.items():
            if (field != 'facial_hair' or facial_hair) and hints.get(field) in options:
                approved[field] = options.index(hints[field])
    # Existing AppearanceProfile carries open text, not typed color IDs. Handle
    # only uncomplicated public initial features that match a supported value.
    # Never bake a private or evolving feature into a shared visual descriptor.
    appearance=actor.get('appearance')
    items=appearance.get('items') if isinstance(appearance,dict) else None
    matches = {}
    for item in items.values() if isinstance(items,dict) else ():
        if not isinstance(item,dict) or not isinstance(item.get('kind'),str): continue
        if item['kind'] == 'facial_hair' and not facial_hair: continue
        if item.get('source_event_id') or item.get('fact_id') or item.get('condition_id') or item.get('revision',1)!=1:
            # A hint from a model which could see private source material is
            # insufficient evidence to publish that same facial feature.
            if item['kind'] == 'facial_hair': approved.pop('facial_hair', None)
            continue
        spec=_TYPED.get(item.get('kind'))
        if not spec or not isinstance(item.get('text'),str): continue
        field, names=spec
        token=item['text'].casefold().strip()
        matches.setdefault(field,set()).add(names.get(token,token))
    for field, tokens in matches.items():
        if len(tokens)==1:
            token=next(iter(tokens))
            if token in STYLES[field]:
                choice=STYLES[field].index(token)
                if field in approved and approved[field]!=choice:
                    raise ValueError('portrait_traits противоречит структурированной внешности: '+field)
                approved[field]=choice
    return approved
