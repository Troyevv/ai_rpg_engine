"""Authoring LLM outputs definitions/operations, never canonical GameState."""

import json
from pydantic import ValidationError


def authoring_catalog(rules):
    # Authoring needs level-one choices, not all twenty advancement tables.
    data = rules.model_dump()
    data["items"] = [item.model_dump(exclude_defaults=True) for item in rules.items]
    return {
        k: data[k]
        for k in (
            "id",
            "version",
            "abilities",
            "ability_array",
            "allocation",
            "starting_gold",
            "equipment_slots",
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

    def generate(self, draft_id, options, checkpoint=None):
        from .setting_generation import SettingGenerator
        from .campaign_generation import CampaignGenerator2, CampaignOptions

        world = SettingGenerator(self.dm, checkpoint=checkpoint).generate(
            draft_id + "_world", options.idea + "\n" + options.setting
        )
        return CampaignGenerator2(self.dm, checkpoint=checkpoint).generate(
            draft_id,
            world,
            CampaignOptions.model_validate(
                {
                    k: v
                    for k, v in options.model_dump().items()
                    if k in CampaignOptions.model_fields
                }
            ),
        )


class ContentGenerator:
    def __init__(self, dm):
        self.dm = dm

    def generate(self, gid, state, topic):
        from .semantic_expansion import expand

        if not self.dm.config:
            raise ValueError("Для расширения мира нужна модель")
        return expand(self.dm, gid, state, topic)


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
