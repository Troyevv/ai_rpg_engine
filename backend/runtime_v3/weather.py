"""Versioned, bounded environment projection. No device clock, randomness or writes.

Only explicitly configured geographic regions have weather. Fictional calendar
season names are not interpreted as terrestrial seasons. No future forecasts.
"""
from hashlib import sha256
from backend.runtime_v3.calendar import current_time, profile_of


def weather_at(state, location_id=None, minute=None):
    profile = state['meta'].get('weather')
    if not profile or not profile.get('enabled', True): return None
    now = state['meta']['world_time']
    minute = now if minute is None else minute
    if minute > now or minute < profile.get("since_minute",0): return None
    location_id = location_id or state['camera'].get('location_id')
    region_id = location_id
    visited = set()
    while region_id and region_id not in profile['regions']:
        if region_id in visited: return None
        visited.add(region_id)
        region_id = state['locations'].get(region_id, {}).get('parent_id')
    if not region_id: return None
    region = profile['regions'][region_id]
    date = current_time(state, minute)
    climate = region['climate']
    season = None
    if profile_of(state).get('system', 'gregorian') == 'gregorian' and date['date'] and region.get('hemisphere'):
        month = int(date['date'][5:7])
        if region['hemisphere'] == 'south': month = (month+5)%12+1
        season = ('winter' if month in (12,1,2) else 'spring' if month in (3,4,5) else 'summer' if month in (6,7,8) else 'autumn')
    # Day-sized weather systems, deterministic for the same canonical region/day.
    digest = sha256(f"1:{profile['seed']}:{region_id}:{minute//1440}".encode()).digest()
    cold = climate == 'polar' or climate == 'temperate' and season == 'winter'
    choices = (['snow','cloudy','clear','heavy_snow','fog','windy','cold_extreme'] if cold else
        ['clear','clear','windy','partly_cloudy','heat_extreme'] if climate == 'arid' else
        ['clear','partly_cloudy','cloudy','drizzle','rain','heavy_rain','thunderstorm','fog','windy'])
    condition = choices[digest[0] % len(choices)]
    baseline = -15 if climate == 'polar' else 29 if climate == 'tropical' else 30 if climate == 'arid' else {'winter':-4,'spring':12,'summer':23,'autumn':10}.get(season)
    temperature = None if baseline is None else baseline + digest[1]%9-4
    if condition == 'heat_extreme' and temperature is not None: temperature += 10
    if condition == 'cold_extreme' and temperature is not None: temperature -= 10
    if condition == 'rain' and temperature is not None and temperature <= 2: condition='sleet'
    if temperature is not None and profile.get('temperature_unit') == 'F': temperature=round(temperature*9/5+32)
    return dict(location_id=location_id, region_id=region_id, date=date['date'], condition=condition,
                temperature=temperature, unit=profile.get('temperature_unit','C'), season=season, forecast=False)
