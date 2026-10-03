"""Bounded staged authoring. A failed stage is retried against unchanged prior stages."""

import json
from pydantic import create_model, ValidationError
from .contracts import Model
from .authoring import stage_schema, AuthoringCompiler, authoring_issues
from .content import SettingDefinition, SettingFoundation, ContentRegistry
from .content_registry import SettingValidator
from .validation import CampaignValidationError, ValidationIssue

SETTING_STAGES = (
    ("foundation", ()),
    ("society", ("equipment_profiles", "species", "archetypes", "backgrounds")),
    (
        "skills_features",
        (
            "skills",
            "damage_types",
            "resources",
            "features",
            "powers",
            "spellcasting",
            "archetypes",
            "backgrounds",
            "species",
            "levels",
            "subclasses",
            "feats",
        ),
    ),
    ("bestiary", ("creatures",)),
    ("equipment", ("items", "archetypes", "backgrounds")),
    ("world_mechanics", ("world_mechanics",)),
)


class AuthoringFailure(CampaignValidationError):
    def __init__(self, issues, stage, draft):
        super().__init__(issues, stage=stage)
        self.draft = draft


class StagedAuthor:
    def __init__(self, dm, progress=None, checkpoint=None):
        self.checkpoint = checkpoint
        self.dm = dm
        self.progress = progress or (lambda stage: None)

    def run(self, id, stage, schema, context, validate, contract):
        if self.checkpoint:
            cached = self.checkpoint.cached(stage)
            if cached is not None:
                return validate(schema.model_validate(cached, strict=True))
        issues = []
        for attempt in range(2):
            self.progress(stage)
            if self.checkpoint:
                self.checkpoint.progress(stage)
            raw = self.dm.call(
                id,
                "authoring_" + stage,
                [
                    {
                        "role": "system",
                        "content": contract
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
            try:
                result = schema.model_validate_json(raw, strict=True)
                compiled = validate(result)
                if self.checkpoint:
                    self.checkpoint.save(stage, result.model_dump(mode="json"))
                return compiled
            except ValidationError as exc:
                issues = authoring_issues(exc, raw, id, stage)
            except CampaignValidationError as exc:
                issues = [i.model_copy(update={"stage": stage}) for i in exc.issues]
        raise AuthoringFailure(issues, stage, context)


def setting_authoring_context(setting, fields):
    """Only editable sections need full definitions; other sections provide ID/name references."""
    if setting is None:
        return None
    data = setting.model_dump(exclude={"content"})
    data["content"] = {}
    for key in type(setting.content).model_fields:
        entries = getattr(setting.content, key)
        if key in fields:
            data["content"][key] = (
                {
                    id: (
                        value.model_dump(exclude_defaults=True)
                        if hasattr(value, "model_dump")
                        else value
                    )
                    for id, value in entries.items()
                }
                if isinstance(entries, dict)
                else entries
            )
        elif isinstance(entries, dict):
            data["content"][key] = {
                id: {"id": id, "name": getattr(value, "name", id)}
                for id, value in entries.items()
            }
        else:
            data["content"][key] = entries
    return data


class SettingGenerator:
    def __init__(self, dm, progress=None, checkpoint=None):
        self.author = StagedAuthor(dm, progress, checkpoint)

    def generate(self, id, concept, existing=None, section=None):
        if not self.author.dm.config:
            raise ValueError("Настрой провайдера и модель")
        draft = existing.model_copy(deep=True) if existing else None
        stages = (
            SETTING_STAGES
            if section is None
            else [v for v in SETTING_STAGES if v[0] == section]
        )
        if not stages and section in ContentRegistry.model_fields:
            stages = [(section, (section,))]
        if not stages:
            raise ValueError("Неизвестный раздел мира")
        for stage, fields in stages:
            contract = (
                "Создай содержимое произвольной вселенной на русском по концепции пользователя. "
                "Механическое ядро неизменно: STR/DEX/CON/INT/WIS/CHA, d20, action/bonus/reaction/movement. "
                "Не предполагай жанр. Не добавляй стандартное фэнтези, если его нет в концепции. "
                "Используй только объявленные ID текущего и предыдущих этапов. Не придумывай ссылки на будущий контент. "
                "Не выдавай состояние игры, произвольные патчи или результаты бросков. "
                "Ресурсы, типы урона, навыки и названия профессий определяет мир. "
                "На society задай equipment profile, минимум вид, профессию и происхождение; skill_count=0 до этапа навыков, пустые ещё не созданные equipment/features. "
                "На skills_features создай тематические навыки, способности, ресурсы и типы урона; назначь их существующим профессиям/видам/происхождениям, сохраняя ID. "
                "На equipment создай компоненты вещей и стартовые наборы профессий, сохраняя их ID. "
                "Сложность существ оценивает движок; threat оставь 0. "
                "При перегенерации учитывай зависимости всех остальных разделов. Исправь все previous_issues, не удаляя механики ради прохождения проверки."
            )
            if stage == "foundation":

                def validate_foundation(value):
                    if draft is None:
                        return SettingDefinition(
                            **value.model_dump(), content=ContentRegistry()
                        )
                    if value.id != draft.id:
                        raise CampaignValidationError(
                            [
                                ValidationIssue(
                                    code="stage_identity_change",
                                    stage=stage,
                                    entity_type="setting",
                                    entity_id=draft.id,
                                    field="id",
                                    message="Сохрани ID существующего мира",
                                )
                            ]
                        )
                    candidate = draft.model_copy(deep=True)
                    for key, field_value in value.model_dump().items():
                        setattr(candidate, key, field_value)
                    return SettingValidator().validate(candidate)

                draft = self.author.run(
                    id,
                    stage,
                    SettingFoundation,
                    {
                        "concept": concept,
                        "setting": (
                            draft.model_dump(exclude={"content"}) if draft else None
                        ),
                    },
                    validate_foundation,
                    contract,
                )
            else:
                schema = stage_schema("SettingStage_" + stage, ContentRegistry, fields)

                def validate(value):
                    candidate = draft.model_copy(deep=True)
                    compiled = AuthoringCompiler.stage(value)
                    content = candidate.content.model_dump()
                    content.update(compiled)
                    candidate.content = ContentRegistry.model_validate(content)
                    for field in ("archetypes", "backgrounds", "species"):
                        previous = getattr(draft.content, field)
                        if (
                            section is None
                            and previous
                            and field in fields
                            and set(previous) != set(getattr(candidate.content, field))
                        ):
                            raise CampaignValidationError(
                                [
                                    ValidationIssue(
                                        code="stage_identity_change",
                                        stage=stage,
                                        entity_type="setting",
                                        entity_id=id,
                                        field=field,
                                        message="Сохрани ID уже созданных сущностей",
                                    )
                                ]
                            )
                    return SettingValidator().validate(
                        candidate,
                        complete=bool(existing) or stage == SETTING_STAGES[-1][0],
                    )

                draft = self.author.run(
                    id,
                    stage,
                    schema,
                    {
                        "concept": concept,
                        "setting": setting_authoring_context(draft, fields),
                    },
                    validate,
                    contract,
                )
        return SettingValidator().validate(draft)
