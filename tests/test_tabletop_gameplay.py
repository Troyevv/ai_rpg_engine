import pytest
from backend.tabletop.catalog import load_ruleset
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.definitions import (
    CharacterBuild,
    CharacterDefinition,
    InventoryEntry,
    SceneCheck,
    CheckEffect,
)
from backend.tabletop.rules import RulesEngine
from backend.tabletop.dice import DiceEngine
from backend.tabletop.models import Command
from test_tabletop import Fixed, runtime
from test_tabletop_creator import fantasy


def rules():
    return load_ruleset("d20-fantasy-v2")


def build(cls="fighter", purchases=None):
    r = rules()
    c = r.classes[cls]
    return CharacterBuild(
        character_class=cls,
        ability_method="allocation",
        abilities=dict(
            strength=15,
            dexterity=13,
            constitution=14,
            intelligence=10,
            wisdom=12,
            charisma=8,
        ),
        skills=c["skills"][: c["skill_count"]],
        feature_choices=c.get("feature_choices", [])[
            : c.get("feature_choice_count", 0)
        ],
        purchases=purchases or [],
    )


def character(b=None, preview=False):
    r = rules()
    e = RulesEngine()
    a = e.build_character(
        CharacterDefinition(
            id="hero",
            name="Hero",
            location_id="room",
            faction_id="heroes",
            build=b or build(),
        ),
        r,
        preview=preview,
    )
    e.equipment_stats(a, {i.id: i for i in r.items})
    return a


def test_allocation_requires_exact_budget_but_preview_accepts_initial_fives():
    b = build()
    b.abilities = {a: 5 for a in rules().abilities}
    assert RulesEngine.allocation_remaining(b.abilities, rules()) == 42
    character(b, preview=True)
    with pytest.raises(ValueError):
        character(b)
    b.abilities["strength"] = 19
    with pytest.raises(ValueError):
        character(b, preview=True)


@pytest.mark.parametrize(
    "cls",
    [
        "fighter",
        "barbarian",
        "rogue",
        "ranger",
        "paladin",
        "cleric",
        "druid",
        "wizard",
        "sorcerer",
        "warlock",
        "bard",
        "monk",
    ],
)
def test_every_class_has_working_build_features_and_progression(cls):
    a = character(build(cls))
    r = rules()
    assert a.features and any(r.features[f].activation != "PASSIVE" for f in a.features)
    assert len(r.subclasses[cls]) >= 2
    assert all(str(n) in r.levels for n in range(2, 21))
    assert any(r.levels[str(n)].features.get(cls) for n in range(2, 21))


def test_shop_remainder_slots_and_overspending():
    a = character(
        build(
            purchases=[
                InventoryEntry(item_id="dagger", equipped=True, slot="MAIN_HAND")
            ]
        )
    )
    assert a.gold == 155 and a.attacks["dagger"]
    a = character(
        build(
            purchases=[
                InventoryEntry(item_id="chain", equipped=True, slot="TORSO"),
                InventoryEntry(item_id="shield", equipped=True, slot="OFF_HAND"),
            ]
        )
    )
    assert a.armor_class == 19  # defense style +1
    assert a.equipment_bonuses["stealth_disadvantage"] == 1
    with pytest.raises(ValueError):
        character(build(purchases=[InventoryEntry(item_id="ring", quantity=3)]))
    with pytest.raises(ValueError):
        character(
            build(
                purchases=[
                    InventoryEntry(item_id="bow", equipped=True, slot="MAIN_HAND"),
                    InventoryEntry(item_id="shield", equipped=True, slot="OFF_HAND"),
                ]
            )
        )


@pytest.mark.parametrize(
    "expression,values,total",
    [
        ("1d20+4+1d4", [12, 3], 19),
        ("2d8+1d6+4", [2, 8, 6], 20),
        ("d20-1d4", [15, 2], 13),
    ],
)
def test_compound_dice(expression, values, total):
    result = DiceEngine(Fixed(*values)).roll(expression)
    assert result.total == total and result.components


