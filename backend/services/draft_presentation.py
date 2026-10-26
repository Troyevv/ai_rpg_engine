"""Disposable draft display projections; calendar arithmetic remains Runtime-owned."""
from backend.runtime_v3.calendar import current_time

WEEKDAYS=('Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье')
MONTHS=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')


def clock_view(clock):
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


def editor_contract():
    from backend.services.draft_world import FIELDS
    from backend.services.draft_initial import EXTENSIONS
    from backend.runtime_v3.models import Character,ScheduledEvent
    enums={};schemas={}
    for kind,model in dict(EXTENSIONS,actor=Character,scheduled_events=ScheduledEvent).items():
        enums[kind]={};schemas[kind]=model.model_json_schema()['properties']
        for key,schema in schemas[kind].items():
            enum=schema.get('enum') or next((part['enum'] for part in schema.get('anyOf',[]) if 'enum' in part),None)
            if enum:enums[kind][key]=enum
    return dict(fields={k:sorted(v) for k,v in FIELDS.items()},enums=enums,schemas=schemas)


def calendar_notices(state):
    metadata=state.get('authoring',{}).get('calendar_completion',{})
    notices=list(metadata.get('notices',[]))
    names={c['id']:c['name'] for c in state.get('characters',[])}
    for cid,record in metadata.get('birth_dates',{}).items():
        if record.get('notice'):
            notices.append(f"{names.get(cid,cid)} · дата рождения: {record['notice']} (/world/characters/{cid}/birth_date)")
    return notices
