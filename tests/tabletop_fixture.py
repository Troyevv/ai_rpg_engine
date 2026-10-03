"""Fixture campaign only; production runtime has no knowledge of its IDs."""

from backend.tabletop.definitions import *
from backend.tabletop.compiler import CampaignCompiler


def definition(companion=False, second_player=False):
    hero = CharacterDefinition(
        id="traveler",
        name="Путник",
        location_id="market",
        faction_id="seekers",
        controller="PLAYER",
        player_id="local",
        build=CharacterBuild(name="Путник"),
    )
    guide = CharacterDefinition(
        id="archivist",
        name="Архивариус",
        location_id="market",
        faction_id="citizens",
        build=CharacterBuild(name="Архивариус"),
        personality="Сухо шутит, говорит коротко.",
        public_lore=["В нижнем архиве пропадают документы."],
        knowledge=["sealed_truth", "rumor"],
    )
    enemy = CharacterDefinition(
        id="sentinel",
        name="Страж хранилища",
        location_id="vault",
        faction_id="wardens",
        build=CharacterBuild(name="Страж"),
        position=5,
        morale=0.9,
    )
    chars = [hero, guide]
    party = [hero.id]
    if companion or second_player:
        ally = CharacterDefinition(
            id="partner",
            name="Спутник",
            location_id="market",
            faction_id="seekers",
            controller="PLAYER" if second_player else "AI",
            player_id="local" if second_player else None,
            build=CharacterBuild(name="Спутник"),
            morale=0.9,
        )
        chars.append(ally)
        party.append(ally.id)
    return CampaignDefinition(
        id="archive_story",
        name="Исчезнувшая рукопись",
        setting=Setting(
            id="archive_world",
            name="Город архивов",
            description="Город над древними хранилищами.",
        ),
        regions=[
            Region(id="district", name="Старый район"),
            Region(id="far_region", name="Дальние земли"),
        ],
        locations=[
            Location(
                id="market",
                name="Площадь",
                description="Архивариус ждёт у фонтана.",
                region_id="district",
                connections=["vault"],
            ),
            Location(
                id="vault",
                name="Хранилище",
                description="Пыльные шкафы и страж у двери.",
                region_id="district",
                connections=["market", "far_room"],
            ),
            Location(
                id="far_room",
                name="Дальний зал",
                description="Безлюдный зал.",
                region_id="far_region",
                connections=["vault"],
            ),
        ],
        factions=[
            Faction(id="seekers", name="Искатели"),
            Faction(id="citizens", name="Горожане"),
            Faction(id="wardens", name="Стражи"),
        ],
        faction_relations=[
            FactionRelation(first="seekers", second="wardens", relation="HOSTILE"),
            FactionRelation(first="seekers", second="citizens", relation="ALLY"),
        ],
        characters=chars,
        creatures=[enemy],
        items=[
            ItemDefinition(id="manuscript", name="Рукопись", type="quest"),
            ItemDefinition(id="coin", name="Старинная монета"),
        ],
        objects=[
            WorldObject(
                id="drawer",
                name="Тайный ящик",
                location_id="vault",
                hidden=True,
                difficulty="EASY",
                contents=[InventoryEntry(item_id="manuscript")],
                secrets=["archive_note"],
            ),
            WorldObject(
                id="spoils",
                name="Сумка стража",
                location_id="vault",
                hidden=True,
                contents=[InventoryEntry(item_id="coin", quantity=3)],
            ),
        ],
        secrets=[
            Secret(
                id="archive_note",
                name="Записка",
                location_id="vault",
                description="Записка указывает на подземный переход.",
            ),
            Secret(
                id="sealed_truth",
                name="Тайна",
                location_id="market",
                description="NEVER_DISCLOSE_1827",
                disclosure="never",
            ),
            Secret(
                id="rumor",
                name="Слух",
                location_id="market",
                description="Архивариус видел торговца в нижнем зале.",
                disclosure="persuasion",
                difficulty="EASY",
            ),
            Secret(
                id="distant_secret",
                name="Дальний секрет",
                location_id="far_room",
                description="REMOTE_SECRET_491",
            ),
        ],
        quests=[
            Quest(
                id="retrieve",
                name="Вернуть рукопись",
                description="Найди рукопись в архиве.",
                giver_id="archivist",
                location_id="vault",
                required_item="manuscript",
                reward=[InventoryEntry(item_id="coin", quantity=5)],
            )
        ],
        encounters=[
            EncounterDefinition(
                id="guard_battle",
                name="Страж архива",
                location_id="vault",
                participants=["sentinel"],
                loot_object="spoils",
            )
        ],
        starting_party=party,
        starting_location="market",
        starting_scene="Ты прибываешь на площадь. Архивариус подзывает тебя.",
    )


def state(**kwargs):
    return CampaignCompiler().compile(definition(**kwargs))


class Fixed:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, lo, hi):
        n = next(self.values)
        assert lo <= n <= hi
        return n