def test_scene_check_has_real_persistent_consequences():
    d = fantasy()
    d.checks = [
        SceneCheck(
            id="runes",
            name="Руны",
            location_id="market",
            category="knowledge",
            ability="intelligence",
            skill="arcana",
            success=[
                CheckEffect(type="attitude", target="archivist", attitude="friendly")
            ],
            failure=[CheckEffect(type="damage", amount=3)],
        )
    ]
    s = CampaignCompiler().compile(d)
    r = runtime(1)
    s, events = r.execute(s, Command(type="check", check_id="runes"))
    before = s.actor("traveler").hp
    s, events = r.resolve_roll(s, s.session_state.pending.id)
    assert (
        s.actor("traveler").hp == before - 3 and s.resolved_checks["runes"] == "FAILURE"
    )
    with pytest.raises(ValueError):
        r.execute(s, Command(type="check", check_id="runes"))


def test_attack_preview_enumerates_advantage_and_never_mutates():
    from tabletop_fixture import state
    from backend.tabletop.models import Encounter
    from backend.tabletop.preview import attack_previews

    s = state()
    a = s.actor("traveler")
    a.location = "vault"
    a.position = 0
    s.encounters["guard_battle"] = Encounter(
        definition_id="guard_battle",
        order=["traveler", "sentinel"],
        initiative={"traveler": 20, "sentinel": 1},
        reaction={"traveler": True, "sentinel": True},
    )
    s.active_encounter = "guard_battle"
    original = s.model_dump()
    normal = attack_previews(s, a)[0]
    assert s.model_dump() == original and normal["available"]
    p = normal["hit_percent"] / 100
    a.conditions.append("helped")
    advantage = attack_previews(s, a)[0]
    assert advantage["hit_percent"] == pytest.approx(100 * (1 - (1 - p) ** 2))
    s.actor("sentinel").conditions.append("dodge")
    assert attack_previews(s, a)[0]["hit_percent"] == normal["hit_percent"]
    a.position = -100
    assert not attack_previews(s, a)[0]["available"]


def test_feature_healing_is_pending_and_consumes_bonus_once():
    from tabletop_gameplay_fixture import gameplay_definition

    s = CampaignCompiler().compile(gameplay_definition(), build())
    r = runtime(5)
    a = s.actor("traveler")
    a.hp = 2
    s, events = r.execute(s, Command(type="use_feature", feature_id="second_wind"))
    assert s.session_state.pending.purpose == "feature_healing"
    assert (
        s.actor("traveler").hp == 2
        and s.actor("traveler").resources["SECOND_WIND"] == 0
    )
    s, events = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("traveler").hp == 8
    assert events[-1]["hp_before"] == 2 and events[-1]["hp_after"] == 8


def test_passive_discovery_and_critical_degree_are_engine_owned():
    from tabletop_gameplay_fixture import gameplay_definition

    d = gameplay_definition()
    d.checks[0].passive = True
    d.checks[0].skill = "perception"
    d.checks[0].ability = "wisdom"
    d.checks[0].difficulty = "TRIVIAL"
    d.checks[1].critical_failure = [CheckEffect(type="alert", target="archivist")]
    s = CampaignCompiler().compile(d, build())
    r = runtime(1)
    s, _ = r.execute(s, Command(type="look"))
    assert "room_clue" in s.player_knowledge and s.session_state.pending is None
    s, _ = r.execute(s, Command(type="check", check_id="deception_check"))
    s, events = r.resolve_roll(s, s.session_state.pending.id)
    assert s.resolved_checks["deception_check"] == "CRITICAL_FAILURE"
    assert "archivist" in s.alerted_actors
    assert next(e for e in events if e.get("roll"))["outcome"] == "CRITICAL_FAILURE"


def test_usable_targets_share_validation_without_spending():
    from tabletop_gameplay_fixture import gameplay_definition
    from backend.tabletop.preview import usable_actions

    s = CampaignCompiler().compile(gameplay_definition(), build("paladin"))
    before = s.model_dump()
    actions = usable_actions(s, s.actor("traveler"))
    assert any(a["kind"] == "feature" for a in actions)
    assert s.model_dump() == before
    assert all(t["id"] != "sentinel" for a in actions for t in a["targets"])
