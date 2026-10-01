"""Catalog mechanics, point-buy authority, live preview and bounded AI roleplay."""

import json
from unittest.mock import patch
import pytest
from backend.tabletop.catalog import load_ruleset
from backend.tabletop.definitions import CharacterBuild, CharacterDefinition
from backend.tabletop.rules import RulesEngine
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.dm import DMContextBuilder
from test_tabletop import api, CONFIG
from tabletop_fixture import definition


def fantasy():
    d = definition()
    d.ruleset_id = "d20-fantasy-v1"
    d.ruleset_version = 3
    for a in d.characters + d.creatures:
        a.build.feature_choices = ["defense_style"]
    return d


def build_for(cls="fighter", species="human", background="wanderer"):
    rules = load_ruleset("d20-fantasy-v1")
    c = rules.classes[cls]
    return CharacterBuild(
        character_class=cls,
        species=species,
        background=background,
        skills=c["skills"][: c["skill_count"]],
        equipment=c["equipment"],
        feature_choices=c.get("feature_choices", [])[
            : c.get("feature_choice_count", 0)
        ],
    )


@pytest.mark.parametrize(
    "cls", ["fighter", "rogue", "ranger", "barbarian", "cleric", "wizard"]
)
@pytest.mark.parametrize(
    "species", ["human", "elf", "dwarf", "halfling", "half_elf", "orc"]
)
def test_all_class_species_builds_have_real_features(cls, species):
    rules = load_ruleset("d20-fantasy-v1")
    b = build_for(cls, species)
    a = RulesEngine().build_character(
        CharacterDefinition(
            id="hero", name=b.name, location_id="x", faction_id="f", build=b
        ),
        rules,
    )
    RulesEngine().equipment_stats(a, {i.id: i for i in rules.items})
    assert a.hp > 0 and a.armor_class >= 10 and a.features
    assert set(rules.species[species]["features"]) <= set(a.features)
    assert set(rules.classes[cls]["features"]) <= set(a.features)
    assert a.campaign_hooks and a.proficiencies
    assert {e.item_id for e in a.inventory} >= {"ration", "torch"}
    assert {"survival", "nature"} <= set(a.skill_proficiencies)


def test_species_and_selected_features_change_actual_mechanics():
    rules = load_ruleset("d20-fantasy-v1")
    engine = RulesEngine()

    def make(b):
        a = engine.build_character(
            CharacterDefinition(
                id="hero", name=b.name, location_id="x", faction_id="f", build=b
            ),
            rules,
        )
        engine.equipment_stats(a, {i.id: i for i in rules.items})
        return a

    human = make(build_for())
    dwarf = make(build_for(species="dwarf"))
    assert dwarf.max_hp == human.max_hp + 2
    assert "persuasion" in human.skill_proficiencies
    alternate = build_for()
    alternate.feature_choices = ["athletic_style"]
    a = make(alternate)
    assert human.armor_class == a.armor_class + 1
    assert (
        engine.check_modifier(a, "strength", "athletics", rules)
        == engine.check_modifier(human, "strength", "athletics", rules) + 2
    )


@pytest.mark.parametrize(
    "scores,valid",
    [
        ([15, 15, 15, 8, 8, 8], True),
        ([8, 8, 8, 8, 8, 8], True),
        ([15, 15, 15, 15, 8, 8], False),
        ([16, 8, 8, 8, 8, 8], False),
        ([7, 8, 8, 8, 8, 8], False),
    ],
)
def test_point_buy_cost_enforced_by_server(scores, valid):
    b = build_for()
    b.ability_method = "point_buy"
    b.abilities = dict(zip(b.abilities, scores))
    if valid:
        RulesEngine().validate_build(b, load_ruleset("d20-fantasy-v1"))
    else:
        with pytest.raises(ValueError):
            RulesEngine().validate_build(b, load_ruleset("d20-fantasy-v1"))


def test_legacy_catalog_and_build_are_unchanged():
    b = CharacterBuild()
    rules = load_ruleset()
    assert rules.id == "d20-basic-v2" and rules.version == 2
    RulesEngine().validate_build(b, rules)
    b.ability_method = "point_buy"
    with pytest.raises(ValueError):
        RulesEngine().validate_build(b, rules)
    assert CampaignCompiler().compile(definition()).actor("traveler").max_hp == 12


