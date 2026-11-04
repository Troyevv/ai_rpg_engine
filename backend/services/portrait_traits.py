"""Finite vocabulary for PUBLIC portrait styling; never interpret literary prose."""
STYLES = {
    'face': ('oval', 'narrow', 'angular', 'broad', 'long', 'round', 'soft'),
    'hair': ('short', 'long', 'bob', 'curly', 'medium', 'wavy', 'fringe', 'bald'),
    'hair_color': ('black', 'brown', 'blond', 'dark_blond', 'red', 'grey', 'white'),
    'skin': ('light', 'warm', 'beige', 'deep', 'olive', 'peach', 'sand'),
    'eyes': ('hazel', 'green', 'grey', 'brown', 'grey_green', 'blue', 'light_green'),
    'clothing': ('plain', 'tshirt', 'shirt', 'blazer', 'jacket', 'cardigan', 'jumper', 'sweater'),
    'clothing_color': ('dark', 'light', 'blue', 'green', 'brown', 'red', 'sand'),
}
# Exact, unambiguous values of a *typed* initial feature, never substrings of
# sentences, names, legacy_text, biographies or derived identity characteristics.
_TYPED = {
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


def graphic_choices(actor, hints=None):
    approved = {}
    if isinstance(hints,dict):
        for field, options in STYLES.items():
            if hints.get(field) in options:
                approved[field] = options.index(hints[field])
    # Existing AppearanceProfile carries open text, not typed color IDs. Handle
    # only uncomplicated public initial features that match a supported value.
    # Never bake a private or evolving feature into a shared visual descriptor.
    appearance=actor.get('appearance')
    items=appearance.get('items') if isinstance(appearance,dict) else None
    matches = {}
    for item in items.values() if isinstance(items,dict) else ():
        if not isinstance(item,dict) or not isinstance(item.get('kind'),str): continue
        if item.get('source_event_id') or item.get('fact_id') or item.get('condition_id') or item.get('revision',1)!=1:
            continue
        spec=_TYPED.get(item.get('kind'))
        if not spec or not isinstance(item.get('text'),str): continue
        field, names=spec
        token=item['text'].casefold().strip()
        matches.setdefault(field,set()).add(names.get(token,token))
    for field, tokens in matches.items():
        if len(tokens)==1:
            token=next(iter(tokens))
            if token in STYLES[field]: approved[field]=STYLES[field].index(token)
    return approved
