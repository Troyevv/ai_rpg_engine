"""Lossless structural import of the project's Markdown summary format."""
import re

SECTIONS = {
    'ГЛАВНОЕ СЕЙЧАС': 'scene', 'ЖАНР И ТОН': 'tone',
    'КЛЮЧЕВЫЕ NPC': 'characters', 'ЧТО ЗНАЮТ / ЧТО ТАЙНА': 'knowledge',
    'МИР': 'locations', 'ОСОБЕННЫЕ МОМЕНТЫ': 'rules',
}


def clean(value):
    return value.strip().strip('*').strip().rstrip(':').strip()


def subsections(text):
    matches = list(re.finditer(r'^#{2,6}\s+(.+)$', text, re.M))
    return [(clean(m[1]), text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip())
            for i, m in enumerate(matches)]


def parse_summary(markdown):
    if not markdown.strip():
        raise ValueError('Выжимка пуста.')
    sections = {}
    active = None
    for line in markdown.replace('\r\n', '\n').splitlines():
        heading = re.match(r'^#{1,6}\s+(.+)$', line)
        title = clean(heading[1]).upper() if heading else ''
        if title in SECTIONS:
            key = SECTIONS[title]
            if key in sections:
                raise ValueError(f'Раздел «{title}» повторяется.')
            active = key
            sections[key] = []
        elif active:
            sections[active].append(line)
    missing = [title for title, key in SECTIONS.items()
               if not ''.join(sections.get(key, [])).strip(' \n-')]
    if missing:
        raise ValueError('Не заполнены разделы: ' + ', '.join(missing))
    blocks = {key: '\n'.join(lines).strip() for key, lines in sections.items()}
    text = blocks['characters']
    markers = list(re.finditer(r'^(?:#{1,6}\s*)?(?:\*\*)?👤\s*(.+)$', text, re.M))
    if len(markers) != 8:
        raise ValueError(f'Ожидается 7 персонажей с маркером 👤, найдено: {len(markers)}.')
    characters = []
    for i, marker in enumerate(markers):
        name = clean(marker[1])
        body = text[marker.end():markers[i+1].start() if i+1 < len(markers) else len(text)].strip()
        fields = {}
        pattern = r'^[·•*\-]\s*(?:\*\*)?([^:\n]+):(?:\*\*)?\s*'
        found = list(re.finditer(pattern, body, re.M))
        for j, match in enumerate(found):
            fields[clean(match[1])] = body[match.end():found[j+1].start() if j+1 < len(found) else len(body)].strip().rstrip('-').strip()
        required = ['Статус', 'Внешность', 'Суть', 'Сейчас', 'Чего хочет']
        if any(not fields.get(key) for key in required):
            raise ValueError(f'У персонажа «{name}» не заполнены обязательные поля: ' + ', '.join(required))
        characters.append({'id': f'character_{i+1}', 'name': name, 'is_player': '(ГГ)' in name,
                           'text': body, 'fields': fields})
    if sum(c['is_player'] for c in characters) != 1 or not characters[0]['is_player']:
        raise ValueError('Первый персонаж должен быть единственным ГГ с отметкой (ГГ).')
    if len({c['name'].casefold() for c in characters}) != 8:
        raise ValueError('Имена персонажей повторяются.')
    relationships = [{'source_id': c['id'], 'target_name': key[len('Отношение к '):], 'text': value}
                     for c in characters for key, value in c['fields'].items()
                     if key.startswith('Отношение к ')]
    return {'schema_version': 1, 'sections': blocks, 'characters': characters,
            'relationships': relationships,
            'locations': [{'name': name, 'text': body} for name, body in subsections(blocks['locations'])],
            'knowledge': [{'name': name, 'text': body} for name, body in subsections(blocks['knowledge'])],
            'scene': blocks['scene'], 'story_notes': blocks['rules']}
