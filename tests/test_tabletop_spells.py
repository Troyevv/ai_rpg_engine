"""Spell slots and canonical multi-roll casting, including concentration and replay."""

import pytest
from backend.tabletop.models import Command, GameState
from backend.tabletop.spells import SpellSlotState
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.ai import GameAI
from test_tabletop import runtime, api, send
from test_tabletop_creator import fantasy, build_for
from test_tabletop_combat_features import combat


def test_cantrip_attack_damage_restart_and_no_slot_cost():
    s = combat("wizard")
    r = runtime(18, 5)
    slots = s.actor("traveler").spell_slots.copy()
    before = s.actor("sentinel").hp
    s, _ = r.execute(
        s, Command(type="cast_spell", spell_id="fire_bolt", target="sentinel")
    )
    assert s.session_state.pending.purpose == "spell_attack"
    assert not s.session_state.mechanical_resolution_complete
    s = GameState.model_validate_json(s.model_dump_json())
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.purpose == "spell_damage"
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("sentinel").hp == before - 5
    assert (
        not s.session_state.spell_cast
        and s.session_state.mechanical_resolution_complete
    )
    assert s.actor("traveler").spell_slots == slots


def test_spell_miss_has_no_damage_roll():
    s, _ = runtime().execute(
        combat("wizard"),
        Command(type="cast_spell", spell_id="fire_bolt", target="sentinel"),
    )
    s, _ = runtime(1).resolve_roll(s, s.session_state.pending.id)
    assert not s.session_state.pending and not s.session_state.spell_cast


def test_spell_slot_spent_once_upcast_and_critical_dice():
    s = combat("wizard")
    a = s.actor("traveler")
    a.spell_slots["2"] = SpellSlotState(maximum=1, remaining=1)
    s, _ = runtime().execute(
        s,
        Command(
            type="cast_spell", spell_id="magic_missile", target="sentinel", slot_level=2
        ),
    )
    assert s.actor("traveler").spell_slots["2"].remaining == 0
    assert s.session_state.pending.expression == "4d4+3"
    s = GameState.model_validate_json(s.model_dump_json())
    s, _ = runtime(1, 1, 1, 1).resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").spell_slots["2"].remaining == 0
    s = combat("wizard")
    r = runtime(20, 4, 5)
    s, _ = r.execute(
        s, Command(type="cast_spell", spell_id="fire_bolt", target="sentinel")
    )
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.critical
    s, events = r.resolve_roll(s, s.session_state.pending.id)
    assert next(e["roll"] for e in events if "roll" in e)["raw"] == [4, 5]


@pytest.mark.parametrize(
    "change,command",
    [
        (
            lambda s: None,
            Command(type="cast_spell", spell_id="fireball", target="sentinel"),
        ),
        (
            lambda s: s.actor("traveler").prepared_spells.clear(),
            Command(type="cast_spell", spell_id="magic_missile", target="sentinel"),
        ),
        (
            lambda s: setattr(s.actor("sentinel"), "position", 200),
            Command(type="cast_spell", spell_id="fire_bolt", target="sentinel"),
        ),
        (
            lambda s: setattr(s.actor("traveler").spell_slots["1"], "remaining", 0),
            Command(type="cast_spell", spell_id="magic_missile", target="sentinel"),
        ),
        (
            lambda s: None,
            Command(type="cast_spell", spell_id="fire_bolt", target="traveler"),
        ),
        (
            lambda s: None,
            Command(
                type="cast_spell", spell_id="fire_bolt", target="sentinel", slot_level=1
            ),
        ),
    ],
)
def test_invalid_cast_leaves_everything_unchanged(change, command):
    s = combat("wizard")
    change(s)
    before = s.model_dump_json()
    with pytest.raises(ValueError):
        runtime().execute(s, command)
    assert s.model_dump_json() == before


def test_area_save_queue_includes_allies_and_resumes_after_reload():
    s = combat("wizard")
    s.actor("traveler").hp = s.actor("traveler").max_hp = 100
    s.actor("sentinel").hp = s.actor("sentinel").max_hp = 100
    r = runtime(20, 2, 2, 2, 1, 2, 2, 2)
    s, _ = r.execute(
        s, Command(type="cast_spell", spell_id="burning_hands", target="sentinel")
    )
    assert (
        s.session_state.pending.actor == "traveler"
        and s.session_state.pending.purpose == "spell_save"
    )
    while s.session_state.pending:
        s = GameState.model_validate_json(s.model_dump_json())
        s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").hp == 97
    assert s.actor("sentinel").hp == 94
    assert s.actor("traveler").spell_slots["1"].remaining == 1


