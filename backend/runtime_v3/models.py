"""Strict persisted models; no historical pointers in the current world."""
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from backend.services.relation_dimensions import RELATION_DIMENSIONS
from backend.services.world_delta_errors import StructuralDeltaError


def identity(kind, *parts):
    return kind + '_' + sha256('\0'.join(map(str, parts)).encode()).hexdigest()[:20]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Observance(StrictModel):
    id: str
    name: str
    month: int = Field(ge=1, le=24)
    day: int = Field(ge=1, le=99)
    character_ids: list[str] = Field(default_factory=list)


class Season(StrictModel):
    name: str
    month: int = Field(ge=1, le=24)
    day: int = Field(ge=1, le=99)


class CalendarProfile(StrictModel):
    id: str = 'gregorian'
    system: Literal['gregorian', 'custom'] = 'gregorian'
    month_lengths: list[int] = Field(default_factory=list, max_length=24)
    month_names: list[str] = Field(default_factory=list, max_length=24)
    weekday_names: list[str] = Field(default_factory=list, max_length=14)
    observances: list[Observance] = Field(default_factory=list, max_length=128)
    seasons: list[Season] = Field(default_factory=list, max_length=24)

    @model_validator(mode='after')
    def valid_profile(self):
        from backend.runtime_v3.calendar import date_parts
        if self.system == 'custom' and (not self.month_lengths or any(not 1 <= n <= 99 for n in self.month_lengths)):
            raise ValueError('custom calendar requires month lengths in 1..99')
        if self.system == 'gregorian' and self.month_lengths:
            raise ValueError('Gregorian month lengths are defined by datetime')
        if self.month_names and len(self.month_names) != (len(self.month_lengths) if self.system == 'custom' else 12):
            raise ValueError('month_names must match months')
        if self.system == 'gregorian' and self.weekday_names and len(self.weekday_names) != 7:
            raise ValueError('Gregorian calendar has seven weekdays')
        if len({o.id for o in self.observances}) != len(self.observances):
            raise ValueError('duplicate observance ID')
        for item in [*self.observances, *self.seasons]:
            date_parts(f'2000-{item.month:02d}-{item.day:02d}', self.model_dump())
        return self


class Calendar(StrictModel):
    start_minute: int = Field(ge=0)
    start_weekday: int = Field(ge=0, le=13)
    start_date: str | None = None
    profile: CalendarProfile = Field(default_factory=CalendarProfile)

    @model_validator(mode='after')
    def valid_anchor(self):
        from backend.runtime_v3.calendar import date_parts
        if self.start_weekday >= len(self.profile.weekday_names or range(7)):
            raise ValueError('start_weekday outside profile week')
        if self.start_date:
            date_parts(self.start_date, self.profile.model_dump())
            if self.profile.system == 'gregorian':
                from datetime import date
                self.start_weekday = date.fromisoformat(self.start_date).weekday()
        return self


class TemporalValue(StrictModel):
    date: str | None = None
    weekday: int | None = Field(default=None, ge=0, le=13)
    day_offset: int | None = Field(default=None, ge=-366, le=366)
    time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    day_period: Literal['night', 'morning', 'afternoon', 'evening'] | None = None

    @model_validator(mode='after')
    def one_temporal_basis(self):
        if sum(v is not None for v in (self.date,self.weekday,self.day_offset)) != 1:
            raise ValueError('temporal value requires exactly one date, weekday or day_offset')
        if self.time is not None and self.day_period is not None:
            raise ValueError('choose exact time or an imprecise period')
        return self


class Motivation(StrictModel):
    id: str
    text: str
    status: Literal['active', 'completed', 'cancelled', 'failed', 'superseded', 'expired', 'blocked'] = 'active'
    source_sequence: int | None = None
    evidence: str = ''
    due_minute: int | None = Field(default=None, ge=0)

    revision: int = Field(default=0, ge=0)
    source_event_id: str | None = None
    # Explicit semantic links, never guessed from the motivation's wording.
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    review_required: list[str] = Field(default_factory=list)
    reviewed_signature: str = ''


class DurableValue(StrictModel):
    id: str
    text: str = Field(min_length=1, max_length=2000)
    status: Literal['active', 'retired'] = 'active'
    revision: int = Field(default=0, ge=0)
    source_ids: list[str] = Field(default_factory=list)
    witnesses: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class Meta(StrictModel):
    schema_version: Literal[3] = 3
    calendar: Calendar | None = None
    turn_id: int = Field(default=0, ge=0)
    world_time: int = Field(default=0, ge=0)


