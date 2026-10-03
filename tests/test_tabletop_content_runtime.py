import pytest
from test_universal_content import campaign
from test_tabletop_combat_features import combat
from test_tabletop import runtime
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.content import (
    ContentItem,
    ResourceDefinition,
    MagazineComponent,
    FiringMode,
)
from backend.tabletop.features import FeatureDefinition
from backend.tabletop.definitions import InventoryEntry
from backend.tabletop.commands import Command
from backend.tabletop.runtime import TabletopRuntime
from backend.tabletop.rules import RulesEngine


def test_item_passive_and_active_grants_are_reversible_without_resource_refill():
    d = campaign()
    c = d.setting_definition.content
    c.resources["PULSE"] = ResourceDefinition(
        id="PULSE", name="Pulse", maximum=1, initial=1
    )
    c.features["lens"] = FeatureDefinition(
        id="lens",
        name="Lens",
        description="Clear view",
        source="ITEM",
        activation="PASSIVE",
        effects=[
            dict(type="check_bonus", key="investigation", value=2),
            dict(type="max_hp", value=3),
        ],
    )
    c.features["pulse"] = FeatureDefinition(
        id="pulse",
        name="Pulse",
        description="Restore",
        source="ITEM",
        activation="ACTION",
        resource="PULSE",
        uses=1,
        effects=[dict(type="heal", value=2)],
    )
    c.items["lens"] = ContentItem(
        id="lens", name="Lens", equipment_slots=["MAIN_HAND"], effects=["lens", "pulse"]
    )
    s = CampaignCompiler().compile(d)
    a = s.actor(s.party[0])
    a.inventory.append(InventoryEntry(item_id="lens"))
    initial = a.max_hp
    before = RulesEngine().check_modifier(a, "intelligence", "investigation", s.ruleset)
    r = TabletopRuntime()
    s, _ = r.execute(s, Command(type="equip", item_id="lens"))
    a = s.actor(s.party[0])
    assert a.max_hp == initial + 3 and "pulse" in a.features
    assert (
        RulesEngine().check_modifier(a, "intelligence", "investigation", s.ruleset)
        == before + 2
    )
    a.hp -= 4
    s, _ = r.execute(s, Command(type="use_feature", feature_id="pulse"))
    assert s.actor(a.id).resources["PULSE"] == 0
    s, _ = r.execute(s, Command(type="unequip", item_id="lens"))
    a = s.actor(a.id)
    assert a.max_hp == initial and "pulse" not in a.features
    assert (
        RulesEngine().check_modifier(a, "intelligence", "investigation", s.ruleset)
        == before
    )
    s, _ = r.execute(s, Command(type="equip", item_id="lens"))
    assert s.actor(a.id).resources["PULSE"] == 0


def test_energy_source_is_finite_across_reload():
    d = campaign()
    c = d.setting_definition.content
    c.resources["charge"] = ResourceDefinition(
        id="charge", name="Charge", maximum=5, initial=0
    )
    c.items["cell"] = ContentItem(
        id="cell",
        name="Cell",
        components=[dict(type="energy", resource_id="charge", capacity=3)],
    )
    s = CampaignCompiler().compile(d)
    a = s.actor(s.party[0])
    a.inventory.append(InventoryEntry(item_id="cell"))
    r = TabletopRuntime()
    s, _ = r.execute(s, Command(type="use_item", item_id="cell"))
    assert s.actor(a.id).resources["charge"] == 3
    s = type(s).model_validate_json(s.model_dump_json())
    s.actor(a.id).resources["charge"] = 0
    with pytest.raises(ValueError, match="нет в инвентаре"):
        r.execute(s, Command(type="use_item", item_id="cell"))


def test_firing_mode_changes_attack_and_damage_and_spends_once():
    s = combat()
    a = s.actor("traveler")
    weapon = next(iter(a.attacks))
    w = a.attacks[weapon]
    w.item_id = weapon
    w.magazine = MagazineComponent(
        ammo_type="bullet",
        capacity=6,
        initial=6,
        modes={"single": 1, "burst": 3},
        mode_effects={
            "burst": FiringMode(
                attack_bonus=-2, damage_bonus=3, damage_expression="2d4"
            )
        },
    )
    a.item_resources[weapon] = 6
    r = runtime(18, 2, 3)
    base = r.rules.attack_modifier(a, weapon)
    s, _ = r.execute(
        s, Command(type="attack", target="sentinel", weapon=weapon, mode="burst")
    )
    assert (
        s.session_state.pending.modifier == base - 2
        and s.actor(a.id).item_resources[weapon] == 3
    )
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.expression == "2d4"
    assert (
        s.session_state.pending.modifier
        == r.rules.damage_modifier(s.actor(a.id), weapon, s.ruleset) + 3
    )
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor(a.id).item_resources[weapon] == 3


