"""Explicit authoring-time completion. Never called by imports or running saves."""
from copy import deepcopy
import hashlib
import json
import re
from backend.runtime_v3.calendar import age_on, date_parts, ordinal, from_ordinal, current_time
from backend.runtime_v3.models import Calendar, CalendarProfile
from pydantic import ValidationError

VERSION = 1
WEEK = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def idea_start(text):
    """Only an explicit start/now clause, never a date in a biography."""
    matches = list(re.finditer(r'(?:\bсейчас\b|начало игры\s*[:—-]?|игра начинается\s*[:—-]?|\bnow\b)\s*([^\n!?]+)', text, re.I))
    values = []
    for match in matches:
        clause = match[1][:120]
        result = {}
        d = re.search(r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b', clause)
        if d:
            raw = d[1]
            if '.' in raw:
                day, month, year = map(int, raw.split('.')); raw = f'{year:04d}-{month:02d}-{day:02d}'
            result['date'] = raw
        t = re.search(r'\b(\d{1,2}):(\d{2})\b', clause)
        if t: result['time'] = f'{int(t[1]):02d}:{t[2]}'
        for i, word in enumerate(WEEK):
            if re.search(r'\b'+word+r'\b', clause, re.I): result['weekday'] = i
        if not d:
            y = re.search(r'\b(\d{4})\s*(?:год|году|г\.)', clause)
            if y: result['year'] = int(y[1])
        if result: values.append(result)
    # Conflicting explicit start clauses require semantic interpretation.
    if values:return values[0] if all(v == values[0] for v in values) else {}
    year=re.match(r'^\s*(\d{4})\s+год[.\s]',text,re.I)
    return {'year':int(year[1])} if year else {}


def synchronize(state, old_minute, minute, calendar):
    state['world_clock'].update(minute=minute, calendar=calendar)
    scene = state['world'].get('scenes', {}).get(state.get('camera', {}).get('scene_id'), {})
    for key in ('start_minute', 'end_minute'):
        if scene.get(key) == old_minute: scene[key] = minute
    for actor in state['world'].get('characters', {}).values():
        if actor.get('minute') == old_minute: actor['minute'] = minute
    from backend.services.draft_world import sync
    return sync(state)


def complete(state, author_text='', seed=None):
    """Generate once; preserve manual edits and recheck only dependent auto DOB."""
    state = deepcopy(state)
    if not isinstance(state.get('world_clock'),dict) or type(state['world_clock'].get('minute')) is not int: return state
    if not isinstance(state.get('world'),dict) or not isinstance(state['world'].get('characters'),dict) or not isinstance(state.get('characters'),list): return state
    from backend.services.world_creation_settings import CalendarStart
    settings = CalendarStart.model_validate(state.get('creation_settings', {}).get('calendar_start') or {})
    meta = state.setdefault('authoring', {}).setdefault('calendar_completion', {})
    meta.setdefault('seed', seed or signature([author_text, state.get('campaign', {})]))
    old = state['world_clock']['minute']
    configured = deepcopy(state['world_clock'].get('calendar') or {})
    previous = meta.get('resolved')
    notices = []
    if previous:
        # Only manual_edit may update this server-owned resolution.
        old = previous['minute']
        configured = deepcopy(previous['calendar'])
        try:cal = Calendar.model_validate(configured).model_dump()
        except ValidationError as exc:
            from backend.services.draft_initial import DraftErrors,error
            raise DraftErrors([error('/world_clock/calendar'+('/'+'/'.join(map(str,e['loc'])) if e['loc'] else ''),e['msg'],e['type']) for e in exc.errors(include_input=False)]) from exc
        now = current_time({'meta': {'world_time': old, 'calendar': cal}})
        cal.update(start_minute=old, start_date=now['date'], start_weekday=now['weekday'])
        minute = old
        sources = previous['sources']
    else:
        idea = idea_start(author_text)
        profile = configured.get('profile') or {}
        if settings.mode == 'gregorian': profile = CalendarProfile().model_dump()
        elif settings.mode == 'custom': profile = settings.profile.model_dump()
        if profile.get('system','gregorian')=='gregorian':profile=dict(profile,month_lengths=[])
        try:profile = CalendarProfile.model_validate(profile).model_dump()
        except ValidationError as exc:
            from backend.services.draft_initial import DraftErrors,error
            raise DraftErrors([error('/world_clock/calendar/profile/'+ '/'.join(map(str,e['loc'])),e['msg'],e['type']) for e in exc.errors(include_input=False)]) from exc
        sources = {'calendar': 'settings' if settings.mode != 'auto' else 'generated'}
        resolved = {}
        for field, explicit, fallback in (
            ('date', settings.date, configured.get('start_date')),
            ('time', settings.time, f'{old%1440//60:02d}:{old%60:02d}'),
            ('weekday', settings.weekday, configured.get('start_weekday', old//1440%len(profile['weekday_names'] or WEEK))),
        ):
            resolved[field] = explicit if explicit is not None else idea.get(field, fallback)
            sources[field] = 'settings' if explicit is not None else 'idea' if field in idea else 'generated'
            if explicit is not None and field in idea and explicit != idea[field]:
                notices.append(f'{field}: применена настройка {explicit}; в идее указано {idea[field]}.')
        if 'year' in idea:
            meta['known_year'] = idea['year']
            if settings.date is None and (not resolved['date'] or int(resolved['date'][:4]) != idea['year']):
                resolved['date'] = None
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', resolved['time']):
            raise ValueError('/creation_settings/calendar_start/time: время должно быть HH:MM (00:00–23:59).')
        hour, minute_of_hour = map(int, resolved['time'].split(':'))
        minute = old//1440*1440 + hour*60 + minute_of_hour
        if resolved['date'] and profile['system']=='gregorian':
            try:
                from datetime import date
                resolved['weekday']=date.fromisoformat(resolved['date']).weekday()
            except ValueError:
                from backend.services.draft_initial import DraftErrors,error
                raise DraftErrors([error('/world_clock/calendar/start_date','Дата отсутствует в григорианском календаре.','calendar_date')])
        try:
            cal = Calendar(start_minute=minute, start_date=resolved['date'], start_weekday=resolved['weekday'], profile=profile).model_dump()
        except ValidationError as exc:
            from backend.services.draft_initial import DraftErrors,error
            raise DraftErrors([error('/world_clock/calendar'+('/'+'/'.join(map(str,e['loc'])) if e['loc'] else ''),e['msg'],e['type']) for e in exc.errors(include_input=False)]) from exc
        if resolved['date'] and profile['system'] == 'gregorian' and idea.get('weekday') is not None and idea['weekday'] != cal['start_weekday']:
            notices.append('День недели вычислен по дате; указанный в идее день недели не совпадает.')
    meta.update(version=VERSION, resolved=dict(minute=minute, calendar=deepcopy(cal), sources=sources))
    if notices: meta['notices'] = notices
    synchronize(state, old, minute, cal)
    fill_birth_dates(state)
    return state


def fill_birth_dates(state):
    meta = state['authoring']['calendar_completion']
    cal = state['world_clock']['calendar']; profile = cal['profile']; today = cal.get('start_date')
    if not today: return
    y, _, _ = date_parts(today, profile)
    records = meta.setdefault('birth_dates', {})
    for card in state['characters']:
        cid = card['id']; actor = state['world']['characters'].get(cid)
        if not actor: continue
        match = re.fullmatch(r'(\d{1,4})(?:\s+(?:лет|год|года))?', str(card.get('fields', {}).get('Возраст', '')).strip())
        prior = records.get(cid, {})
        if prior.get('source') == 'manual' or actor.get('birth_provenance', {}).get('source') == 'unknown': continue
        if not match: continue
        age = int(match[1]); birth = actor.get('birth_date')
        if birth and (prior.get('value') != birth or prior.get('source') != 'automatic'): continue
        if birth and age_on(birth, today, profile) == age: continue
        # At most two calendar years; exact Runtime age predicate handles leap policy.
        candidates = []
        for year in (y-age-1, y-age):
            if not 1 <= year <= 9999: continue
            first = ordinal(f'{year:04d}-01-01', profile)
            last = ordinal(f'{year+1:04d}-01-01', profile)-1 if year < 9999 else (9999*sum(profile['month_lengths']) if profile['system']=='custom' else ordinal('9999-12-31', profile))
            for n in range(first, last+1):
                value = from_ordinal(n, profile)
                if age_on(value, today, profile) == age: candidates.append(value)
        if not candidates:
            if prior.get('source')=='automatic':actor['birth_date']=None
            records[cid] = dict(source='automatic', value=None, notice='Дата рождения вне поддерживаемого диапазона лет 1–9999.')
            continue
        group=actor.get('birth_provenance',{}).get('twin_group')
        if group:
            established={a['birth_date'] for a in state['world']['characters'].values() if a.get('birth_date') and a.get('birth_provenance',{}).get('twin_group')==group}
            if established:
                candidates=[d for d in candidates if d in established] if len(established)==1 else []
                if not candidates:
                    records[cid]=dict(source='automatic',value=None,notice='Даты близнецов противоречат заданному возрасту; требуется уточнение.')
                    continue
        chosen = candidates[int(signature([meta['seed'], group or cid]), 16)%len(candidates)]
        actor['birth_date'] = chosen
        records[cid] = dict(source='automatic', value=chosen, input_signature=signature([age,today,profile]))
        actor['birth_provenance'] = dict(actor.get('birth_provenance') or {}, source='authoring_automatic', input_signature=records[cid]['input_signature'])


def manual_edit(state, path, old_minute=None):
    meta = state.get('authoring', {}).get('calendar_completion')
    if not meta: return state
    if path.startswith('/world/characters/') and path.endswith('/birth_date'):
        cid = path.split('/')[3].replace('~1','/').replace('~0','~')
        meta.setdefault('birth_dates', {})[cid] = dict(source='manual', value=state['world']['characters'][cid].get('birth_date'))
        state['world']['characters'][cid]['birth_provenance'] = {'source':'manual'}
    if path.startswith('/world_clock'):
        meta['resolved']['minute']=state['world_clock']['minute']
        meta['resolved']['calendar']=deepcopy(state['world_clock']['calendar'])
        meta['resolved']['sources'] = {'calendar':'manual','date':'manual','time':'manual','weekday':'manual'}
        if old_minute is not None:
            synchronize(state, old_minute, state['world_clock']['minute'], state['world_clock']['calendar'])
    return complete(state)
