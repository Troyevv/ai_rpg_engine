import pytest
from test_universal_content import campaign
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.content import ContentItem
from backend.tabletop.definitions import WorldObject, InventoryEntry
from backend.tabletop.commands import Command
from backend.tabletop.runtime import TabletopRuntime
from backend.tabletop.dice import DiceEngine


def state():
    d = campaign()
    d.setting_definition.content.items["bag"] = ContentItem(
        id="bag", name="Bag", components=[{"type": "container", "capacity": 2}]
    )
    d.objects.append(
        WorldObject(
            id="case",
            name="Case",
            location_id=d.starting_location,
            components=[
                {"type": "container", "capacity": 2},
                {"type": "breakable", "hit_points": 1, "defence": 1},
            ],
        )
    )
    result = CampaignCompiler().compile(d)
    actor = result.actor(result.party[0])
    actor.inventory.extend(
        [InventoryEntry(item_id="bag"), InventoryEntry(item_id="potion", quantity=3)]
    )
    return result


def test_container_capacity_atomicity_and_unpack_after_serialization():
    s = state()
    runtime = TabletopRuntime()
    aid = s.party[0]
    s, _ = runtime.execute(
        s, Command(type="store_item", item_id="potion", target="bag", quantity=2)
    )
    assert (
        sum(e.quantity for e in s.actor(aid).inventory if e.container_id == "bag") == 2
    )
    before = s.model_dump()
    with pytest.raises(ValueError, match="места"):
        runtime.execute(
            s, Command(type="store_item", item_id="potion", target="bag", quantity=1)
        )
    assert s.model_dump() == before
    s = type(s).model_validate_json(s.model_dump_json())
    s, _ = runtime.execute(
        s, Command(type="unpack_item", item_id="potion", target="bag", quantity=1)
    )
    assert (
        sum(e.quantity for e in s.actor(aid).inventory if e.container_id == "bag") == 1
    )
    with pytest.raises(ValueError, match="освободи"):
        runtime.execute(s, Command(type="drop_item", item_id="bag"))


class Maximum:
    def randint(self, a, b):
        return b


def test_break_object_uses_two_canonical_rolls_and_opens_container():
    s = state()
    runtime = TabletopRuntime(DiceEngine(Maximum()))
    s, _ = runtime.execute(
        s, Command(type="object_action", target="case", operation="break")
    )
    assert s.session_state.pending.purpose == "object_attack"
    s, events = runtime.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.purpose == "object_damage"
    s, events = runtime.resolve_roll(s, s.session_state.pending.id)
    assert s.objects["case"].hit_points == 0 and s.objects["case"].opened
    s, _ = runtime.execute(
        s, Command(type="store_item", target="case", item_id="potion", quantity=2)
    )
    assert s.objects["case"].contents[0].quantity == 2


def test_terminal_and_hazard_use_declared_feature_and_damage_type():
    from backend.tabletop.features import FeatureDefinition
    from backend.tabletop.content import DamageTypeDefinition

    d = campaign()
    c = d.setting_definition.content
    c.features["terminal_heal"] = FeatureDefinition(
        id="terminal_heal",
        name="Terminal",
        description="Restores HP",
        activation="ACTION",
        effects=[dict(type="heal", value=2)],
    )
    c.damage_types["pressure"] = DamageTypeDefinition(id="pressure", name="Pressure")
    d.objects.append(
        WorldObject(
            id="terminal",
            name="Terminal",
            location_id=d.starting_location,
            components=[dict(type="terminal", feature_id="terminal_heal")],
        )
    )
    d.objects.append(
        WorldObject(
            id="hazard",
            name="Hazard",
            location_id=d.starting_location,
            components=[
                dict(type="hazard", damage_expression="1d4", damage_type="pressure")
            ],
        )
    )
    s = CampaignCompiler().compile(d)
    a = s.actor(s.party[0])
    a.hp = 2
    r = TabletopRuntime()
    s, _ = r.execute(
        s, Command(type="object_action", operation="activate", target="terminal")
    )
    assert s.actor(a.id).hp == 5
    from tabletop_fixture import Fixed

    r = TabletopRuntime(DiceEngine(Fixed(1, 4)))
    s.actor(a.id).damage_modifiers["pressure"] = 0
    s, _ = r.execute(s, Command(type="interact", target="hazard"))
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.session_state.pending.purpose == "hazard_damage"
    s, _ = r.resolve_roll(s, s.session_state.pending.id)
    assert s.actor(a.id).hp == 5 and s.objects["hazard"].trap_triggered
