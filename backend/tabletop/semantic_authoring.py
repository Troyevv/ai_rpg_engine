"""Retry semantic input only; persist it before deterministic compilation."""

import json
from pydantic import ValidationError
from .validation import ValidationIssue, CampaignValidationError
from .setting_generation import AuthoringFailure

CONTRACT = (
    "Создай содержательный мир или открытую приключенческую ситуацию по запросу на русском. "
    "Сохрани свободу действий игрока. Используй только ограниченные семантические данные схемы: "
    "имена, смысл, темы, цели и намерения. Для blueprint не создавай ссылки между сущностями: граф построит код. "
    "Не создавай код, формулы, DSL, характеристики, build игрока, кубики, internal IDs или механику. "
    "Не заполняй мир множеством сущностей: достаточно нескольких выразительных творческих семейств. "
    "knowledge — обычные знания, не ссылки на секреты. "
    "Не добавляй жанровые предположения. Не помещай тайны в публичные описания. Механики выберет компилятор. "
)


def exception_diagnostics(dm, exc, stage, attempt):
    """Retain useful failure evidence without persisting credentials or headers."""
    import os
    import re
    import requests
    import openai

    config = dm.config if isinstance(dm.config, dict) else {}
    message = str(exc)
    secrets = [getattr(dm, "api_key", None)]
    secrets += [
        v
        for k, v in os.environ.items()
        if any(t in k.upper() for t in ("API_KEY", "TOKEN", "PASSWORD", "SECRET"))
    ]
    secrets += [
        v
        for k, v in config.items()
        if any(t in k.lower() for t in ("key", "token", "password", "authorization"))
        and isinstance(v, str)
    ]
    for secret in sorted((v for v in secrets if v), key=len, reverse=True):
        message = message.replace(secret, "[REDACTED]")
    message = re.sub(
        r"(?im)(authorization|api[-_ ]?key|token|password|cookie)\s*['\"]?\s*[:=]\s*[^\n,}]+",
        r"\1=[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)Bearer\s+\S+|sk-[A-Za-z0-9_-]+", "[REDACTED]", message)
    message = re.sub(r"https?://[^\s]+", "[URL REDACTED]", message)
    is_provider = isinstance(
        exc,
        (TimeoutError, ConnectionError, requests.RequestException, openai.OpenAIError),
    )
    # RuntimeError/ValueError are raised by the existing provider adapter for response/configuration errors.
    adapter_error = isinstance(exc, (RuntimeError, ValueError))
    return dict(
        code="provider_error"
        if is_provider
        else "provider_response_error"
        if adapter_error
        else "authoring_internal_error",
        exception_type=type(exc).__name__,
        provider=config.get("provider", "unknown"),
        model=config.get("model", "unknown"),
        stage=stage,
        original_message=message[:2000],
        attempt=attempt,
    )


def generate_semantic(author, id, stage, schema, context):
    checkpoint = author.checkpoint
    if checkpoint:
        cached = checkpoint.cached(stage)
        if cached is not None:
            return schema.model_validate(cached, strict=True)
    issues = []
    for attempt in range(2):
        author.progress(stage)
        if checkpoint:
            checkpoint.progress(stage)
        try:
            raw = author.dm.call(
                id,
                "authoring_" + stage,
                [
                    {
                        "role": "system",
                        "content": CONTRACT
                        + "\nВерни только JSON по схеме:\n"
                        + json.dumps(
                            schema.model_json_schema(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "context": context,
                                "previous_issues": [i.model_dump() for i in issues],
                                "attempt": attempt + 1,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                True,
            )
        except Exception as exc:
            details = exception_diagnostics(author.dm, exc, stage, attempt + 1)
            raise AuthoringFailure(
                [
                    ValidationIssue(
                        code=details.pop("code"),
                        context=details,
                        stage=stage,
                        entity_type="authoring",
                        entity_id=id,
                        field="provider",
                        message="Не удалось получить творческое описание. Подробности сохранены в диагностике.",
                    )
                ],
                stage,
                context,
            ) from exc
        try:
            dto = schema.model_validate_json(raw, strict=True)
        except ValidationError as exc:
            issues = [
                ValidationIssue(
                    code="semantic_generation_error"
                    if e["type"] == "value_error"
                    else "schema_error",
                    stage=stage,
                    entity_type="semantic",
                    entity_id=id,
                    field=".".join(map(str, e["loc"])),
                    message=e["msg"],
                )
                for e in exc.errors(include_input=False)
            ]
            continue
        if checkpoint:
            checkpoint.save(stage, dto.model_dump(mode="json", exclude_unset=True))
        return dto
    raise AuthoringFailure(issues, stage, context)


def compile_stage(author, stage, compile):
    author.progress(stage)
    if author.checkpoint:
        author.checkpoint.progress(stage)
    try:
        result = compile()
    except CampaignValidationError as exc:
        code = (
            "reference_error"
            if exc.stage == "reference"
            else "mechanical_validation_error"
        )
        raise CampaignValidationError(
            [
                i.model_copy(
                    update={"code": code, "context": {**i.context, "cause": i.code}}
                )
                for i in exc.issues
            ],
            stage=stage,
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise CampaignValidationError(
            [
                ValidationIssue(
                    code="compiler_error",
                    stage=stage,
                    entity_type="compiler",
                    entity_id="",
                    field="compilation",
                    message=str(exc),
                )
            ],
            stage=stage,
        ) from exc
    if author.checkpoint:
        author.checkpoint.save(stage, {"complete": True})
    return result
