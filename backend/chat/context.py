"""Bounded text context, with an explicitly approximate conservative token budget."""
import json
import math
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[2] / 'prompts'
TEMPLATE = (PROMPTS / 'chat_summary_template.md').read_text()
RP_PROMPT = (PROMPTS / 'chat_rp.md').read_text()
INITIAL_PROMPT = (PROMPTS / 'chat_initial.md').read_text()
OPENING_PROMPT = (PROMPTS / 'chat_opening.md').read_text()
SUMMARY_PROMPT = (PROMPTS / 'chat_summary.md').read_text()


def estimate(value):
    # Byte-level upper estimate for text, including JSON framing; unlike bytes/2
    # this also budgets punctuation, emoji and poorly compressible input safely.
    # NOT a tokenizer or provider usage. Keep an additional protocol/safety reserve.
    return len(json.dumps(value, ensure_ascii=False).encode())


def budget(messages, config):
    from backend.chat.capabilities import DEEPSEEK
    config = dict(config)
    if config['provider']=='deepseek' and config['model'] in DEEPSEEK:
        config['context_length'] = min(config['context_length'], 1000000)
    from backend.chat.tokenization import count
    tokens, method = count({'messages': messages, 'max_tokens': config['max_tokens'],
                           'temperature': config['temperature'], 'thinking': config['thinking']},config)
    tokens += 32
    margin = max(512, math.ceil(config['context_length'] * .15))
    available = config['context_length'] - config['max_tokens'] - margin
    return dict(estimated_tokens=tokens, available=available, output=config['max_tokens'],
                margin=margin, context_length=config['context_length'], fits=tokens <= available,
                ratio=round(tokens / max(1, available), 3), approximate=True, token_method=method)


def assemble(settings, memory, tail, messages, *, summary=False, bookmarks=()):
    if summary:
        system = SUMMARY_PROMPT + '\n\nШаблон:\n' + TEMPLATE
        system += f"\nЦелевой бюджет выжимки: {settings['summary_target']} токенов (оценка)."
        # Author rules are explicit instructions, memory remains a user document.
        system += '\nАвторские правила RP:\n' + settings['prompt']
    else:
        system = settings['prompt']
    system += '\nЯзык игры: ' + settings['language']
    result = [{'role': 'system', 'content': system},
              {'role': 'user', 'content': 'Авторская память (справочные данные, возможны спойлеры):\n' + memory}]
    marked = {item['message_id']: item for item in bookmarks} if summary else {}
    if marked:
        system_rules = ('\nЗакладки — приоритетные свидетельства, а не обязательные квесты. '
                        'Утверждённая память и явные авторские исправления имеют приоритет перед старой цитатой. '
                        'Заметка автора — пояснение, не доказательство события без текста сообщения. '
                        'Предложенные в цитате варианты действий не совершены: учитывай только реально сыгранное. '
                        'Не переноси авторские тайны в знания персонажей.')
        result[0]['content'] += system_rules
        current_ids = {m.get('id') for m in messages}
        evidence = []
        for item in bookmarks:
            source = dict(message_id=item['message_id'], seq=item['seq'], role=item['role'],
                          priority=item['priority'], author_note=item['note'])
            if item['message_id'] in current_ids:
                source['source'] = 'Полный текст ниже, в помеченном сообщении переписки.'
            else:
                source['quoted_message'] = item['content']
            evidence.append(source)
        result.append({'role':'user','content':'Закладки активной ветки, выбранные автором для этого обновления:\n'+
                       json.dumps(evidence,ensure_ascii=False)})
    if not summary and tail:
        result.append({'role': 'user', 'content': 'Уже произошедший конец сцены; не повторяй действия:\n' +
                       '\n\n'.join(m['role'] + ': ' + m['content'] for m in tail)})
    result.extend({'role': m['role'], 'content':
                   (f"[Источник закладки: сообщение №{m['seq']}, id={m['id']}]\n" if m.get('id') in marked else '')+m['content']}
                  for m in messages)
    if summary:
        result.append({'role': 'user', 'content': 'Подготовь полный обновлённый черновик выжимки.'})
    return result


def require_fit(messages, config, reserve=0):
    value = budget(messages, config)
    if value['estimated_tokens'] + reserve > value['available']:
        raise ValueError('Контекст не помещается (консервативная оценка). Текст сохранён в редакторе. '
                         'Сократите память/ввод или выберите совместимую модель и размер окна; '
                         'история не обрезана и вызов не отправлен.')
    return value
