"""Authoring test data, not a product preset."""

from tabletop_gameplay_fixture import gameplay_definition
from backend.tabletop.catalog import load_ruleset
from backend.tabletop.content_migration import import_catalog
from backend.tabletop.content import ContentItem, CreatureTemplate


def authoring_reply(prompt, request):
    import json
    from backend.tabletop.authoring import authoring_payload

    world = import_catalog(load_ruleset("d20-fantasy-v2"))
    world.id = "test_universal"
    world.name = "Мир стеклянных приливов"
    world.description = "Поселения внутри стеклянных волн собирают застывшие голоса."
    d = gameplay_definition()
    for item in d.items:
        world.content.items[item.id] = ContentItem(
            id=item.id,
            name=item.name,
            description=item.description,
            category=item.type,
            value=item.value,
            components=[dict(type="quest" if item.type == "quest" else "currency")],
        )
    world.content.creatures["glass_guard"] = CreatureTemplate(
        id="glass_guard",
        name="Страж",
        attributes={
            k: 10
            for k in (
                "strength",
                "dexterity",
                "constitution",
                "intelligence",
                "wisdom",
                "charisma",
            )
        },
        base_hp=18,
        base_armor=12,
        attacks=[
            dict(
                id="strike",
                name="Удар",
                damage_type="physical",
                damage_expression="1d4",
                accuracy=2,
            )
        ],
        ai_profile="aggressive",
    )
    d.setting_definition = world
    d.ruleset_id = "d20-core-v1"
    d.items = []
    d.creatures = []
    d.encounters = []
    d.schedules = []
    for check in d.checks:
        if check.actor_id == "sentinel":
            check.actor_id = "guard_battle_1"
        for effect in check.failure:
            if effect.target == "sentinel":
                effect.target = "guard_battle_1"
    for actor in d.characters:
        actor.knowledge = []
    schema = json.loads(prompt.split("Верни только JSON по схеме:\n", 1)[1])
    title = schema["title"]
    if title == "SettingFoundation":
        return world.model_dump(
            exclude={
                "content",
                "schema_version",
                "revision",
                "archetype_label",
                "currency_label",
                "starting_currency",
            }
        )
    if title.startswith("SettingStage_"):
        stage = title.removeprefix("SettingStage_")
        data = world.content.model_dump()
        if stage == "society":
            for group in ("archetypes", "species", "backgrounds"):
                for row in data[group].values():
                    row["features"] = []
                    if group != "species":
                        row["skills"] = []
                        row["equipment"] = []
                    if group == "archetypes":
                        row["skill_count"] = 0
                        row["feature_choices"] = []
                        row["feature_choice_count"] = 0
                        row["equipment_choices"] = []
        if stage == "skills_features":
            for group in ("archetypes", "backgrounds"):
                for row in data[group].values():
                    row["equipment"] = []
                    if group == "archetypes":
                        row["equipment_choices"] = []
        return authoring_payload({k: data[k] for k in schema["properties"]})
    if title == "EncounterRequests":
        return {
            "requests": [
                dict(
                    id="guard_battle",
                    name="Страж архива",
                    location_id="vault",
                    faction_id="wardens",
                    difficulty="MEDIUM",
                    available_creatures=["glass_guard"],
                    loot_object="spoils",
                )
            ]
        }
    if title.startswith("CampaignStage_"):
        return authoring_payload({k: d.model_dump()[k] for k in schema["properties"]})
    raise ValueError("Unknown fixture stage")
