import re


def scene_metadata(state):
    if isinstance(state.get('scene_meta'), dict):
        meta = state['scene_meta']
        known = {c['id'] for c in state['characters']}
        return {'time': str(meta.get('time', '')), 'location': str(meta.get('location', '')),
                'present_ids': [cid for cid in meta.get('present_ids', []) if cid in known]}
    text = state.get('scene', '')
    values = {}
    for key, labels in [('time', 'Время'), ('location', 'Место|Локация'), ('nearby', 'Рядом|Присутствуют')]:
        match = re.search(r'(?mi)^\s*(?:[-*·]\s*)?(?:\*\*)?(?:' + labels + r')\s*:(?:\*\*)?\s*([^\n]+)', text)
        values[key] = match[1].strip() if match else ''
    if not values['time']:
        times = set(re.findall(r'\b(?:[01]?\d|2[0-3]):[0-5]\d\b', text))
        if len(times) == 1:
            values['time'] = next(iter(times))
            weekday=re.search(r'(?i)\b(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье|пн|вт|ср|чт|пт|сб|вс)\b',text)
            if weekday:values['time']=weekday[0]+' '+values['time']
    names = {n.strip().casefold() for n in re.split(r'[,;]', values['nearby'])}
    present = [c['id'] for c in state['characters'] if re.sub(r'\s*\(ГГ\)', '', c['name']).strip().casefold() in names or c['name'].casefold() in names]
    return {'time': values['time'], 'location': values['location'], 'present_ids': present}