def test_healing_word_bonus_and_long_rest_restore_slots():
    s = combat("cleric")
    s.actor("traveler").hp = 1
    r = runtime(4)
    s, _ = r.execute(
        s, Command(type="cast_spell", spell_id="healing_word", target="traveler")
    )
    assert s.encounter.action and not s.encounter.bonus_action
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").hp > 1
    s.active_encounter = None
    s.session_state.mode = "EXPLORATION"
    s, _ = r.execute(s, Command(type="rest", rest="long"))
    assert s.actor("traveler").spell_slots["1"].remaining == 2


def test_concentration_real_bonus_damage_save_failure_and_expiry():
    s = combat("cleric")
    s.actor("traveler").prepared_spells = ["bless"]
    r = runtime(1)
    before = r.rules.attack_modifier(
        s.actor("traveler"), next(iter(s.actor("traveler").attacks))
    )
    s, _ = r.execute(s, Command(type="cast_spell", spell_id="bless", target="traveler"))
    a = s.actor("traveler")
    assert a.concentration and "blessed" in a.conditions
    assert r.rules.attack_modifier(a, next(iter(a.attacks))) == before + 1
    r.combat.damage(s, a, 2, False, [])
    r.spells_service.resume(s, [])
    assert s.session_state.pending.purpose == "concentration"
    s = GameState.model_validate_json(s.model_dump_json())
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert (
        not s.actor("traveler").concentration
        and "blessed" not in s.actor("traveler").conditions
    )
    s.encounter.action = True
    s, _ = r.execute(s, Command(type="cast_spell", spell_id="bless", target="traveler"))
    s.game_time += 60
    r.spells_service.resume(s, [])
    assert not s.actor("traveler").concentration


def test_preparation_and_build_spell_boundaries():
    build = build_for("wizard")
    build.spells = ["fireball"]
    with pytest.raises(ValueError):
        CampaignCompiler().compile(fantasy(), build)
    s = CampaignCompiler().compile(fantasy(), build_for("wizard"))
    s, _ = runtime().execute(
        s, Command(type="prepare_spells", spells=["burning_hands"])
    )
    assert s.actor("traveler").prepared_spells == ["burning_hands"]
    with pytest.raises(ValueError):
        runtime().execute(s, Command(type="prepare_spells", spells=["bless"]))


def test_ai_selects_and_executes_spell_via_same_rules():
    s = combat("wizard")
    runtime().apply(s, GameAI().decision(s, "traveler").command, "traveler", [])
    decision = GameAI().decision(s, "traveler")
    assert decision.behavior == "CastSpell"
    s.controllers["traveler"].controller = "AI"
    s.controllers["traveler"].player_id = None
    events = []
    runtime(18, 5).apply(s, decision.command, "traveler", events)
    assert not s.session_state.spell_cast and any(
        e.get("kind") == "damage" for e in events
    )


def test_cast_http_idempotency_durable_pending_and_no_double_slot(api):
    c, app = api
    draft = c.post(
        "/api/tabletop/drafts", json={"definition": fantasy().model_dump()}
    ).json()
    g = c.post(
        "/api/tabletop/games",
        json={
            "draft_id": draft["id"],
            "draft_revision": draft["revision"],
            "character": build_for("cleric").model_dump(),
        },
    ).json()
    body = {
        "revision": g["revision"],
        "request_id": "cast-once",
        "command": {
            "type": "cast_spell",
            "spell_id": "cure_wounds",
            "target": "traveler",
        },
    }
    path = f"/api/tabletop/games/{g['id']}/actions"
    one = c.post(path, json=body)
    two = c.post(path, json=body)
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    assert (
        one.json()["state"]["characters"]["traveler"]["spell_slots"]["1"]["remaining"]
        == 1
    )
    assert one.json()["state"]["pending"]["purpose"] == "spell_healing"
