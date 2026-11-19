"""The literary reply, its optional final physical scene and player-facing menu."""
import json
import re

FORMAT = ('JSON: сначала "scene" (полный текст сцены строкой), затем "actions" (ровно шесть '
          'разных конкретных продолжений без предрешённого результата, каждое {"text":"…","facts":[]}). '
          'Для текущей сцены facts пуст, для прежних сведений укажи ID известных POV фактов. '
          'Не раскрывай скрытое. Необязательное "ending": {"location_id":"ID","present_ids":["ID"],'
          '"elapsed_minutes":0}. Только достигнутое место и физически присутствующие, включая героя. '
          'Если место или время не определены, опусти соответствующие данные.')
_DECODER = json.JSONDecoder()
_START = re.compile(r'^\s*\{\s*"scene"\s*:\s*"')


def requested(messages):
    for msg in reversed(messages):
        content = msg.get('content', '')
        if content.startswith('Текущий ввод\n'):
            try:
                return json.loads(content.split('\n', 1)[1]).get('response_format', '').startswith(FORMAT)
            except (ValueError, AttributeError):
                return False
    return False


def _complete_metadata(remainder):
    """Recover only fully decoded values after a complete scene string."""
    frame = {}
    rest = remainder.lstrip()
    try:
        while rest.startswith(','):
            key, end = _DECODER.raw_decode(rest[1:].lstrip())
            rest = rest[1:].lstrip()[end:].lstrip()
            if not rest.startswith(':') or not isinstance(key, str):
                break
            rest = rest[1:].lstrip()
            if key == 'actions' and rest.startswith('['):
                actions = frame['actions'] = []
                rest = rest[1:].lstrip()
                while rest and not rest.startswith(']') and len(actions) < 6:
                    action, end = _DECODER.raw_decode(rest)
                    actions.append(action)
                    rest = rest[end:].lstrip()
                    if not rest.startswith(','):
                        break
                    rest = rest[1:].lstrip()
                if not rest.startswith(']'):
                    break
                rest = rest[1:].lstrip()
            else:
                value, end = _DECODER.raw_decode(rest)
                if key == 'ending':
                    frame[key] = value
                rest = rest[end:].lstrip()
    except ValueError:
        pass
    return frame


def read(text, *, complete):
    """None means a recorded plain-text provider reply. Never stream JSON scaffolding."""
    if complete:
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get('scene'), str):
            return obj['scene'], {k:obj[k] for k in ('ending','actions') if k in obj}
    match = _START.match(text)
    if match:
        start = match.end()-1
        try:
            prose, end = _DECODER.raw_decode(text, start)
            if complete:
                return prose, _complete_metadata(text[end:])
        except ValueError:
            # While streaming only the terminal escape may be incomplete.
            prefix = text[start:]
            prefix = re.sub(r'(?<!\\)((?:\\\\)*)\\u[0-9a-fA-F]{0,3}$', r'\1', prefix)
            if (len(prefix)-len(prefix.rstrip('\\'))) % 2:
                prefix = prefix[:-1]
            try:
                prose = json.loads(prefix+'"')
            except ValueError:
                return (text, {}) if complete else ('', {})
        if prose and 0xd800 <= ord(prose[-1]) <= 0xdbff:
            prose = prose[:-1]
        return prose, {}
    if (complete and isinstance(obj, dict)) or (not complete and (not text.strip() or text.lstrip().startswith('{'))):
        return '', {}
    return None


def scene_fields(frame):
    ending = frame.get('ending')
    if not isinstance(ending, dict):
        return {}
    scene = {}
    if 'elapsed_minutes' in ending:
        scene['elapsed_minutes'] = ending['elapsed_minutes']
    if 'location_id' in ending or 'present_ids' in ending:
        scene['ending'] = {key:ending[key] for key in ('location_id','present_ids') if key in ending}
    return scene


def menu(frame, state):
    """Scope retained actions to the same viewpoint and its declared facts."""
    actions = frame.get('actions')
    actions = actions if isinstance(actions, list) else []
    camera = state['camera']
    pov = camera.get('pov_actor_id') or camera.get('controlled_actor_id')
    seen, choices = set(), []
    for item in actions[:6]:
        if not isinstance(item, dict):
            continue
        text, refs = item.get('text'), item.get('facts')
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 800 or not isinstance(refs,list):
            continue
        if any(not isinstance(fid, str) or not pov or
               state['knowledge'].get(pov+':'+fid, {}).get('status') != 'known' for fid in refs):
            continue
        key = ' '.join(text.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        choices.append(dict(action=text.strip(), speech=''))
    return choices, menu_diagnostics(len(actions), len(choices))


def menu_diagnostics(received, available):
    return [] if received==available==6 else [dict(section='choices', code='narrative_menu_count',
        action='show_available', received=received, available=available)]
