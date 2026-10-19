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
    if value.get('schema_version') == 3:
        _check(models.WorldStateV3, value['world_state'], 'world_state')
    else:
        from backend.services.draft_world import prepare
        value = prepare(value)
        _check_explicit_fields(value)
    try:
        return migrate_v2(value)
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
