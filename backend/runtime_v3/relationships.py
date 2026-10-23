"""Directed feelings: semantic proposals, canonical provenance, local rejection.

No automatic points or emotion simulation. Prior History events are the only
source for autonomous proposals; explicit player declarations override them.
"""
from copy import deepcopy
import math
from backend.runtime_v3.models import Relationship
from backend.services.relation_dimensions import RELATION_DIMENSIONS

MAX_AUTONOMOUS_STEP = 5


def interaction_event(event, source, target):
    """Conservative eligibility; prose-only legacy events are not upgraded."""
    participants = event.get('participants', [])
    if not isinstance(participants, list) or source not in participants or target not in participants:
        return False
    action = event.get('scene_action') or {}
    if not isinstance(action, dict):
        return False
    # An offer is an actual utterance, but is never evidence of its acceptance.
    return (event.get('player_interaction') is True or
            action.get('actor_id') in (source, target) and
            action.get('modality') in ('speech', 'physical', 'departure') and
            action.get('phase') != 'offer' and action.get('response') != 'open')


def blocked(event, key, receipts):
    return any(c.get('entity') == key and (
        event['id'] in c.get('source_event_ids', []) or
        c.get('source') in ('player_edit', 'player_input') and
        c.get('turn_id', -1) >= event.get('turn_id', -1)) for c in receipts)


def apply_relationships(resolver, raw):
    from backend.runtime_v3.resolver import normalized
    section = 'relationship_changes'
    def player_owned(item):
        quote = item.get('player_evidence') if isinstance(item, dict) else None
        return (isinstance(item, dict) and resolver.mode == 'turn' and
                item.get('source_id') == resolver.protected_actor_id and
                item.get('player_assertion') == 'explicit_directed_feelings' and
                isinstance(quote, str) and bool(normalized(quote)) and
                normalized(quote) in normalized(resolver.player_input))
    # A same-response autonomous interpretation cannot precede/win over an override.
    seen = set()
    rows = sorted(enumerate(raw.records[section]), key=lambda row: not player_owned(row[1]))
    for i, item in rows:
        if not isinstance(item, dict):
            resolver.warn(section, i, 'Ожидался объект.'); continue
        source, target = item.get('source_id'), item.get('target_id')
        key = f'{source}:{target}'
        def reject(code, reason):
            resolver.warn(section, i, reason, entity=key, code=code)
        if (not isinstance(source, str) or not isinstance(target, str) or source == target or
                source not in resolver.state['characters'] or target not in resolver.state['characters']):
            reject('relationship_endpoint_invalid', 'Неизвестное или совпадающее направление отношений.'); continue
        if key in seen:
            reject('relationship_duplicate', 'Повторное направление отношений.'); continue
        seen.add(key)
        if resolver.state['characters'][source]['life_status'] == 'dead':
            reject('relationship_source_dead', 'Мёртвый персонаж не меняет чувства.'); continue
        quote = item.get('player_evidence')
        owned = player_owned(item)
        ids = item.get('source_event_ids', [])
        events = []
        if not owned:
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 8 or
                    any(not isinstance(e, str) or not e for e in ids) or len(set(ids)) != len(ids) or
                    item.get('assertion') != 'grounded_feelings' or
                    not isinstance(item.get('rationale'), str) or not item['rationale'].strip() or
                    not resolver.relationship_query):
                reject('relationship_evidence_required', 'Чувствам нужен явный ввод игрока или принятые канонические взаимодействия.'); continue
            events = resolver.relationship_query(key, ids)
            receipts = resolver.relationship_receipts + resolver.history.relationship_changes
            if (len(events) != len(ids) or {e.get('id') for e in events} != set(ids) or any(not interaction_event(e, source, target) or
                    blocked(e, key, receipts) for e in events)):
                reject('relationship_source_invalid', 'Основание отсутствует, уже использовано, предшествует правке или не является взаимодействием.'); continue
        prior = resolver.state['relationships'].get(key)
        entry = deepcopy(prior or Relationship(source_id=source, target_id=target).model_dump())
        dimensions = item.get('dimensions', {})
        if not isinstance(dimensions, dict):
            reject('relationship_dimension_invalid', 'Некорректные измерения отношений.'); continue
        valid = {}
        for dim, value in dimensions.items():
            if (dim not in RELATION_DIMENSIONS or type(value) not in (int, float) or
                    not math.isfinite(value) or not -100 <= value <= 100):
                resolver.warn(section, i, 'Некорректное измерение отношений.', 'dimensions.'+str(dim), key, 'relationship_dimension_invalid')
            else:
                valid[dim] = value
        baseline = entry
        if not owned:
            # Main turn + background / LTA groups share one step budget.
            earlier = next((c for c in receipts if c.get('entity') == key and
                            c.get('turn_id') == resolver.turn_id), None)
            if earlier:
                baseline = earlier.get('before') or {'dimensions': {}}
        if not owned and any(abs(v-baseline['dimensions'].get(d, 0)) > MAX_AUTONOMOUS_STEP for d, v in valid.items()):
            reject('relationship_step_exceeded', 'Автономное изменение превышает допустимый постепенный сдвиг.'); continue
        if 'context' in item:
            if not isinstance(item['context'], str) or len(item['context']) > 12000:
                reject('relationship_context_invalid', 'Некорректный контекст отношений.'); continue
            entry['context'] = item['context']
        entry['dimensions'].update(valid)
        if (entry == prior and not owned) or not valid and 'context' not in item:
            continue
        resolver.state['relationships'][key] = entry
        resolver.history.relationship_changes.append(dict(entity=key, before=deepcopy(prior), after=deepcopy(entry),
            turn_id=resolver.turn_id, player_observed=resolver.observed,
            source='player_input' if owned else 'canonical_interaction',
            source_event_ids=[] if owned else list(ids), evidence=quote if owned else item.get('evidence', ''),
            rationale='' if owned else item['rationale']))
