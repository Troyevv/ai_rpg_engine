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
    status: Literal['active', 'completed', 'cancelled', 'failed', 'superseded', 'expired'] = 'active'
    source_sequence: int | None = None
    evidence: str = ''
    due_minute: int | None = Field(default=None, ge=0)


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


class Character(StrictModel):
    id: str
    location_id: str | None = None
    situation: str = ''
    birth_date: str | None = None
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


def fatal(message, code='current_state_invalid', repairable=False, **path):
    raise StructuralDeltaError('Runtime v3: ' + message, code=code, repairable=repairable, **path)


def assert_world_state_v3_invariants(state, before=None):
    state = salvage_calendar_data(state)
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
