"""Reference failures are complete, durable, actionable, and never become state."""

import json
import sqlite3
from unittest.mock import Mock, patch

import pytest

from backend.tabletop.catalog import load_ruleset
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.definitions import (
    CharacterBuild,
    GenerationOptions,
    InventoryEntry,
)
from backend.tabletop.generation import CampaignGenerator
from backend.tabletop.authoring import authoring_payload
from backend.tabletop.repository import TabletopRepository
from backend.tabletop.validation import (
    CampaignReferenceValidator,
    CampaignValidationError,
)
from tabletop_fixture import definition
from test_tabletop import api, CONFIG

# Every reference-bearing field, including both actor collections and catalog items.
CASES = [
    ("locations", "region_id", "region_id"),
    ("locations", "connections", "connections"),
    ("secrets", "location_id", "location_id"),
    ("objects", "location_id", "location_id"),
    ("objects", "secrets", "secrets"),
    ("objects", "contents", "contents.item_id"),
    ("quests", "location_id", "location_id"),
    ("quests", "giver_id", "giver_id"),
    ("quests", "required_item", "required_item"),
    ("quests", "reward", "reward.item_id"),
    ("encounters", "location_id", "location_id"),
    ("encounters", "participants", "participants"),
    ("encounters", "loot_object", "loot_object"),
    ("encounters", "quest_id", "quest_id"),
    ("faction_relations", "first", "first"),
    ("faction_relations", "second", "second"),
    (None, "starting_location", "starting_location"),
    (None, "starting_party", "starting_party"),
] + [
    (group, field, diagnostic)
    for group in ("characters", "creatures")
    for field, diagnostic in (
        ("location_id", "location_id"),
        ("faction_id", "faction_id"),
        ("knowledge", "knowledge"),
        ("relationships", "relationships"),
        ("inventory", "inventory.item_id"),
        ("build", "build.equipment"),
    )
]


@pytest.mark.parametrize("group,field,diagnostic", CASES)
def test_every_reference_is_checked(group, field, diagnostic):
    d = definition()
    entity = getattr(d, group)[0] if group else d
    value = getattr(entity, field)
    if field == "build":
        value.equipment.append("missing")
    elif field in ("inventory", "contents", "reward"):
        value.append(InventoryEntry(item_id="missing"))
    elif isinstance(value, list):
        value.append("missing")
    elif isinstance(value, dict):
        value["missing"] = 1
    else:
        setattr(entity, field, "missing")
    before = d.model_dump()
    issues = CampaignReferenceValidator().validate(d, load_ruleset())
    assert len(issues) == 1
    assert issues[0].field == diagnostic and issues[0].reference == "missing"
    assert issues[0].code == "unknown_reference"
    with pytest.raises(CampaignValidationError) as caught:
        CampaignCompiler().compile(d)
    assert caught.value.issues == issues and caught.value.stage == "reference"
    assert (
        d.model_dump() == before
    )  # No repair, deletion, guessed ID or partial output.


def test_collects_exactly_four_deterministic_errors():
    d = definition()
    d.characters[0].knowledge.append("missing_secret")
    d.characters[1].relationships["missing_actor"] = -1
    d.quests[0].giver_id = "missing_giver"
    d.encounters[0].participants.append("missing_enemy")
    validator = CampaignReferenceValidator()
    issues = validator.validate(d, load_ruleset())
    assert len(issues) == 4 and validator.validate(d, load_ruleset()) == issues
    assert [(i.entity_id, i.field, i.reference) for i in issues] == [
        ("traveler", "knowledge", "missing_secret"),
        ("archivist", "relationships", "missing_actor"),
        ("retrieve", "giver_id", "missing_giver"),
        ("guard_battle", "participants", "missing_enemy"),
    ]
    with pytest.raises(CampaignValidationError) as caught:
        CampaignCompiler().compile(d)
    assert caught.value.issues == issues
    message = caught.value.public_message()
    assert all(
        text in message
        for text in (
            "Архивариус",
            "archivist",
            "knowledge",
            "missing_secret",
            "relationships",
            "missing_actor",
        )
    )
    assert "Неизвестные знания или отношения персонажа" not in message


