"""Disposable draft display projections; calendar arithmetic remains Runtime-owned."""
from backend.runtime_v3.calendar import current_time

WEEKDAYS=('Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье')
MONTHS=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')


def launch_view(state, visible):
    """Camera/agency labels from canon, names only from the authorized projection."""
    names={c['id']:c['name'] for c in visible.get('characters',[])}
    person=lambda cid,empty: names.get(cid,'Скрытый персонаж') if cid else empty
    camera=state.get('camera',{});actor=state.get('controlled_actor_id')
    # Runtime ContextScope uses explicit POV, then controlled actor. Camera
    # subject identifies framing and never silently becomes POV or control.
    pov=camera.get('pov_actor_id') or actor
    return dict(protagonist=person(state.get('protagonist_id'),'Мир без протагониста'),
        controlled_actor=person(actor,'Нет управляемого персонажа'),
        camera_mode='Наблюдатель' if camera.get('mode')=='observer' else 'Взгляд персонажа',
        pov=person(pov,'Наблюдение за сценой'),subject=person(camera.get('subject_id'),'Сцена целиком'))


def clock_view(clock):
    if clock is not None and not isinstance(clock,dict):return {'label':'Некорректный календарь — проверьте диагностику'}
    clock=clock or {};minute=clock.get('minute',0)
    state={'meta':{'world_time':minute,'calendar':clock.get('calendar')}}
    try:
        value=current_time(state);profile=(clock.get('calendar') or {}).get('profile') or {}
        custom=profile.get('system')=='custom'
        day=value['weekday_name'] if custom else WEEKDAYS[value['weekday']]
        if value['date']:
            y,m,d=map(int,value['date'].split('-'))
            names=profile.get('month_names') if custom else MONTHS
            stamp=f'{d} {names[m-1]} {y}' if names and m<=len(names) else value['date']
        else:stamp=f"день {value['day']} (дата неизвестна)"
        import calendar
        year=int(value['date'][:4]) if value.get('date') else None
        lengths=profile.get('month_lengths',[]) if custom else [calendar.monthrange(year,m)[1] if year else (None if m==2 else calendar.monthrange(2001,m)[1]) for m in range(1,13)]
        effective=dict(regional=profile.get('regional'),system=profile.get('system','gregorian'),month_names=profile.get('month_names') or ([] if custom else list(MONTHS)),weekday_names=profile.get('weekday_names') or ([] if custom else list(WEEKDAYS)),month_lengths=lengths,year=year,seasons=profile.get('seasons',[]),observances=profile.get('observances',[]))
        return dict(value,effective=effective,label=f"{day}, {stamp}, {value['time']}")
    except (ValueError,KeyError,IndexError,TypeError):return {'label':'Некорректный календарь — проверьте диагностику'}


def time_selection(clock, minute, selected_date=None):
    """Resolve a calendar date using the same ordinal functions as Runtime."""
    from backend.runtime_v3.calendar import ordinal
    if minute<0:raise ValueError('Время должно быть неотрицательным.')
    if selected_date is not None:
        calendar=clock.get('calendar') or {}
        if not calendar.get('start_date'):raise ValueError('Сначала задайте начальную дату календаря.')
        profile=calendar.get('profile') or {}
        days=ordinal(selected_date,profile)-ordinal(calendar['start_date'],profile)
        minute=(calendar['start_minute']//1440+days)*1440+minute%1440
        if minute<0:raise ValueError('Дата находится до начала отсчёта мира.')
    return clock_view(dict(clock,minute=minute))


def editor_contract():
    from backend.services.draft_world import FIELDS
    from backend.services.draft_initial import EXTENSIONS
    from backend.runtime_v3.models import Character,ScheduledEvent
    enums={};schemas={};definitions={}
    for kind,model in dict(EXTENSIONS,actor=Character,scheduled_events=ScheduledEvent).items():
        enums[kind]={};schema=model.model_json_schema();schemas[kind]=schema['properties'];definitions.update(schema.get('$defs',{}))
        for key,schema in schemas[kind].items():
            enum=schema.get('enum') or next((part['enum'] for part in schema.get('anyOf',[]) if 'enum' in part),None)
            if enum:enums[kind][key]=enum
    from backend.services.draft_player_view import RESERVED_FIELDS
    return dict(fields={k:sorted(v) for k,v in FIELDS.items()},enums=enums,schemas=schemas,definitions=definitions,
                field_visibility_excluded=sorted(RESERVED_FIELDS))


def calendar_notices(state):
    metadata=state.get('authoring',{}).get('calendar_completion',{})
    notices=list(metadata.get('notices',[]))
    names={c['id']:c['name'] for c in state.get('characters',[])}
    for cid,record in metadata.get('birth_dates',{}).items():
        if record.get('notice'):
            notices.append(f"{names.get(cid,cid)} · дата рождения: {record['notice']} (/world/characters/{cid}/birth_date)")
    return notices


def event_times(state,group='events',field='minute'):
    """Format only events already admitted by the caller's author/player projection."""
    clock=state.get('world_clock',{})
    return {eid:clock_view(dict(clock,minute=event[field]))['label']
            if event.get(field) is not None else 'Дата неизвестна'
            for eid,event in state.get('world',{}).get(group,{}).items()}


def event_periods(state):
    """Classify admitted events relative to Runtime's local day, not wall time."""
    from backend.runtime_v3.calendar import MINUTES_PER_DAY
    now=state.get('world_clock',{}).get('minute',0)
    return {eid:('today' if event['minute']//MINUTES_PER_DAY==now//MINUTES_PER_DAY else 'past' if event['minute']<now else 'future')
            for eid,event in state.get('world',{}).get('events',{}).items()
            if isinstance(event.get('minute'),(int,float)) and not isinstance(event.get('minute'),bool)}
