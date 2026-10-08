"""Read-only calendar arithmetic over monotonic local world minutes.

Gregorian arithmetic uses datetime. Custom profiles use explicitly configured,
fixed month lengths (no implied Earth seasons/timezones or geographic inference).
Annual Feb 29 dates occur only in leap years; age advances on March 1 otherwise.
No recurrence here writes events, Knowledge, or actions.
"""
from datetime import date
import re

MINUTES_PER_DAY = 1440
MAX_RANGE_DAYS = 400
MAX_NEARBY_EVENTS = 12
DAY_PERIODS = ((0, 'night'), (360, 'morning'), (720, 'afternoon'), (1080, 'evening'), (1320, 'night'))
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
RU_WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


def day_period(clock):
    return next(name for start, name in reversed(DAY_PERIODS) if clock >= start)


def profile_of(state):
    return (state['meta'].get('calendar') or {}).get('profile') or {}


def date_parts(value, profile=None):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Дата должна иметь формат YYYY-MM-DD.')
    y, m, d = map(int, value.split('-'))
    profile = profile or {}
    if profile.get('system') == 'custom':
        months = profile['month_lengths']
        if not (1 <= y <= 9999 and 1 <= m <= len(months) and 1 <= d <= months[m-1]):
            raise ValueError('Дата отсутствует в выбранном календаре.')
    else:
        date(y, m, d)
    return y, m, d


def ordinal(value, profile):
    y, m, d = date_parts(value, profile)
    if profile.get('system') == 'custom':
        lengths = profile['month_lengths']
        return (y-1)*sum(lengths) + sum(lengths[:m-1]) + d
    return date(y, m, d).toordinal()


def from_ordinal(value, profile):
    if profile.get('system') != 'custom':
        return date.fromordinal(value).isoformat()
    lengths = profile['month_lengths']
    y, rest = divmod(value-1, sum(lengths))
    if not 0 <= y < 9999: raise ValueError('Дата вне диапазона календаря.')
    for m, length in enumerate(lengths, 1):
        if rest < length: return f'{y+1:04d}-{m:02d}-{rest+1:02d}'
        rest -= length
    raise ValueError('Дата вне диапазона календаря.')


