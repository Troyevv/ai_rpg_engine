"""Bounded text context, with an explicitly approximate conservative token budget."""
import json
import math
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[2] / 'prompts'
TEMPLATE = (PROMPTS / 'chat_summary_template.md').read_text()
RP_PROMPT = (PROMPTS / 'chat_rp.md').read_text()
SUMMARY_PROMPT = (PROMPTS / 'chat_summary.md').read_text()


def estimate(value):
    # UTF-8/2 is deliberately conservative for mixed Cyrillic/Latin prose;
    # NOT a tokenizer or provider usage. Include JSON framing and 15% reserve.
    return math.ceil(len(json.dumps(value, ensure_ascii=False).encode()) / 2)


def budget(messages, config):
    tokens = estimate({'messages': messages, 'max_tokens': config['max_tokens'],
                       'temperature': config['temperature'], 'thinking': config['thinking']}) + 32
    margin = max(512, math.ceil(config['context_length'] * .15))
    available = config['context_length'] - config['max_tokens'] - margin
    return dict(estimated_tokens=tokens, available=available, output=config['max_tokens'],
                margin=margin, context_length=config['context_length'], fits=tokens <= available,
                ratio=round(tokens / max(1, available), 3), approximate=True)


def assemble(settings, memory, tail, messages, *, summary=False):
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
    if not summary and tail:
        result.append({'role': 'user', 'content': 'Уже произошедший конец сцены; не повторяй действия:\n' +
                       '\n\n'.join(m['role'] + ': ' + m['content'] for m in tail)})
    result.extend({'role': m['role'], 'content': m['content']} for m in messages)
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
