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
    if stage == 'life': payload = normalize_relationship_dimensions(payload)
    if stage == 'opening' and isinstance(payload, dict):
        payload = deepcopy(payload)
        calendar = payload.get('calendar')
        profile = calendar.get('profile') if isinstance(calendar, dict) else None
        for event in (payload.get('scheduled_events') or {}).values() if isinstance(payload.get('scheduled_events', {}), dict) else ():
            if not isinstance(event, dict): continue
            for field in ('temporal', 'end_temporal'):
                temporal = event.get(field)
                if not isinstance(temporal, dict): continue
                clock = temporal.get('time')
                if isinstance(clock, str) and temporal.get('day_period'):
                    import re
                    from backend.runtime_v3.calendar import day_period
                    if re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', clock):
                        hour, minute = map(int, clock.split(':'))
                        if day_period(hour*60+minute) == temporal['day_period']:
                            temporal['day_period'] = None
        if isinstance(profile, dict) and profile.get('system', 'gregorian') == 'gregorian':
            # Redundant Earth month tables are representation, not custom calendars.
            if profile.get('month_lengths') in ([31,28,31,30,31,30,31,31,30,31,30,31],
                                               [31,29,31,30,31,30,31,31,30,31,30,31]):
                profile['month_lengths'] = []
    value = _check(STAGES[stage], payload, stage).model_dump()
    if stage == 'life':
        value['relationships'] = pair_keys(value['relationships'], 'source_id', 'target_id', 'life/relationships')
        value['objective_relations'] = normalize_symmetric_phases(value['objective_relations'])
    if stage == 'lore':
        knowledge = {}
        for row in value['knowledge'].values():
            key = row['actor_id'] + ':' + row['fact_id']
            if key in knowledge:
                raise ValueError('lore/knowledge: duplicate actor/fact pair')
            knowledge[key] = row
        value['knowledge'] = knowledge
    return value


def normalize_symmetric_phases(records):
    from backend.runtime_v3.life import SYMMETRIC
    result = {}; active = {}
    for rid, original in sorted(records.items()):
        row = deepcopy(original)
        if row['id'] != rid: raise ValueError('life/objective_relations: conflicting record ID')
        if row['kind'] in SYMMETRIC:
            row['source_id'], row['target_id'] = sorted((row['source_id'], row['target_id']))
        key = (row['kind'], row['source_id'], row['target_id'])
        if row['kind'] in SYMMETRIC and row['status'] == 'active' and key in active:
            prior = result[active[key]]
            structural = set(row) - {'id', 'context', 'evidence'}
            if any(row[k] != prior[k] for k in structural):
                raise ValueError('life/objective_relations: conflicting duplicate symmetric phase')
            for field in ('context', 'evidence'):
                if row[field] and row[field] != prior[field]:
                    prior[field] += ('\n' if prior[field] else '') + row[field]
            continue
        result[rid] = row
        if row['status'] == 'active': active[key] = rid
    return result


def normalize_relationship_dimensions(payload):
    from backend.services.relation_dimensions import RELATION_DIMENSIONS
    import json
    import math
    result = deepcopy(payload)
    if not isinstance(result, dict) or not isinstance(result.get('relationships', {}), dict): return result
    for row in result.get('relationships', {}).values():
        if not isinstance(row, dict) or not isinstance(row.get('dimensions', {}), dict): continue
        if not isinstance(row.get('context', ''), str): continue
        extra = {key: value for key, value in row.get('dimensions', {}).items() if key not in RELATION_DIMENSIONS}
        if extra and all(type(v) in (int, float) and math.isfinite(v) for v in extra.values()):
            # Unsupported labels have no canonical numeric meaning. Preserve them
            # as unclassified authoring prose, never guess an equivalent dimension.
            row['context'] = row.get('context', '') + '\nДополнительное описание модели (не шкала Runtime): ' + json.dumps(extra, ensure_ascii=False, sort_keys=True)
            row['dimensions'] = {k:v for k,v in row['dimensions'].items() if k in RELATION_DIMENSIONS}
    return result


