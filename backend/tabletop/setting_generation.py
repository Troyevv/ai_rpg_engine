"""Bounded staged authoring. A failed stage is retried against unchanged prior stages."""

import json
from pydantic import create_model, ValidationError
from .authoring import authoring_issues
from .validation import CampaignValidationError

SETTING_STAGES = (("setting_semantics", ()), ("setting_compile", ()))


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

    def generate(self, id, concept, existing=None, section=None, generation=None):
        from .semantic import SemanticSettingDTO, SemanticModel
        from .semantic_authoring import generate_semantic, compile_stage
        from .procedural_content import ProceduralContentCompiler

        if not self.author.dm.config:
            raise ValueError("Настрой провайдера и модель")
        from .generation_config import GenerationConfig

        generation = generation or (
            existing.generation_config if existing else GenerationConfig()
        )
        schema = SemanticSettingDTO
        source = existing.semantic_source if existing else None
        if section and not source:
            raise ValueError(
                "Для раздела старого мира нужен semantic source; доступна полная перегенерация или ручное редактирование"
            )
        groups = {
            "foundation": (
                "name",
                "description",
                "genre",
                "tone",
                "themes",
                "era",
                "technology",
                "supernatural",
                "lore",
            ),
            "society": (
                "species",
                "professions",
                "backgrounds",
                "cultures",
                "factions",
            ),
            "skills_features": (
                "skills",
                "professions",
                "species",
                "backgrounds",
                "conditions",
                "damage_concepts",
            ),
            "bestiary": ("creatures",),
            "equipment": ("items", "professions", "backgrounds"),
            "world_mechanics": ("environments", "interactions", "conditions"),
            "archetypes": ("professions",),
            "features": ("professions", "species"),
            "powers": ("professions",),
            "spellcasting": ("professions",),
            "resources": ("professions",),
            "levels": ("professions",),
            "subclasses": ("professions",),
            "feats": ("professions",),
            "equipment_profiles": ("species",),
            "damage_types": ("damage_concepts",),
        }
        if section:
            fields = groups.get(section, (section,))
            if not set(fields) <= set(SemanticSettingDTO.model_fields):
                raise ValueError(
                    "Раздел редактируется вместе с semantic-профессиями или предметами"
                )
            from copy import deepcopy

            schema = create_model(
                "SemanticSettingSection",
                __base__=SemanticModel,
                **{
                    k: (
                        SemanticSettingDTO.model_fields[k].annotation,
                        deepcopy(SemanticSettingDTO.model_fields[k]),
                    )
                    for k in fields
                },
            )
        context = {
            "concept": concept,
            "existing_semantics": source,
            "coverage_targets": generation.targets,
        }
        value = generate_semantic(self.author, id, "setting_semantics", schema, context)
        dto = SemanticSettingDTO.model_validate(
            {**(source or {}), **value.model_dump()}
        )
        return compile_stage(
            self.author,
            "setting_compile",
            lambda: ProceduralContentCompiler().compile(
                existing.id if existing else id,
                dto,
                existing.revision if existing else 0,
                generation,
            ),
        )
