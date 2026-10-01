"""Authoring LLM outputs definitions/operations, never canonical GameState."""

import json
from pydantic import ValidationError
from .validation import CampaignValidationError, ValidationIssue, schema_error
from .definitions import CampaignDefinition, CampaignMutation
from .compiler import CampaignCompiler
from .catalog import load_ruleset


def authoring_catalog(rules):
    # Authoring needs level-one choices, not all twenty advancement tables.
    data = rules.model_dump()
    return {
        k: data[k]
        for k in (
            "id",
            "version",
            "abilities",
            "ability_array",
            "skills",
            "classes",
            "species",
            "backgrounds",
            "items",
        )
    } | {
        "spells": {k: v.model_dump() for k, v in rules.spells.items() if v.level <= 1},
        "spellcasting": {k: v.model_dump() for k, v in rules.spellcasting.items()},
    }


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
Location.travel_minutes: ключи только connections, значения 1–1440 минут.
NPCSchedule.actor_id -> AI персонаж вне партии; destination_id -> locations.id; after_quest -> quests.id или null.
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
        rules = load_ruleset("d20-fantasy-v1")
        prompt = (
            "Создай полноценную playable CampaignDefinition на русском. Только JSON по схеме. "
            "ruleset_id=d20-fantasy-v1, ruleset_version=3. Для каждого build выбери feature_choices по feature_choice_count класса. "
            "Никаких полей runtime HP, AC, результатов бросков или state patches. "
            "Заполни initial_conflict и 2–4 публичных plot_hooks, не раскрывающих секреты. "
            "Дай фракциям public_goal, NPC — цели, отношения и намерения, заданиям — доступные условия выполнения. "
            "Можно добавить schedules для обычных NPC вне партии: проверяемые перемещения после delay_minutes и необязательного after_quest. "
            "В travel_minutes задай время известных переходов. build.spells/prepared_spells можно оставить null для стартового набора класса. "
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
                            "catalog": authoring_catalog(rules),
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
            "Только typed CreateLocation/NPC/Item/Quest/Encounter/Object/Faction/Region/Secret/Schedule, DefineFactionRelation и ConnectLocations. "
            "DefineFactionRelation допустим лишь для новой фракции; задай HOSTILE для нового врага. "
            "CreateSchedule может управлять только новым AI NPC, не существующим персонажем. "
            "Новый секрет можно дать новому NPC или скрытому объекту; не копируй старые секреты. "
            "Не переопределяй существующие ID и не раскрывай существующие секреты. "
            "Новая локация в существующем или создаваемом регионе; соедини её с current_location. NPC только AI. "
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
            "catalog": authoring_catalog(state.ruleset),
            "game_time_minutes": state.game_time // 60,
            "public_hooks": state.definition.plot_hooks,
            "completed_quests": [
                q.id
                for q in state.definition.quests
                if state.quests[q.id] == "completed"
            ],
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


class CharacterRoleplayGenerator:
    """Generates only user-reviewable prose. Mechanics never come from this output."""

    def __init__(self, dm):
        self.dm = dm

    def generate(self, draft_id, definition, build, field):
        from .definitions import CharacterRoleplay

        public_setting = {
            "name": definition.setting.name,
            "description": definition.setting.description,
            "genre": definition.setting.genre,
            "tone": definition.setting.tone,
        }
        allowed = list(CharacterRoleplay.model_fields)
        if field != "all" and field not in allowed:
            raise ValueError("Недопустимое поле персонажа")
        raw = self.dm.call(
            draft_id,
            "character_generation",
            [
                {
                    "role": "system",
                    "content": "Создай roleplay-портрет героя на русском с учётом концепции и мира. "
                    "Только JSON по схеме. Не назначай HP/AC/бонусы, предметы, заклинания или игровые результаты. "
                    "Не раскрывай тайны кампании и не решай действия за игрока. При генерации отдельного поля верни только его. "
                    "Схема: "
                    + json.dumps(
                        CharacterRoleplay.model_json_schema(), ensure_ascii=False
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "setting": public_setting,
                            "character": build.model_dump(),
                            "field": field,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            True,
        )
        try:
            result = CharacterRoleplay.model_validate_json(raw)
        except ValidationError:
            raise ValueError(
                "Модель вернула некорректный портрет. Механика и персонаж не изменены."
            ) from None
        values = result.model_dump(exclude_none=True)
        if field != "all":
            values = {field: values[field]} if values.get(field) else {}
        if not values or (field == "all" and set(values) != set(allowed)):
            raise ValueError("Модель вернула неполный портрет. Повтори генерацию.")
        return values