def pair_keys(records, first, second, path):
    result = {}
    for row in records.values():
        key = row[first] + ':' + row[second]
        if key in result: raise ValueError(path + ': duplicate pair')
        result[key] = row
    return result


def validate_ties(payload, registry):
    value = _check(TiesPart, normalize_relationship_dimensions(payload), 'ties').model_dump()
    value['relationships'] = pair_keys(value['relationships'], 'source_id', 'target_id', 'ties/relationships')
    value['objective_relations'] = normalize_symmetric_phases(value['objective_relations'])
    actors = {r['id'] for r in registry if r['kind'] == 'character'}
    from backend.services.relation_dimensions import RELATION_DIMENSIONS
    for row in value['relationships'].values():
        if set(row['dimensions']) - set(RELATION_DIMENSIONS) or any(not -100 <= n <= 100 for n in row['dimensions'].values()):
            raise ValueError('ties/relationships/dimensions: unsupported dimension or value outside -100..100')
    for section in ('objective_relations', 'relationships'):
        for key, row in value[section].items():
            if row['source_id'] not in actors or row['target_id'] not in actors:
                raise ValueError(f'ties/{section}/{key}: both endpoints must be Character IDs; organizational jobs belong to roles')
    return value


def validate_opening(payload, people):
    value = validate('opening', payload)
    camera = value['camera']
    actors = {p['id']:p for p in people}
    controlled = camera['controlled_actor_id']
    # The controlled actor is necessarily present in actor camera mode. Complete
    # only this redundant membership, using an already accepted physical location.
    if camera['mode'] == 'actor' and controlled in actors:
        actor = actors[controlled]
        if actor.get('life_status', 'alive') != 'dead':
            if actor['location_id'] != camera['location_id']:
                raise ValueError('opening/camera/location_id: differs from accepted controlled actor location')
            if controlled not in camera['present_character_ids']:
                camera['present_character_ids'].append(controlled)
    for cid in camera['present_character_ids']:
        if cid not in actors or actors[cid]['location_id'] != camera['location_id']:
            raise ValueError('opening/camera/present_character_ids: unknown actor or conflicting accepted location')
    return value


def allocate_entities(setting, interpretation, namespace, protected=()):
    """Providers propose a roster, but cannot reidentify explicit user entities."""
    setting = validate('setting', setting)
    explicit = {row['id']: row for row in protected}
    explicit.update({row['id']: row for row in interpretation['entities']})
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
                           origin=explicit[eid].get('origin','explicit') if row['existing_id'] is not None else 'generated'))
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


def validate_places(payload, registry):
    payload = deepcopy(payload)
    # Organization inherits SocialPhase.context, whereas Location uses description.
    # Preserve the provider's common presentation alias without changing Runtime.
    if isinstance(payload, dict) and isinstance(payload.get('organizations'), dict):
        for row in payload['organizations'].values():
            if isinstance(row, dict) and isinstance(row.get('description'), str) and isinstance(row.get('context', ''), str):
                text = row.pop('description')
                row['context'] = row.get('context', '') + ('\n' if row.get('context') and text else '') + text
    value = validate('places', payload)
    for kind, field in (('location', 'locations'), ('organization', 'organizations')):
        expected = {r['id']: r['name'] for r in registry if r['kind'] == kind}
        if set(value[field]) != set(expected):
            raise ValueError(f'places/{field}: return exactly the registered IDs; no unplanned entities')
        for eid, row in value[field].items():
            if row['id'] != eid or row['name'] != expected[eid]:
                raise ValueError(f'places/{field}/{eid}: changed registered identity')
            if field == 'locations' and row['parent_id'] is not None and row['parent_id'] not in expected:
                raise ValueError(f'places/locations/{eid}/parent_id: unknown location')
    for child, parent in value['parent_organizations'].items():
        if child not in value['organizations'] or parent not in value['organizations']:
            raise ValueError('places/parent_organizations: unknown organization')
    return value


