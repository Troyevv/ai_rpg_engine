"""No arbitrary XP command; earned progression and validated level choices."""

import pytest
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.models import Command, GameState
from backend.tabletop.services.progression import ProgressionService
from backend.tabletop.repository import TabletopRepository
from test_tabletop import runtime, api, send
from test_tabletop_creator import fantasy, build_for
from test_tabletop_combat_features import combat


def character(cls="fighter"):
    return CampaignCompiler().compile(fantasy(), build_for(cls))


def next_command(s, feat=""):
    a = s.actor("traveler")
    o = ProgressionService.options(s, a)
    return Command(
        type="level_up",
        subclass=o["subclasses"][0]["id"] if o.get("subclasses") else "",
        feat_id=feat,
        ability_increases=(
            [] if feat or not o.get("asi") else ["constitution", "constitution"]
        ),
        learn_spells=[v["id"] for v in o.get("spells", [])][: o.get("learn_spells", 0)],
    )


@pytest.mark.parametrize(
    "cls", ["fighter", "rogue", "ranger", "barbarian", "cleric", "wizard"]
)
def test_all_six_classes_progress_1_to_20_with_persistent_features(cls):
    s = character(cls)
    r = runtime()
    s.actor("traveler").xp = 355000
    while s.actor("traveler").level < 20:
        before = s.actor("traveler").model_copy(deep=True)
        command = next_command(s)
        if before.abilities["constitution"] >= 20 and command.ability_increases:
            command.ability_increases = ["wisdom", "wisdom"]
        s, _ = r.execute(s, command)
        a = s.actor("traveler")
        assert a.level == before.level + 1 and a.max_hp > before.max_hp
        assert len(a.features) == len(set(a.features))
        assert a.proficiency_bonus == 2 + (a.level - 1) // 4
        assert set(before.features) <= set(a.features)
        s = GameState.model_validate_json(s.model_dump_json())
    assert a.level == 20 and a.subclass and a.proficiency_bonus == 6
    if cls in ("wizard", "cleric"):
        assert "9" in a.spell_slots
    if cls == "ranger":
        assert "5" in a.spell_slots and "6" not in a.spell_slots
    with pytest.raises(ValueError):
        r.execute(s, Command(type="level_up"))


def test_completion_rewards_are_earned_once_and_milestone_is_independent():
    s = character()
    r = runtime()
    s.campaign.progression_mode = "milestone"
    s.completed_encounters = ["archive_guard"]
    # use actual catalog IDs rather than relying on names
    s.completed_encounters = [s.definition.encounters[0].id]
    events = []
    r.progression_service.reconcile(s, events)
    assert s.actor("traveler").xp == 150
    assert not ProgressionService.options(s, s.actor("traveler"))["available"]
    s.quests[s.definition.quests[0].id] = "completed"
    r.progression_service.reconcile(s, events)
    assert s.actor("traveler").xp == 450 and s.actor("traveler").milestones == 1
    assert ProgressionService.options(s, s.actor("traveler"))["available"]
    before = s.model_dump_json()
    r.progression_service.reconcile(s, events)
    assert before == s.model_dump_json()
    s, _ = r.execute(s, Command(type="level_up"))
    assert not ProgressionService.options(s, s.actor("traveler"))["available"]


@pytest.mark.parametrize(
    "command",
    [
        Command(type="level_up"),
        Command(type="level_up", feat_id="tough"),
        Command(type="level_up", subclass="fighter_path_1"),
    ],
)
def test_unearned_level_is_atomic(command):
    s = character()
    before = s.model_dump_json()
    with pytest.raises(ValueError):
        runtime().execute(s, command)
    assert s.model_dump_json() == before


