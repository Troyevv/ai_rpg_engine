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
        return dict(value,label=f"{day}, {stamp}, {value['time']}")
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
