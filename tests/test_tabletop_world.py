"""World evolution cannot control players, leak remote events or reset progressed actors."""

import json
import pytest
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.definitions import NPCSchedule, CampaignMutation
from backend.tabletop.models import Command, GameState
from backend.tabletop.projection import public_state, NarrationProjection
from backend.tabletop.services.world import WorldService
from backend.tabletop.validation import CampaignValidationError
from backend.tabletop.generation import authoring_catalog
from test_tabletop import runtime
from test_tabletop_creator import fantasy


def scheduled():
    d = fantasy()
    d.schedules = [
        NPCSchedule(
            id="archive_visit",
            name="Визит",
            actor_id="archivist",
            destination_id="far_room",
            delay_minutes=5,
        )
    ]
    d.locations[0].travel_minutes = {"vault": 12}
    return d


def test_schedule_advances_from_time_and_persists_once():
    s = CampaignCompiler().compile(scheduled())
    r = runtime()
    s, _ = r.execute(s, Command(type="move", target="vault"))
    assert s.game_time == 720 and s.actor("archivist").location == "far_room"
    assert s.completed_schedules == ["archive_visit"]
    assert len(s.world_events) == 1
    s = GameState.model_validate_json(s.model_dump_json())
    WorldService.advance(s, [])
    assert len(s.world_events) == 1
    assert "archive_visit" not in json.dumps(public_state(s))
    assert "archive_visit" not in json.dumps(NarrationProjection.build(s))


def test_visible_departure_is_reported_without_revealing_destination():
    s = CampaignCompiler().compile(scheduled())
    s.game_time = 300
    events = []
    WorldService.advance(s, events)
    assert any(e.get("kind") == "world_movement" for e in events)
    assert "far_room" not in json.dumps(events) and "Дальний зал" not in json.dumps(
        events, ensure_ascii=False
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda d: setattr(d.schedules[0], "actor_id", "missing"),
        lambda d: setattr(d.schedules[0], "destination_id", "missing"),
        lambda d: setattr(d.schedules[0], "after_quest", "missing"),
        lambda d: setattr(d.schedules[0], "actor_id", "traveler"),
        lambda d: d.locations[0].travel_minutes.update(far_room=10),
    ],
)
def test_invalid_schedules_and_travel_are_rejected_by_compiler(change):
    d = scheduled()
    change(d)
    with pytest.raises(CampaignValidationError):
        CampaignCompiler().compile(d)


def test_reference_validator_reports_all_new_reference_errors():
    d = scheduled()
    d.schedules[0].actor_id = "no_actor"
    d.schedules[0].destination_id = "no_place"
    d.schedules[0].after_quest = "no_quest"
    with pytest.raises(CampaignValidationError) as failure:
        CampaignCompiler().compile(d)
    assert {i.field for i in failure.value.issues} >= {
        "actor_id",
        "destination_id",
        "after_quest",
    }


def test_schedule_waits_for_quest_and_unfinished_encounter():
    d = scheduled()
    d.schedules[0].actor_id = "sentinel"
    d.schedules[0].after_quest = d.quests[0].id
    s = CampaignCompiler().compile(d)
    s.game_time = 900
    WorldService.advance(s, [])
    assert not s.completed_schedules
    s.quests[d.quests[0].id] = "completed"
    WorldService.advance(s, [])
    assert not s.completed_schedules
    s.completed_encounters = [d.encounters[0].id]
    WorldService.advance(s, [])
    assert s.actor("sentinel").location == "far_room"


def test_reputation_is_awarded_once_and_only_known_factions_are_public():
    s = CampaignCompiler().compile(fantasy())
    s.quests[s.definition.quests[0].id] = "completed"
    WorldService.advance(s, [])
    before = s.faction_reputation.copy()
    WorldService.advance(s, [])
    assert before == s.faction_reputation and list(before.values()) == [1]
    assert "wardens" not in {f["id"] for f in public_state(s)["factions"]}


def expansion():
    npc = fantasy().creatures[0].model_dump()
    npc.update(
        id="new_guard",
        name="Новый страж",
        location_id="new_hall",
        faction_id="new_faction",
        knowledge=["new_secret"],
    )
    return CampaignMutation.model_validate(
        {
            "operations": [
                {
                    "type": "CreateRegion",
                    "value": {"id": "new_region", "name": "Новый край"},
                },
                {
                    "type": "CreateLocation",
                    "value": {
                        "id": "new_hall",
                        "name": "Новый зал",
                        "region_id": "new_region",
                    },
                },
                {"type": "ConnectLocations", "first": "market", "second": "new_hall"},
                {
                    "type": "CreateFaction",
                    "value": {"id": "new_faction", "name": "Новая фракция"},
                },
                {
                    "type": "DefineFactionRelation",
                    "value": {
                        "first": "seekers",
                        "second": "new_faction",
                        "relation": "HOSTILE",
                    },
                },
                {
                    "type": "CreateSecret",
                    "value": {
                        "id": "new_secret",
                        "name": "Новая тайна",
                        "description": "NEW_PRIVATE_SECRET",
                        "location_id": "new_hall",
                        "disclosure": "never",
                    },
                },
                {"type": "CreateNPC", "value": npc},
                {
                    "type": "CreateSchedule",
                    "value": {
                        "id": "new_route",
                        "name": "Маршрут",
                        "actor_id": "new_guard",
                        "destination_id": "market",
                        "delay_minutes": 20,
                    },
                },
                {
                    "type": "CreateEncounter",
                    "value": {
                        "id": "new_fight",
                        "name": "Новый бой",
                        "location_id": "new_hall",
                        "participants": ["new_guard"],
                    },
                },
            ]
        }
    )


def test_expansion_can_make_real_hostile_region_without_resetting_hero():
    s = CampaignCompiler().compile(fantasy())
    s.actor("traveler").xp = 300
    s, _ = runtime().execute(s, Command(type="level_up"))
    before = s.actor("traveler").model_dump_json()
    s = CampaignCompiler().extend(s, expansion())
    assert s.actor("traveler").model_dump_json() == before
    assert s.hostile("traveler", "new_guard") and s.schedule_due["new_route"] == 1200
    assert "NEW_PRIVATE_SECRET" not in json.dumps(public_state(s))
    r = runtime(20, 1)
    s, _ = r.execute(s, Command(type="move", target="new_hall"))
    s, _ = r.execute(s, Command(type="start_encounter", target="new_fight"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.encounter and "new_guard" in s.encounter.order


def test_expansion_cannot_rewrite_old_relations_or_schedule_old_npc():
    s = CampaignCompiler().compile(fantasy())
    before = s.model_dump_json()
    for op in [
        {
            "type": "DefineFactionRelation",
            "value": {"first": "seekers", "second": "wardens", "relation": "ALLY"},
        },
        {
            "type": "CreateSchedule",
            "value": {
                "id": "control_old",
                "name": "Приказ",
                "actor_id": "archivist",
                "destination_id": "vault",
                "delay_minutes": 1,
            },
        },
    ]:
        with pytest.raises(ValueError):
            CampaignCompiler().extend(
                s, CampaignMutation.model_validate({"operations": [op]})
            )
        assert s.model_dump_json() == before


def test_authoring_context_excludes_level_tables_and_high_level_spells():
    rules = CampaignCompiler().compile(fantasy()).ruleset
    catalog = authoring_catalog(rules)
    assert "levels" not in catalog and "condition_definitions" not in catalog
    assert all(spell["level"] <= 1 for spell in catalog["spells"].values())
    assert "fighter" in catalog["classes"]
