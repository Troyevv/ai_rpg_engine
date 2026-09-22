"""One monotonic story clock. Old display strings are parsed without rewriting history."""
import re
from backend.services.scene import scene_metadata

WEEKDAYS = ('Пн','Вт','Ср','Чт','Пт','Сб','Вс')

DAYS = {'пн':0,'понедельник':0,'вт':1,'вторник':1,'ср':2,'среда':2,'чт':3,'четверг':3,
        'пт':4,'пятница':4,'сб':5,'суббота':5,'вс':6,'воскресенье':6}


def parse_time(value, reference=0):
    value=str(value).casefold()
    match=re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b',value)
    if not match:return None
    day=reference//1440
    explicit=re.search(r'день\s+(\d+)',value)
    if explicit:day=max(0,int(explicit[1])-1)
    else:
        for name,index in DAYS.items():
            if re.search(r'(?<!\w)'+name+r'(?!\w)',value):
                day=(day//7)*7+index
                break
    if 'следующий день' in value or 'завтра' in value:day=reference//1440+1
    return day*1440+int(match[1])*60+int(match[2])


def current_time(state):
    clock=state.get('world_clock',{})
    if isinstance(clock.get('minute'),int):return clock['minute']
    base=parse_time(clock.get('last_event_time',''))
    scene=parse_time(scene_metadata(state)['time'],base or 0)
    return max(v for v in (base,scene,0) if v is not None)


def label(minute):
    return f'День {minute//1440+1} ({WEEKDAYS[minute//1440%7]}) {minute%1440//60:02d}:{minute%60:02d}'


def advance(before,after,scene,elapsed=None,minimum=0):
    now=current_time(before)
    value=parse_time(scene['time'],now)
    if value is None:
        # Legacy worlds without a clock start at day 1 00:00, never invent elapsed time.
        value=now
    if elapsed is not None:
        if type(elapsed) is not int or not 0<=elapsed<=10080:
            raise ValueError('Длительность сцены должна быть целым числом минут от 0 до 10080.')
        if value%1440==(now+elapsed)%1440 and not re.search(r'день\s+\d+|'+ '|'.join(DAYS),scene['time'],re.I):
            value=now+elapsed
        if value not in (now, now+elapsed):
            raise ValueError('Время сцены не совпадает с её длительностью.')
        value=now+elapsed
    elif value==now:
        value=now+minimum
    if value<now:
        raise ValueError('Время сцены раньше текущего времени мира. Минимум: '+label(now))
    after['world_clock']={'minute':value,'last_event_time':label(value)}
    scene['time']=label(value)
    return value
