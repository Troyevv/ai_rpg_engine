"""Read-only structural views of approved Markdown, never a second world model.

Recognize explicit template labels / CommonMark headings and source spans only.
Unknown layouts remain editable source. No inferred identities or world events.
"""
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
import re

from markdown_it import MarkdownIt

PARSER = MarkdownIt('commonmark', {'html': False})
SECTIONS = ('ГЛАВНОЕ СЕЙЧАС','ЖАНР И ТОН','ГЛАВНЫЙ ГЕРОЙ','КЛЮЧЕВЫЕ NPC',
            'ОТНОШЕНИЯ','ЧТО ЗНАЮТ / ЧТО ТАЙНА','МИР','ЛОКАЦИИ',
            'АКТИВНЫЕ СОБЫТИЯ И ОБЯЗАТЕЛЬСТВА','НЕЗАКРЫТЫЕ ЛИНИИ','ХРОНОЛОГИЯ',
            'ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ')
GROUPS = ('Текущее состояние','Связи','Знания','Тайны','Биография')
FIELDS = {'возраст','статус','внешность','характер','манера речи','голос','занятие',
          'место проживания','финансы','важные вещи / имущество','физическое состояние',
          'значимые привычки','значимые связи','где находится','чем занят','актуальные обязательства',
          'ближайшие планы','незакрытые проблемы','привычки / особенности','слабости','сейчас',
          'чего хочет','цели','текущие намерения','текущие проблемы','обязательства / обещания',
          'что ожидает от гг','знает','подозревает','ошибочно считает','не знает','тайны','прошлое'}


def plain(value):
    tokens = PARSER.parseInline(value)[0].children or []
    return ''.join('\n' if t.type in ('softbreak','hardbreak') else t.content
                   for t in tokens if t.type not in ('image','html_inline')).strip()


def structure(text):
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    tokens = PARSER.parse(text)
    allowed, headings, excluded = set(), {}, set()
    for i, token in enumerate(tokens):
        if token.map and token.type in ('fence','code_block','blockquote_open','html_block'):
            excluded.update(range(*token.map))
        if token.map and token.level==0 and token.type in ('paragraph_open','heading_open'):
            allowed.update(range(*token.map))
        if token.type=='heading_open' and token.level==0 and token.map:
            headings[token.map[0]] = (plain(tokens[i+1].content),int(token.tag[1]))
    entries = []
    for n,line in enumerate(lines):
        if n in excluded: continue
        label,level = headings.get(n,(plain(line.strip()),0))
        entries.append(dict(line=n,start=offsets[n],label=label,level=level,top=n in allowed))
    sections = []
    for entry in entries:
        if entry['top'] and entry['label'].upper() in SECTIONS:
            sections.append(dict(title=entry['label'].upper(),start=entry['start'],level=entry['level']))
    for i,s in enumerate(sections):
        s['end'] = sections[i+1]['start'] if i+1<len(sections) else len(text)
        s['text'] = text[s['start']:s['end']]
    return entries,sections


