"""Safe Markdown rendering with unambiguous, session-preserving NPC links."""
from html import escape
import re
from markdown_it import MarkdownIt
from markdown_it.token import Token


def character_aliases(characters):
    candidates = {}
    for character in characters:
        name = re.sub(r'\s*\(ГГ\)\s*', '', character['name']).strip()
        aliases = [name, *character.get('aliases', [])]
        first_name = name.split()[0] if name else ''
        if first_name:
            aliases.append(first_name)
        aliases.extend(re.findall(r'«([^»]+)»', name))
        for alias in aliases:
            alias = alias.strip()
            if alias:
                candidates.setdefault(alias.casefold(), set()).add(character['id'])
    # Shared first names never pick an arbitrary NPC.
    return {alias: next(iter(ids)) for alias, ids in candidates.items() if len(ids) == 1}


def linked_markdown(markdown, characters):
    aliases = character_aliases(characters)
    parser = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable('table')
    tokens = parser.parse(markdown)
    if not aliases:
        return parser.renderer.render(tokens, parser.options, {})
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r')(?!\w)', re.I)
    for token in tokens:
        if token.type != 'inline' or not token.children:
            continue
        children, link_depth = [], 0
        for child in token.children:
            if child.type == 'link_open':
                link_depth += 1
            if child.type != 'text' or link_depth:
                children.append(child)
            else:
                start = 0
                for match in pattern.finditer(child.content):
                    plain = Token('text', '', 0)
                    plain.content = child.content[start:match.start()]
                    children.append(plain)
                    button = Token('html_inline', '', 0)
                    character_id = aliases[match[0].casefold()]
                    button.content = (f'<button type="button" class="npc-link" data-character-id="{escape(character_id, quote=True)}" '
                                      f'aria-label="Открыть карточку: {escape(match[0], quote=True)}">{escape(match[0])}</button>')
                    children.append(button)
                    start = match.end()
                tail = Token('text', '', 0)
                tail.content = child.content[start:]
                children.append(tail)
            if child.type == 'link_close':
                link_depth -= 1
        token.children = children
    return parser.renderer.render(tokens, parser.options, {})