def test_preview_matches_compiled_sheet_and_has_no_persistence(api):
    c, app = api
    b = build_for(species="orc", background="soldier")
    b.ability_method = "point_buy"
    b.abilities = dict(zip(b.abilities, [15, 15, 15, 8, 8, 8]))
    res = c.post(
        "/api/tabletop/build/preview",
        json={"build": b.model_dump(), "ruleset_id": "d20-fantasy-v1"},
    )
    assert res.status_code == 200, res.text
    preview = res.json()
    actor = CampaignCompiler().compile(fantasy(), b).actor("traveler")
    for field in (
        "hp",
        "armor_class",
        "speed",
        "bonuses",
        "inventory",
        "features",
        "proficiencies",
    ):
        assert preview["sheet"][field] == actor.model_dump()[field]
    assert (
        preview["points_remaining"] == 0 and c.get("/api/tabletop/games").json() == []
    )
    b.abilities["charisma"] = 15
    assert (
        c.post(
            "/api/tabletop/build/preview",
            json={"build": b.model_dump(), "ruleset_id": "d20-fantasy-v1"},
        ).status_code
        == 409
    )


PORTRAIT = {
    "name": "Александр",
    "appearance": "Серый плащ",
    "biography": "Бывший стражник",
    "personality": "Немногословный",
    "ideals": "Защищать слабых",
    "bonds": "Старая стража",
    "flaws": "Упрямый",
}


@pytest.mark.parametrize("field", ["all", *PORTRAIT])
def test_ai_roleplay_requires_explicit_acceptance_and_keeps_mechanics(api, field):
    c, app = api
    draft = c.post(
        "/api/tabletop/drafts", json={"definition": fantasy().model_dump()}
    ).json()
    build = build_for()
    before = build.model_dump_json()
    output = PORTRAIT if field == "all" else {field: PORTRAIT[field]}
    calls = []

    def stream(**kw):
        calls.append(kw)
        yield json.dumps(output)

    with patch("llm.chat_stream", side_effect=stream):
        r = c.post(
            "/api/tabletop/characters/generate",
            json={
                "draft_id": draft["id"],
                "build": build.model_dump(),
                "field": field,
                "config": CONFIG,
                "api_key": "secret",
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["fields"] == output and len(calls) == 1
    assert "NEVER_DISCLOSE" not in json.dumps([call["messages"] for call in calls])
    assert build.model_dump_json() == before
    assert (
        c.get("/api/tabletop/drafts/" + draft["id"]).json()["definition"]
        == draft["definition"]
    )
    assert c.get("/api/tabletop/games").json() == []
    accepted = build.model_copy(update=output)
    actor = CampaignCompiler().compile(fantasy(), accepted).actor("traveler")
    assert actor.abilities == build.abilities
    context = DMContextBuilder.build(CampaignCompiler().compile(fantasy(), accepted))
    for k in output:
        assert context["characters"]["traveler"][k] == output[k]


def test_ai_cannot_generate_mechanics_or_overwrite_unrequested_fields(api):
    c, app = api
    draft = c.post(
        "/api/tabletop/drafts", json={"definition": fantasy().model_dump()}
    ).json()
    body = {
        "draft_id": draft["id"],
        "build": build_for().model_dump(),
        "field": "name",
        "config": CONFIG,
        "api_key": "secret",
    }
    with patch(
        "llm.chat_stream",
        return_value=iter([json.dumps({"name": "Александр", "hp": 999})]),
    ):
        assert c.post("/api/tabletop/characters/generate", json=body).status_code == 409
    with patch("llm.chat_stream", return_value=iter([json.dumps(PORTRAIT)])):
        assert c.post("/api/tabletop/characters/generate", json=body).json()[
            "fields"
        ] == {"name": "Александр"}


def test_equipment_proficiencies_affect_attacks_and_reject_untrained_armor():
    from backend.tabletop.models import InventoryEntry

    rules = load_ruleset("d20-fantasy-v1")
    engine = RulesEngine()
    build = build_for("wizard")
    actor = engine.build_character(
        CharacterDefinition(
            id="hero", name=build.name, location_id="x", faction_id="f", build=build
        ),
        rules,
    )
    items = {item.id: item for item in rules.items}
    actor.inventory = [InventoryEntry(item_id="sword", equipped=True)]
    engine.equipment_stats(actor, items)
    assert not actor.attacks["sword"].proficient
    assert engine.attack_modifier(actor, "sword") == engine.modifier(
        actor.abilities["strength"]
    )
    armor = next(item for item in rules.items if item.type == "armor")
    actor.inventory.append(InventoryEntry(item_id=armor.id, equipped=True))
    with pytest.raises(ValueError, match="не владеет"):
        engine.equipment_stats(actor, items)
