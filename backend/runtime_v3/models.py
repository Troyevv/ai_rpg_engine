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


class Calendar(StrictModel):
    start_minute: int = Field(ge=0)
    start_weekday: int = Field(ge=0, le=6)
    start_date: str | None = None


class Motivation(StrictModel):
    id: str
    text: str
    status: Literal['active', 'completed', 'cancelled', 'failed', 'superseded'] = 'active'
    source_sequence: int | None = None
    evidence: str = ''
    due_minute: int | None = Field(default=None, ge=0)


class Meta(StrictModel):
    schema_version: Literal[3] = 3
    calendar: Calendar | None = None
    turn_id: int = Field(default=0, ge=0)
    world_time: int = Field(default=0, ge=0)


class Camera(StrictModel):
    location_id: str | None = None
    present_character_ids: list[str] = Field(default_factory=list)
    controlled_actor_id: str | None = None
    mode: Literal['actor', 'observer'] = 'actor'
    situation: str = ''


class Character(StrictModel):
    id: str
    location_id: str | None = None
    situation: str = ''
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


class Fact(StrictModel):
    id: str
    text: str
    visibility: Literal['public', 'secret'] = 'public'
    character_ids: list[str] = Field(default_factory=list)


class Knowledge(StrictModel):
    actor_id: str
    fact_id: str
    status: Literal['known', 'suspected', 'unknown'] = 'known'


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


def fatal(message, code='current_state_invalid', repairable=False, **path):
    raise StructuralDeltaError('Runtime v3: ' + message, code=code, repairable=repairable, **path)


def assert_world_state_v3_invariants(state, before=None):
    try:
        value = WorldStateV3.model_validate(state).model_dump()
    except ValidationError as exc:
        fatal(str(exc), 'current_state_schema_invalid')
    actors, locations = value['characters'], value['locations']
    for section in ('characters', 'locations', 'facts', 'threads', 'scheduled_events'):
        for key, record in value[section].items():
            if not key or record['id'] != key:
                fatal('конфликт canonical ID', section=section, entity=key)
    camera = value['camera']
    if camera['location_id'] is not None and camera['location_id'] not in locations:
        fatal('неизвестное место камеры')
    present = camera['present_character_ids']
    if len(set(present)) != len(present) or set(present) - actors.keys():
        fatal('неизвестные или повторные участники камеры')
    if camera['controlled_actor_id'] is not None and camera['controlled_actor_id'] not in actors:
        fatal('неизвестный controlled actor')
    if camera['mode'] == 'actor' and camera['controlled_actor_id'] not in present:
        fatal('controlled actor отсутствует в камере')
    for cid, actor in actors.items():
        if actor['location_id'] is not None and actor['location_id'] not in locations:
            fatal('неизвестное место персонажа', entity=cid)
        if cid in present and actor['location_id'] != camera['location_id']:
            fatal('позиция участника не совпадает с камерой', entity=cid)
    for key, item in value['knowledge'].items():
        if item['actor_id'] not in actors or item['fact_id'] not in value['facts'] or key != item['actor_id'] + ':' + item['fact_id']:
            fatal('повреждена ссылка текущего Knowledge', entity=key)
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
        digest = sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest != self.before_hash:
            fatal('patch создан для другого состояния', 'stale_patch')
        result = deepcopy(before)
        for section, records in self.upserts.items():
            if section not in ('characters', 'locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events'):
                fatal('неизвестная секция patch')
            result[section].update(deepcopy(records))
        result['meta'], result['camera'] = deepcopy(self.meta), deepcopy(self.camera)
        return assert_world_state_v3_invariants(result, before)
