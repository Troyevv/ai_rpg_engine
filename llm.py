import os
from dataclasses import dataclass, field

import requests
from openai import OpenAI


LM_STUDIO_URL = "http://localhost:1234"
OPENAI_BASE_URL = f"{LM_STUDIO_URL}/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


@dataclass(frozen=True)
class ProviderSpec:
    base_url: str
    key_env: str = ''
    default_key: str = ''
    extra_body: dict = field(default_factory=dict)
    thinking_models: tuple[str, ...] = ()

# New compatible services can be registered here without changing game logic.
PROVIDERS = {
    'local': ProviderSpec(OPENAI_BASE_URL, default_key='lm-studio'),
    'deepseek': ProviderSpec(DEEPSEEK_BASE_URL, 'DEEPSEEK_API_KEY', extra_body={'thinking': {'type': 'disabled'}}, thinking_models=('deepseek-flash','deepseek-v4-flash','deepseek-v4-flash-vision-exp','deepseek-v4-pro')),
}


def thinking_options(provider, model, level):
    spec = PROVIDERS.get(provider)
    if not spec or model not in spec.thinking_models:
        return 'off', {}
    level = level if level in ('off','low','high') else 'off'
    return level, {'extra_body': {'thinking': {'type': 'disabled' if level=='off' else 'enabled'}},
                   **({'reasoning_effort':level} if level!='off' else {})}


def deepseek_key(api_key=None):
    key = (api_key or '').strip() or os.getenv('DEEPSEEK_API_KEY', '').strip()
    if not key:
        raise ValueError('Укажи API-ключ DeepSeek в настройках или DEEPSEEK_API_KEY.')
    return key


def get_deepseek_models(api_key=None):
    key = deepseek_key(api_key)
    try:
        with OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=key, timeout=30.0, max_retries=0) as client:
            return sorted(model.id for model in client.models.list().data)
    except Exception as exc:
        raise RuntimeError(deepseek_error(exc)) from None


def deepseek_error(exc):
    status = getattr(exc, 'status_code', None)
    return {401: 'DeepSeek: неверный API-ключ.', 402: 'DeepSeek: недостаточно средств.',
            429: 'DeepSeek: превышен лимит запросов. Повтори позже.',
            400: 'DeepSeek: проверь имя модели и параметры запроса.'}.get(
                status, 'DeepSeek: запрос не выполнен. Проверь соединение и доступность API.')




# =========================================================
# Models
# =========================================================

def get_available_models() -> list[str]:
    response = requests.get(
        f"{LM_STUDIO_URL}/api/v1/models",
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    models = data.get("models", [])

    result = []

    for model in models:
        model_key = (
            model.get("key")
            or model.get("model_key")
            or model.get("id")
        )

        if model_key:
            result.append(model_key)

    return result


def get_models_info() -> dict:
    response = requests.get(
        f"{LM_STUDIO_URL}/api/v1/models",
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_loaded_models() -> list[dict]:
    data = get_models_info()

    models = data.get("models", [])

    loaded = []

    for model in models:
        instances = model.get(
            "loaded_instances",
            [],
        )

        for instance in instances:
            loaded.append(
                {
                    "model_key": (
                        model.get("key")
                        or model.get("model_key")
                        or model.get("id")
                    ),
                    "display_name": (
                        model.get("display_name")
                        or model.get("name")
                        or model.get("key")
                        or model.get("id")
                    ),
                    "instance_id": (
                        instance.get("id")
                        or instance.get("instance_id")
                    ),
                    "config": instance.get(
                        "config",
                        {},
                    ),
                    "max_context_length": model.get(
                        "max_context_length"
                    ),
                    "raw_model": model,
                    "raw_instance": instance,
                }
            )

    return loaded


def find_loaded_model(
    model_key: str,
) -> dict | None:

    for model in get_loaded_models():
        if model["model_key"] == model_key:
            return model

    return None


# =========================================================
# Load
# =========================================================

def load_model(
    model: str,
    context_length: int = 16384,
    eval_batch_size: int = 512,
    flash_attention: bool = True,
    offload_kv_cache_to_gpu: bool = True,
) -> dict:

    response = requests.post(
        f"{LM_STUDIO_URL}/api/v1/models/load",
        json={
            "model": model,
            "context_length": context_length,
            "eval_batch_size": eval_batch_size,
            "flash_attention": flash_attention,
            "offload_kv_cache_to_gpu": (
                offload_kv_cache_to_gpu
            ),
            "echo_load_config": True,
        },
        timeout=600,
    )

    response.raise_for_status()

    if not response.content:
        return {}

    try:
        return response.json()
    except ValueError:
        return {}


# =========================================================
# Unload
# =========================================================

def unload_model(
    instance_id: str,
) -> dict:

    response = requests.post(
        f"{LM_STUDIO_URL}/api/v1/models/unload",
        json={
            "instance_id": instance_id,
        },
        timeout=120,
    )

    response.raise_for_status()

    if not response.content:
        return {}

    try:
        return response.json()
    except ValueError:
        return {}


def unload_all_models() -> int:
    loaded = get_loaded_models()

    count = 0

    for model in loaded:
        instance_id = model.get(
            "instance_id"
        )

        if not instance_id:
            continue

        unload_model(
            instance_id
        )

        count += 1

    return count


# =========================================================
# Inference
# =========================================================

def chat_stream(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 8000,
    require_complete: bool = False,
    cancel_event=None,
    on_stream=None,
    response_format=None,
    provider='local',
    api_key=None,
    thinking='off',
    on_usage=None,
):
    if provider not in PROVIDERS:
        raise ValueError('Неизвестный провайдер модели.')
    remote = provider != 'local'
    spec = PROVIDERS[provider]
    key = spec.default_key if not remote else ((api_key or '').strip() or os.getenv(spec.key_env, '').strip())
    if not key:
        raise ValueError('Укажи API-ключ провайдера.')
    client = OpenAI(base_url=spec.base_url, api_key=key, timeout=60.0, max_retries=0)
    stream = None
    finish_reason = None
    try:
        extra = {"response_format": response_format} if response_format else {}
        if spec.extra_body:
            extra['extra_body'] = spec.extra_body
        effective_thinking, thinking_args = thinking_options(provider,model,thinking)
        extra.update(thinking_args)
        if remote:
            extra['stream_options'] = {'include_usage': True}
        if effective_thinking == 'off':
            extra['temperature'] = temperature
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Генерация остановлена.")
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            **extra,
        )
        if on_stream is not None:
            on_stream(stream)
        for chunk in stream:
            usage = getattr(chunk, 'usage', None)
            if on_usage and usage is not None:
                value = usage if isinstance(usage, dict) else usage.model_dump() if hasattr(usage, 'model_dump') else None
                if value is not None:
                    on_usage(value)
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Генерация остановлена.")
            if not chunk.choices:
                continue

            if chunk.choices[0].finish_reason is not None:
                finish_reason = chunk.choices[0].finish_reason

            delta = chunk.choices[0].delta

            content = getattr(
                delta,
                "content",
                None,
            )

            if content:
                yield content

        if require_complete and finish_reason != "stop":
            raise RuntimeError("Ответ не завершён: увеличь лимит ответа/контекста и повтори генерацию.")
    except Exception as exc:
        if remote and not isinstance(exc, RuntimeError):
            raise RuntimeError(deepseek_error(exc)) from None
        raise
    finally:
        # Always close the provider stream, including cancellation and errors.
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass
        client.close()
