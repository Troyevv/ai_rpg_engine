import requests
from openai import OpenAI


LM_STUDIO_URL = "http://localhost:1234"
OPENAI_BASE_URL = f"{LM_STUDIO_URL}/v1"


client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key="lm-studio",
)


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
):
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    try:
        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            content = getattr(
                delta,
                "content",
                None,
            )

            if content:
                yield content

    finally:
        # Важно для кнопки остановки:
        # если Streamlit прервёт текущий run,
        # соединение с LM Studio будет закрыто.
        try:
            stream.close()
        except Exception:
            pass