@lru_cache(maxsize=8)
def characters(text):
    entries,sections = structure(text)
    cards = []
    for section in sections:
        if section['title'] not in ('ГЛАВНЫЙ ГЕРОЙ','КЛЮЧЕВЫЕ NPC'): continue
        candidates = []
        for e in entries:
            if not e['top'] or not section['start']<e['start']<section['end']: continue
            label = e['label']; emoji = label.startswith('👤')
            heading = e['level']>section['level'] and e['level']>0
            if not (emoji or heading) or label.casefold() in {g.casefold() for g in GROUPS}: continue
            # Colon-bearing headings are field labels, not new people.
            if not emoji and (':' in label or label.upper() in SECTIONS or label.casefold() in FIELDS): continue
            name = label.removeprefix('👤').strip()
            if not name or (name.startswith('[') and name.endswith(']')): continue
            candidates.append(dict(name=name,start=e['start'],level=e['level'],explicit=emoji))
        # Only direct child headings identify cards. Deeper headings belong to
        # that card, and are retained in its original source.
        if candidates:
            if any(c['explicit'] for c in candidates): candidates=[c for c in candidates if c['explicit']]
            rank = min((c['level'] for c in candidates if c['level']),default=0)
            candidates = [c for c in candidates if not c['level'] or c['level']==rank]
        for i,c in enumerate(candidates):
            end = candidates[i+1]['start'] if i+1<len(candidates) else section['end']
            source = text[c['start']:end]
            # Presentation groups use explicit source labels only. Keep every
            # byte in each group, including unknown/multiline fields; never
            # reconstruct the approved document from extracted values.
            boundaries=[dict(name='Описание',start=c['start'],content_start=c['start'])]
            for e in entries:
                if c['start']<e['start']<end and e['top'] and e['label'].casefold() in {g.casefold() for g in GROUPS}:
                    newline=text.find('\n',e['start'],end)
                    boundaries.append(dict(name=e['label'],start=e['start'],content_start=newline+1 if newline!=-1 else end))
            blocks=[dict(title=g['name'],text=text[g['content_start']:boundaries[n+1]['start'] if n+1<len(boundaries) else end])
                    for n,g in enumerate(boundaries)]
            group='Описание';fields=[]
            for e in entries:
                if not c['start']<e['start']<end: continue
                value = plain(re.sub(r'^[·•*+\-]\s+', '',e['label']).strip())
                if value.casefold() in {g.casefold() for g in GROUPS}: group=value;continue
                label,sep,body = value.partition(':')
                if sep and (label.casefold() in FIELDS or label.casefold().startswith('отношение к ')):
                    fields.append(dict(group=group,label=label,value=body.strip() or 'Не установлено'))
            cards.append(dict(key=f"character-{c['start']}",name=c['name'],kind='hero' if section['title']=='ГЛАВНЫЙ ГЕРОЙ' else 'npc',
                              start=c['start'],end=end,text=source,fields=fields,blocks=blocks))
    # A raw section remains available even when only some people were recognized.
    sources = [dict(key=f"section-{s['start']}",name=s['title'],kind='source',start=s['start'],end=s['end'],text=s['text'],fields=[])
               for s in sections if s['title'] in ('ГЛАВНЫЙ ГЕРОЙ','КЛЮЧЕВЫЕ NPC','ОТНОШЕНИЯ','ЧТО ЗНАЮТ / ЧТО ТАЙНА')]
    if not sources:
        sources=[dict(key='document',name='Исходная выжимка',kind='source',start=0,end=len(text),text=text,fields=[])]
    return dict(cards=cards,sources=sources)


def character(text,key):
    view=characters(text)
    for item in view['cards']+view['sources']:
        if item['key']==key: return item
    raise ValueError('Раздел не найден в этой версии памяти. Загрузите актуальную выжимку.')


def patch_character(text,key,replacement):
    item=character(text,key)
    if not replacement.strip(): raise ValueError('Раздел не может быть пустым. Удалите его явно в полном редакторе.')
    if item['end']<len(text) and not replacement.endswith(('\n','\r')): replacement+='\n'
    result=text[:item['start']]+replacement+text[item['end']:]
    if len(result)>500000: raise ValueError('Выжимка превышает допустимый размер 500 000 символов.')
    return result


def text_diff(before,after):
    old,new=before.splitlines(keepends=True),after.splitlines(keepends=True)
    hunks=[]
    for group in SequenceMatcher(None,old,new,autojunk=True).get_grouped_opcodes(3):
        lines=[]
        for tag,a,b,c,d in group:
            if tag in ('equal','delete','replace'):
                lines.extend(dict(kind='context' if tag=='equal' else 'removed',text=line,old_line=a+i+1,
                                  new_line=c+i+1 if tag=='equal' else None) for i,line in enumerate(old[a:b]))
            if tag in ('insert','replace'):
                lines.extend(dict(kind='added',text=line,old_line=None,new_line=c+i+1) for i,line in enumerate(new[c:d]))
        hunks.append(dict(old_start=group[0][1]+1,new_start=group[0][3]+1,lines=lines))
    return hunks


def changes(before,after):
    _,old=structure(before);_,new=structure(after)
    # Exact unique section names only. Duplicate / unstructured labels are not
    # matched by similarity or interpreted as renamed identities.
    counts_old=Counter(s['title'] for s in old);counts_new=Counter(s['title'] for s in new)
    labels=list(dict.fromkeys([s['title'] for s in old+new]))
    groups=[]
    for label in labels:
        if counts_old[label]>1 or counts_new[label]>1: continue
        a=next((s['text'] for s in old if s['title']==label),'')
        b=next((s['text'] for s in new if s['title']==label),'')
        if a!=b: groups.append(dict(title=label,kind='added' if not a else 'removed' if not b else 'changed',before=a,after=b))
    return dict(groups=groups,hunks=text_diff(before,after),changed=before!=after,
                interpretation='Точные изменения текста. Причины, события и изменение знаний требуют авторской проверки.')
