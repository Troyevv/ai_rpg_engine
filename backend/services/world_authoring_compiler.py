"""Pure author-document compilation through the existing InitialWorldStateV2 gate."""
from copy import deepcopy
from dataclasses import dataclass
from graphlib import TopologicalSorter, CycleError

from backend.runtime_v3 import models as m
from backend.services import world_authoring as a
from backend.services.initial_world_v2 import normalize, _check
from backend.services.world_creation_settings import CreationSettings

LEVELS = {'very_low': -80., 'low': -40., 'neutral': 0., 'high': 40., 'very_high': 80.}
CARD_FIELDS = {'age': 'Возраст', 'role': 'Роль', 'biography': 'Биография',
               'appearance': 'Внешность', 'personality': 'Характер',
               'communication': 'Стиль общения', 'habits': 'Привычки',
               'strengths': 'Сильные стороны', 'weaknesses': 'Слабости', 'fears': 'Страхи и уязвимости'}


class CompileError(ValueError):
    def __init__(self, path, reason, action='Исправьте запись в авторском документе и повторите сборку.'):
        self.diagnostic = dict(category='technical', path=path, reason=reason, action=action)
        super().__init__(f'{path}: {reason} {action}')


@dataclass(frozen=True)
class Compilation:
    snapshot: dict
    id_map: dict
    diagnostics: list
    transformations: list


