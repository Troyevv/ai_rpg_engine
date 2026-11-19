"""Free metadata only. No probing completions and no guessed model/tokenizer identity."""
import os
import llm

# Official API table, checked 2026-11-17. Decimal 1M is a conservative floor.
SOURCE = 'https://api-docs.deepseek.com/quick_start/pricing/'
DEEPSEEK = {'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp', 'deepseek-v4-pro'}


def positive(value):
    return value if type(value) is int and 2048 <= value <= 2097152 else None


def discover(provider, model, credentials):
    if provider == 'deepseek':
        return dict(context_length=1000000, max_output=384000, source=SOURCE, checked='2026-11-17') if model in DEEPSEEK else dict(context_length=None, source='Модель отсутствует в проверенной таблице DeepSeek')
    try:
        if provider == 'local':
            limits = []
            for item in llm.get_models_info().get('models', []):
                for instance in item.get('loaded_instances', []):
                    if model in (item.get('key'), item.get('id'), instance.get('id')):
                        limit = positive(instance.get('config', {}).get('context_length'))
                        if not limit: return dict(context_length=None, source='Нет окна загруженного экземпляра LM Studio')
                        limits.append(limit)
            return dict(context_length=min(limits) if limits else None, source='LM Studio: loaded_instances.config.context_length')
        if provider == 'compatible':
            # Reuse the registered provider client; only GET /models, never inference.
            spec = llm.PROVIDERS[provider]
            with llm.OpenAI(base_url=spec.base_url, api_key=credentials.resolve(provider) or os.getenv(spec.key_env, ''), timeout=10, max_retries=0) as client:
                matches = [m.model_dump() for m in client.models.list().data if m.id == model]
            if len(matches) == 1:
                values = [positive(matches[0].get(k)) for k in ('context_length', 'context_window')]
                values = [v for v in values if v]
                return dict(context_length=min(values) if values else None, source='Метаданные GET /models')
    except Exception:
        pass  # Never return transport errors containing endpoint credentials.
    return dict(context_length=None, source='Достоверные метаданные недоступны')


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
