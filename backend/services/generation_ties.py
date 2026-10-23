"""Bounded provider work; canonical ties remain owned by LifePart/Runtime."""
from itertools import combinations
from backend.services import initial_world_stages as stages

PAIR_LIMIT = 6


def batches(registry):
    pairs = list(combinations(sorted(r['id'] for r in registry if r['kind'] == 'character'), 2))
    return [dict(id=f'life_ties_{i // PAIR_LIMIT:04d}', pairs=pairs[i:i + PAIR_LIMIT])
            for i in range(0, len(pairs), PAIR_LIMIT)]


def context(original, batch):
    ids = {cid for pair in batch['pairs'] for cid in pair}
    return dict(registry=original['registry'],
                people=[p for p in original['people'] if p['id'] in ids],
                constraints=original['constraints'], assigned_pairs=batch['pairs'])


def check_pairs(value, batch):
    allowed = {tuple(pair) for pair in batch['pairs']}
    for section in ('objective_relations', 'relationships'):
        for row in value[section].values():
            if tuple(sorted((row['source_id'], row['target_id']))) not in allowed:
                raise ValueError('ties/' + section + ': pair is outside the assigned batch')
    return value


def validate(raw, registry, batch):
    value = check_pairs(stages.validate_ties(raw, registry), batch)
    # IDs are technical identities allocated here, not narrative facts. Namespace
    # them before downstream lore can reference them; never merge distinct phases.
    prefix = batch['id'] + '_'
    value['objective_relations'] = {
        (key if key.startswith(prefix) else prefix + key):
            dict(row, id=key if key.startswith(prefix) else prefix + key)
        for key, row in value['objective_relations'].items()}
    return value


def combine(parts, registry):
    result = dict(objective_relations={}, relationships={})
    for part in parts:
        for section in result:
            if result[section].keys() & part[section].keys():
                raise ValueError('ties/' + section + ': duplicate batch record')
            result[section].update(part[section])
    return stages.validate_ties(result, registry)
