"""Free metadata only. No probing completions and no guessed model/tokenizer identity."""
import json
import os
from hashlib import sha256
import llm

# Official API table, checked 2026-11-19. Decimal 1M is a conservative floor.
SOURCE = 'https://api-docs.deepseek.com/quick_start/pricing/'
DEEPSEEK = {'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp', 'deepseek-v4-pro'}


def positive(value):
    return value if type(value) is int and value > 0 else None


def discover(provider, model, credentials=None, *, api_key=None):
    endpoint = {}
    configured_limits = {}
    if provider == 'deepseek':
        return dict(context_length=1000000, max_output=384000, source=SOURCE, checked='2026-11-19') if model in DEEPSEEK else dict(context_length=None, source='Модель отсутствует в проверенной таблице DeepSeek')
    try:
        if provider == 'local':
            limits = []
            for item in llm.get_models_info().get('models', []):
                for instance in item.get('loaded_instances', []):
                    if model in (item.get('key'), item.get('model_key'), item.get('id'), instance.get('id')):
                        limit = positive(instance.get('config', {}).get('context_length'))
                        if not limit: return dict(context_length=None, source='Нет окна загруженного экземпляра LM Studio')
                        limits.append(limit)
            return dict(context_length=min(limits) if limits else None, source='LM Studio: loaded_instances.config.context_length')
        if provider == 'compatible':
            # Reuse the registered provider client; only GET /models, never inference.
            spec = llm.PROVIDERS[provider]
            if not spec.base_url:
                return dict(context_length=None, source='Совместимый endpoint не настроен')
            # Explicit limits are scoped to this exact endpoint AND model. Never
            # expose the endpoint (it may contain credentials) in diagnostics.
            endpoint['endpoint_id'] = sha256(spec.base_url.encode()).hexdigest()[:16]
            configured = json.loads(os.getenv('COMPATIBLE_MODEL_LIMITS', '{}')).get(spec.base_url, {}).get(model)
            if isinstance(configured, dict):
                configured_limits = dict(context_length=positive(configured.get('context_length')),
                                         max_input=positive(configured.get('max_input')),
                                         max_output=positive(configured.get('max_output')))
            with llm.OpenAI(base_url=spec.base_url, api_key=api_key or (credentials and credentials.resolve(provider)) or os.getenv(spec.key_env, ''), timeout=10, max_retries=0) as client:
                matches = [m.model_dump() for m in client.models.list().data if m.id == model]
            if len(matches) == 1:
                metadata = matches[0]
                windows = [positive(metadata.get(k)) for k in ('context_length', 'context_window')]
                discovered = dict(context_length=min(filter(None, windows), default=None),
                                  max_input=positive(metadata.get('max_input_tokens')),
                                  max_output=positive(metadata.get('max_output_tokens')))
                limits = {key: min(filter(None, (value, configured_limits.get(key))), default=None)
                          for key, value in discovered.items()}
                source = 'Метаданные GET /models'
                if any(configured_limits.values()):
                    source += ' и серверные ограничения'
                return dict(limits, source=source, **endpoint)
    except Exception:
        pass  # Never return transport errors containing endpoint credentials.
    if any(configured_limits.values()):
        return dict(configured_limits, source='Серверная конфигурация (не подтверждена провайдером)', **endpoint)
    return dict(context_length=None, source='Достоверные метаданные недоступны', **endpoint)