def validate_character_batch(payload, expected_ids, registry):
    from backend.services.generated_appearance import normalize_batch
    from backend.services.generated_characters import normalize_cards
    value = validate('characters', normalize_cards(normalize_batch(payload)))
    expected = set(expected_ids)
    if set(value['characters']) != expected or set(value['cards']) != expected:
        raise ValueError('characters: result must contain exactly the assigned batch IDs')
    names = {row['id']: row['name'] for row in registry}
    for cid in expected:
        actor, card = value['characters'][cid], value['cards'][cid]
        if actor['id'] != cid or card['id'] != cid or card['name'] != names[cid] or actor['display_name'] != names[cid]:
            raise ValueError(f'characters/{cid}: changed assigned identity')
    return value


def compose(setting, registry, places, batches, life, lore, opening, interpretation, creation=None):
    """Zero-provider assembly; reject omissions, collisions and broken references."""
    setting = validate('setting', setting)
    places = validate('places', places)
    life = validate('life', life)
    lore = validate('lore', lore)
    opening = validate('opening', opening)
    from backend.services.generation_constraints import validate_stage_facts
    for stage,part in [('setting',setting),('places',places),('life',life),('lore',lore),('opening',opening)]:
        validate_stage_facts(stage,part,interpretation)
    if interpretation['blocking_ids']:
        raise ValueError('interpretation: unresolved blocking ambiguities')
    actors, cards = {}, {}
    for batch in batches:
        from backend.services.generation_constraints import validate_character_facts
        validated = validate_stage_facts('characters',validate_character_batch(batch, list(batch['characters']), registry), interpretation)
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
    opening = validate_opening(opening, list(actors.values()))
    facts = deepcopy(lore['facts'])
    from backend.services.generated_characters import private_card_facts
    for fid, fact in private_card_facts(cards).items():
        if fid in facts: raise ValueError('facts: initial card secret identity collision')
        facts[fid] = fact
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
    if creation is not None:
        from backend.services.world_creation_settings import CreationSettings
        settings=CreationSettings.model_validate(creation)
        meta.update(npc_expressiveness=settings.npc_expressiveness,narrative_pacing=settings.narrative_pacing.model_dump(),narrative_risk=settings.narrative_risk.model_dump())
    state = _check(m.WorldStateV3, dict(meta=meta, camera=opening['camera'], characters=actors,
        locations=places['locations'], organizations=places['organizations'],
        facts=facts, knowledge=lore['knowledge'], threads=lore['threads'],
        scheduled_events=opening['scheduled_events'], **life), 'assembly').model_dump()
    snapshot = dict(schema_version=3, world_state=state, character_cards=list(cards.values()),
        campaign={'campaign':setting['campaign'], 'initial_world':deepcopy(interpretation), 'creation':deepcopy(creation)},
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

# Provider-facing subsets reuse the same canonical fields. The last unit of each
# logical stage combines them into its existing LifePart/LorePart checkpoint.
from pydantic import create_model

def _subset_model(name, model, fields):
    return create_model(name, __base__=m.StrictModel,
        **{key:(model.model_fields[key].annotation, model.model_fields[key]) for key in fields})

TiesPart = _subset_model('TiesPart', LifePart, ('objective_relations','relationships'))
CircumstancesPart = _subset_model('CircumstancesPart', LifePart,
    tuple(k for k in LifePart.model_fields if k not in TiesPart.model_fields))
BackgroundPart = _subset_model('BackgroundPart', LorePart, ('facts','initial_history'))
KnowledgePart = _subset_model('KnowledgePart', LorePart, ('knowledge','threads'))
CREATIVE_PARTS = {'ties':TiesPart,'circumstances':CircumstancesPart,
                  'background':BackgroundPart,'knowledge':KnowledgePart}
