"""Bounded generation DTOs and deterministic composition into Runtime v3.

These are request/checkpoint payloads, not independently authoritative world
models. Only InitialWorldStateV2 can turn their composition into a playable draft.
"""
from copy import deepcopy
from typing import Literal

from pydantic import Field, model_validator

from backend.runtime_v3 import models as m
from backend.services.initial_world_v2 import _check, normalize, validate_initial_history


class Campaign(m.StrictModel):
    title: str = Field(min_length=1, max_length=300)
    setting: str = Field(default='', max_length=6000)
    era: str = Field(default='', max_length=1000)
    genre: str = Field(default='', max_length=1000)
    tone: str = Field(default='', max_length=2000)
    description: str = Field(default='', max_length=12000)
    public_description: str = Field(default='', max_length=6000)
    rules: str = Field(default='', max_length=6000)


class PlannedEntity(m.StrictModel):
    key: str = Field(min_length=1, max_length=100, pattern=r'^[\w-]+$')
    kind: Literal['character', 'location', 'organization']
    name: str = Field(min_length=1, max_length=200)
    existing_id: str | None = None
    tier: Literal['protagonist', 'core', 'secondary'] | None = None


class SettingPart(m.StrictModel):
    campaign: Campaign
    entities: list[PlannedEntity] = Field(max_length=200)

    @model_validator(mode='after')
    def unique_keys(self):
        if len({item.key for item in self.entities}) != len(self.entities):
            raise ValueError('duplicate planning key')
        if sum(item.tier == 'protagonist' for item in self.entities) > 1:
            raise ValueError('multiple protagonists')
        return self


class CharacterCard(m.StrictModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list, max_length=20)
    fields: dict[str, str] = Field(default_factory=dict, max_length=40)


class CharactersPart(m.StrictModel):
    characters: dict[str, m.Character] = Field(max_length=5)
    cards: dict[str, CharacterCard] = Field(max_length=5)


class PlacesPart(m.StrictModel):
    locations: dict[str, m.Location] = Field(default_factory=dict, max_length=100)
    organizations: dict[str, m.Organization] = Field(default_factory=dict, max_length=100)
    # Converted to Fact/Claim at composition; never persisted as another graph.
    parent_organizations: dict[str, str] = Field(default_factory=dict, max_length=100)


class LifePart(m.StrictModel):
    objective_relations: dict[str, m.ObjectiveRelation] = Field(default_factory=dict, max_length=200)
    relationships: dict[str, m.Relationship] = Field(default_factory=dict, max_length=200)
    residences: dict[str, m.Residence] = Field(default_factory=dict, max_length=100)
    roles: dict[str, m.NarrativeRole] = Field(default_factory=dict, max_length=200)
    possessions: dict[str, m.SignificantPossession] = Field(default_factory=dict, max_length=100)
    contacts: dict[str, m.Contact] = Field(default_factory=dict, max_length=100)
    conditions: dict[str, m.Condition] = Field(default_factory=dict, max_length=100)
    reproductive_events: dict[str, m.ReproductiveEvent] = Field(default_factory=dict, max_length=40)
    pregnancies: dict[str, m.Pregnancy] = Field(default_factory=dict, max_length=40)


