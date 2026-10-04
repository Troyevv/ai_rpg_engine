"""Campaign authoring against a fixed setting snapshot and staged compiler checks."""

from pydantic import Field
from .contracts import Model, Id, Difficulty
from .definitions import EncounterDefinition
from .content import CreatureInstance
from .content_registry import SettingValidator, creature_threat
from .setting_generation import StagedAuthor
from .generation_config import CampaignGenerationConfig
from .validation import CampaignValidationError, ValidationIssue


class CampaignOptions(Model):
    generation: CampaignGenerationConfig = Field(
        default_factory=CampaignGenerationConfig
    )
    idea: str = Field(min_length=3, max_length=6000)
    title: str = Field(default="", max_length=120)
    tone: str = ""
    scale: str = ""
    adventure_type: str = ""
    difficulty: Difficulty = "MEDIUM"
    party_size: int = Field(default=1, ge=1, le=4)
    starting_situation: str = ""
    wishes: str = ""


class EncounterRequest(Model):
    id: Id
    name: str
    description: str = ""
    location_id: Id
    faction_id: Id
    difficulty: Difficulty = "MEDIUM"
    habitats: list[str] = []
    available_creatures: list[Id] = []
    environment_modifier: float = Field(default=1, ge=0.5, le=2)
    loot_object: Id | None = None
    quest_id: Id | None = None


class EncounterRequests(Model):
    requests: list[EncounterRequest] = Field(default_factory=list, max_length=10)


class EncounterBuilder:
    factors = {
        "TRIVIAL": 0.25,
        "EASY": 0.5,
        "MEDIUM": 1,
        "HARD": 1.5,
        "VERY_HARD": 2,
        "EXTREME": 3,
    }

    def build(self, request, setting, party_size, party_level=1, seed=0):
        content = setting.content
        candidates = [
            c
            for c in content.creatures.values()
            if (not request.available_creatures or c.id in request.available_creatures)
            and (
                not request.habitats
                or not c.habitats
                or set(c.habitats) & set(request.habitats)
            )
        ]
        if not candidates:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code="no_encounter_candidates",
                        stage="encounters",
                        entity_type="encounter",
                        entity_id=request.id,
                        field="available_creatures",
                        message="Нет допустимых существ для столкновения",
                    )
                ]
            )
        from .procedural_content import BalanceEngine

        budget = BalanceEngine.encounter_budget(
            party_size, party_level, request.difficulty, request.environment_modifier
        )
        from .generation_config import GeneratorContext

        order = GeneratorContext(seed)
        candidates.sort(
            key=lambda c: (c.rarity, order.rng(request.id, c.id).random(), c.id)
        )
        selected = []
        remaining = budget
        while len(selected) < min(8, party_size * 3):
            valid = [c for c in candidates if creature_threat(c, content) <= remaining]
            if not valid:
                break
            creature = valid[0]
            selected.append(creature)
            remaining -= creature_threat(creature, content)
        if not selected:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code="encounter_budget_exceeded",
                        stage="encounters",
                        entity_type="encounter",
                        entity_id=request.id,
                        field="available_creatures",
                        message="Ни одно доступное существо не укладывается в бюджет",
                        context={"budget": budget},
                    )
                ]
            )
        instances = [
            CreatureInstance(
                id=f"{request.id}_{i + 1}",
                name=c.name,
                template_id=c.id,
                location_id=request.location_id,
                faction_id=request.faction_id,
                attitude="hostile",
            )
            for i, c in enumerate(selected)
        ]
        return (
            EncounterDefinition(
                id=request.id,
                name=request.name,
                description=request.description,
                location_id=request.location_id,
                participants=[c.id for c in instances],
                loot_object=request.loot_object,
                quest_id=request.quest_id,
            ),
            instances,
        )


class CampaignGenerator2:
    stages = (("semantics", ()), ("compile", ()))

    def __init__(self, dm, progress=None, checkpoint=None):
        self.author = StagedAuthor(dm, progress, checkpoint)

    def generate(self, id, setting, options):
        from .semantic import SemanticCampaignDTO
        from .semantic_authoring import generate_semantic, compile_stage
        from .semantic_campaign import SemanticCampaignCompiler

        setting = SettingValidator().validate(setting)
        # Display names and descriptions, not executable registry or canonical IDs.
        context = {
            "options": options.model_dump(exclude={"generation"}),
            "coverage_targets": options.generation.targets,
            "world": {
                "name": setting.name,
                "description": setting.description,
                "tone": setting.tone,
                "lore": setting.custom_lore,
                "content": {
                    group: [
                        {"name": v.name, "description": v.description}
                        for v in getattr(setting.content, group).values()
                    ]
                    for group in (
                        "species",
                        "archetypes",
                        "backgrounds",
                        "skills",
                        "items",
                        "creatures",
                    )
                },
            },
        }
        dto = generate_semantic(
            self.author, id, "campaign_semantics", SemanticCampaignDTO, context
        )
        return compile_stage(
            self.author,
            "campaign_compile",
            lambda: SemanticCampaignCompiler().compile(id, dto, setting, options),
        )