class RemoteInteraction(StrictModel):
    actor_id: str
    channel: Literal['message', 'phone', 'video', 'radio', 'other']
    last_active_turn: int = Field(ge=0)


class Camera(StrictModel):
    location_id: str | None = None
    present_character_ids: list[str] = Field(default_factory=list)
    controlled_actor_id: str | None = None
    mode: Literal['actor', 'observer'] = 'actor'
    situation: str = ''
    remote_interactions: list[RemoteInteraction] = Field(default_factory=list)


class Capabilities(StrictModel):
    conscious: bool | None = None
    can_perceive: bool | None = None
    can_act: bool | None = None
    can_speak: bool | None = None
    can_move: bool | None = None


class NameChange(StrictModel):
    previous: str = Field(min_length=1)
    current: str = Field(min_length=1)
    minute: int = Field(ge=0)
    date: str | None = None
    turn_id: int = Field(ge=0)
    evidence: str
    fact_id: str | None = None


class ObjectiveRelation(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal['spouse', 'partner', 'engaged', 'parent', 'adoptive_parent',
                  'guardian', 'foster_parent', 'step_parent', 'sibling', 'contact',
                  'friend', 'close_friend', 'coworker']
    source_id: str
    target_id: str
    status: Literal['active', 'closed'] = 'active'
    since: int | None = Field(default=None, ge=0)
    until: int | None = Field(default=None, ge=0)
    since_date: str | None = None
    until_date: str | None = None
    outcome: Literal['', 'ended', 'divorced', 'widowed', 'superseded', 'revoked'] = ''
    context: str = ''
    evidence: str = ''
    source_turn: int | None = Field(default=None, ge=0)
    fact_id: str | None = None
    closure_fact_id: str | None = None


class Condition(StrictModel):
    id: str = Field(min_length=1)
    actor_id: str
    description: str = Field(min_length=1)
    status: Literal['active', 'resolved', 'cancelled', 'unknown_outcome'] = 'active'
    duration: Literal['temporary', 'persistent', 'unknown'] = 'unknown'
    effects: Capabilities = Field(default_factory=Capabilities)
    since: int | None = Field(default=None, ge=0)
    until: int | None = Field(default=None, ge=0)
    evidence: str = ''
    source_turn: int | None = Field(default=None, ge=0)
    fact_id: str | None = None


class PersonalityItem(StrictModel):
    field: Literal['traits', 'communication', 'habits', 'strengths', 'weaknesses', 'fears', 'preferences', 'temperament']
    text: str = Field(min_length=1)
    revision: int = Field(default=0, ge=0)
    source_ids: list[str] = Field(default_factory=list)
    witnesses: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class DevelopmentEvidence(StrictModel):
    id: str
    source_event_id: str
    source_turn: int = Field(ge=0)
    minute: int = Field(ge=0)
    meaning: str = Field(min_length=1, max_length=300)
    kind: Literal['behavior', 'experience', 'turning_point']
    player_owned: bool = False
    evidence: str = Field(min_length=1, max_length=1000)
    witnesses: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class PersonalityProfile(StrictModel):
    items: dict[str, PersonalityItem] = Field(default_factory=dict)
    evidence: dict[str, DevelopmentEvidence] = Field(default_factory=dict)
    applied: list[str] = Field(default_factory=list)
    seen_sources: list[str] = Field(default_factory=list)


class ReproductionPolicy(StrictModel):
    # Narrative game rules, not medical estimates. Persist with the world.
    protected: float = Field(default=0.01, ge=0, le=1)
    unprotected: float = Field(default=0.2, ge=0, le=1)
    unknown: float = Field(default=0, ge=0, le=1)
    child_weights: list[float] = Field(default_factory=lambda: [0.98, 0.019, 0.001], min_length=1, max_length=8)
    gestation_days: int = Field(default=280, ge=1, le=1000)
    adult_age: int = Field(default=18, ge=18)
    shared_family_name: bool = True

    @model_validator(mode='after')
    def valid_weights(self):
        if any(x < 0 for x in self.child_weights) or sum(self.child_weights) <= 0:
            raise ValueError('invalid child count weights')
        return self


class ReproductiveEvent(StrictModel):
    id: str
    participants: list[str]
    gestational_actor_id: str
    impregnating_actor_id: str
    protection: Literal['protected', 'unprotected', 'unknown']
    source_event_id: str
    evidence: str
    turn_id: int
    earliest_minute: int = Field(ge=0)
    latest_minute: int = Field(ge=0)
    exact_minute: int | None = Field(default=None, ge=0)
    conceived: bool
    pregnancy_id: str | None = None
    closed: bool = False
    policy: ReproductionPolicy


class ChildOutcome(StrictModel):
    id: str
    sex: Literal['female', 'male']


class Pregnancy(StrictModel):
    id: str
    event_id: str
    gestational_actor_id: str
    parent_ids: list[str]
    status: Literal['active', 'due', 'born'] = 'active'
    earliest_minute: int = Field(ge=0)
    latest_minute: int = Field(ge=0)
    conception_minute: int | None = Field(default=None, ge=0)
    due_minute: int = Field(ge=0)
    children: list[ChildOutcome] = Field(min_length=1, max_length=8)
    birth_event_id: str | None = None
    birth_minute: int | None = None
    fact_id: str
    count_fact_id: str
    sex_fact_ids: dict[str, str]


class NamingDecision(StrictModel):
    id: str
    pregnancy_id: str
    child_id: str
    components: dict[str, str]
    display_name: str | None = None
    status: Literal['proposed', 'agreed', 'cancelled', 'replaced']
    decision_actor_ids: list[str]
    delegated_to: str | None = None
    established: bool = False
    source_event_id: str
    evidence: str
    fact_id: str
    replaces: str | None = None



class Character(StrictModel):
    id: str
    location_id: str | None = None
    situation: str = ''
    birth_date: str | None = None
    life_status: Literal['alive', 'dead', 'missing', 'unknown'] = 'unknown'
    life_fact_id: str | None = None
    display_name: str | None = Field(default=None, min_length=1)
    name_history: list[NameChange] = Field(default_factory=list)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    developmental_stage: Literal['unknown', 'infant', 'child', 'adolescent', 'adult'] = 'unknown'
    parentage_complete_fact_id: str | None = None
    reproductive_capability: Literal['can_become_pregnant', 'can_impregnate', 'neither', 'unknown'] = 'unknown'
    biological_sex: Literal['female', 'male'] | None = None
    identity_components: dict[str, str] = Field(default_factory=dict)
    birth_provenance: dict[str, str | int | None] = Field(default_factory=dict)
    personality: PersonalityProfile | None = None
    values: dict[str, DurableValue] | None = None
    physical_state: str = ''
    emotion: str = ''
    emotion_source_sequence: int | None = None
    goals: list[Motivation] = Field(default_factory=list)
    intentions: list[Motivation] = Field(default_factory=list)
    obligations: list[Motivation] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def legacy_motivations(cls, value):
        if not isinstance(value, dict): return value
        value = deepcopy(value)
        for field in ('goals', 'intentions', 'obligations'):
            value[field] = [dict(id=identity(field, value.get('id'), i, item), text=item)
                if isinstance(item, str) else item for i, item in enumerate(value.get(field, []))]
        return value


class Location(StrictModel):
    id: str
    name: str
    description: str = ''
    parent_id: str | None = None
    kind: str = Field(default='unknown', min_length=1)
    aliases: list[str] = Field(default_factory=list)


class SocialPhase(StrictModel):
    """One immutable identity/phase; closing never replaces earlier chronology."""
    id: str = Field(min_length=1)
    status: Literal['active', 'closed'] = 'active'
    since: int | None = Field(default=None, ge=0)
    until: int | None = Field(default=None, ge=0)
    since_date: str | None = None
    until_date: str | None = None
    context: str = ''
    evidence: str = ''
    source_turn: int | None = Field(default=None, ge=0)
    fact_id: str | None = None
    closure_fact_id: str | None = None
    outcome: str = ''


class Residence(SocialPhase):
    actor_id: str
    location_id: str


class NarrativeRole(SocialPhase):
    actor_id: str
    kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organization_id: str | None = None
    field: str | None = None


class Organization(SocialPhase):
    name: str = Field(min_length=1)
    kind: str = Field(default='unknown', min_length=1)
    status: Literal['active', 'closed', 'unknown'] = 'unknown'
    aliases: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    name_history: list[NameChange] = Field(default_factory=list)


class Claim(StrictModel):
    """Explicit single-valued slot. Never inferred by comparing prose."""
    subject_id: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    scope: str = Field(default='', max_length=200)


class Fact(StrictModel):
    id: str
    text: str
    visibility: Literal['public', 'secret'] = 'public'
    character_ids: list[str] = Field(default_factory=list)
    claim: Claim | None = None


class Knowledge(StrictModel):
    actor_id: str
    fact_id: str
    status: Literal['known', 'suspected', 'unknown', 'outdated', 'refuted', 'superseded'] = 'known'
    revision: int = Field(default=0, ge=0)
    source_event_id: str | None = None
    evidence: str = ''
    source_turn: int | None = Field(default=None, ge=0)
    replaced_by: str | None = None


class Relationship(StrictModel):
    source_id: str
    target_id: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    context: str = ''


class Thread(StrictModel):
    id: str
    description: str
    character_ids: list[str] = Field(default_factory=list)
    status: Literal['active', 'developing', 'dormant', 'resolved', 'paused'] = 'active'
    state: str = ''
    relevance: float = Field(default=0.5, ge=0, le=1)


class ScheduledEvent(StrictModel):
    id: str
    description: str
    character_ids: list[str] = Field(default_factory=list)
    due_minute: int | None = Field(default=None, ge=0)
    status: Literal['pending', 'resolved', 'cancelled'] = 'pending'
    condition: str = ''
    type: str = 'event'
    location_id: str | None = None
    interrupts: bool = False
    last_attempt_minute: int | None = Field(default=None, ge=0)
    temporal: TemporalValue | None = None
    time_reference_minute: int | None = Field(default=None, ge=0)
    commitment: bool = False  # Legacy scheduled events keep their original semantics.
    end_temporal: TemporalValue | None = None
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    started_minute: int | None = Field(default=None, ge=0)
    outcome: Literal['', 'fulfilled', 'blocked', 'missed', 'cancelled', 'dependency_cancelled'] = ''
    evidence: str = ''
    source_turn: int | None = Field(default=None, ge=0)


class WorldStateV3(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    camera: Camera
    characters: dict[str, Character]
    locations: dict[str, Location] = Field(default_factory=dict)
    facts: dict[str, Fact] = Field(default_factory=dict)
    knowledge: dict[str, Knowledge] = Field(default_factory=dict)
    relationships: dict[str, Relationship] = Field(default_factory=dict)
    threads: dict[str, Thread] = Field(default_factory=dict)
    scheduled_events: dict[str, ScheduledEvent] = Field(default_factory=dict)
    objective_relations: dict[str, ObjectiveRelation] = Field(default_factory=dict)
    conditions: dict[str, Condition] = Field(default_factory=dict)
    residences: dict[str, Residence] = Field(default_factory=dict)
    roles: dict[str, NarrativeRole] = Field(default_factory=dict)
    organizations: dict[str, Organization] = Field(default_factory=dict)
    reproduction_policy: ReproductionPolicy = Field(default_factory=ReproductionPolicy)
    reproductive_events: dict[str, ReproductiveEvent] = Field(default_factory=dict)
    pregnancies: dict[str, Pregnancy] = Field(default_factory=dict)
    naming_decisions: dict[str, NamingDecision] = Field(default_factory=dict)


def fatal(message, code='current_state_invalid', repairable=False, **path):
    raise StructuralDeltaError('Runtime v3: ' + message, code=code, repairable=repairable, **path)


def assert_world_state_v3_invariants(state, before=None):
    from backend.runtime_v3.knowledge import salvage, slot
    state = salvage(state)
    state = salvage_calendar_data(state)
    from backend.runtime_v3.values import salvage_values
    from backend.runtime_v3.lifecycle import salvage_metadata
    salvage_values(state)
    salvage_metadata(state)
    from backend.runtime_v3.life import salvage_life_data
    state = salvage_life_data(state)
    try:
        value = WorldStateV3.model_validate(state).model_dump()
    except ValidationError as exc:
        fatal(str(exc), 'current_state_schema_invalid')
    actors, locations = value['characters'], value['locations']
    for section in ('characters', 'locations', 'facts', 'threads', 'scheduled_events'):
        for key, record in value[section].items():
            if not key or record['id'] != key:
                fatal('конфликт canonical ID', section=section, entity=key)
    for cid,actor in actors.items():
        for field in ('goals','intentions','obligations'):
            ids=[r['id'] for r in actor[field]]
            if len(ids)!=len(set(ids)):
                fatal('повторный motivation ID', section=field, entity=cid)
    camera = value['camera']
    if camera['location_id'] is not None and camera['location_id'] not in locations:
        fatal('неизвестное место камеры')
    present = camera['present_character_ids']
    if len(set(present)) != len(present) or set(present) - actors.keys():
        fatal('неизвестные или повторные участники камеры')
    if camera['controlled_actor_id'] is not None and camera['controlled_actor_id'] not in actors:
        fatal('неизвестный controlled actor')
    if camera['mode'] == 'actor' and camera['controlled_actor_id'] not in present and actors.get(camera['controlled_actor_id'], {}).get('life_status') != 'dead':
        fatal('controlled actor отсутствует в камере')
    remote = camera['remote_interactions']
    if len({r['actor_id'] for r in remote}) != len(remote):
        fatal('повторный участник удалённого взаимодействия')
    for interaction in remote:
        if interaction['actor_id'] not in actors or interaction['actor_id'] in present or interaction['last_active_turn'] > value['meta']['turn_id']:
            fatal('некорректный участник удалённого взаимодействия')
    for cid, actor in actors.items():
        if actor['location_id'] is not None and actor['location_id'] not in locations:
            fatal('неизвестное место персонажа', entity=cid)
        if cid in present and actor['location_id'] != camera['location_id']:
            fatal('позиция участника не совпадает с камерой', entity=cid)
    claim_values = {}
    for key, item in value['knowledge'].items():
        if item['actor_id'] not in actors or item['fact_id'] not in value['facts'] or key != item['actor_id'] + ':' + item['fact_id']:
            fatal('повреждена ссылка текущего Knowledge', entity=key)
        if item['replaced_by'] is not None and item['replaced_by'] not in value['facts']:
            fatal('повреждена ссылка исправления Knowledge', entity=key)
        claim_slot = slot(value['facts'][item['fact_id']])
        if item['status'] == 'known' and claim_slot:
            slot_key = (item['actor_id'], claim_slot)
            claim_value = value['facts'][item['fact_id']]['claim']['value']
            if slot_key in claim_values and claim_values[slot_key] != claim_value:
                fatal('противоречащие текущие Knowledge одного слота', entity=key)
            claim_values[slot_key] = claim_value
    for key, item in value['relationships'].items():
        if item['source_id'] not in actors or item['target_id'] not in actors or key != item['source_id'] + ':' + item['target_id']:
            fatal('повреждена ссылка отношения', entity=key)
        if set(item['dimensions']) - set(RELATION_DIMENSIONS) or any(not -100 <= n <= 100 for n in item['dimensions'].values()):
            fatal('повреждено измерение отношений', entity=key)
    for section in ('facts', 'threads', 'scheduled_events'):
        for key, item in value[section].items():
            if set(item['character_ids']) - actors.keys():
                fatal('неизвестный связанный персонаж', section=section, entity=key)
    for item in value['scheduled_events'].values():
        if item['location_id'] is not None and item['location_id'] not in locations:
            fatal('неизвестное место scheduled event', section='scheduled_events', entity=item['id'])
    from backend.runtime_v3.life import validate_life_state
    try: validate_life_state(value)
    except ValueError as exc: fatal(str(exc), 'life_state_invalid')
    from backend.runtime_v3.residence import validate_residence_state
    try: validate_residence_state(value)
    except ValueError as exc: fatal(str(exc), 'residence_state_invalid')
    from backend.runtime_v3.reproduction import validate_reproduction
    try: validate_reproduction(value)
    except ValueError as exc: fatal(str(exc), 'reproduction_state_invalid')
    if before and (value['meta']['world_time'] < before['meta']['world_time'] or value['meta']['turn_id'] < before['meta']['turn_id']):
        fatal('время или номер хода движется назад')
    return value


@dataclass
class WorldHistoryV3:
    """A single append-only batch. Records may be incomplete legacy payloads."""
    turns: list = field(default_factory=list)
    events: list = field(default_factory=list)
    movements: list = field(default_factory=list)
    knowledge_acquisitions: list = field(default_factory=list)
    relationship_changes: list = field(default_factory=list)
    state_changes: list = field(default_factory=list)
    legacy: list = field(default_factory=list)

    def to_dict(self):
        return deepcopy(vars(self))


@dataclass(frozen=True)
class StatePatch:
    """Internal mutation plan; never exposed as the extraction schema."""
    before_hash: str
    meta: dict
    camera: dict
    upserts: dict

    def apply(self, before):
        import json
        before = assert_world_state_v3_invariants(before)
        digest = sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest != self.before_hash:
            fatal('patch создан для другого состояния', 'stale_patch')
        result = deepcopy(before)
        for section, records in self.upserts.items():
            if section not in ('characters', 'locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events', 'objective_relations', 'conditions', 'residences', 'roles', 'organizations', 'reproductive_events', 'pregnancies', 'naming_decisions'):
                fatal('неизвестная секция patch')
            result.setdefault(section, {}).update(deepcopy(records))
        result['meta'], result['camera'] = deepcopy(self.meta), deepcopy(self.camera)
        return assert_world_state_v3_invariants(result, before)


def salvage_calendar_data(state):
    """Read boundary only: preserve old snapshots, degrade optional additions locally.

    New imports are validated strictly before confirmation. Malformed old optional
    data is logged and ignored in the read projection; stored history is untouched.
    """
    import logging
    from backend.runtime_v3.calendar import date_parts
    state = deepcopy(state)
    if not isinstance(state, dict): return state
    meta = state.get('meta', {})
    cal = meta.get('calendar') if isinstance(meta,dict) else None
    profile = {}
    if isinstance(cal,dict):
        profile = cal.get('profile') or {}
        try:
            # Salvage individual optional observances/seasons, keeping the rest.
            base = {k:v for k,v in profile.items() if k not in ('observances','seasons')}
            valid_profile = CalendarProfile.model_validate(base).model_dump()
            for field, model in (('observances',Observance),('seasons',Season)):
                items = profile.get(field,[])
                if not isinstance(items,list): items=[]
                seen = set()
                for item in items[:128 if field=='observances' else 24]:
                    try:
                        item = model.model_validate(item).model_dump()
                        date_parts(f"2000-{item['month']:02d}-{item['day']:02d}",valid_profile)
                        key = item.get('id', (item['month'],item['day']))
                        if key in seen: raise ValueError('duplicate calendar entry')
                        seen.add(key)
                        valid_profile[field].append(item)
                    except (ValueError,TypeError,KeyError):
                        logging.getLogger(__name__).warning('Ignoring malformed optional calendar %s entry',field)
            profile = valid_profile
        except (ValueError,TypeError,AttributeError):
            logging.getLogger(__name__).warning('Ignoring invalid calendar profile; retaining relative time')
            profile = CalendarProfile().model_dump()
            cal['start_date'] = None
            if type(cal.get('start_weekday')) is int: cal['start_weekday'] %= 7
        cal['profile'] = profile
        if cal.get('start_date') is not None:
            try: date_parts(cal['start_date'],profile)
            except (ValueError,TypeError):
                logging.getLogger(__name__).warning('Ignoring invalid optional calendar start_date')
                cal['start_date']=None
    characters = state.get('characters',{})
    if isinstance(characters,dict):
        for character in characters.values():
            if not isinstance(character,dict): continue
            if character.get('birth_date') is not None:
                try: date_parts(character['birth_date'],profile)
                except (ValueError,TypeError):
                    logging.getLogger(__name__).warning('Ignoring invalid optional birth_date for %s',character.get('id'))
                    character['birth_date']=None
    scheduled = state.get('scheduled_events',{})
    if isinstance(scheduled,dict):
        for event in scheduled.values():
            if not isinstance(event,dict): continue
            for key in ('temporal', 'end_temporal'):
                if event.get(key) is not None:
                    try: event[key] = TemporalValue.model_validate(event[key]).model_dump()
                    except (ValueError,TypeError):
                        logging.getLogger(__name__).warning('Ignoring invalid optional scheduled %s for %s',key,event.get('id'))
                        event[key]=None
            for key in ('commitment', 'depends_on', 'started_minute', 'outcome', 'evidence', 'source_turn'):
                if key not in event: continue
                try:
                    ScheduledEvent.model_validate(dict(id='check', description='', **{key:event[key]}))
                except (ValueError, TypeError):
                    logging.getLogger(__name__).warning('Ignoring invalid optional commitment %s for %s',key,event.get('id'))
                    event.pop(key)

            reference = event.get('time_reference_minute')
            if reference is not None and (type(reference) is not int or reference < 0):
                logging.getLogger(__name__).warning('Ignoring invalid temporal reference for %s',event.get('id'))
                event['time_reference_minute']=None
    if isinstance(scheduled, dict) and all(isinstance(e, dict) for e in scheduled.values()):
        from backend.runtime_v3.commitments import invalid_dependencies
        for eid in sorted(invalid_dependencies(scheduled)):
            logging.getLogger(__name__).warning('Ignoring invalid optional commitment dependencies for %s',eid)
            scheduled[eid]['depends_on']=[]
    return state
