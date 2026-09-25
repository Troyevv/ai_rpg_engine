"""Conservative player-source verification, never psychological inference.

Arbitrary paraphrase entailment cannot be proven without another model. Accept
literal explicit declarations and a small set of lossless surface forms; reject
ambiguous claims for repair/omission. This code never generates or rewrites values.
"""
import re
import unicodedata

PLAYER_SOURCE_DESCRIPTION = ('Для controlled_actor только явное утверждение в player_input текущего хода, '
    'подтверждённое player_evidence этого поля. Narrative и жесты не являются основанием. '
    'Отсутствие поля = NO CHANGE; сохраняй неизменённые элементы списков. Для NPC — обычное evidence.')

PLAYER_FIELDS = ('goals', 'intentions', 'emotion', 'obligations')
PLAYER_AGENCY_CONTRACT = '''Для controlled_actor goals / intentions / emotion разрешены только из явного player_input текущего хода, никогда из completed_narrative, карточки, жестов, отношений или психологических выводов. Obligations требуют явного обещания/обязательства самого игрока. Если источник неясен — ОПУСТИ поле. Отсутствие поля = NO CHANGE. Сохраняй прежние элементы списков, если игрок явно не отменяет/заменяет их. Для каждого изменённого поля передай player_evidence: emotion — точная цитата-строка из player_input, goals/intentions/obligations — список точных цитат (по одной на каждый новый элемент, в порядке новых элементов). Цитируй полное явное утверждение игрока, не вырезай слова из отрицаний, вопросов, условий или речи NPC. Значение держи максимально дословным: произвольная перефразировка не является доказательством. Например «Я злюсь на неё» подтверждает emotion «злится», а «Я сжимаю кулак» — нет. «Решаю завтра поговорить с Людой» подтверждает intentions [«поговорить с Людой завтра»]. Не переноси player_evidence в WorldState. Для NPC действуют обычные narrative evidence.'''

# Explicit speech acts, anchored at the start of the player's own statement.
PATTERNS = {
    'goals': re.compile(r'^(?:теперь\s+)?(?:моя\s+(?:(?:новая|главная)\s+)*цель|мои\s+(?:новые\s+)?цели)\s*(?:—|–|-|:|это)\s*(.+)$', re.I),
    'intentions': re.compile(r'^(?:я\s+)?(?:решаю|решил(?:а)?|намерен(?:а)?|планирую|собираюсь)\s+(.+)$', re.I),
    'obligations': re.compile(r'^(?:я\s+)?(?:обещаю|обязуюсь)\s+(.+)$', re.I),
}
# Only explicit emotion predicates, not gestures, tone, appearance or situations.
EMOTIONS = {
    'злюсь': 'злится', 'ревную': 'ревнует', 'боюсь': 'боится',
    'тревожусь': 'тревожится', 'грущу': 'грустит', 'радуюсь': 'радуется',
    'стыжусь': 'стыдится', 'смущаюсь': 'смущается', 'ненавижу': 'ненавидит',
}
CLEAR = {
    'goals': {'отказываюсь от всех прежних целей', 'у меня больше нет целей'},
    'intentions': {'отказываюсь от всех прежних намерений', 'у меня больше нет намерений'},
    'obligations': {'отменяю все свои обязательства'},
}


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().replace('ё', 'е').split()).strip(' .!')


def declarations(player_input):
    # Mask complete quoted spans BEFORE splitting sentences, including multiline
    # dialogue. Otherwise the middle sentence in an NPC quote looks first-person.
    masked = re.sub(r'«[^»]*»|“[^”]*”|"[^"]*"', ' QUOTED_SPEECH ', player_input, flags=re.S)
    return [part.strip() for part in re.split(r'[.!;\n]+', masked) if part.strip()
            and not any(mark in part for mark in ('?', '«', '»', '"', '“', '”', 'QUOTED_SPEECH'))
            and not re.search(r'\b(?:если|бы|якобы|возможно|кажется|будто)\b', part, re.I)]


