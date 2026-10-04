"""Generated definitions, controller ownership, hidden context and durable v2 play."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.definitions import CampaignMutation, CharacterBuild
from backend.tabletop.models import Command, GameState
from backend.tabletop.projection import public_state, DMProjection
from backend.tabletop.migrations import migrate
from backend.tabletop.repository import TabletopRepository
from backend.tabletop.ai import GameAI
from tabletop_fixture import definition, state
from test_tabletop import runtime, combat_state, api, create, send, CONFIG


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.locations[0].connections.append("missing"),
        lambda d: setattr(d.locations[0], "region_id", "missing"),
        lambda d: d.characters[0].knowledge.append("missing"),
        lambda d: setattr(d.characters[0], "faction_id", "missing"),
        lambda d: setattr(d.objects[0].contents[0], "item_id", "missing"),
        lambda d: setattr(d.quests[0], "required_item", "missing"),
        lambda d: setattr(d.encounters[0], "loot_object", "missing"),
        lambda d: d.locations[0].connections.clear(),
        lambda d: setattr(d.characters[0], "controller", "AI"),
        lambda d: setattr(d, "ruleset_version", 99),
        lambda d: setattr(d.objects[0], "id", "traveler"),
        lambda d: setattr(d.objects[0], "check_skill", "athletics"),
    ],
)
def test_compiler_rejects_invalid_world(change):
    d = definition()
    change(d)
    with pytest.raises(ValueError):
        CampaignCompiler().compile(d)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.abilities.update(strength=20),
        lambda b: setattr(b, "species", "dragon"),
        lambda b: setattr(b, "character_class", "wizard"),
        lambda b: b.skills.append("stealth"),
        lambda b: b.equipment.append("potion"),
    ],
)
def test_build_derived_stats_not_user_numbers(change):
    b = CharacterBuild()
    change(b)
    with pytest.raises(ValueError):
        CampaignCompiler().compile(definition(), b)


def test_custom_build_and_authoritative_dc():
    d = definition()
    d.objects[0].dc = 23
    s = CampaignCompiler().compile(
        d, CharacterBuild(name="Ирина", appearance="Серый плащ")
    )
    assert s.actor("traveler").name == "Ирина" and s.actor("traveler").hp == 12
    assert s.actor("traveler").appearance == "Серый плащ"
    s, _ = runtime().execute(s, Command(type="move", target="vault"))
    s, _ = runtime().execute(
        s, Command(type="check", purpose="search", difficulty="TRIVIAL")
    )
    assert s.session_state.pending.dc == 23


def test_pending_owner_independent_of_selected_actor():
    r = runtime(20, 18, 1)
    s = state(second_player=True)
    s, _ = r.execute(s, Command(type="move", target="vault"))
    s, _ = r.execute(s, Command(type="start_encounter"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert (
        s.session_state.pending.actor == "partner"
        and s.session_state.controlled_actor == "traveler"
    )
    assert (
        GameState.model_validate(s.model_dump()).session_state.pending.actor
        == "partner"
    )
    with pytest.raises(ValueError):
        r.resolve_roll(s, s.session_state.pending.id, player_id="outsider")
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.encounter.order == ["traveler", "partner", "sentinel"]
    s, _ = r.execute(s, Command(type="end_turn"))
    with pytest.raises(ValueError):
        r.execute(s, Command(type="dodge", actor_id="traveler"))
    s, _ = r.execute(s, Command(type="dodge", actor_id="partner"))
    assert "dodge" in s.actor("partner").conditions
    with pytest.raises(ValueError):
        r.execute(s, Command(type="look", actor_id="sentinel"))


def test_ai_decisions_pure_and_neutral_factions():
    s = combat_state()
    before = s.model_dump_json()
    ai = GameAI()
    assert {"UseFeature", "SeekCover", "Surrender"} <= {
        type(b).__name__ for b in ai.registry.behaviors
    }
    assert (
        ai.decision(s, "sentinel").behavior == "Attack"
        and s.model_dump_json() == before
    )
    s.definition.faction_relations = []
    assert not s.hostile("traveler", "sentinel")
    assert ai.decide(s, "sentinel").type == "dodge"


def test_relevant_dm_context_without_public_secret_leak():
    s = state(companion=True)
    hidden = json.dumps(DMProjection.build(s), ensure_ascii=False)
    assert "NEVER_DISCLOSE_1827" in hidden and "REMOTE_SECRET_491" not in hidden
    visible = json.dumps(public_state(s), ensure_ascii=False)
    assert "NEVER_DISCLOSE" not in visible and "REMOTE_SECRET" not in visible
    assert "far_room" not in visible and "drawer" not in visible
    assert "goals" not in visible and "current_intent" not in visible


def test_dialogue_persuasion_and_impossible_request():
    s = state()
    r = runtime(20)
    s, e = r.execute(s, Command(type="dialogue", target="archivist"))
    assert s.quests["retrieve"] == "active" and s.player_knowledge
    s, _ = r.execute(s, Command(type="check", purpose="persuade", target="archivist"))
    s, e = r.resolve_roll(s, s.session_state.pending.id)
    assert "rumor" in s.player_knowledge and "sealed_truth" not in s.player_knowledge
    s, e = r.execute(s, Command(type="check", purpose="persuade", target="archivist"))
    assert not s.session_state.pending and e[-1]["kind"] == "refusal"


def test_search_trap_unlock_inventory_quest():
    d = definition()
    d.objects[0].locked = True
    d.objects[0].trap_damage = 3
    s = CampaignCompiler().compile(d)
    r = runtime(20, 20, 1)
    for c in [
        Command(type="dialogue", target="archivist"),
        Command(type="move", target="vault"),
        Command(type="check", purpose="search"),
    ]:
        s, _ = r.execute(s, c)
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    with pytest.raises(ValueError):
        r.execute(s, Command(type="take_item", target="drawer", item_id="manuscript"))
    with pytest.raises(ValueError):
        r.execute(s, Command(type="interact", target="drawer"))
    s, _ = r.execute(s, Command(type="check", target="drawer", purpose="unlock"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    s, _ = r.execute(s, Command(type="interact", target="drawer"))
    assert s.session_state.pending.purpose == "save"
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").hp == 9
    s, _ = r.execute(
        s, Command(type="take_item", target="drawer", item_id="manuscript")
    )
    s, _ = r.execute(s, Command(type="use_item", item_id="potion"))
    assert s.actor("traveler").hp == 12
    s, _ = r.execute(s, Command(type="move", target="market"))
    s, _ = r.execute(s, Command(type="dialogue", target="archivist"))
    assert s.quests["retrieve"] == "completed"
    assert [
        (e.item_id, e.quantity)
        for e in s.actor("traveler").inventory
        if e.item_id == "coin"
    ] == [("coin", 5)]
    s, _ = r.execute(s, Command(type="dialogue", target="archivist"))
    assert (
        sum(e.quantity for e in s.actor("traveler").inventory if e.item_id == "coin")
        == 5
    )
    s, _ = r.execute(s, Command(type="drop_item", item_id="coin", quantity=2))
    oid = next(o.id for o in s.definition.objects if o.id.startswith("dropped_"))
    s, _ = r.execute(
        s, Command(type="take_item", target=oid, item_id="coin", quantity=2)
    )
    assert (
        sum(e.quantity for e in s.actor("traveler").inventory if e.item_id == "coin")
        == 5
    )


def test_loot_requires_victory_not_flee_or_guessed_id():
    d = definition()
    d.objects[1].hidden = False
    s = CampaignCompiler().compile(d)
    s, _ = runtime().execute(s, Command(type="move", target="vault"))
    assert not s.objects["spoils"].revealed
    s, e = runtime().execute(
        s, Command(type="check", target="spoils", purpose="search")
    )
    assert not s.session_state.pending
    with pytest.raises(ValueError):
        runtime().execute(s, Command(type="interact", target="spoils"))
    s = combat_state()
    s, e = runtime().execute(s, Command(type="flee"))
    assert not s.objects["spoils"].revealed and not s.completed_encounters
    s = combat_state()
    r = runtime(20, 8, 8)
    s, _ = r.execute(s, Command(type="attack", target="sentinel"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    s, e = r.resolve_roll(s, s.session_state.pending.id)
    assert (
        s.completed_encounters == ["guard_battle"]
        and s.objects["spoils"].revealed
        and not s.objects["spoils"].opened
    )
    s, _ = r.execute(s, Command(type="interact", target="spoils"))
    s, _ = r.execute(
        s, Command(type="take_item", target="spoils", item_id="coin", quantity=3)
    )
    assert any(
        e.item_id == "coin" and e.quantity == 3 for e in s.actor("traveler").inventory
    )


def test_bonus_and_reaction_budgets_and_death_save():
    s = combat_state()
    s.actor("traveler").hp = 3
    r = runtime()
    s, _ = r.execute(s, Command(type="recover"))
    assert s.actor("traveler").hp == 7 and not s.encounter.bonus_action
    with pytest.raises(ValueError):
        r.execute(s, Command(type="recover"))
    s, _ = r.execute(s, Command(type="guard"))
    assert not s.encounter.reaction["traveler"]
    with pytest.raises(ValueError):
        r.execute(s, Command(type="guard"))
    s = combat_state()
    s.actor("traveler").hp = 0
    s.actor("traveler").conditions = ["unconscious"]
    r.drive(s, [])
    assert s.session_state.pending.purpose == "death"
    s, _ = runtime(20).resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").hp == 1 and s.encounter


def test_player_opportunity_reaction_resumes_movement():
    s = combat_state()
    s.encounter.index = 1
    r = runtime(1)
    events = []
    r.move(s, "sentinel", 10, events)
    assert (
        s.session_state.reaction["actor"] == "traveler"
        and s.actor("sentinel").position == 5
    )
    s, _ = r.execute(s, Command(type="reaction_attack", actor_id="traveler"))
    assert s.session_state.pending.purpose == "attack"
    # Prevent automatic follow-up attack while verifying the resumed movement.
    s.encounter.action = False
    s.encounter.movement = 10
    s, e = r.resolve_roll(s, s.session_state.pending.id)
    assert (
        not s.session_state.reaction
        and s.encounter.round == 2
        and s.actor("sentinel").position == 15
    )


def extension():
    return CampaignMutation.model_validate(
        {
            "operations": [
                {
                    "type": "CreateLocation",
                    "value": {"id": "tower", "name": "Башня", "region_id": "district"},
                },
                {"type": "ConnectLocations", "first": "market", "second": "tower"},
            ]
        }
    )


def test_mutations_atomic_and_no_generic_patch():
    s = state()
    after = CampaignCompiler().extend(s, extension())
    assert "tower" in after.locations and "tower" not in s.locations
    assert after.actor("traveler") == s.actor("traveler")
    with pytest.raises(ValueError):
        CampaignMutation.model_validate({"operations": [{"type": "Patch", "hp": 999}]})
    with pytest.raises(ValueError):
        CampaignCompiler().extend(after, extension())
    with pytest.raises(ValueError):
        CampaignCompiler().extend(
            s,
            CampaignMutation.model_validate(
                {
                    "operations": [
                        {
                            "type": "RevealKnowledge",
                            "secret_id": "sealed_truth",
                            "source_id": "drawer",
                        }
                    ]
                }
            ),
        )
    assert s.player_knowledge == {}


@pytest.mark.parametrize(
    "fixture",
    ["tabletop_v1.json", "tabletop_v1_pending.json", "tabletop_v1_attack.json"],
)
def test_migration_preserves_saved_stats_and_pending(tmp_path, fixture):
    old = json.loads((Path(__file__).parent / "fixtures" / fixture).read_text())
    s = migrate(old)
    assert (
        s.schema_version == 2 and s.actor("hero").hp == old["characters"]["hero"]["hp"]
    )
    assert s.actor("hero").armor_class == 16
    repo = TabletopRepository(tmp_path / "migration.db")
    gid = repo.create(state())
    with repo.connect() as db:
        db.execute(
            "UPDATE tabletop_games SET state_json=? WHERE id=?", (json.dumps(old), gid)
        )
    rev, loaded = repo.load(gid)
    assert rev == 0 and loaded == s
    with repo.connect() as db:
        assert (
            json.loads(
                db.execute("SELECT original_json FROM tabletop_migrations").fetchone()[
                    0
                ]
            )
            == old
        )
    assert repo.load(gid)[1] == s
    if s.session_state.pending:
        assert s.session_state.pending.id == old["session_state"]["pending"]["id"]
        s, _ = runtime(20, 1).resolve_roll(s, s.session_state.pending.id)
        assert s.encounter


def test_generated_draft_start_expand_and_staged_usage(api):
    c, app = api

    def stream(**kw):
        from semantic_fixture import (
            world_blueprint as world,
            campaign_blueprint as campaign,
        )
        from backend.tabletop.procedural_content import stable_id

        kw["on_usage"]({"prompt_tokens": 123, "completion_tokens": 45})
        prompt = kw["messages"][0]["content"]
        if "WorldBlueprint" in prompt:
            yield json.dumps(world())
        elif "CampaignBlueprint" in prompt:
            yield json.dumps(campaign())
        elif "ExpansionBlueprint" in prompt:
            yield json.dumps({"locations": [{"name": "Башня"}]})
        else:
            yield "Мир продолжает жить."

    with patch("llm.chat_stream", side_effect=stream):
        res = c.post(
            "/api/tabletop/generate",
            json={
                "options": {"idea": "Город архивов"},
                "config": CONFIG,
                "api_key": "secret",
            },
        )
        assert res.status_code == 200, res.text
        d = res.json()
        assert {u["stage"] for u in d["usage"]} == {
            "authoring_setting_blueprint",
            "authoring_campaign_blueprint",
        }
        g = c.post(
            "/api/tabletop/games",
            json={
                "draft_id": d["id"],
                "draft_revision": d["revision"],
                "character": d["definition"]["characters"][0]["build"],
            },
        ).json()
        g = send(
            c,
            g,
            command={"type": "expand", "topic": "Найти башню"},
            config=CONFIG,
            api_key="secret",
        ).json()
    assert "Башня" in [l["name"] for l in g["state"]["locations"]]
    assert {
        "authoring_setting_blueprint",
        "authoring_campaign_blueprint",
        "authoring_content_blueprint",
    } <= {u["stage"] for u in g["usage"]}
    assert "NEVER_DISCLOSE" not in json.dumps(g) and "REMOTE_SECRET" not in json.dumps(
        g
    )
    assert "NEVER_DISCLOSE" not in c.get(f"/api/tabletop/games/{g['id']}/context").text


def test_invalid_generation_and_dynamic_content_leave_state_unchanged(api):
    c, app = api
    g = create(c)
    with patch(
        "llm.chat_stream",
        return_value=iter(
            ['{"operations":[{"type":"Patch","hp":999,"secret":"NEVER"}]}']
        ),
    ):
        res = send(
            c,
            g,
            command={"type": "expand", "topic": "Башня"},
            config=CONFIG,
            api_key="secret",
        )
    assert res.status_code == 409 and "NEVER" not in res.text
    after = c.get(f"/api/tabletop/games/{g['id']}").json()
    assert after["revision"] == g["revision"] and after["state"] == g["state"]
    with patch("llm.chat_stream", return_value=iter(["{}"])):
        res = c.post(
            "/api/tabletop/generate",
            json={"options": {"idea": "Город"}, "config": CONFIG, "api_key": "secret"},
        )
    assert res.status_code == 409 and len(c.get("/api/tabletop/games").json()) == 1


def test_multiple_enemies_and_ai_companion_take_turns():
    d = definition(companion=True)
    other = d.creatures[0].model_copy(deep=True)
    other.id = "second_sentinel"
    other.build.name = "Второй страж"
    d.creatures.append(other)
    d.encounters[0].participants.append(other.id)
    s = CampaignCompiler().compile(d)
    r = runtime(20, 18, 1, 2, 12, 2, 1, 1)
    s, _ = r.execute(s, Command(type="move", target="vault"))
    s, _ = r.execute(s, Command(type="start_encounter"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert len(s.encounter.order) == 4
    s, events = r.execute(s, Command(type="end_turn"))
    assert s.encounter.round == 2
    assert {e["roll"]["actor"] for e in events if "roll" in e} == {
        "partner",
        "sentinel",
        "second_sentinel",
    }


def test_flee_allows_continued_exploration():
    s = combat_state()
    s, _ = runtime().execute(s, Command(type="flee"))
    s, _ = runtime().execute(s, Command(type="move", target="market"))
    assert (
        s.actor("traveler").location == "market"
        and "fled" not in s.actor("traveler").conditions
    )


def test_trap_death_saves_outside_combat_and_stable_rest():
    d = definition()
    d.objects[0].hidden = False
    d.objects[0].trap_damage = 3
    s = CampaignCompiler().compile(d)
    s.actor("traveler").hp = 1
    r = runtime(1, 10, 10, 10)
    s, _ = r.execute(s, Command(type="move", target="vault"))
    s, _ = r.execute(s, Command(type="interact", target="drawer"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.purpose == "death"
    for _ in range(3):
        s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert "stable" in s.actor("traveler").conditions and not s.session_state.pending
    s, _ = r.execute(s, Command(type="rest", rest="long"))
    assert s.actor("traveler").hp == s.actor("traveler").max_hp