def current_time(state, minute=None):
    meta = state['meta']; minute = meta['world_time'] if minute is None else minute
    cal = meta.get('calendar') or dict(start_minute=meta['world_time'], start_weekday=meta['world_time']//1440%7)
    profile = profile_of(state)
    days = minute//1440 - cal['start_minute']//1440
    weekday_names = profile.get('weekday_names') or WEEKDAYS
    weekday = (cal['start_weekday'] + days) % len(weekday_names)
    value = None
    if cal.get('start_date'):
        try:
            value = from_ordinal(ordinal(cal['start_date'], profile)+days, profile)
            if profile.get('system') != 'custom': weekday = date.fromisoformat(value).weekday()
        except (ValueError, OverflowError): pass  # Relative time remains usable at date limits.
    clock = minute % 1440
    result = dict(world_time=minute, day=days+1, date=value, weekday=weekday,
                  weekday_name=weekday_names[weekday], time=f'{clock//60:02d}:{clock%60:02d}',
                  day_period=day_period(clock), season=None)
    if value:
        _, m, d = date_parts(value, profile)
        seasons = sorted(profile.get('seasons', []), key=lambda s:(s['month'],s['day']))
        if seasons:
            result['season'] = next((s['name'] for s in reversed(seasons) if (s['month'],s['day']) <= (m,d)), seasons[-1]['name'])
    result['summary'] = f"Day {result['day']} / {value or 'date unknown'} / {result['weekday_name']} / {result['time']} / {result['day_period']}"
    return result


def calendar_label(state, minute=None):
    p = current_time(state, minute)
    custom = profile_of(state).get('weekday_names')
    weekday = custom[p['weekday']] if custom else RU_WEEKDAYS[p['weekday']]
    return f"День {p['day']} · " + (f"{p['date']} · " if p['date'] else '') + f"{weekday} · {p['time']}"


def age_on(birth_date, today, profile=None):
    if not birth_date or not today: return None
    try:
        by,bm,bd = date_parts(birth_date, profile); y,m,d = date_parts(today, profile)
        if (by,bm,bd) > (y,m,d): return None
        return y-by-int((m,d)<(bm,bd))
    except (ValueError, KeyError): return None


def _dates(state, relevant_ids=None):
    profile = profile_of(state)
    for item in profile.get('observances', []):
        ids = item.get('character_ids', [])
        if ids and relevant_ids is not None and not set(ids) & set(relevant_ids): continue
        yield dict(item, kind='personal' if ids else 'observance')
    for cid, character in sorted(state['characters'].items()):
        if relevant_ids is not None and cid not in relevant_ids: continue
        birth = character.get('birth_date')
        try: y,m,d = date_parts(birth, profile)
        except (ValueError, KeyError): continue
        yield dict(id='birthday:'+cid, name=None, month=m, day=d, kind='birthday', character_ids=[cid], since_year=y)


def calendar_range(state, start_date, end_date, relevant_ids=None):
    profile = profile_of(state)
    start, end = ordinal(start_date, profile), ordinal(end_date, profile)
    if not 0 <= end-start < MAX_RANGE_DAYS:
        raise ValueError(f'Диапазон календаря: от 1 до {MAX_RANGE_DAYS} дней.')
    current = current_time(state)
    anchor = (state['meta'].get('calendar') or {}).get('start_date')
    origin = ordinal(anchor, profile) if anchor else None
    rules = list(_dates(state, relevant_ids))
    days, events = [], []
    for n in range(start, end+1):
        value = from_ordinal(n, profile); y,m,d = date_parts(value, profile)
        if profile.get('system') == 'custom':
            weekday = ((state['meta']['calendar']['start_weekday'] + n-origin) % len(profile.get('weekday_names') or WEEKDAYS)) if origin is not None else None
            length = profile['month_lengths'][m-1]
        else:
            import calendar as std_calendar
            weekday = date(y,m,d).weekday(); length = std_calendar.monthrange(y,m)[1]
        days.append(dict(date=value, year=y, month=m, day=d, weekday=weekday,
                         day_number=n-origin+1 if origin is not None else None,
                         month_length=length, month_start=d==1, month_end=d==length, year_start=m==1 and d==1))
        for rule in rules:
            if (rule['month'],rule['day']) == (m,d) and y >= rule.get('since_year',1):
                events.append(dict(id=f"{rule['id']}:{value}", date=value, kind=rule['kind'],
                                   name=rule['name'], character_ids=rule.get('character_ids',[])))
    return dict(current=current, start_date=start_date, end_date=end_date, days=days, events=events,
                profile={k:profile.get(k) for k in ('id','system','month_names','weekday_names')})


def nearby_calendar(state, relevant_ids):
    current = current_time(state); profile = profile_of(state)
    if not current['date']: return []
    n = ordinal(current['date'], profile)
    lo = max(1,n-1)
    hi = min(ordinal('9999-12-31', {}) if profile.get('system') != 'custom' else 9999*sum(profile['month_lengths']), n+7)
    events = calendar_range(state, from_ordinal(lo,profile), from_ordinal(hi,profile), relevant_ids)['events']
    return sorted(events,key=lambda e:(abs(ordinal(e['date'],profile)-n),e['date'],e['id']))[:MAX_NEARBY_EVENTS]


# Legacy compatibility recognises only explicit weekday/relative-day + clock/period.
# Unrecognised prose is unresolved, never guessed due. Relative values are anchored
# to stored reference_minute (campaign start for old saves), never to each read.
_WEEKDAY_PATTERN = ('понедельник', 'вторник', 'сред', 'четверг', 'пятниц', 'суббот', 'воскресень')
_PERIOD_PATTERN = {'morning':r'утр\w*|morning', 'afternoon':r'днём|днем|afternoon', 'evening':r'вечер\w*|evening', 'night':r'ноч\w*|night'}


def scheduled_time(state, event):
    reference = event.get('time_reference_minute')
    if reference is None: reference = (state['meta'].get('calendar') or {}).get('start_minute',state['meta']['world_time'])
    temporal = dict(event.get('temporal') or {})
    due = event.get('due_minute')
    if not temporal and (due is None or due == 0):
        text = event.get('condition','').casefold()
        if re.search(r'\b(?:не|not|или|or|после|after|до|before)\b',text): text = ''
        weekdays = [i for i,pattern in enumerate(_WEEKDAY_PATTERN) if re.search(r'\b(?:'+pattern+r'\w*|'+WEEKDAYS[i]+r')\b',text)]
        if profile_of(state).get('system') == 'custom':
            weekdays = [i for i,name in enumerate(profile_of(state).get('weekday_names') or WEEKDAYS) if re.search(r'\b'+re.escape(name.casefold())+r'\b',text)]
        if len(weekdays)==1: temporal['weekday'] = weekdays[0]
        for pattern,offset in ((r'\b(?:завтра|tomorrow)\b',1),(r'\b(?:сегодня|today)\b',0),(r'\b(?:вчера|yesterday)\b',-1)):
            if re.search(pattern,text): temporal['day_offset']=offset
        for period,pattern in _PERIOD_PATTERN.items():
            if re.search(r'\b(?:'+pattern+r')\b',text): temporal['day_period']=period
        clock = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b',text)
        if clock: temporal['time']=f'{int(clock[1]):02d}:{clock[2]}'
    resolved = due if type(due) is int and due > 0 else None
    if temporal:
        base = current_time(state, reference); offset = None
        if temporal.get('date') and base['date']:
            try: offset = ordinal(temporal['date'],profile_of(state))-ordinal(base['date'],profile_of(state))
            except (ValueError,KeyError): pass
        elif temporal.get('day_offset') is not None: offset = temporal['day_offset']
        elif temporal.get('weekday') is not None:
            week_length = len(profile_of(state).get('weekday_names') or WEEKDAYS)
            if temporal['weekday'] < week_length:
                offset = (temporal['weekday']-base['weekday']) % week_length
        if offset is not None:
            clock = temporal.get('time')
            minute = int(clock[:2])*60+int(clock[3:]) if clock else next((n for n,p in DAY_PERIODS if p==temporal.get('day_period')),0)
            resolved = reference//1440*1440 + offset*1440+minute
        else: resolved = None
    status = 'unresolved' if resolved is None else 'future' if resolved > state['meta']['world_time'] else 'due'
    return dict(status=status, due_minute=resolved)


def scheduled_due(state, event):
    return scheduled_time(state,event)['due_minute']
