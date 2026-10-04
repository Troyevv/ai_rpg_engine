"""Bounded staged authoring. A failed stage is retried against unchanged prior stages."""

import json
from pydantic import create_model, ValidationError
from .authoring import authoring_issues
from .validation import CampaignValidationError

SETTING_STAGES = (("setting_blueprint", ()), ("setting_compile", ()))


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
        from .blueprints import WorldBlueprint, world_context
        from .semantic import SemanticModel
        from .semantic_authoring import generate_semantic, compile_stage
        from .procedural_world import ProceduralWorldGenerator
        from .generation_config import GenerationConfig

        if not self.author.dm.config:
            raise ValueError("Настрой провайдера и модель")
        generation = generation or (
            existing.generation_config if existing else GenerationConfig()
        )
        checkpoint = self.author.checkpoint
        # Resume already successful pre-blueprint jobs without a new provider request.
        legacy = checkpoint.cached("setting_semantics") if checkpoint else None
        if legacy is not None:
            from .procedural_content import ProceduralContentCompiler

            return compile_stage(
                self.author,
                "setting_compile",
                lambda: ProceduralContentCompiler().compile(
                    existing.id if existing else id,
                    legacy,
                    existing.revision if existing else 0,
                    generation,
                ),
            )
        source = existing.semantic_source if existing else None
        has_blueprint = source and "premise" in source and "professions" not in source
        schema = WorldBlueprint
        groups = {
            "foundation": (
                "name",
                "premise",
                "genre",
                "tone",
                "themes",
                "world_rules",
                "lore",
            ),
            "society": ("peoples", "archetypes", "origins", "cultures", "factions"),
            "skills_features": ("skill_domains", "archetypes", "power_traditions"),
            "bestiary": ("threat_families",),
            "creatures": ("threat_families",),
            "equipment": ("equipment_families",),
            "items": ("equipment_families",),
            "world_mechanics": ("world_rules", "locations", "power_traditions"),
            "archetypes": ("archetypes",),
            "skills": ("skill_domains",),
            "backgrounds": ("origins",),
            "species": ("peoples",),
            "equipment_profiles": ("peoples",),
        }
        for key in (
            "features",
            "powers",
            "spellcasting",
            "resources",
            "levels",
            "subclasses",
            "feats",
            "damage_types",
            "conditions",
        ):
            groups[key] = ("power_traditions", "archetypes")
        if section:
            if not has_blueprint:
                raise ValueError(
                    "Для частичной генерации нужен compact blueprint; старый мир можно редактировать вручную или перегенерировать целиком"
                )
            from copy import deepcopy

            fields = groups.get(section, (section,))
            if not set(fields) <= set(WorldBlueprint.model_fields):
                raise ValueError("Неизвестный раздел blueprint")
            selected_fields = {}
            for key in fields:
                field = deepcopy(WorldBlueprint.model_fields[key])
                field.default = None
                field.default_factory = None
                selected_fields[key] = (
                    WorldBlueprint.model_fields[key].annotation,
                    field,
                )
            schema = create_model(
                "WorldBlueprintSection", __base__=SemanticModel, **selected_fields
            )
        context = {
            "concept": concept,
            "existing_world": world_context(existing) if existing else None,
        }
        value = generate_semantic(self.author, id, "setting_blueprint", schema, context)
        blueprint = WorldBlueprint.model_validate(
            {**(source if section else {}), **value.model_dump(exclude_unset=True)}
        )
        result = compile_stage(
            self.author,
            "setting_compile",
            lambda: ProceduralWorldGenerator().generate(
                existing.id if existing else id,
                blueprint,
                generation,
                existing.revision if existing else 0,
            ),
        )
        if section == "foundation":
            result.content = existing.content.model_copy(deep=True)
            result.generation_metadata = existing.generation_metadata.copy()
            result.starting_currency = existing.starting_currency
        return result
