"""Retry semantic input only; persist it before deterministic compilation."""

import json
from pydantic import ValidationError
from .validation import ValidationIssue, CampaignValidationError
from .setting_generation import AuthoringFailure

CONTRACT = (
    "Создай содержательный мир или открытую приключенческую ситуацию по запросу на русском. "
    "Сохрани свободу действий игрока. Используй только ограниченные семантические данные схемы: "
    "имена, смысл, роли, цели, отношения и намерения. Ссылки — точные названия концептов. "
    "Не создавай код, формулы, DSL, характеристики, build игрока, кубики, internal IDs или механику. "
    "Unsupported способности обозначай intent=unsupported с полным описанием. "
    "Не добавляй жанровые предположения. Не помещай тайны в публичные описания. Механики выберет компилятор. "
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
            raise AuthoringFailure(
                [
                    ValidationIssue(
                        code="provider_error",
                        stage=stage,
                        entity_type="authoring",
                        entity_id=id,
                        field="provider",
                        message="Провайдер не вернул ответ; проверь соединение и настройки.",
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
            checkpoint.save(stage, dto.model_dump(mode="json"))
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
