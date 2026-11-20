"""Finite vocabulary for PUBLIC portrait styling; never interpret literary prose."""
from typing import get_args
from backend.runtime_v3.models import FacialHair

FACIAL_HAIR = get_args(FacialHair)
from backend.runtime_v3.portrait_catalog import CATALOG, STYLES, ILLUSTRATION_STYLES


def input_diagnostics(cards, version=3):
    """Address unsupported cosmetic hints before later canonical preparation.

    The optional hint object is the repair unit: unsupported features can be
    omitted without inventing a replacement or changing literary appearance.
    """
    options = dict(ILLUSTRATION_STYLES if version==4 else STYLES, form=('human', 'neutral'))
    errors = []
    for index, card in enumerate(cards if isinstance(cards, list) else []):
        if not isinstance(card, dict) or 'portrait_traits' not in card:
            continue
        hints = card['portrait_traits']
        if hints is None:  # Legacy optional null was always equivalent to absent.
            continue
        invalid = [k for k, v in hints.items() if k not in options or not isinstance(v,str) or v not in options[k]] if isinstance(hints, dict) else None
        if invalid or invalid is None:
            errors.append(dict(path=f'/characters/{index}/portrait_traits', category='portrait_traits',
                message='Неподдерживаемые параметры иллюстрации пропущены.', invalid_fields=invalid))
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
    'face': ('face', {}),
    'build': ('build', {'худощавый':'slim','полный':'full','коренастый':'stocky','широкоплечий':'broad','атлетичный':'athletic','средний':'average'}),
    'skin': ('skin', {'светлая':'light','смуглая':'deep','оливковая':'olive'}),
    'eye_color': ('eyes', {
        'ореховые':'hazel', 'зелёные':'green', 'зеленые':'green', 'серые':'grey',
        'карие':'brown', 'серо-зелёные':'grey_green', 'голубые':'blue', 'синие':'blue',
        'светло-зелёные':'light_green'}),
}


_LABEL_IDS = {field:{label.casefold():key for key,label in options.items()}
              for field,options in CATALOG['styles'].items()}


def input_schema(version=3):
    options = ILLUSTRATION_STYLES if version==4 else STYLES
    return {'type':'object', 'properties':{'form':{'enum':['human','neutral']},
            **{k:{'enum':list(v)} for k,v in options.items()}}, 'additionalProperties':False}


def graphic_choices(actor, hints=None, *, facial_hair=False, warnings=None, catalog_labels=False, semantic=False):
    styles=ILLUSTRATION_STYLES if semantic else STYLES
    approved = {}
    if isinstance(hints,dict):
        for field, options in styles.items():
            if (field != 'facial_hair' or facial_hair) and isinstance(hints.get(field),str) and hints[field] in options:
                approved[field] = hints[field] if semantic else options.index(hints[field])
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
            if item['kind'] in _TYPED: approved.pop(_TYPED[item['kind']][0], None)
            continue
        spec=_TYPED.get(item.get('kind'))
        if not spec or spec[0] not in styles or not isinstance(item.get('text'),str): continue
        field, names=spec
        token=item['text'].casefold().strip()
        if semantic:
            token = next((key for key,label in styles[field].items() if label.casefold()==token),token)
        elif catalog_labels:
            token = _LABEL_IDS[field].get(token,token)
        elif field == 'face':
            continue
        matches.setdefault(field,set()).add(names.get(token,token))
    for field, tokens in matches.items():
        if len(tokens)==1:
            token=next(iter(tokens))
            if token in styles[field]:
                choice=token if semantic else STYLES[field].index(token)
                if field in approved and approved[field]!=choice:
                    if warnings is not None:
                        warnings.append('Открытая черта имеет приоритет: '+field)
                approved[field]=choice
    return approved
