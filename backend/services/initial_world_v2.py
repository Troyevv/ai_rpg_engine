"""Initial-world normalization boundary, reusing the runtime migration/validator.

InitialWorldStateV2 is an operation, not another authoritative world model.
Creative providers and conservative importers supply the same authoring envelope.
This module performs no provider calls and never completes missing story facts.
"""
from copy import deepcopy
from typing import Literal

from pydantic import ValidationError

from backend.runtime_v3 import models
from backend.runtime_v3.migration import migrate_v2
from backend.services.world_delta_errors import StructuralDeltaError


Operation = Literal['creative_generate', 'normalize_existing']


def authoring_from_runtime(source):
    """Project a canonical snapshot into the existing editable document.

    The canonical snapshot is not retained as a second mutable state. Canonical
    fields live in the corresponding authoring records; only presentation and
    portable History metadata are kept separately from those records.
    """
    snapshot = normalize(source).snapshot
    state = snapshot['world_state']; meta = state['meta']; camera = state['camera']
    cards = {row['id']: deepcopy(row) for row in snapshot.get('character_cards', [])}
    world = deepcopy(state)
    for section in ('meta', 'camera', 'locations'):
        world.pop(section)
    world.update({key: deepcopy(value) for key, value in meta.items()
                  if key not in ('schema_version', 'world_time', 'calendar')})
    world['version'] = 2
    world.update(scenes={}, events={}, scene_records={})
    def place(lid):
        return state['locations'][lid]['name'] if lid is not None else 'Не указано'
    for cid, actor in world['characters'].items():
        cards.setdefault(cid, dict(id=cid, name=actor['display_name'] or cid, fields={}))
        actor['location'] = place(actor['location_id']) if actor['location_id'] is not None else None
    for fact in world['facts'].values():
        fact['secret'] = fact.pop('visibility') == 'secret'
    for event in world['scheduled_events'].values():
        event['participants'] = event.pop('character_ids')
    sid = models.identity('initial_scene', camera['location_id'], camera['present_character_ids'])
    world['scenes'][sid] = dict(id=sid, location=place(camera['location_id']), location_id=camera['location_id'],
        participants=deepcopy(camera['present_character_ids']), text=camera['situation'],
        start_minute=meta['world_time'], end_minute=meta['world_time'], status='active', event_ids=[])
    presentation = snapshot.get('campaign', {})
    campaign = presentation.get('campaign', presentation)
    campaign = {key: value for key, value in campaign.items()
                if key in ('title','setting','era','genre','tone','description','public_description','rules')
                and isinstance(value, str)}
    campaign.setdefault('title', '')
    history = deepcopy(source.get('initial_history', {}))
    return dict(initial_state_version=2, characters=list(cards.values()), world=world,
        locations=[dict(row, text=row['description']) for row in state['locations'].values()],
        protagonist_id=meta['current_protagonist_id'], controlled_actor_id=camera['controlled_actor_id'],
        camera=dict(deepcopy(camera), scene_id=sid),
        world_clock=dict(minute=meta['world_time'], calendar=deepcopy(meta['calendar'])),
        campaign=campaign, runtime_campaign=deepcopy(presentation),
        memory=deepcopy(snapshot.get('memory', {})), initial_history=history,
        initial_history_missing=bool(source.get('history_head')) and not bool(history))


def validate_initial_history(source):
    """Portable existing History batches, never a second Milestone collection."""
    history = source.get('initial_history', {})
    if not isinstance(history, dict):
        raise ValueError('initial_history: expected a History object')
    unknown = set(history) - set(models.WorldHistoryV3.__dataclass_fields__)
    if unknown:
        raise ValueError('initial_history: unknown section')
    for section, rows in history.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'initial_history/{section}: expected a list of records')
    return history


def _check(model, value, path):
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        # Do not echo model inputs (which may contain author-only secrets).
        details = '; '.join(
            path + '/' + '/'.join(map(str, error['loc'])) + ': ' + error['type']
            for error in exc.errors(include_input=False)
        )
        raise ValueError(details) from exc


