"""Authoring LLM outputs definitions/operations, never canonical GameState."""

import json
from pydantic import ValidationError
from .validation import CampaignValidationError, ValidationIssue, schema_error
from .definitions import CampaignDefinition, CampaignMutation
from .compiler import CampaignCompiler
from .catalog import load_ruleset

REFERENCE_CONTRACT = """
КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: соблюдай ссылочную целостность CampaignDefinition.
Любая ссылка должна указывать на сущность, реально объявленную в этом документе
или в переданном каталоге. Имя не заменяет ID. Не придумывай ссылки без сущностей.
CharacterDefinition (characters и creatures):
- knowledge[] содержит исключительно существующие secrets.id, не отдельные ID знаний
  и не текст фактов. Если персонаж не знает существующих секретов, верни [].
- relationships: ключи только characters.id или creatures.id, никогда имена.
  Если отношений нет, верни {}. Несуществующие участники запрещены.
- location_id -> locations.id; faction_id -> factions.id.
- inventory[].item_id -> catalog.items.id или items.id.
- build.equipment[] -> catalog.items.id; набор должен соответствовать классу.
Location.region_id -> regions.id; Location.connections[] -> locations.id.
Secret.location_id -> locations.id.
WorldObject.location_id -> locations.id; WorldObject.secrets[] -> secrets.id.
WorldObject.contents[].item_id -> catalog.items.id или items.id.
Quest.location_id -> locations.id; Quest.giver_id -> characters.id или creatures.id.
Quest.required_item -> catalog.items.id или items.id.
Quest.reward[].item_id -> catalog.items.id или items.id.
Encounter.location_id -> locations.id.
Encounter.participants[] -> characters.id или creatures.id.
Encounter.loot_object -> objects.id; Encounter.quest_id -> quests.id.
FactionRelation.first и FactionRelation.second -> factions.id.
starting_party[] -> characters.id или creatures.id; starting_location -> locations.id.
Необязательные ссылки без цели должны быть null, не пустой строкой и не выдуманным ID.
Проверь каждую ссылку перед возвратом JSON, включая обе коллекции actors и предметы
каталога. Не создавай reference на entity, которой нет в документе/catalog.
Существующий секрет объекта и участники encounter должны находиться в соответствующей
локации. Все члены стартовой партии находятся в starting_location.
"""


class CampaignGenerator:
    def __init__(self, dm):
        self.dm = dm

    def generate(self, draft_id, options):
        if not self.dm.config:
            raise ValueError("Для генерации кампании выбери модель")
        rules = load_ruleset()
        prompt = (
            "Создай полноценную playable CampaignDefinition на русском. Только JSON по схеме. "
            "Никаких полей runtime HP, AC, результатов бросков или state patches. "
            "Создай 3–6 связанных локаций, 2–5 NPC, хотя бы задание с giver_id, скрытый объект с предметом, "
            "секрет, контейнер добычи и encounter с враждебной фракцией. Все ID уникальны, ASCII. "
            "Все локации достижимы. Первый starting_party — PLAYER с player_id=local. NPC: AI. "
            "Build выбирается из каталога: точный стандартный набор abilities, навыки класса и точный equipment класса. "
            "Имена build.name и персонажа должны совпадать. Старт безопасен; бой в другой локации. "
            "Не переопределяй предметы каталога в items. faction_relations должны явно задавать HOSTILE для врагов. "
            "secrets.description скрыт, обычные descriptions публичны: не дублируй там секреты. "
            "Object contents содержит InventoryEntry. Quest required_item — ID реально доступного предмета. "
            + REFERENCE_CONTRACT
            + "\nСхема: "
            + json.dumps(CampaignDefinition.model_json_schema(), ensure_ascii=False)
        )
        raw = self.dm.call(
            draft_id,
            "campaign_generation",
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "options": options.model_dump(),
                            "catalog": rules.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            True,
        )
        try:
            definition = CampaignDefinition.model_validate_json(raw)
        except ValidationError as exc:
            raise schema_error(exc) from None
        try:
            definition = CampaignCompiler().validate(definition)
            if (
                len(definition.locations) < 3
                or not definition.quests
                or not definition.encounters
                or not definition.objects
            ):
                raise ValueError(
                    "Сгенерированному миру нужны минимум три локации, задание, объект и столкновение"
                )
            if len(definition.starting_party) != options.party_size:
                raise ValueError(
                    "Размер сгенерированной партии не соответствует запросу"
                )
            return definition
        except CampaignValidationError:
            raise
        except ValueError as exc:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code="semantic_validation",
                        entity_type="campaign",
                        entity_id=definition.id,
                        field="definition",
                        message=str(exc),
                    )
                ],
                stage="semantic",
                definition=definition,
            ) from None


class ContentGenerator:
    def __init__(self, dm):
        self.dm = dm

    def generate(self, gid, state, topic):
        if not self.dm.config:
            raise ValueError("Для расширения мира нужна модель")
        hero = state.actor(state.session_state.controlled_actor)
        prompt = (
            "Верни только CampaignMutation JSON. Создай новый связанный контент по запросу игрока. "
            "Только CreateLocation/NPC/Item/Quest/Encounter/Object/Faction и ConnectLocations. "
            "Не переопределяй существующие ID и не раскрывай существующие секреты. "
            "Новая локация в существующем регионе, соедини её с current_location. NPC только AI. "
            "Не добавляй предмет напрямую игроку: помести его в объект. "
            "NPC build строго из каталога. Все ссылки проверяются до commit. "
            "Схема: "
            + json.dumps(CampaignMutation.model_json_schema(), ensure_ascii=False)
        )
        context = {
            "current_location": hero.location,
            "region": next(
                l.region_id for l in state.definition.locations if l.id == hero.location
            ),
            "existing_ids": [
                x.id
                for group in (
                    state.definition.locations,
                    state.definition.characters,
                    state.definition.creatures,
                    state.definition.items,
                    state.definition.objects,
                    state.definition.quests,
                    state.definition.encounters,
                    state.definition.factions,
                )
                for x in group
            ],
            "factions": [
                {"id": f.id, "name": f.name} for f in state.definition.factions
            ],
            "catalog": state.ruleset.model_dump(),
            "request": topic,
        }
        raw = self.dm.call(
            gid,
            "content_generation",
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            True,
        )
        try:
            mutation = CampaignMutation.model_validate_json(raw)
            return CampaignCompiler().extend(state, mutation), mutation
        except ValueError:
            raise ValueError(
                "Новый контент не прошёл проверку схемы или ссылок. Состояние не изменено."
            ) from None