class LorePart(m.StrictModel):
    facts: dict[str, m.Fact] = Field(default_factory=dict, max_length=200)
    knowledge: dict[str, m.Knowledge] = Field(default_factory=dict, max_length=500)
    threads: dict[str, m.Thread] = Field(default_factory=dict, max_length=80)
    initial_history: dict[str, list[dict]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def portable_history(self):
        validate_initial_history({'initial_history': self.initial_history})
        if sum(len(rows) for rows in self.initial_history.values()) > 200:
            raise ValueError('initial History exceeds bounded stage budget')
        return self


class OpeningPart(m.StrictModel):
    world_time: int = Field(ge=0)
    calendar: m.Calendar | None = None
    camera: m.Camera
    scheduled_events: dict[str, m.ScheduledEvent] = Field(default_factory=dict, max_length=80)


STAGES = {'setting': SettingPart, 'places': PlacesPart, 'characters': CharactersPart,
          'life': LifePart, 'lore': LorePart, 'opening': OpeningPart}


def validate(stage, payload):
    return _check(STAGES[stage], payload, stage).model_dump()


def allocate_entities(setting, interpretation, namespace):
    """Providers propose a roster, but cannot reidentify explicit user entities."""
    setting = validate('setting', setting)
    explicit = {row['id']: row for row in interpretation['entities']}
    result = []
    used = set()
    for index, row in enumerate(setting['entities']):
        eid = row['existing_id']
        if eid is not None:
            original = explicit.get(eid)
            if original is None or any(row[key] != original[key] for key in ('kind', 'name')):
                raise ValueError(f'setting/entities/{index}: changed explicit identity')
            tier = original.get('tier') or row['tier']
        else:
            if any(row['name'] == item['name'] and row['kind'] == item['kind'] for item in explicit.values()):
                raise ValueError(f'setting/entities/{index}: explicit identity requires existing_id')
            eid = m.identity(row['kind'], namespace, row['key'])
            tier = row['tier']
        if eid in used:
            raise ValueError(f'setting/entities/{index}: duplicate identity')
        used.add(eid)
        result.append(dict(id=eid, name=row['name'], kind=row['kind'], tier=tier,
                           origin='explicit' if row['existing_id'] is not None else 'generated'))
    if set(explicit) - used:
        raise ValueError('setting/entities: omitted source entities')
    return result


def character_batches(registry):
    """Stable bounded batches. User-defined actors are never cut to meet a target."""
    core = [row['id'] for row in registry if row['kind'] == 'character' and row['tier'] != 'secondary']
    secondary = [row['id'] for row in registry if row['kind'] == 'character' and row['tier'] == 'secondary']
    return [dict(id=f'{tier}_{index//size}', character_ids=ids[index:index+size])
            for tier, ids, size in [('core', core, 3), ('secondary', secondary, 5)]
            for index in range(0, len(ids), size)]


def validate_character_batch(payload, expected_ids, registry):
    value = validate('characters', payload)
    expected = set(expected_ids)
    if set(value['characters']) != expected or set(value['cards']) != expected:
        raise ValueError('characters: result must contain exactly the assigned batch IDs')
    names = {row['id']: row['name'] for row in registry}
    for cid in expected:
        actor, card = value['characters'][cid], value['cards'][cid]
        if actor['id'] != cid or card['id'] != cid or card['name'] != names[cid] or actor['display_name'] != names[cid]:
            raise ValueError(f'characters/{cid}: changed assigned identity')
    return value


def compose(setting, registry, places, batches, life, lore, opening, interpretation):
    """Zero-provider assembly; reject omissions, collisions and broken references."""
    setting = validate('setting', setting)
    places = validate('places', places)
    life = validate('life', life)
    lore = validate('lore', lore)
    opening = validate('opening', opening)
    if interpretation['blocking_ids']:
        raise ValueError('interpretation: unresolved blocking ambiguities')
    actors, cards = {}, {}
    for batch in batches:
        validated = validate_character_batch(batch, list(batch['characters']), registry)
        if set(actors) & set(validated['characters']):
            raise ValueError('characters: repeated batch identity')
        actors.update(validated['characters']); cards.update(validated['cards'])
    for kind, records in [('character', actors), ('location', places['locations']), ('organization', places['organizations'])]:
        if set(records) != {row['id'] for row in registry if row['kind'] == kind}:
            raise ValueError(f'{kind}: missing or unplanned identities')
    for row in registry:
        if row['kind'] in ('location','organization'):
            record = places[row['kind']+'s'][row['id']]
            if record['id'] != row['id'] or record['name'] != row['name']:
                raise ValueError(f"{row['kind']}/{row['id']}: changed planned identity")
    facts = deepcopy(lore['facts'])
    for child, parent in places['parent_organizations'].items():
        fid = m.identity('organization_parent', child, parent)
        if fid in facts: raise ValueError(f'facts/{fid}: duplicate parent claim')
        if child not in places['organizations'] or parent not in places['organizations']:
            raise ValueError('places/parent_organizations: unknown organization')
        # Public knowledge is not inferred from existence of the objective link.
        facts[fid] = m.Fact(id=fid, text=f"{places['organizations'][child]['name']} → {places['organizations'][parent]['name']}",
            visibility='secret', claim=m.Claim(subject_id=child,predicate='organization.parent',value=parent)).model_dump()
    protagonists = [row['id'] for row in registry if row['tier'] == 'protagonist']
    meta = dict(world_time=opening['world_time'], calendar=opening['calendar'],
                current_protagonist_id=protagonists[0] if protagonists else None)
    state = m.WorldStateV3(meta=meta, camera=opening['camera'], characters=actors,
        locations=places['locations'], organizations=places['organizations'],
        facts=facts, knowledge=lore['knowledge'], threads=lore['threads'],
        scheduled_events=opening['scheduled_events'], **life).model_dump()
    snapshot = dict(schema_version=3, world_state=state, character_cards=list(cards.values()),
        campaign={'campaign':setting['campaign'], 'initial_world':deepcopy(interpretation)},
        initial_history=lore['initial_history'])
    # Immutable provenance travels with the canonical save, not as Knowledge.
    return normalize(snapshot, operation='normalize_existing').snapshot


def fingerprint(value):
    """Stable typed JSON hash for the *declared* inputs of a generation unit."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def input_manifest(resources, required):
    missing = set(required) - resources.keys()
    if missing: raise ValueError('checkpoint/inputs: missing ' + ', '.join(sorted(missing)))
    return {key: fingerprint(resources[key]) for key in sorted(required)}


def stale_units(checkpoints, resources):
    """Transitive artifact invalidation, separate from in-world relationships.

    A unit declares inputs and produced resource keys. Unrelated resource changes
    do not invalidate its accepted output. Outputs of a stale unit cannot satisfy
    a dependent checkpoint even if their old bytes still exist in the journal.
    """
    stale, unavailable = set(), set()
    while True:
        newly = {unit for unit, checkpoint in checkpoints.items() if unit not in stale and any(
            key in unavailable or key not in resources or fingerprint(resources[key]) != digest
            for key, digest in checkpoint['inputs'].items())}
        if not newly: return sorted(stale)
        stale.update(newly)
        for unit in newly: unavailable.update(checkpoints[unit]['outputs'])
