"""Chat reply/summary policy over shared provider metadata."""
from backend.services.model_capabilities import DEEPSEEK, discover


def resolve(config, credentials, stage='reply'):
    value = dict(config)
    # Missing flags mean a legacy explicit configuration, not an automatic migration.
    auto = value.get('auto_context', False)
    known = discover(value['provider'], value['model'], credentials) if value['model'].strip() else {}
    limit = known.get('context_length')
    if auto and not limit:
        raise ValueError('Размер контекста неизвестен. В дополнительных настройках отключите автоматический контекст и укажите проверенное окно модели.')
    if auto: value['context_length'] = limit
    elif limit: value['context_length'] = min(value['context_length'], limit)
    if value.get('auto_output', False):
        value['max_tokens'] = min(4096 if stage=='reply' else 16384, value['context_length']//3)
    if known.get('max_output'):
        value['max_tokens'] = min(value['max_tokens'], known['max_output'])
    return value


def settings(value, credentials):
    return dict(value, **{stage:resolve(value[stage], credentials, stage) for stage in ('reply','summary')})