def test_subclass_asi_feat_and_spell_choices_are_validated():
    s = character()
    s.actor("traveler").xp = 100000
    r = runtime()
    s, _ = r.execute(s, Command(type="level_up"))
    with pytest.raises(ValueError):
        r.execute(s, Command(type="level_up", subclass="wizard_path_1"))
    s, _ = r.execute(s, next_command(s))
    old = s.actor("traveler").max_hp
    s, _ = r.execute(s, next_command(s, feat="tough"))
    assert s.actor("traveler").max_hp == old + 8 + 6
    assert s.actor("traveler").feats == ["tough"]
    with pytest.raises(ValueError):
        r.execute(
            s, Command(type="level_up", ability_increases=["strength", "strength"])
        )
    with pytest.raises(ValueError):
        r.execute(s, Command(type="level_up", learn_spells=["fireball"]))
    while s.actor("traveler").level < 7:
        s, _ = r.execute(s, next_command(s))
    with pytest.raises(ValueError):
        r.execute(s, next_command(s, feat="tough"))


def test_constitution_increase_is_retroactive_once_and_does_not_reset_hp():
    s = character()
    s.actor("traveler").xp = 2700
    r = runtime()
    s, _ = r.execute(s, next_command(s))
    s, _ = r.execute(s, next_command(s))
    a = s.actor("traveler")
    before = a.max_hp
    a.hp = 1
    s, _ = r.execute(s, next_command(s))
    assert s.actor("traveler").max_hp == before + 9 + 3
    assert s.actor("traveler").hp == 1 + 9 + 3
    with pytest.raises(ValueError):
        r.execute(s, next_command(s))


def test_slots_preserve_spent_slots_on_level_up_and_high_spells_need_level():
    s = character("wizard")
    s.actor("traveler").xp = 900
    r = runtime()
    s.actor("traveler").spell_slots["1"].remaining = 0
    s, _ = r.execute(s, Command(type="level_up"))
    assert s.actor("traveler").spell_slots["1"].remaining == 2
    with pytest.raises(ValueError):
        r.execute(
            s,
            Command(
                type="level_up", subclass="wizard_path_1", learn_spells=["fireball"]
            ),
        )
    s, _ = r.execute(
        s,
        Command(
            type="level_up", subclass="wizard_path_1", learn_spells=["scorching_ray"]
        ),
    )
    assert (
        "scorching_ray" in s.actor("traveler").spells
        and s.actor("traveler").spell_slots["2"].remaining == 2
    )


def test_extra_attack_uses_one_action_and_stops_after_allowed_count():
    s = character()
    s.actor("traveler").xp = 6500
    r = runtime()
    while s.actor("traveler").level < 5:
        s, _ = r.execute(s, next_command(s))
    r = runtime(20, 1, 1, 1)
    s, _ = r.execute(s, Command(type="move", target="vault"))
    s, _ = r.execute(s, Command(type="start_encounter"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    s, _ = r.execute(s, Command(type="attack", target="sentinel"))
    assert not s.encounter.action and s.encounter.attacks_remaining == 1
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    s, _ = r.execute(s, Command(type="attack", target="sentinel"))
    assert s.encounter.attacks_remaining == 0
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    with pytest.raises(ValueError):
        r.execute(s, Command(type="attack", target="sentinel"))


def test_level_up_http_duplicate_restart_replay_and_rollback(api):
    c, app = api
    s = character()
    s.actor("traveler").xp = 300
    repo = TabletopRepository(app.state.repository.path)
    gid = repo.create(s)
    g = c.get("/api/tabletop/games/" + gid).json()
    first = send(c, g, command={"type": "level_up"})
    second = send(c, g, command={"type": "level_up"})
    assert (
        first.status_code == second.status_code == 200 and first.json() == second.json()
    )
    assert (
        TabletopRepository(app.state.repository.path)
        .load(gid)[1]
        .actor("traveler")
        .level
        == 2
    )
    assert repo.replay(gid, first.json()["revision"]).actor("traveler").level == 2
    restored = send(c, first.json(), "rollback").json()
    assert restored["state"]["characters"]["traveler"]["level"] == 1
