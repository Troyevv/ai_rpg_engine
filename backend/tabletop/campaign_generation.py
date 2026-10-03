"""Campaign authoring against a fixed setting snapshot and staged compiler checks."""

from copy import deepcopy
from pydantic import Field, create_model
from .contracts import Model, Id, Difficulty
from .definitions import CampaignDefinition, Setting, EncounterDefinition
from .content import CreatureInstance
from .content_registry import SettingValidator, setting_rules, creature_threat
from .compiler import CampaignCompiler
from .generation import REFERENCE_CONTRACT, authoring_catalog
from .setting_generation import StagedAuthor
from .authoring import stage_schema, AuthoringCompiler
from .validation import CampaignValidationError, ValidationIssue


class CampaignOptions(Model):
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

    def build(self, request, setting, party_size, party_level=1):
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
        budget = (
            party_size
            * (18 + party_level * 12)
            * self.factors[request.difficulty]
            / request.environment_modifier
        )
        candidates.sort(key=lambda c: (c.rarity, -creature_threat(c, content), c.id))
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
                id=f"{request.id}_{i+1}",
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
    stages = (
        ("concept", ("id", "name", "initial_conflict", "plot_hooks", "starting_scene")),
        ("locations", ("regions", "locations", "starting_location")),
        ("society", ("factions", "faction_relations", "characters", "starting_party")),
        ("objects", ("quests", "secrets", "objects")),
        ("encounters", ()),
        ("checks_schedules", ("checks", "schedules", "context_actions", "objects")),
    )

    def __init__(self, dm, progress=None, checkpoint=None):
        self.author = StagedAuthor(dm, progress, checkpoint)

    def generate(self, id, setting, options):
        setting = SettingValidator().validate(setting)
        rules = setting_rules(setting)
        payload = dict(
            schema_version=1,
            ruleset_id=rules.id,
            ruleset_version=rules.version,
            setting_definition=setting.model_dump(),
            setting=Setting(
                id=setting.id,
                name=setting.name,
                description=setting.description,
                genre=setting.genre,
                tone=setting.tone,
                technology=setting.technology_description,
                magic=setting.supernatural_description,
            ).model_dump(),
            regions=[],
            locations=[],
            factions=[],
            characters=[],
            creatures=[],
            creature_instances=[],
            items=[],
            objects=[],
            quests=[],
            secrets=[],
            encounters=[],
            checks=[],
            schedules=[],
            starting_party=[],
        )
        contract = (
            "Создай конкретное приключение в переданном мире, не меняя законы мира и контент. "
            "На каждом этапе верни только поля схемы, используй ID ранее созданных сущностей. "
            "NPC/герои выбирают build из каталога; существа создаются EncounterBuilder по шаблонам, не задавай им HP/AC/stats. "
            "На society knowledge=[] до создания secrets. Стартовая партия находится в starting_location, первый участник PLAYER player_id=local, другие AI. "
            "Build: шесть значений стандартного массива, skill_count навыков класса, корректные feature_choices и equipment. "
            "Все места достижимы по connections; starting_location существует. Не создавай связи с будущими местами. "
            "На encounters задай requests: место, враждебная фракция, сложность и доступные template ID. Бюджет считает движок. "
            "SceneCheck: skill соответствует default_ability или alternate_abilities; save не имеет skill. "
            "Passive использует навыки с PASSIVE_PERCEPTION/PASSIVE_INSIGHT и только безопасное reveal, без failure и critical_failure. "
            "reveal_secret/reveal_object только в своей локации, never-disclosure запрещён; move только к соседу; attitude/alert не управляет PLAYER. "
            "Каждая проверка имеет значимые последствия. schedules только AI вне партии. "
            + REFERENCE_CONTRACT
        )
        for stage, fields in self.stages:
            if stage == "encounters":
                schema = EncounterRequests
            else:
                schema = stage_schema(
                    "CampaignStage_" + stage, CampaignDefinition, fields
                )

            def validate(value):
                candidate = deepcopy(payload)
                if stage == "encounters":
                    candidate["encounters"] = []
                    candidate["creature_instances"] = []
                    for request in value.requests:
                        missing = set(request.available_creatures) - set(
                            setting.content.creatures
                        )
                        if missing:
                            raise CampaignValidationError(
                                [
                                    ValidationIssue(
                                        code="missing_content_reference",
                                        stage=stage,
                                        entity_type="encounter",
                                        entity_id=request.id,
                                        field="available_creatures",
                                        reference=ref,
                                        target_id=ref,
                                        message="Неизвестный шаблон существа",
                                    )
                                    for ref in sorted(missing)
                                ]
                            )
                        encounter, instances = EncounterBuilder().build(
                            request, setting, options.party_size
                        )
                        candidate["encounters"].append(encounter.model_dump())
                        candidate["creature_instances"].extend(
                            i.model_dump() for i in instances
                        )
                else:
                    candidate.update(AuthoringCompiler.stage(value))
                    if stage == "checks_schedules" and {
                        o["id"] for o in candidate["objects"]
                    } != {o["id"] for o in payload["objects"]}:
                        raise CampaignValidationError(
                            [
                                ValidationIssue(
                                    code="stage_identity_change",
                                    stage=stage,
                                    entity_type="campaign",
                                    entity_id=id,
                                    field="objects",
                                    message="Сохрани все объекты предыдущего этапа; здесь можно связать их с готовыми действиями",
                                )
                            ]
                        )
                if stage == "locations":
                    places = {l["id"]: l for l in candidate["locations"]}
                    issues = []
                    region_ids = {region["id"] for region in candidate["regions"]}
                    for field in ("locations", "regions"):
                        seen = set()
                        for entity in candidate[field]:
                            if entity["id"] in seen:
                                issues.append(
                                    ValidationIssue(
                                        code="duplicate_id",
                                        stage=stage,
                                        entity_type=field,
                                        entity_id=entity["id"],
                                        field="id",
                                        message="Повторяющийся ID",
                                    )
                                )
                            seen.add(entity["id"])
                    for loc in places.values():
                        if loc["region_id"] not in region_ids:
                            issues.append(
                                ValidationIssue(
                                    code="unknown_reference",
                                    stage=stage,
                                    entity_type="location",
                                    entity_id=loc["id"],
                                    field="region_id",
                                    target_id=loc["region_id"],
                                    message="Неизвестный регион",
                                )
                            )
                        for ref in loc["connections"]:
                            if ref not in places:
                                issues.append(
                                    ValidationIssue(
                                        code="unknown_reference",
                                        stage=stage,
                                        entity_type="location",
                                        entity_id=loc["id"],
                                        field="connections",
                                        reference=ref,
                                        message="Переход ссылается на неизвестную локацию",
                                    )
                                )
                    if candidate["starting_location"] not in places:
                        issues.append(
                            ValidationIssue(
                                code="unknown_reference",
                                stage=stage,
                                entity_type="campaign",
                                entity_id=candidate["id"],
                                field="starting_location",
                                message="Стартовая локация отсутствует",
                            )
                        )
                    if issues:
                        raise CampaignValidationError(issues, stage=stage)
                    visited = set()
                    todo = [candidate["starting_location"]]
                    while todo:
                        loc = todo.pop()
                        if loc not in visited:
                            visited.add(loc)
                            todo.extend(places[loc]["connections"])
                    if visited != set(places):
                        raise CampaignValidationError(
                            [
                                ValidationIssue(
                                    code="unreachable_location",
                                    stage=stage,
                                    entity_type="location",
                                    entity_id=loc,
                                    field="connections",
                                    message="Место недостижимо из стартовой локации",
                                )
                                for loc in sorted(set(places) - visited)
                            ]
                        )
                if stage not in ("concept", "locations"):
                    CampaignCompiler().validate(candidate)
                    if len(candidate["starting_party"]) != options.party_size:
                        raise CampaignValidationError(
                            [
                                ValidationIssue(
                                    code="starting_party_mismatch",
                                    stage=stage,
                                    entity_type="campaign",
                                    entity_id=candidate["id"],
                                    field="starting_party",
                                    message="Размер партии не соответствует запросу",
                                )
                            ]
                        )
                return candidate

            payload = self.author.run(
                id,
                "campaign_" + stage,
                schema,
                {
                    "options": options.model_dump(),
                    "world": setting.model_dump(exclude={"content"}),
                    "catalog": authoring_catalog(rules),
                    "creatures": {
                        k: {
                            "id": k,
                            "name": v.name,
                            "habitats": v.habitats,
                            "threat": v.threat,
                            "rarity": v.rarity,
                        }
                        for k, v in setting.content.creatures.items()
                    },
                    "campaign": {
                        k: v for k, v in payload.items() if k != "setting_definition"
                    },
                },
                validate,
                contract,
            )
        return CampaignCompiler().validate(payload)
