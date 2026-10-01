"""Feature authority, tactical action economy and durable mechanical resolution."""

import pytest
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.models import Command, GameState
from backend.tabletop.conditions import ConditionEngine
from backend.tabletop.projection import public_state
from backend.tabletop.ai import GameAI
from test_tabletop_creator import fantasy, build_for
from test_tabletop import runtime, api


def combat(cls="fighter"):
    s = CampaignCompiler().compile(fantasy(), build_for(cls))
    r = runtime(20, 1)
    s, _ = r.execute(s, Command(type="move", target="vault"))
    s, _ = r.execute(s, Command(type="start_encounter"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    # A second controlled actor lets tests inspect turn boundaries without extra AI RNG.
    s.controllers["sentinel"].controller = "PLAYER"
    s.controllers["sentinel"].player_id = "local"
    return s


def test_second_wind_cost_healing_and_atomic_resource_failure():
    s = combat()
    s.actor("traveler").hp = 1
    r = runtime()
    next_state, events = r.execute(
        s, Command(type="use_feature", feature_id="second_wind")
    )
    assert next_state.actor("traveler").hp == 7
    assert next_state.actor("traveler").resources["SECOND_WIND"] == 0
    assert next_state.encounter.action and not next_state.encounter.bonus_action
    assert (
        s.actor("traveler").hp == 1
        and s.actor("traveler").resources["SECOND_WIND"] == 1
    )
    before = next_state.model_dump_json()
    with pytest.raises(ValueError):
        r.execute(next_state, Command(type="use_feature", feature_id="second_wind"))
    assert next_state.model_dump_json() == before
    assert any(e.get("kind") == "feature" for e in events)


@pytest.mark.parametrize(
    "fid,target",
    [
        ("rage", ""),
        ("martial_training", ""),
        ("second_wind", "sentinel"),
        ("not_real", ""),
    ],
)
def test_invalid_feature_does_not_spend_anything(fid, target):
    s = combat()
    before = s.model_dump_json()
    with pytest.raises(ValueError):
        runtime().execute(s, Command(type="use_feature", feature_id=fid, target=target))
    assert s.model_dump_json() == before


def test_rest_recharges_features_and_keeps_long_rest_resources():
    s = CampaignCompiler().compile(fantasy(), build_for())
    s.actor("traveler").resources["SECOND_WIND"] = 0
    s, _ = runtime().execute(s, Command(type="rest", rest="short"))
    assert s.actor("traveler").resources["SECOND_WIND"] == 1
    s.actor("traveler").resources["SECOND_WIND"] = 0
    s, _ = runtime().execute(s, Command(type="rest", rest="short"))
    assert s.actor("traveler").resources["SECOND_WIND"] == 1
    s = CampaignCompiler().compile(fantasy(), build_for("barbarian"))
    s.actor("traveler").resources["RAGE"] = 0
    s, _ = runtime().execute(s, Command(type="rest", rest="short"))
    assert s.actor("traveler").resources["RAGE"] == 0
    s, _ = runtime().execute(s, Command(type="rest", rest="long"))
    assert s.actor("traveler").resources["RAGE"] == 2


def test_rage_changes_damage_and_expires_at_encounter_end():
    s = combat("barbarian")
    r = runtime()
    s, _ = r.execute(s, Command(type="use_feature", feature_id="rage"))
    a = s.actor("traveler")
    weapon = next(iter(a.attacks))
    assert (
        r.rules.damage_modifier(a, weapon, s.ruleset)
        == r.rules.modifier(a.abilities[a.attacks[weapon].ability]) + 2
    )
    before = a.hp
    r.combat.damage(s, a, 7, False, [])
    assert a.hp == before - 3
    s.actor("sentinel").conditions = ["surrendered"]
    r.combat.ended(s, [])
    assert not s.encounter and "rage" not in a.conditions


def test_cunning_action_uses_bonus_and_preserves_action():
    s = combat("rogue")
    movement = s.encounter.movement
    s, _ = runtime().execute(s, Command(type="use_feature", feature_id="cunning_dash"))
    assert s.encounter.movement == movement * 2
    assert s.encounter.action and not s.encounter.bonus_action


@pytest.mark.parametrize(
    "conditions,target_conditions,expected",
    [
        (["helped"], [], 1),
        (["poisoned"], [], -1),
        (["helped", "focused", "poisoned"], [], 0),
        ([], ["dodge"], -1),
        (["hidden"], ["dodge"], 0),
        ([], ["prone"], 1),
    ],
)
def test_advantage_sources_cancel_and_are_projected(
    conditions, target_conditions, expected
):
    s = combat()
    s.actor("traveler").conditions = conditions
    s.actor("sentinel").conditions = target_conditions
    s, _ = runtime().execute(s, Command(type="attack", target="sentinel"))
    pending = s.session_state.pending
    assert pending.advantage == expected and pending.advantage_sources
    assert public_state(s)["pending"]["advantage_sources"] == pending.advantage_sources
    assert "helped" not in s.actor("traveler").conditions
    # Pending modifiers survive serialized restart.
    assert (
        GameState.model_validate_json(s.model_dump_json()).session_state.pending
        == pending
    )


@pytest.mark.parametrize(
    "condition,command",
    [
        ("stunned", Command(type="attack", target="sentinel")),
        ("grappled", Command(type="move", distance=5)),
        ("restrained", Command(type="move", distance=5)),
    ],
)
def test_condition_effects_restrict_actions_and_movement(condition, command):
    s = combat()
    s.actor("traveler").conditions = [condition]
    before = s.model_dump_json()
    with pytest.raises(ValueError):
        runtime().execute(s, command)
    assert s.model_dump_json() == before


@pytest.mark.parametrize(
    "maneuver,condition", [("grapple", "grappled"), ("shove", "prone")]
)
def test_maneuver_requires_roll_and_applies_only_after_success(maneuver, condition):
    s = combat()
    r = runtime(20)
    s, _ = r.execute(s, Command(type=maneuver, target="sentinel"))
    assert condition not in s.actor("sentinel").conditions
    assert not s.encounter.action and s.session_state.pending.outcome == maneuver
    s = GameState.model_validate_json(s.model_dump_json())
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert condition in s.actor("sentinel").conditions
    if condition == "grappled":
        assert s.actor("sentinel").condition_sources[condition] == "traveler"


def test_hide_requires_distance_and_success_then_expires_on_attack():
    s = combat()
    with pytest.raises(ValueError):
        runtime().execute(s, Command(type="hide"))
    s.actor("sentinel").position = 15
    r = runtime(20)
    s, _ = r.execute(s, Command(type="hide"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert "hidden" in s.actor("traveler").conditions
    s.encounter.action = True
    s.actor("sentinel").position = 5
    s, _ = r.execute(s, Command(type="attack", target="sentinel"))
    assert s.session_state.pending.advantage == 1
    assert "hidden" not in s.actor("traveler").conditions


def test_ready_survives_reload_triggers_reaction_and_cannot_duplicate():
    s = combat()
    r = runtime(1)
    s, _ = r.execute(s, Command(type="ready", target="sentinel"))
    assert not s.encounter.action and s.encounter.ready == {"traveler": "sentinel"}
    s = GameState.model_validate_json(s.model_dump_json())
    s, _ = r.execute(s, Command(type="end_turn"))
    assert s.session_state.reaction["actor"] == "traveler"
    s, _ = r.execute(s, Command(type="reaction_attack", actor_id="traveler"))
    assert not s.encounter.reaction["traveler"]
    pid = s.session_state.pending.id
    s, _ = r.resolve_roll(s, pid)
    assert not s.session_state.reaction and not s.encounter.ready
    with pytest.raises(ValueError):
        r.resolve_roll(s, pid)


def test_free_interaction_then_action_and_failure_are_atomic():
    s = combat()
    r = runtime()
    s, _ = r.execute(s, Command(type="unequip", item_id="sword"))
    assert s.encounter.action and not s.encounter.free_interaction
    s, _ = r.execute(s, Command(type="equip", item_id="sword"))
    assert not s.encounter.action
    before = s.model_dump_json()
    with pytest.raises(ValueError):
        r.execute(s, Command(type="unequip", item_id="sword"))
    assert s.model_dump_json() == before


def test_ai_feature_decision_is_pure_and_uses_shared_service():
    s = combat()
    s.encounter.index = 1
    enemy = s.actor("sentinel")
    enemy.hp = 1
    enemy.morale = 1
    before = s.model_dump_json()
    decision = GameAI().decision(s, enemy.id)
    assert decision.behavior == "UseFeature"
    assert s.model_dump_json() == before
    events = []
    runtime().apply(s, decision.command, enemy.id, events)
    assert enemy.hp > 1 and enemy.resources["SECOND_WIND"] == 0


def test_feature_http_idempotency_stale_revision_restart_replay_rollback(api):
    from backend.tabletop.repository import TabletopRepository
    from test_tabletop import send

    c, app = api
    draft = c.post(
        "/api/tabletop/drafts", json={"definition": fantasy().model_dump()}
    ).json()
    response = c.post(
        "/api/tabletop/games",
        json={
            "draft_id": draft["id"],
            "draft_revision": draft["revision"],
            "character": build_for().model_dump(),
        },
    )
    assert response.status_code == 200, response.text
    g = response.json()
    body = {
        "revision": g["revision"],
        "request_id": "one-feature",
        "command": {"type": "use_feature", "feature_id": "second_wind"},
    }
    path = f"/api/tabletop/games/{g['id']}/actions"
    first = c.post(path, json=body)
    duplicate = c.post(path, json=body)
    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json()
    assert c.post(path, json={**body, "request_id": "stale-feature"}).status_code == 409
    g = first.json()
    assert g["state"]["characters"]["traveler"]["resources"]["SECOND_WIND"] == 0
    repo = TabletopRepository(app.state.repository.path)
    assert repo.load(g["id"])[1].actor("traveler").resources["SECOND_WIND"] == 0
    assert (
        repo.replay(g["id"], g["revision"]).actor("traveler").resources["SECOND_WIND"]
        == 0
    )
    undone = send(c, g, "rollback").json()
    assert undone["state"]["characters"]["traveler"]["resources"]["SECOND_WIND"] == 1