def literal_forms(body):
    forms = {normalized(body)}
    # A leading time adverb may move to the end without changing its scope.
    match = re.fullmatch(r'(завтра|сегодня|послезавтра)\s+(.+)', normalized(body))
    if match and not re.search(r'[,;:]|\b(?:но|если|не|или)\b', match[2]):
        forms.add(match[2] + ' ' + match[1])
    return forms


def claim_matches(field, value, quote):
    """The quote must already be verified as a WHOLE current-input statement."""
    claim, source = normalized(value), normalized(quote)
    if not claim:
        return False
    pattern = PATTERNS.get(field)
    if pattern:
        match = pattern.fullmatch(source)
        if match:
            # Keep all negation, object and scope words in the literal body.
            forms = literal_forms(match[1]) | {source}
            if field == 'obligations':
                # A narrow explicit arrival promise; do not reinterpret general
                # promises or change the destination of an existing clause.
                arrival = re.fullmatch(r'([а-яa-z]+) приехать (сегодня|завтра|послезавтра) к (\w+|\d{2}:\d{2})', match[1])
                if arrival:
                    hours = {'часу':'01:00','двум':'02:00','трем':'03:00','четырем':'04:00',
                        'пяти':'05:00','шести':'06:00','семи':'07:00','восьми':'08:00',
                        'девяти':'09:00','десяти':'10:00','одиннадцати':'11:00','двенадцати':'12:00'}
                    clock = hours.get(arrival[3], arrival[3])
                    forms.add(f'приехать к {arrival[1]} {arrival[2]} к {clock}')
            return claim in forms
        return False
    match = re.fullmatch(r'я (\w+)(.*)', source)
    if match and match[1] in EMOTIONS:
        tail = match[2]
        full = EMOTIONS[match[1]] + tail
        forms = {source, full}
        # A simple complement can be omitted; never drop negation/conditions or
        # invent a different target. Only an explicit leading emotion assertion
        # can survive a following concrete action; gestures alone never qualify.
        if not tail or re.fullmatch(r' (?:на|из-за|за) [\w -]+', tail) and not re.search(r'\b(?:не|но|если|или|и)\b', tail):
            forms.add(EMOTIONS[match[1]])
        if re.fullmatch(r' и (?:я )?(?:сжимаю|отвожу|подхожу|смотрю|ухожу|закрываю|открываю) [\w -]+', tail):
            forms.add(EMOTIONS[match[1]])
        return claim in forms
    # Open vocabulary remains possible without semantic guessing: retain exactly
    # the feeling explicitly named by the player.
    match = re.fullmatch(r'я (?:чувствую|испытываю) (.+)', source)
    return bool(match and claim in {source, match[1]})


def supported_player_field(field, value, old_value, player_input, evidence):
    """No changes without explicit source; list omission never means deletion."""
    if value == old_value:
        return True
    statements = declarations(player_input)
    valid_quotes = {normalized(s) for s in statements}
    quotes = evidence if isinstance(evidence, list) else [evidence]
    if not quotes or any(not isinstance(q, str) or normalized(q) not in valid_quotes for q in quotes):
        return False
    if field == 'emotion':
        return len(quotes) == 1 and claim_matches(field, value, quotes[0])
    old = old_value or []
    removed = any(item not in value for item in old)
    if not value:
        return any(normalized(q).removeprefix('я ') in CLEAR[field] for q in quotes)
    # Explicit replacement of goals is different from adding one new intention.
    replacement = field == 'goals' and any(re.match(r'^(?:теперь моя|моя новая|мои новые)\b', normalized(q)) for q in quotes)
    if removed and not replacement:
        return False
    added = [item for item in value if item not in old]
    return bool(added) and len(quotes) == len(added) and all(
        claim_matches(field, item, quote) for item, quote in zip(added, quotes))