def _check_explicit_fields(source):
    """Authoring must not silently salvage a newly supplied canonical record.

    Runtime's historical load remains permissive for optional damaged metadata;
    new drafts instead expose errors before any canonical data can be lost.
    """
    world = source['world']
    for cid, entry in world['characters'].items():
        _check(models.Character, {k: v for k, v in entry.items()
                                 if k in models.Character.model_fields}, f'world/characters/{cid}')
    for lid, entry in enumerate(source.get('locations', [])):
        _check(models.Location, dict(id=entry['id'], name=entry['name'],
               description=entry.get('description', entry.get('text', '')),
               **{k: entry[k] for k in ('parent_id', 'kind', 'aliases') if k in entry}),
               f'locations/{lid}')
    for field in models.Meta.model_fields:
        if field in world:
            _check(models.Meta, {field: world[field]}, f'world/{field}')
    if source.get('world_clock', {}).get('calendar') is not None:
        _check(models.Calendar, source['world_clock']['calendar'], 'world_clock/calendar')
    excluded = {'meta', 'camera', 'characters', 'locations', 'reproduction_policy'}
    for section, field in models.WorldStateV3.model_fields.items():
        if section in excluded or section not in world:
            continue
        if not isinstance(world[section], dict):
            raise ValueError(f'world/{section}: expected a record map')
        model = field.annotation.__args__[1]
        for key, entry in world[section].items():
            if not isinstance(entry, dict):
                raise ValueError(f'world/{section}/{key}: expected a record')
            record = {k: v for k, v in entry.items() if k in model.model_fields}
            if section == 'facts':
                record['visibility'] = 'secret' if entry.get('secret') else 'public'
            if section == 'scheduled_events':
                record['character_ids'] = entry.get('participants', [])
            _check(model, record, f'world/{section}/{key}')
    if 'reproduction_policy' in world:
        _check(models.ReproductionPolicy, world['reproduction_policy'], 'world/reproduction_policy')


def normalize(source, *, operation: Operation = 'normalize_existing'):
    """Return the existing MigrationResult, with isolated validated Runtime data.

    Operation is explicit for callers/accounting, but cannot change canonical
    semantics. Creative completion belongs exclusively to generation stages.
    Historical saves continue to use migrate_snapshot directly.
    """
    if operation not in ('creative_generate', 'normalize_existing'):
        raise ValueError('operation: unknown initial-world operation')
    value = deepcopy(source)
    validate_initial_history(value)
    # Symmetric endpoints have no narrative direction. Reuse Runtime's kind
    # vocabulary to normalize their representation before strict validation;
    # directed parent/adoption/guardian links must never be reordered.
    from backend.runtime_v3.life import SYMMETRIC
    records=(value.get('world_state') if value.get('schema_version')==3 else value.get('world')) or {}
    relations=records.get('objective_relations',{}) if isinstance(records,dict) else {}
    for relation in relations.values() if isinstance(relations,dict) else ():
        if isinstance(relation,dict) and isinstance(relation.get('kind'),str) and relation['kind'] in SYMMETRIC and all(isinstance(relation.get(k),str) for k in ('source_id','target_id')):
            relation['source_id'],relation['target_id']=sorted((relation['source_id'],relation['target_id']))
    if value.get('schema_version') == 3:
        _check(models.WorldStateV3, value['world_state'], 'world_state')
    else:
        from backend.services.draft_world import prepare
        value = prepare(value)
        _check_explicit_fields(value)
    try:
        result = migrate_v2(value)
        if value.get('schema_version') == 3:
            for section, rows in value.get('initial_history', {}).items():
                result.history[section].extend(deepcopy(rows))
        raw = value['world_state'] if value.get('schema_version') == 3 else value['world']
        canonical = result.snapshot['world_state']
        for key, knowledge in raw.get('knowledge', {}).items():
            if knowledge.get('replaced_by') is not None and knowledge['replaced_by'] not in canonical['facts']:
                raise ValueError(f'knowledge/{key}/replaced_by: unknown Fact ID')
        from backend.runtime_v3.possessions import validate_record
        for key, item in raw.get('possessions', {}).items():
            row = _check(models.SignificantPossession, item, f'possessions/{key}').model_dump()
            try:
                if row['id'] != key: raise ValueError('conflicting canonical ID')
                validate_record(row, canonical)
            except ValueError as exc:
                raise ValueError(f'possessions/{key}: {exc}') from exc
        return result
    except StructuralDeltaError as exc:
        path = '/'.join(str(exc.path[key]) for key in ('section', 'entity', 'field') if key in exc.path)
        raise ValueError((path + ': ' if path else '') + str(exc)) from exc


def readiness(source):
    """Canonical half of the start gate; no persistence and no creative calls."""
    try:
        result = normalize(source)
    except (ValueError, TypeError, KeyError) as exc:
        return {'errors': [str(exc)], 'warnings': []}
    return {'errors': [], 'warnings': [
        '/'.join(str(row[k]) for k in ('section', 'entity', 'field') if k in row)
        + ': ' + row['reason'] for row in result.report if row.get('action') == 'drop_record'
    ]}
