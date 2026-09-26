"""Allowlisted, source-backed state patches. No arbitrary JSON paths."""
from backend.services.world_delta_errors import StructuralDeltaError

from copy import deepcopy
import json
import unicodedata


class EvidenceError(StructuralDeltaError):
    """An extraction must be corrected before any state can be committed."""


def normalized_evidence(value):
    # Keep words, case and punctuation: no fuzzy semantic matching.
    value = unicodedata.normalize("NFC", value)
    value = value.translate(str.maketrans({c: chr(34) for c in "«»“”„"}))
    return " ".join(value.split())


def text(value, label, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise StructuralDeltaError(f'Некорректное поле: {label}.', code='schema_invalid')
    return value.strip()


def exact_keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise StructuralDeltaError('Неверная структура изменений.', code='schema_invalid')


def apply_updates(before, payload, narrative, user_text, turn, kind="turn"):
    from backend.services.pov import controlled
    if isinstance(payload, str):
        payload = json.loads(payload)
    exact_keys(payload, ['scene', 'characters', 'relationships', 'facts', 'events', 'plans', 'locations', 'choices', 'world_delta'], ['scene', 'choices'])
    state = deepcopy(before)
    ids = {c['id'] for c in state['characters']}
    cards = {c['id']: c for c in state['characters']}
    sources = [normalized_evidence(narrative), normalized_evidence(user_text)]
    evidence_path = ''

    def evidence(item):
        quote = item.get('evidence')
        if (not isinstance(quote, str) or not quote.strip() or len(quote) > 12000
                or not any(normalized_evidence(quote) in source for source in sources)):
            raise EvidenceError(f'Изменение {evidence_path} не подтверждено цитатой из хода.')

    def known(values):
        if not isinstance(values, list) or any(not isinstance(v, str) or v not in ids for v in values):
            raise StructuralDeltaError('Неизвестный персонаж в изменениях.', code='unknown_character')
        return list(dict.fromkeys(values))

    def items(key):
        nonlocal evidence_path
        value = payload.get(key, [])
        if not isinstance(value, list) or len(value) > 50:
            raise StructuralDeltaError(f'Неверный список: {key}.', code='schema_invalid')
        for index, item in enumerate(value):
            evidence_path = f'{key}[{index}].evidence'
            yield item

    scene = payload['scene']
    exact_keys(scene, ['text', 'time', 'location', 'present_ids', 'elapsed_minutes'], ['text', 'time', 'location', 'present_ids'])
    if 'elapsed_minutes' in scene and (type(scene['elapsed_minutes']) is not int or not 0<=scene['elapsed_minutes']<=10080):
        raise StructuralDeltaError('Некорректная длительность scene.elapsed_minutes.', code='schema_invalid')
    state['scene'] = text(scene['text'], 'scene.text')
    state['sections']['scene'] = state['scene']
    state['scene_meta'] = {'time': text(scene['time'], 'time', 120), 'location': text(scene['location'], 'location', 200),
                           'present_ids': known(scene['present_ids'])}
    choices = payload['choices']
    expected_choices = 0 if kind=='background' else 6
    if not isinstance(choices,list) or len(choices)!=expected_choices:
        raise StructuralDeltaError('Для закулисной сцены нужен пустой choices.' if kind=='background' else 'Нужно ровно 6 вариантов действий.', code='schema_invalid')
    normalized = []
    for choice in choices:
        exact_keys(choice, ['action', 'speech'], ['action'])
        action = text(choice['action'], 'action', 500)
        speech = choice.get('speech') or ''
        if not isinstance(speech, str) or len(speech) > 1000:
            raise StructuralDeltaError('Некорректная реплика варианта.', code='schema_invalid')
        normalized.append({'action': action, 'speech': speech.strip()})
    if len({(c['action'].casefold(), c['speech'].casefold()) for c in normalized}) != expected_choices:
        raise StructuralDeltaError('Варианты действий повторяются.', code='schema_invalid')
    for change in items('characters'):
        exact_keys(change, ['id', 'now', 'goal', 'evidence'], ['id', 'evidence'])
        known([change['id']]); evidence(change)
        card = cards[change['id']]
        if 'now' in change:
            card['fields']['Сейчас'] = text(change['now'], 'now')
        if 'goal' in change:
            if card['id']==controlled(before):
                raise StructuralDeltaError('Нельзя менять желания ГГ за игрока.', code='schema_invalid')
            card['fields']['Чего хочет'] = text(change['goal'], 'goal')
    # Arrows describe this turn only. Historical changes remain in turns.changes_json.
    for relationship in state['relationships']:
        relationship.pop('change', None)
    changed_pairs = set()
    for change in items('relationships'):
        exact_keys(change, ['source_id', 'target_id', 'text', 'direction', 'aspect', 'reason', 'evidence', 'existing_index'],
                   ['source_id', 'target_id', 'text', 'direction', 'aspect', 'reason', 'evidence'])
        known([change['source_id'], change['target_id']]); evidence(change)
        if change['source_id'] == change['target_id'] or change['direction'] not in ('up', 'down', 'neutral'):
            raise StructuralDeltaError('Некорректное направление отношений.', code='schema_invalid')
        pair = (change['source_id'], change['target_id'])
        if pair in changed_pairs:
            raise StructuralDeltaError('Направленная связь повторяется в изменениях.', code='schema_invalid')
        changed_pairs.add(pair)
        reason, aspect = text(change['reason'], 'reason'), text(change['aspect'], 'aspect', 120)
        target = cards[change['target_id']]['name']
        relation = next((r for r in state['relationships'] if r['source_id'] == change['source_id'] and
                         (r.get('target_id') == change['target_id'] or r.get('target_name') == target)), None)
        if change.get('existing_index') is not None:
            index = change['existing_index']
            if type(index) is not int or not 0 <= index < len(before['relationships']):
                raise StructuralDeltaError('Неизвестная связь отношений.', code='schema_invalid')
            relation = state['relationships'][index]
            if relation['source_id'] != change['source_id'] or relation.get('target_id', change['target_id']) != change['target_id']:
                raise StructuralDeltaError('Нельзя менять участников существующей связи.', code='schema_invalid')
        if relation is None:
            relation = {'source_id': change['source_id'], 'target_id': change['target_id'], 'target_name': target}
            state['relationships'].append(relation)
        relation.update(target_id=change['target_id'], text=text(change['text'], 'relationship.text'))
        if change['direction'] != 'neutral':
            relation['change'] = {'direction': change['direction'], 'reason': f'{aspect}: {reason}', 'turn': turn}
    for fact in items('facts'):
        exact_keys(fact, ['text', 'known_by', 'evidence'], ['text', 'known_by', 'evidence'])
        evidence(fact)
        state.setdefault('facts', []).append({'text': text(fact['text'], 'fact'), 'known_by': known(fact['known_by']), 'turn': turn})
    for event in items('events'):
        exact_keys(event, ['text', 'character_ids', 'evidence'], ['text', 'character_ids', 'evidence'])
        evidence(event)
        state.setdefault('events', []).append({'text': text(event['text'], 'event'), 'character_ids': known(event['character_ids']), 'turn': turn})
    for plan in items('plans'):
        exact_keys(plan, ['id', 'text', 'character_ids', 'status', 'evidence'], ['id', 'text', 'character_ids', 'status', 'evidence'])
        evidence(plan)
        if plan['status'] not in ('open', 'done', 'cancelled'):
            raise StructuralDeltaError('Некорректный статус договорённости.', code='schema_invalid')
        record = {'id': text(plan['id'], 'plan.id', 100), 'text': text(plan['text'], 'plan.text'),
                  'character_ids': known(plan['character_ids']), 'status': plan['status'], 'turn': turn}
        plans = state.setdefault('plans', [])
        prior = next((p for p in plans if p['id'] == record['id']), None)
        if prior:
            prior.update(record)
        else:
            plans.append(record)
    for location in items('locations'):
        exact_keys(location, ['name', 'text', 'evidence'], ['name', 'text', 'evidence'])
        evidence(location)
        record = {'name': text(location['name'], 'location.name', 200), 'text': text(location['text'], 'location.text')}
        prior = next((p for p in state['locations'] if p['name'] == record['name']), None)
        if prior:
            prior.update(record)
        else:
            state['locations'].append(record)
    return state, normalized, payload


def choice_input(choice):
    return choice['action'] + (': «' + choice['speech'] + '»' if choice.get('speech') else '')


def apply_world_updates(before, payload, narrative, user_text, turn, kind='turn', discard_unsupported=False, simulation=False):
    """Validate a canonical extraction before changing any world state.

    Only explicitly isolated secondary failures may be discarded. Other
    validation failures reject the entire candidate and leave the save intact.
    """
    from backend.services.world_delta_errors import sanitize_secondary
    from backend.services.pov import apply_scene_policy
    from backend.services.world import record_scene
    from backend.services.world_delta import apply_delta, SecondaryDeltaError
    from backend.services.world_delta import add_promotions, WorldDelta
    from backend.services.timeline import current_time
    try:
        payload = json.loads(payload) if isinstance(payload,str) else deepcopy(payload)
    except json.JSONDecodeError as exc:
        raise StructuralDeltaError(str(exc),'schema_invalid') from exc
    exact_keys(payload, ('scene','choices','world_delta'), ('scene','choices','world_delta'))
    warnings=[]
    from pydantic import ValidationError
    try:
        WorldDelta.model_validate(payload['world_delta'])
    except ValidationError as exc:
        raise StructuralDeltaError(str(exc),'schema_invalid',section='world_delta') from exc
    original_indices={section:list(range(len(entries))) for section,entries in payload['world_delta'].items() if isinstance(entries,list)}
    iterations=0
    while True:
        # The scene/choice validator is shared with older saves; never pass legacy
        # patches through its mutation path.
        try:
            delta=WorldDelta.model_validate(payload['world_delta']).model_dump(exclude_none=True)
            prepared=add_promotions(before,delta['promotions'],narrative,user_text)
            state,choices,_=apply_updates(prepared,{'scene':payload['scene'],'choices':payload['choices']},narrative,user_text,turn,kind)
            state,audience=apply_scene_policy(prepared,state,payload,kind,simulation=simulation)
            from backend.services.temporal_delta import validate_timeline
            interval_start=current_time(before)
            if simulation:
                observed=prepared['world']['scenes'][prepared['camera']['scene_id']].get('end_minute')
                if type(observed) is int and 0<=observed<=interval_start:interval_start=observed
            temporal=validate_timeline(prepared,state,delta,narrative,user_text,since=interval_start)
            if kind=='background' and before.get('camera',{}).get('scope')!='scene' and before.get('protagonist_id') in temporal['involved']:
                raise StructuralDeltaError('Закулисье включает основного персонажа','scene_invalid')
            record_scene(state,payload,turn,kind)
            state=apply_delta(state,payload['world_delta'],narrative,user_text,turn,since=interval_start,promotions_prepared=True,before_state=prepared,temporal=temporal)
            audience=sorted(set(audience)|temporal['involved'])
            return state,choices,payload,audience,warnings
        except SecondaryDeltaError as exc:
            if not discard_unsupported:raise
            iterations+=1
            if iterations>4096:
                raise StructuralDeltaError('Sanitization iteration limit','sanitization_internal',repairable=False)
            previous=deepcopy(payload['world_delta'])
            warnings.append(sanitize_secondary(payload['world_delta'],exc,original_indices))
            if previous==payload['world_delta']:
                raise StructuralDeltaError('Sanitization made no progress','sanitization_internal',repairable=False)


def apply_supported_updates(before, payload, narrative, user_text, turn, kind="turn"):
    """After one repair, omit only unsupported patches and report each omission.

    All structural/ID/choice errors still fail atomically; rejected claims never
    enter canonical state or memory. The full narrative is retained in the journal.
    """
    import re
    payload = json.loads(payload) if isinstance(payload,str) else deepcopy(payload)
    warnings = []
    while True:
        try:
            state, choices, changes = apply_updates(before,payload,narrative,user_text,turn,kind)
            return state,choices,changes,warnings
        except EvidenceError as exc:
            match = re.search(r'(characters|relationships|facts|events|plans|locations)\[(\d+)\]', str(exc))
            if not match:
                raise
            key,index = match[1],int(match[2])
            rejected = payload[key].pop(index)
            warnings.append({'section':key,'reason':'Нет подтверждённой цитаты текущего хода', 'rejected':rejected})