def test_catalog_nullable_and_both_actor_collections():
    d = definition()
    d.characters[1].relationships = {"sentinel": -1}
    d.creatures[0].relationships = {"archivist": 1}
    d.creatures[0].knowledge = ["sealed_truth"]
    d.objects[0].contents.append(InventoryEntry(item_id="potion"))
    d.quests[0].required_item = "sword"
    d.quests[0].giver_id = None
    d.encounters[0].loot_object = None
    d.encounters[0].quest_id = None
    assert CampaignReferenceValidator().validate(d, load_ruleset()) == []
    CampaignCompiler().compile(d)
    d.characters[1].relationships = {d.creatures[0].name: -1}
    assert (
        CampaignReferenceValidator().validate(d, load_ruleset())[0].reference
        == "Страж хранилища"
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.locations[0].connections.clear(),
        lambda d: d.characters.append(d.characters[0].model_copy(deep=True)),
        lambda d: setattr(d.characters[0], "location_id", "vault"),
        lambda d: setattr(d.characters[0], "controller", "AI"),
        lambda d: setattr(d.characters[1], "player_id", "local"),
        lambda d: setattr(d.characters[0].build, "species", "dragon"),
        lambda d: setattr(d.secrets[0], "location_id", "market"),
        lambda d: setattr(d.objects[0], "check_skill", "athletics"),
        lambda d: d.encounters[0].participants.append("archivist"),
        lambda d: d.encounters[0].participants.append("sentinel"),
        lambda d: setattr(d.objects[1], "location_id", "market"),
        lambda d: setattr(d.faction_relations[0], "second", "seekers"),
        lambda d: setattr(d.items[0], "healing", 2),
        lambda d: setattr(d.objects[0].contents[0], "equipped", True),
    ],
)
def test_semantic_guards_stay_strict(change):
    d = definition()
    change(d)
    assert CampaignReferenceValidator().validate(d, load_ruleset()) == []
    with pytest.raises(CampaignValidationError) as caught:
        CampaignCompiler().compile(d)
    assert caught.value.stage == "semantic"


@pytest.mark.parametrize("invalid", [False, True])
def test_generator_contract_and_bounded_semantic_repair(invalid):
    from semantic_fixture import world, campaign

    data = campaign()
    if invalid:
        data["npcs"][0]["knowledge"] = ["Unknown secret"]
    dm = Mock(config=CONFIG)
    dm.call.side_effect = [json.dumps(world()), json.dumps(data), json.dumps(data)]
    generator = CampaignGenerator(dm)
    if invalid:
        with pytest.raises(CampaignValidationError) as caught:
            generator.generate("draft", GenerationOptions(idea="Город архивов"))
        assert all(i.code == "semantic_generation_error" for i in caught.value.issues)
        assert dm.call.call_count == 3
    else:
        result = generator.generate("draft", GenerationOptions(idea="Город архивов"))
        assert result.player_slot and all(
            a.controller == "AI" for a in result.characters
        )
        assert dm.call.call_count == 2
    assert "CharacterBuild" not in json.dumps(dm.call.call_args_list, default=str)


def generate(c, d):
    if isinstance(d, str):
        with patch("llm.chat_stream", side_effect=lambda *a, **k: iter([d])) as llm:
            response = c.post(
                "/api/tabletop/generate",
                json={
                    "options": {"idea": "Город архивов"},
                    "config": CONFIG,
                    "api_key": "secret",
                },
            )
        assert llm.call_count == 2
        return response

    def reject(*args, **kwargs):
        return CampaignCompiler().validate(d)

    with patch.object(CampaignGenerator, "generate", side_effect=reject):
        return c.post(
            "/api/tabletop/generate",
            json={
                "options": {"idea": "Город архивов"},
                "config": CONFIG,
                "api_key": "secret",
            },
        )


