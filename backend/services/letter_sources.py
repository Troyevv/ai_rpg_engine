"""Complete authored Markdown letter blocks in the ordinary Narrative stream.

Only explicit top-level fences are canonical text sources; no prose guessing.
The RemoteEvent remains the canonical record after Extraction binds a source.
"""
import json
from markdown_it import MarkdownIt
from backend.services.world_delta_errors import StructuralDeltaError


def enabled(state):
    return any(state['meta']['communication'].get(k) for k in ('letter', 'courier', 'telegram')) or any(e['channel'] in ('LETTER','COURIER_LETTER','TELEGRAM') for e in state.get('remote_events',{}).values())


CONTRACT = ('LETTER AUTHORING CONTRACT: Write ordinary streaming Markdown prose. '
    'You may show NPC letter contents to the reader, even when the controlled actor does not know them. '
    'When an NPC actually writes/sends a new historical letter, include its COMPLETE literal text once '
    'in a top-level fenced Markdown block: opening line ```letter, full text including greeting/signature, closing line ```. '
    'The surrounding scene may describe writing without quoting the letter again. '
    'This optional block is the authored source, not JSON or a tool call. No block is needed on ordinary turns. '
    'Use one block per new letter, in send order. Never put a quotation of an old letter in a letter fence. '
    'Never write voluntary letters for the controlled actor; the player supplies that text. '
    'Reader visibility grants NO character Knowledge. Sending and delivery are not reading. '
    'Only Runtime determines delivery. Replies are optional. SMS/chat and CallScene keep their formats.')


def parse(narrative):
    """Read explicit Markdown syntax, never infer boundaries in literary prose."""
    lines = narrative.splitlines(keepends=True)
    result = []
    for token in MarkdownIt('commonmark').parse(narrative):
        if token.type != 'fence' or token.info.strip() != 'letter':
            continue
        start, end = token.map
        if (token.level != 0 or end <= start + 1
                or lines[start].strip() != token.markup + 'letter'
                or lines[end - 1].strip() != token.markup):
            raise StructuralDeltaError('Незавершённый блок полного текста письма.', 'letter_source_incomplete', repairable=False)
        content = ''.join(lines[start + 1:end - 1])
        # The newline before the closing fence is Markdown syntax.
        if content.endswith('\r\n'): content = content[:-2]
        elif content.endswith('\n'): content = content[:-1]
        if not content.strip() or len(content) > 4000 or len(result) >= 16:
            raise StructuralDeltaError('Недопустимый полный текст письма.', 'letter_source_invalid', repairable=False)
        result.append(dict(id=f'letter-{len(result)+1}', type='letter', content=content))
    return result


def metadata(artifacts):
    return [{k:v for k,v in a.items() if k != 'content'} for a in artifacts]


def author_context(state):
    """Bounded GM input, not a public projection or Character Knowledge grant."""
    from backend.runtime_v3.remote_models import HISTORICAL_CHANNELS
    controlled = state['camera']['controlled_actor_id']
    rows = []
    for e in sorted(state['remote_events'].values(), key=lambda e: (-e['world_time'], e['id'])):
        if e['channel'] not in HISTORICAL_CHANNELS:
            continue
        row = {k: e[k] for k in ('id','channel','sender_id','recipient_ids','status','read_by','delivered_to')}
        if controlled == e['sender_id'] or controlled in e['read_by'] or any(a != controlled for a in e['delivered_to']):
            row['content'] = e['content']
        rows.append(row)
        if len(rows) == 6: break
    return {'role':'system', 'content':CONTRACT + '\nGM-only correspondence: ' + json.dumps(rows,ensure_ascii=False) +
        '\nNPCs may explicitly read delivered letters, or leave them unread. An optional response must be a new authored letter block. '
        'Reader visibility is not character Knowledge; never let a character act on an unread letter. Reference existing letter IDs when depicting reads; never duplicate sends.'}


def extraction_context(artifacts):
    return {'role':'system', 'content':'Complete author-created letter blocks (numbered in source order): '+json.dumps(metadata(artifacts),ensure_ascii=False)+
        '. Bind every new send using remote_events.artifact_id, channel, sender_id, recipient_ids; omit content. '
        'Runtime copies the complete source block, never an Extractor paraphrase. Missing full text cannot be invented. '
        'Reader visibility is not character Knowledge. For an established NPC read use existing_event_id and reader_id. '
        'Only delivered letters can be read. Never invent controlled actor sending or reading.'}


def generate_result(generate, stage, messages, limit, temperature, state, **kwargs):
    if enabled(state):
        from copy import copy
        messages = copy(messages)
        messages.append(author_context(state))
    narrative = ''.join(generate(stage, messages, limit, temperature, **kwargs))
    return narrative, parse(narrative) if enabled(state) else []