def compile_document(document, id_map=None, creation=None):
    """No mutation, I/O, random ID or implicit wall-clock inputs."""
    doc = _check(a.Document, document, 'author_document')
    ids = deepcopy(id_map or {})
    if any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in ids.items()):
        raise CompileError('id_map', 'Некорректная таблица идентификаторов.')
    if len(set(ids.values())) != len(ids):
        raise CompileError('id_map', 'Идентификаторы разных записей совпадают.')
    mapping, diagnostics = [], []
    sections = {key: getattr(doc, key) for key in a.Sections.model_fields}
    registered = {}
    for section, records in sections.items():
        keys = [r.key for r in records]
        if len(set(keys)) != len(keys):
            raise CompileError(section, 'Повторяющийся локальный ключ.')
        registered[section] = set(keys)
        for row in records:
            slot = section + '/' + row.key
            ids.setdefault(slot, m.identity('author_' + section, row.key))
            if set(row.field_origins) - set(type(row).model_fields):
                raise CompileError(slot + '/field_origins', 'Происхождение указано для отсутствующего поля.')
    if len(set(ids.values())) != len(ids):
        raise CompileError('id_map', 'Коллизия новых и сохранённых идентификаторов.')

    def ref(section, key, path, optional=False):
        if optional and key is None:
            return None
        if key not in registered[section]:
            raise CompileError(path, f'Неизвестная ссылка {key!r} в разделе {section}.')
        return ids[section + '/' + key]

    def actor(key, path, optional=False):
        return ref('characters', key, path, optional)

    def records(section):
        for row in sections[section]:
            yield row, ids[section + '/' + row.key], section + '/' + row.key

    def track(row, path, target, methods=None):
        for field in type(row).model_fields:
            mapping.append(dict(source=path + '/' + field, target=target,
                method=(methods or {}).get(field, 'copy'),
                origin=row.field_origins.get(field, row.origin)))

    def hierarchy(section, field):
        graph = {}
        for row in sections[section]:
            parent = getattr(row, field)
            parents = parent if isinstance(parent, list) else ([parent] if parent else [])
            for key in parents:
                ref(section, key, section + '/' + row.key + '/' + field)
            graph[row.key] = set(parents)
        try:
            tuple(TopologicalSorter(graph).static_order())
        except CycleError as exc:
            raise CompileError(section, 'Цикл в иерархии или временной зависимости.') from exc

    hierarchy('locations', 'parent')
    hierarchy('organizations', 'parent')
    hierarchy('events', 'after')
    opening = doc.opening
    clock = opening.time.clock
    if clock is None or (opening.time.date is None and opening.time.weekday is None):
        raise CompileError('opening/time', 'Для запуска нужны время суток и дата либо день недели.',
                           'Уточните стартовую точку; приблизительное историческое время менять не нужно.')
    if opening.time.period is not None or opening.time.day_offset is not None:
        raise CompileError('opening/time', 'Начальная точка должна иметь собственную дату или день недели и точное время.')
    minute = int(clock[:2]) * 60 + int(clock[3:])
    calendar = _check(m.Calendar, dict(start_minute=minute, start_weekday=opening.time.weekday or 0,
        start_date=opening.time.date, profile=opening.calendar.model_dump()), 'opening/calendar').model_dump()
    if opening.time.date and opening.time.weekday is not None and calendar['start_weekday'] != opening.time.weekday:
        raise CompileError('opening/time', 'Дата противоречит дню недели.')
    settings = CreationSettings.model_validate(creation or {})
    controlled = actor(opening.controlled, 'opening/controlled', True)
    meta = m.Meta(world_time=minute, calendar=calendar,
        current_protagonist_id=actor(opening.protagonist, 'opening/protagonist', True),
        npc_expressiveness=settings.npc_expressiveness,
        narrative_pacing=settings.narrative_pacing, narrative_risk=settings.narrative_risk).model_dump()
    camera = m.Camera(mode='actor' if controlled else 'observer', controlled_actor_id=controlled,
        pov_actor_id=actor(opening.pov, 'opening/pov', True),
        location_id=ref('locations', opening.location, 'opening/location', True),
        present_character_ids=[actor(k, 'opening/present') for k in opening.present],
        situation=opening.situation).model_dump()
    state = dict(meta=meta, camera=camera, **{k: {} for k in m.WorldStateV3.model_fields if k not in ('meta', 'camera', 'reproduction_policy')})
    cards = []
    history = {'events': [], 'legacy': []}
    for row, rid, path in records('characters'):
        values = {key: getattr(row, key) for key in ('situation', 'physical_state', 'birth_date', 'life_status')}
        personality = {('traits' if f == 'personality' else f): dict(field='traits' if f == 'personality' else f, text=getattr(row, f))
            for f in ('personality', 'communication', 'habits', 'strengths', 'weaknesses', 'fears') if getattr(row, f)}
        for field in ('goals', 'intentions', 'obligations'):
            motives = getattr(row, field)
            if len({v.key for v in motives}) != len(motives):
                raise CompileError(path + '/' + field, 'Повторяющийся ключ мотивации.')
            if rid == controlled and any(v.origin != 'explicit' for v in motives):
                raise CompileError(path + '/' + field, 'Управляемому герою добавлена незаданная мотивация.')
            values[field] = [dict(id=m.identity(field, rid, v.key), text=v.text) for v in motives]
        state['characters'][rid] = m.Character(id=rid, display_name=row.name,
            location_id=ref('locations', row.location, path + '/location', True),
            appearance=m.AppearanceProfile(legacy_text=row.appearance),
            personality=m.PersonalityProfile(items=personality), **values).model_dump()
        cards.append(dict(id=rid, name=row.name, aliases=row.aliases,
                          fields={label: getattr(row, field) for field, label in CARD_FIELDS.items() if getattr(row, field)}))
        track(row, path, 'world_state/characters/' + rid, {'age': 'card_text_no_birthdate', 'biography': 'card_text', 'appearance': 'legacy_text'})
    for row, rid, path in records('locations'):
        state['locations'][rid] = m.Location(id=rid, name=row.name, kind=row.kind, description=row.description,
            parent_id=ref('locations', row.parent, path + '/parent', True)).model_dump()
        track(row, path, 'world_state/locations/' + rid)
    for row, rid, path in records('organizations'):
        state['organizations'][rid] = m.Organization(id=rid, name=row.name, kind=row.kind, context=row.description,
            location_ids=[ref('locations', k, path + '/locations') for k in row.locations]).model_dump()
        if row.parent:
            parent = ref('organizations', row.parent, path + '/parent')
            fid = m.identity('organization_parent', rid, parent)
            state['facts'][fid] = m.Fact(id=fid, text=row.name + ' → ' + next(p.name for p in doc.organizations if p.key == row.parent),
                visibility='secret', claim=m.Claim(subject_id=rid, predicate='organization.parent', value=parent)).model_dump()
        track(row, path, 'world_state/organizations/' + rid, {'parent': 'structural_fact'})
    for row, rid, path in records('objective_relations'):
        state['objective_relations'][rid] = m.ObjectiveRelation(id=rid, kind=row.kind,
            source_id=actor(row.source, path + '/source'), target_id=actor(row.target, path + '/target'),
            status=row.status, context=row.context, evidence=row.time_description).model_dump()
        track(row, path, 'world_state/objective_relations/' + rid)
    for row, _, path in records('feelings'):
        source, target = actor(row.source, path + '/source'), actor(row.target, path + '/target')
        key = source + ':' + target
        if key in state['relationships']:
            raise CompileError(path, 'Повторяющаяся направленная связь.')
        state['relationships'][key] = m.Relationship(source_id=source, target_id=target,
            dimensions={k: LEVELS[v] for k, v in row.levels.items() if v != 'unknown'}, context=row.context).model_dump()
        track(row, path, 'world_state/relationships/' + key, {'levels': 'qualitative_table_unknown_absent'})
    for row, rid, path in records('facts'):
        state['facts'][rid] = m.Fact(id=rid, text=row.text, visibility='secret' if row.secret else 'public',
            character_ids=[actor(k, path + '/participants') for k in row.participants]).model_dump()
        track(row, path, 'world_state/facts/' + rid)
    for row, rid, path in records('events'):
        event = dict(id=rid, text=row.text, time_description=row.time_description,
            participants=[actor(k, path + '/participants') for k in row.participants],
            witnesses=[actor(k, path + '/witnesses') for k in row.witnesses],
            fact_ids=[ref('facts', k, path + '/facts') for k in row.facts], medium=row.medium,
            after=[ref('events', k, path + '/after') for k in row.after])
        history['events'].append(event)
        track(row, path, 'initial_history/events/' + rid)
    for row, _, path in records('knowledge'):
        cid, fid = actor(row.actor, path + '/actor'), ref('facts', row.fact, path + '/fact')
        event = ref('events', row.event, path + '/event', True)
        if event:
            source = next(e for e in history['events'] if e['id'] == event)
            if cid not in source['witnesses'] or fid not in source['fact_ids'] or source['medium'] == 'other':
                raise CompileError(path + '/event', 'Событие не подтверждает передачу данного факта этому персонажу.')
        key = cid + ':' + fid
        knowledge = m.Knowledge(actor_id=cid, fact_id=fid, status=row.status, source_event_id=event,
            evidence='\n'.join(s for s in (row.evidence, row.time_description) if s)).model_dump()
        if row.current:
            if key in state['knowledge']:
                raise CompileError(path, 'Два текущих состояния знания одного факта.')
            state['knowledge'][key] = knowledge
        else:
            history['legacy'].append(dict(kind='prior_knowledge', **knowledge))
        track(row, path, ('world_state/knowledge/' + key) if row.current else 'initial_history/legacy')
    for section, model, fields in (
        ('residences', m.Residence, {'actor': 'characters', 'location': 'locations'}),
        ('roles', m.NarrativeRole, {'actor': 'characters', 'organization': 'organizations'}),
        ('conditions', m.Condition, {'actor': 'characters'}),
        ('possessions', m.SignificantPossession, {'owner': 'characters', 'holder': 'characters', 'location': 'locations'})):
        for row, rid, path in records(section):
            values = row.model_dump(exclude={'key', 'origin', 'field_origins', *fields})
            if section == 'possessions':
                description = values.pop('description')
                if description:
                    fid = m.identity('possession_description', rid)
                    state['facts'][fid] = m.Fact(id=fid, text=description, visibility='secret').model_dump()
                    values['fact_id'] = fid
            for field, target in fields.items():
                values[field + '_id'] = ref(target, getattr(row, field), path + '/' + field, field in ('organization', 'owner', 'holder', 'location') and section != 'residences')
            state[section][rid] = _check(model, dict(id=rid, **values), path).model_dump()
            track(row, path, 'world_state/' + section + '/' + rid)
    for row, rid, path in records('commitments'):
        participants = [actor(k, path + '/participants') for k in row.participants]
        if controlled in participants and row.origin != 'explicit':
            raise CompileError(path, 'Управляемому герою добавлено незаданное обязательство.')
        time = row.time
        basis = sum(v is not None for v in (time.date, time.weekday, time.day_offset))
        if basis == 0 and any(v is not None for v in (time.clock, time.period)):
            raise CompileError(path + '/time', 'У времени обязательства отсутствует точка отсчёта.')
        temporal = _check(m.TemporalValue, dict(date=time.date, weekday=time.weekday, day_offset=time.day_offset,
            time=time.clock, day_period=time.period), path + '/time').model_dump() if basis else None
        state['scheduled_events'][rid] = m.ScheduledEvent(id=rid, description=row.description,
            character_ids=participants, location_id=ref('locations', row.location, path + '/location', True),
            temporal=temporal, time_reference_minute=minute if temporal else None,
            commitment=True, evidence=time.description).model_dump()
        track(row, path, 'world_state/scheduled_events/' + rid)
    for field in a.World.model_fields:
        mapping.append(dict(source='world/' + field, target='campaign/campaign/' + field, method='copy', origin='unknown'))
    for field in a.Opening.model_fields:
        mapping.append(dict(source='opening/' + field, target='world_state/meta' if field in ('time', 'calendar', 'protagonist') else 'world_state/camera', method='calendar_or_reference', origin='unknown'))
    diagnostics.extend(dict(category='semantic', path='uncertainties/' + str(i), reason=text,
        action='Примите интерпретацию или исправьте авторский документ.') for i, text in enumerate(doc.uncertainties))
    snapshot = dict(schema_version=3, world_state=_check(m.WorldStateV3, state, 'compiled').model_dump(),
        character_cards=cards, campaign={'campaign': doc.world.model_dump(), 'creation': settings.model_dump()}, initial_history=history)
    result = normalize(snapshot, operation='creative_generate')
    dropped = [r for r in result.report if r.get('action') == 'drop_record']
    if dropped:
        raise CompileError('compiled', 'Каноническая нормализация отбросила данные: ' + str(dropped))
    return Compilation(result.snapshot, ids, diagnostics, mapping)