def test_invalid_draft_survives_restart_and_manual_correction(api):
    c, app = api
    d = definition()
    d.characters[1].knowledge.append("unknown_secret")
    d.characters[1].relationships["unknown_npc"] = 1
    response = generate(c, d)
    assert response.status_code == 409
    body = response.json()
    assert len(body["validation_issues"]) == 2 and body["stage"] == "reference"
    did = body["draft_id"]
    repo = TabletopRepository(app.state.repository.path)
    draft = repo.draft(did)
    assert draft["generation_status"] == "INVALID"
    assert draft["definition"] == d.model_dump()
    assert draft["validation_issues"] == body["validation_issues"]
    assert draft["usage"] == []  # Compiler rejection injected without provider calls.
    assert c.get("/api/tabletop/drafts").json()[0]["generation_status"] == "INVALID"
    assert c.get(f"/api/tabletop/drafts/{did}").json() == draft
    request = {
        "draft_id": did,
        "draft_revision": 0,
        "character": CharacterBuild().model_dump(),
    }
    assert c.post("/api/tabletop/games", json=request).status_code == 409
    with repo.connect() as db:
        for table in ("tabletop_games", "tabletop_history", "tabletop_settings"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert c.get("/api/tabletop/games").json() == []
    # Rejected author edits cannot overwrite a persisted draft or its revision.
    rejected = c.put(
        f"/api/tabletop/drafts/{did}",
        json={"revision": 0, "definition": d.model_dump()},
    )
    assert rejected.status_code == 409 and repo.draft(did) == draft
    fixed = c.put(
        f"/api/tabletop/drafts/{did}",
        json={"revision": 0, "definition": definition().model_dump()},
    ).json()
    assert fixed["generation_status"] == "VALID" and fixed["validation_issues"] == []
    assert fixed["revision"] == 1
    request["draft_revision"] = 1
    game = c.post("/api/tabletop/games", json=request)
    assert game.status_code == 200
    for text in (
        game.text,
        c.get(f"/api/tabletop/games/{game.json()['id']}/context").text,
    ):
        for hidden in (
            "NEVER_DISCLOSE",
            "REMOTE_SECRET",
            "unknown_secret",
            "validation_issues",
            "definition_json",
        ):
            assert hidden not in text


@pytest.mark.parametrize(
    "raw", ["{}", "not JSON", '{"name":{"private":"HIDDEN_PAYLOAD"}}']
)
def test_schema_errors_are_friendly_and_do_not_persist(api, raw):
    c, app = api
    response = generate(c, raw)
    assert response.status_code == 409
    assert (
        response.json()["stage"] == "setting_semantics"
        and response.json()["draft_id"] is None
    )
    assert all(
        term not in response.text
        for term in ("HIDDEN_PAYLOAD", "input_value", "pydantic", "Traceback")
    )
    assert c.get("/api/tabletop/drafts").json() == []
    assert c.get("/api/tabletop/games").json() == []


def test_semantic_failure_is_saved_as_invalid_draft(api):
    c, app = api
    d = definition()
    d.locations[0].connections.clear()
    response = generate(c, d)
    assert response.status_code == 409 and response.json()["stage"] == "semantic"
    saved = c.get("/api/tabletop/drafts/" + response.json()["draft_id"]).json()
    assert (
        saved["generation_status"] == "INVALID"
        and saved["definition"] == d.model_dump()
    )
    assert c.get("/api/tabletop/games").json() == []


def test_draft_schema_migration_preserves_existing_data(tmp_path):
    path = tmp_path / "old.db"
    d = definition()
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE tabletop_drafts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0, definition_json TEXT NOT NULL, source TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO tabletop_drafts VALUES(?, ?, ?, ?)",
            ("old", 7, d.model_dump_json(), "generated"),
        )
    for _ in range(2):
        saved = TabletopRepository(path).draft("old")
        assert saved["definition"] == d.model_dump() and saved["revision"] == 7
        assert (
            saved["generation_status"] == "VALID" and saved["validation_issues"] == []
        )