@pytest.mark.parametrize("kind", ["attack", "automatic", "save", "area"])
@pytest.mark.parametrize("multiplier", [0, 0.5, 2])
def test_custom_power_damage_all_player_resolution_paths(kind, multiplier):
    s = combat("wizard")
    a = s.actor("traveler")
    target = s.actor("sentinel")
    target.hp = target.max_hp = 100
    spell = s.ruleset.spells["fire_bolt"].model_copy(deep=True)
    spell.id = "custom"
    spell.damage_type = "discord"
    spell.damage = "1d4"
    spell.attack_roll = kind == "attack"
    spell.target_type = "area" if kind == "area" else "enemy"
    spell.area = 5 if kind == "area" else 0
    spell.save = "dexterity" if kind in ("save", "area") else None
    spell.resource_cost = {"voice": 2}
    a.resources["voice"] = 3
    a.spells.append("custom")
    s.ruleset.spells["custom"] = spell
    target.damage_modifiers = {"discord": multiplier}
    a.position = -10
    target.position = 0
    r = (
        runtime(18, 4)
        if kind == "attack"
        else runtime(1, 4) if kind in ("save", "area") else runtime(4)
    )
    s, _ = r.execute(
        s, Command(type="cast_spell", spell_id="custom", target="sentinel")
    )
    while s.session_state.pending:
        s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor("sentinel").hp == 100 - int(4 * multiplier)
    assert s.actor("traveler").resources["voice"] == 1


def test_background_knowledge_contacts_reputation_and_equipment_are_in_runtime():
    d = campaign()
    background = d.setting_definition.content.backgrounds[
        d.characters[0].build.background
    ]
    background.knowledge = ["Голоса сохраняются в стекле."]
    background.contacts = ["Смотритель волн"]
    background.reputation = {"citizens": 12}
    s = CampaignCompiler().compile(d)
    from backend.tabletop.projection import public_state

    public = public_state(s)
    assert public["characters"]["traveler"]["background_contacts"] == [
        "Смотритель волн"
    ]
    assert "Голоса сохраняются в стекле." in public["knowledge"].values()
    assert s.faction_reputation["citizens"] == 12


def test_npc_custom_power_damage_respects_immunity_and_resource_cost():
    s = combat("wizard")
    a = s.actor("traveler")
    a.resources["voice"] = 3
    s.controllers[a.id].controller = "AI"
    s.controllers[a.id].player_id = None
    spell = s.ruleset.spells["fire_bolt"]
    spell.damage_type = "discord"
    spell.resource_cost = {"voice": 2}
    target = s.actor("sentinel")
    target.damage_modifiers = {"discord": 0}
    before = target.hp
    r = runtime(18, 4)
    events = []
    r.spells_service.execute(
        s,
        Command(type="cast_spell", spell_id="fire_bolt", target="sentinel"),
        a.id,
        events,
    )
    assert target.hp == before and a.resources["voice"] == 1


def test_consumable_feature_uses_shared_cost_and_consumes_exactly_one_item():
    from backend.tabletop.definitions import ItemDefinition

    s = combat()
    a = s.actor("traveler")
    a.hp = 1
    s.ruleset.features["medical_pulse"] = FeatureDefinition(
        id="medical_pulse",
        name="Pulse",
        description="Heal",
        activation="ACTION",
        effects=[dict(type="heal", value=2)],
    )
    s.items["medical_pack"] = ItemDefinition(
        id="medical_pack",
        name="Medical pack",
        type="consumable",
        components=[
            dict(type="medical", feature_id="medical_pulse", action_cost="ACTION")
        ],
    )
    a.inventory.append(InventoryEntry(item_id="medical_pack", quantity=2))
    s, _ = runtime().execute(s, Command(type="use_item", item_id="medical_pack"))
    assert s.actor(a.id).hp == 4 and not s.encounter.action
    assert (
        sum(e.quantity for e in s.actor(a.id).inventory if e.item_id == "medical_pack")
        == 1
    )


def test_context_action_grants_only_its_declared_feature():
    from backend.tabletop.context_actions import ContextAction

    d = campaign()
    d.setting_definition.content.features["context_heal"] = FeatureDefinition(
        id="context_heal",
        name="Heal",
        description="Heal",
        activation="ACTION",
        effects=[dict(type="heal", value=2)],
    )
    d.context_actions.append(
        ContextAction(
            id="clinic",
            name="Clinic",
            location_id=d.starting_location,
            feature_id="context_heal",
        )
    )
    s = CampaignCompiler().compile(d)
    a = s.actor(s.party[0])
    a.hp = 1
    r = TabletopRuntime()
    with pytest.raises(ValueError):
        r.execute(s, Command(type="use_feature", feature_id="context_heal"))
    s, _ = r.execute(s, Command(type="context_action", action_id="clinic"))
    assert s.actor(a.id).hp == 4 and "context_heal" not in s.actor(a.id).features
