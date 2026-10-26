"""Local versioned holiday rules; no network, locale inference, or world mutation on reads.

Coverage is intentionally 2025..2030. Future one-off decrees are not guaranteed.
IDs use explicit English source names + country + occurrence date, independently of UI
locale. Author overrides apply to ONE occurrence (including deletion), not future years.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import re
import holidays

VERSION = 'holidays-0.87-v1'
MIN_YEAR, MAX_YEAR = 2025, 2030
COUNTRIES = {
    'RU': ('Россия', 'Россия', r'россия|россии|russia|москва|moscow'),
    'DE': ('Германия', 'Европа', r'германия|германии|germany|берлин|berlin'),
    'FR': ('Франция', 'Европа', r'франция|франции|france|париж|paris'),
    'GB': ('Великобритания', 'Европа', r'великобритания|великобритании|united kingdom|лондон|london'),
    'IT': ('Италия', 'Европа', r'италия|италии|italy|рим|rome'),
    'ES': ('Испания', 'Европа', r'испания|испании|spain|мадрид|madrid'),
    'PL': ('Польша', 'Европа', r'польша|польше|poland|варшава|warsaw'),
    'US': ('США', 'Америка', r'сша|united states|usa|нью-йорк|new york'),
    'CA': ('Канада', 'Америка', r'канада|канаде|canada|оттава|ottawa'),
    'MX': ('Мексика', 'Америка', r'мексика|мексике|mexico|мехико'),
    'BR': ('Бразилия', 'Америка', r'бразилия|бразилии|brazil|бразилиа|brasilia'),
    'AR': ('Аргентина', 'Америка', r'аргентина|аргентине|argentina|буэнос-айрес|buenos aires'),
}


class CoverageError(ValueError):
    pass


def source(country, subdivision=None, years=(), observed=False):
    if holidays.__version__ != '0.87':
        raise CoverageError('Версия правил праздников недоступна; сохранённый набор не подменён.')
    if country not in COUNTRIES:
        raise CoverageError('Страна не поддержана каталогом. Используйте собственные даты.')
    empty = holidays.country_holidays(country, expand=False, language='en_US', observed=False)
    if subdivision and subdivision not in empty.subdivisions:
        raise CoverageError('Область не поддержана источником; выберите общенациональный набор явно.')
    return holidays.country_holidays(country, subdiv=subdivision, years=years, expand=False,
                                    language='en_US', observed=observed, categories='public')


def catalog():
    return dict(version=VERSION, min_year=MIN_YEAR, max_year=MAX_YEAR, language='en_US',
                countries=[dict(code=c, name=v[0], group=v[1], subdivisions=list(source(c).subdivisions)) for c,v in COUNTRIES.items()])


def occurrences(regional, start, end):
    if regional['version'] != VERSION:
        raise CoverageError('Сохранённая версия правил праздников недоступна; автоматическая подмена запрещена.')
    lo, hi = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (hi-lo).days < 400:
        raise ValueError('Диапазон календаря: от 1 до 400 дней.')
    if not MIN_YEAR <= lo.year <= hi.year <= MAX_YEAR:
        raise CoverageError(f'Праздничный набор поддерживает годы {MIN_YEAR}–{MAX_YEAR}; нужны собственные даты.')
    # A moved occurrence may enter the selected interval from an adjacent year.
    years=set(range(max(MIN_YEAR,lo.year-1), min(MAX_YEAR,hi.year+1)+1))
    for override in regional.get('overrides',[]):
        if override.get('date') and start<=override['date']<=end:
            original=override['id'].rsplit(':',1)[-1]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',original) and MIN_YEAR<=int(original[:4])<=MAX_YEAR:years.add(int(original[:4]))
    base=source(regional['country'],regional.get('subdivision'),years,False)
    full=source(regional['country'],regional.get('subdivision'),years,True) if regional.get('observed') else base
    if not base:raise CoverageError('Источник не предоставил годовой набор; прежний календарь сохранён.')
    overrides={v['id']:v for v in regional.get('overrides',[])}
    events=[]
    for day in sorted(full):
        # get_list is the documented multi-holiday API, not an arbitrary split.
        for name in full.get_list(day):
            observed=name not in base.get_list(day)
            identity='regional:'+sha256((regional['country']+'\0'+name).encode()).hexdigest()[:20]+':'+day.isoformat()
            override=overrides.get(identity,{})
            if override.get('removed'):continue
            value=override.get('date') or day.isoformat()
            if start <= value <= end:
                events.append(dict(id=identity,date=value,name=override.get('name') or name,kind='observance',
                                   observed=observed,source=VERSION,character_ids=[],original_date=day.isoformat()))
    return sorted(events,key=lambda e:(e['date'],e['id']))


def resolve(settings, choice):
    country=choice.get('country') if choice.get('holidays')=='country' else None
    geographic=[]
    if settings.get('world_type')=='real_world':
        geographic=[c for c,v in COUNTRIES.items() if re.search(r'\b(?:'+v[2]+r')\b',settings.get('geography',''),re.I)]
        if choice.get('holidays','auto')=='auto' and len(geographic)==1:country=geographic[0]
    season=choice.get('seasons','auto')
    if season=='auto':
        # Country alone is not proof of a climate. These named temperate cities are
        # sufficient to suggest a visible, overridable three-month GAME convention.
        geography=settings.get('geography','') if settings.get('world_type')=='real_world' and len(geographic)==1 else ''
        if re.search(r'\b(?:москва|moscow|берлин|berlin|париж|paris|лондон|london|рим|rome|мадрид|madrid|варшава|warsaw|оттава|ottawa|нью-йорк|new york)\b',geography,re.I):season='north'
        elif re.search(r'\b(?:буэнос-айрес|buenos aires)\b',geography,re.I):season='south'
        else:season=None
    return country,season


def apply(state, choice, explicit=False):
    """Atomic draft-only transformation; preserves all non-owned records and dates."""
    from backend.runtime_v3.models import CalendarProfile
    from backend.services.world_creation_settings import CalendarPresets
    choice=CalendarPresets.model_validate(choice).model_dump()
    result=deepcopy(state)
    profile=result['world_clock']['calendar'].setdefault('profile',{})
    meta=result.setdefault('authoring',{}).setdefault('calendar_presets',{})
    previous=deepcopy(meta)
    archived={o['id']:o for o in profile.get('regional_overrides',[])}
    archived.update({o['id']:o for o in (profile.get('regional') or {}).get('overrides',[])})
    profile['regional_overrides']=list(archived.values())
    if previous and not explicit:return result
    if choice['holidays']=='country' and not choice['country']:raise CoverageError('Выберите конкретную страну праздников.')
    country,season=resolve(result.get('creation_settings',{}),choice)
    notices=[]
    if choice['holidays'] in ('none','custom'):profile['regional']=None
    if choice['seasons']=='none':profile['seasons_enabled']=False
    elif choice['seasons']!='auto' or explicit:profile['seasons_enabled']=True
    if profile.get('system','gregorian')!='gregorian':
        if country or season in ('north','south'):notices.append('Земной набор несовместим со своим календарём; собственные даты сохранены.')
    else:
        if country:
            source(country,choice.get('subdivision')) # invalid region rolls back entire package
            existing=profile.get('regional')
            regional=dict(country=country,subdivision=choice.get('subdivision'),version=VERSION,
                          language='en_US',observed=choice['observed'],overrides=list(archived.values()))
            start_date=result['world_clock']['calendar'].get('start_date')
            if start_date and MIN_YEAR<=int(start_date[:4])<=MAX_YEAR:
                occurrences(regional,f'{int(start_date[:4]):04d}-01-01',f'{int(start_date[:4]):04d}-12-31')
            # auto never overwrites an existing authored choice.
            if explicit or not existing:profile['regional']=regional
        elif choice['holidays'] in ('none','custom'):profile['regional']=None
        elif choice['holidays']=='auto':notices.append('Страна праздников не определена. Можно выбрать набор вручную.')
        owned=previous.get('owned_seasons',[])
        current=profile.get('seasons',[])
        custom=[v for v in current if v not in owned]
        manually_changed=bool(owned) and current!=owned
        same_choice=previous.get('selection',{}).get('seasons')==choice['seasons']
        if season in ('north','south') and not custom and not (manually_changed and same_choice):
            names=('Весна','Лето','Осень','Зима') if season=='north' else ('Осень','Зима','Весна','Лето')
            profile['seasons']=[dict(name=n,month=m,day=1) for m,n in zip((3,6,9,12),names)]
            meta['owned_seasons']=deepcopy(profile['seasons'])
        elif season=='none':
            profile['seasons']=custom;meta['owned_seasons']=[]
        elif season is None:notices.append('Календарный профиль сезонов не определён; собственные сезоны сохранены.')
    profile=CalendarProfile.model_validate(profile).model_dump()
    result['world_clock']['calendar']['profile']=profile
    meta.update(selection=choice,notices=notices)
    result.setdefault('creation_settings',{}).setdefault('calendar_start',{})['presets']=choice
    completion=result.get('authoring',{}).get('calendar_completion',{})
    if completion.get('resolved'):completion['resolved']['calendar']=deepcopy(result['world_clock']['calendar'])
    return result


def preview(state):
    from backend.runtime_v3.calendar import current_time, from_ordinal, ordinal
    clock=state['world_clock'];cal=clock['calendar'];profile=cal.get('profile') or {}
    now=current_time({'meta':{'world_time':clock['minute'],'calendar':cal}})
    notices=list(state.get('authoring',{}).get('calendar_presets',{}).get('notices',[]))
    events=[]
    if not now['date']:notices.append('Игровой год неизвестен: годовые даты ещё не рассчитаны.')
    elif profile.get('regional'):
        try:events=occurrences(profile['regional'],now['date'],from_ordinal(min(ordinal(now['date'],{})+90, date.max.toordinal()),{}))
        except CoverageError as exc:notices.append(str(exc))
    regional=profile.get('regional')
    if regional:regional=dict(regional,display_name=COUNTRIES.get(regional['country'],(regional['country'],))[0])
    return dict(current=now,events=events,notices=notices,regional=regional)
