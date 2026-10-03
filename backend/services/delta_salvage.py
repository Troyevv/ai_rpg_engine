"""Whitelisted raw-schema salvage. Never invent provenance or hide other errors."""
from pydantic import ValidationError
from backend.services.world_delta_errors import StructuralDeltaError, SecondaryDeltaError, sanitize_secondary

# Promotions define identities, unlike updates to existing entities. Missing
# promotion provenance stays structural; references must not silently lose IDs.
EVIDENCE_RECORDS = frozenset(('facts', 'events', 'knowledge', 'characters',
                            'relationships', 'threads', 'scheduled_events', 'transitions'))


def salvage_missing_evidence(delta, indices, enabled):
    from backend.services.world_delta import WorldDelta
    try:
        WorldDelta.model_validate(delta)
        return []
    except ValidationError as exc:
        errors = exc.errors()
        def permitted(error):
            loc = error['loc']
            return (error['type'] == 'missing' and len(loc) == 3
                    and loc[0] in EVIDENCE_RECORDS and type(loc[1]) is int and loc[2] == 'evidence')
        # Inspect ALL errors first: dropping a record must not hide wrong types,
        # unknown fields, or another missing mandatory field in that record.
        if not enabled or not all(permitted(error) for error in errors):
            raise StructuralDeltaError(str(exc), 'schema_invalid', section='world_delta') from exc
        warnings = []
        for error in sorted(errors, key=lambda e: e['loc'][:2], reverse=True):
            section, index, _ = error['loc']
            record = delta[section][index]
            entity = record.get('id') or record.get('actor_id') or record.get('source_id')
            removal = SecondaryDeltaError(section, index, 'Обязательное evidence отсутствует. Запись отброшена.',
                entity=entity, cause_field='evidence', code='evidence_missing')
            warning = sanitize_secondary(delta, removal, indices)
            warning.update(field='evidence', message=warning['reason'])
            warnings.append(warning)
        WorldDelta.model_validate(delta)
        return warnings


def cascade_removed(delta, before, removed, indices):
    """Only known discarded IDs authorize dependency removal, never unknown IDs."""
    warnings = []
    facts = removed['facts'] - set(before['world']['facts'])
    events = removed['events']
    for section in ('events', 'knowledge', 'threads', 'scheduled_events'):
        for index in range(len(delta.get(section, [])) - 1, -1, -1):
            item = delta[section][index]
            if section == 'events':
                for n in range(len(item.get('fact_ids', [])) - 1, -1, -1):
                    if item['fact_ids'][n] in facts:
                        error = SecondaryDeltaError(section, index, 'Ссылка на отброшенный факт удалена.',
                            field=f'fact_ids.{n}', entity=item['id'], path=('fact_ids', n), code='dependency_removed')
                        warnings.append(sanitize_secondary(delta, error, indices))
                continue
            dependent = (item['fact_id'] in facts or item['source_event_id'] in events) if section == 'knowledge' else (
                item['last_event_id'] in events if section == 'threads' else item.get('resolved_event_id') in events)
            if dependent:
                error = SecondaryDeltaError(section, index, 'Запись зависит от отброшенного изменения.',
                    entity=item.get('id') or item.get('actor_id'), code='dependency_removed')
                warnings.append(sanitize_secondary(delta, error, indices))
    return warnings
