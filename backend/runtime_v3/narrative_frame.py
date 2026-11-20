"""The literary reply, its optional final physical scene and player-facing menu."""
import json
import re

# Keep the historical prefix for jobs whose original messages are replayed on retry.
_FRAME_PREFIX = 'JSON object: "scene": full literary prose first;'
RECORDED_FORMAT = (_FRAME_PREFIX + ' required "actions": exactly 6 distinct open choices in the story language, '
          'each {"text":"…"}. Current-scene actions and personal decisions need only text. Add "facts" '
          'with exact POV-known fact IDs only when relying on prior information. No secrets or predetermined outcomes. Optional "ending": '
          'location_id, present_ids (everyone physically there at the end, including arrivals and the player '
          'in actor mode), elapsed_minutes (actual duration). Omit unknown ending fields.')
FORMAT = 'JSON со сценой и вариантами'
AUTHOR_FORMAT = (FORMAT + '. Верни один объект, первым полем scene с полным художественным текстом, '
    'затем actions. Цель — шесть разных уместных продолжений. Предложения оставляют выбор игроку. '
    'В text дай короткое конкретное действие в инфинитиве на языке истории. Если герой говорит, '
    'добавь speech — одну живую дословную реплику без внешних кавычек, в его голосе, с учётом отношений '
    'и происходящего. Для молчаливого действия опусти speech. Предложи разные намерения, а не '
    'перефразировки одного ответа. Не объясняй игроку механику и не предрешай реакцию окружающих. '
    'В режиме наблюдателя предлагай направления сцены, не присваивая игроку речь персонажа. '
    'Используй только доступные POV сведения. Необязательный facts содержит ID известных этому POV фактов. '
    'Пример формы (подбери действия для своей сцены):\n'
    '{"scene":"За окном стемнело. Мёрфи отставила чашку.",'
    '"actions":[{"text":"Спросить Мёрфи об отце","speech":"Мёрф, а каким ты вообще считаешь папу?"},'
    '{"text":"Подойти к окну и посмотреть на улицу."},{"text":"Предложить чай","speech":"Ещё тёплый. Налить?"},'
    '{"text":"Достать семейный альбом."},{"text":"Попросить остаться","speech":"Посиди со мной ещё минутку."},'
    '{"text":"Выйти во двор подышать."}]}')
_DECODER = json.JSONDecoder()
_JSON_FENCE = re.compile(r'^\s*```json[ \t]*\r?\n', re.IGNORECASE)
_START = re.compile(r'^\s*\{\s*"scene"\s*:\s*"')
# Isolate a malformed flat object only at its own JSON array item boundary.
# Never search inside nested objects or rewrite its text or knowledge references.
_ACTION_ROW = re.compile(r'\{(?:[^{}"\\]|"(?:[^"\\]|\\.)*")*\}(?=\s*[,\]])')


def requested(messages):
    for msg in reversed(messages):
        content = msg.get('content', '')
        if content.startswith('Текущий ввод\n'):
            try:
                return json.loads(content.split('\n', 1)[1]).get('response_format', '').startswith((FORMAT, _FRAME_PREFIX, 'JSON: сначала "scene"'))
            except (ValueError, AttributeError):
                return False
    return False


def _complete_metadata(remainder):
    """Recover only fully decoded values after a complete scene string."""
    frame = {}
    rest = remainder.lstrip()
    try:
        if rest.startswith('}'):
            # Flash can close the scene object and send its menu as the next JSON object.
            # Accept only a complete actions envelope, never arbitrary trailing prose or endings.
            tail = rest[1:].strip()
            if tail.startswith('{'):
                menu = json.loads(tail)
                if isinstance(menu, dict) and set(menu) == {'actions'} and isinstance(menu['actions'], list):
                    return menu
            return frame
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
                    try:
                        action, end = _DECODER.raw_decode(rest)
                    except ValueError:
                        row = _ACTION_ROW.match(rest)
                        if not row:
                            raise
                        action, end = None, row.end()
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


_QUOTED_FRAME = re.compile(r'^\s*\{\s*«scene»\s*:\s*«')


def _json_delimiters(text):
    """Normalize a localized wire envelope, preserving quotation marks inside prose."""
    out = []
    depth = 0
    escaped = False
    ascii_string = False
    for char in text:
        if escaped:
            escaped = False
        elif char == '\\' and (depth or ascii_string):
            escaped = True
        elif char == '"' and not depth:
            ascii_string = not ascii_string
        elif char == '«' and not ascii_string:
            depth += 1
            if depth == 1:
                char = '"'
        elif char == '»' and depth:
            depth -= 1
            if depth == 0:
                char = '"'
        elif char == '"' and depth:
            char = '\\"'
        out.append(char)
    return ''.join(out)


def read(text, *, complete):
    """None means a recorded plain-text provider reply. Never stream JSON scaffolding."""
    # Some providers wrap the requested scene object in a Markdown code block.
    # Reserve the opening line while streaming. Keep other fenced prose verbatim.
    fence = _JSON_FENCE.match(text)
    if fence:
        body = text[fence.end():]
        if _START.match(body) or _QUOTED_FRAME.match(body):
            if complete:
                body, newline, closing = body.rstrip().rpartition('\n')
                if not newline or closing.strip() != '```':
                    return None
            text = body
        elif not complete and (not body.strip() or body.lstrip().startswith('{')):
            return '', {}
        else:
            return None
    elif not complete and '```json'.startswith(text.strip().lower()):
        return '', {}
    if _QUOTED_FRAME.match(text):
        text = _json_delimiters(text)
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
    for item in actions:
        if len(choices)==6:
            break
        if not isinstance(item, dict):
            continue
        text, refs = item.get('text'), item.get('facts', [])
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 800 or not isinstance(refs,list):
            continue
        if any(not isinstance(fid, str) or not pov or
               state['knowledge'].get(pov+':'+fid, {}).get('status') != 'known' for fid in refs):
            continue
        # The author owns both strings. Historical text-only entries remain literal.
        speech = item.get('speech', '')
        if not isinstance(speech, str) or len(text.strip()) + len(speech.strip()) > 800:
            continue
        key = tuple(' '.join(part.casefold().split()) for part in (text, speech))
        if key in seen:
            continue
        seen.add(key)
        choice = dict(action=text.strip(), speech=speech.strip())
        if state['meta'].get('interaction_focus') == 'call':
            choice['interaction_channel'] = 'call'
        choices.append(choice)
    source = ('actions' if isinstance(frame.get('actions'), list) else
              'invalid_actions' if 'actions' in frame else 'missing_actions')
    return choices, menu_diagnostics(len(actions), len(choices), source)


def menu_diagnostics(received, available, source=None):
    return [] if received==available==6 else [dict(section='choices', code='narrative_menu_count',
        action='show_available', received=received, available=available,
        source=source or ('legacy_suggestions' if received else 'unstructured_reply'))]
