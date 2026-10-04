import pytest
from backend.tabletop.authoring import authoring_payload
from backend.tabletop.catalog import load_ruleset
from backend.tabletop.content_migration import import_catalog
from backend.tabletop.content_registry import SettingValidator, setting_rules, average
from backend.tabletop.content import (
    ContentItem,
    CreatureTemplate,
    CreatureInstance,
    ResourceDefinition,
    DamageTypeDefinition,
    SkillDefinition,
)
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.resources import ResourceEngine
from backend.tabletop.commands import Command
from backend.tabletop.runtime import TabletopRuntime
from backend.tabletop.validation import CampaignValidationError
from backend.tabletop.setting_repository import SettingRepository
from backend.tabletop.repository import TabletopRepository
from tabletop_gameplay_fixture import gameplay_definition


def setting():
    return import_catalog(load_ruleset("d20-fantasy-v2"))


def campaign():
    d = gameplay_definition()
    d.ruleset_id = "d20-core-v1"
    d.setting_definition = setting()
    for item in d.items:
        d.setting_definition.content.items[item.id] = ContentItem(
            id=item.id,
            name=item.name,
            description=item.description,
            category=item.type,
            value=item.value,
            components=[dict(type="quest" if item.type == "quest" else "currency")],
        )
    d.items = []
    return d


def test_catalog_adapter_compiles_without_changing_legacy_potion():
    d = campaign()
    state = CampaignCompiler().compile(d)
    assert state.items["potion"].healing == next(
        i.healing for i in load_ruleset("d20-fantasy-v2").items if i.id == "potion"
    )
    assert state.ruleset.abilities == load_ruleset("d20-fantasy-v2").abilities
    assert len(state.ruleset.classes) == 13
    assert state.items["ring"].ac_bonus == 1


@pytest.mark.parametrize(
    "skill,damage,resource",
    [
        ("resonance", "discord", "voice"),
        ("navigation", "pressure", "air"),
        ("weaving", "unravel", "thread"),
    ],
)
def test_custom_content_uses_same_engine(skill, damage, resource):
    d = campaign()
    c = d.setting_definition.content
    c.skills[skill] = SkillDefinition(
        id=skill,
        name=skill,
        default_ability="intelligence",
        alternate_abilities=["wisdom"],
    )
    c.damage_types[damage] = DamageTypeDefinition(id=damage, name=damage)
    c.resources[resource] = ResourceDefinition(
        id=resource, name=resource, maximum=4, initial=4
    )
    c.archetypes["fighter"].resources = [resource]
    c.items["instrument"] = ContentItem(
        id="instrument",
        name="Инструмент",
        value=1,
        equipment_slots=["MAIN_HAND"],
        components=[
            dict(
                type="weapon",
                damage_expression="2d6+1d4",
                damage_type=damage,
                resource_usage=[dict(resource_id=resource, amount=2)],
            ),
            dict(type="magazine", ammo_type="pellet", capacity=3, initial=1),
        ],
    )
    c.items["ammo"] = ContentItem(
        id="ammo",
        name="Расходник",
        value=1,
        components=[dict(type="ammo", ammo_type="pellet")],
    )
    state = CampaignCompiler().compile(d)
    a = state.actor(state.party[0])
    from backend.tabletop.definitions import InventoryEntry

    a.inventory = [
        InventoryEntry(item_id="instrument", equipped=True, slot="MAIN_HAND"),
        InventoryEntry(item_id="ammo", quantity=5),
    ]
    from backend.tabletop.rules import RulesEngine

    rules = RulesEngine()
    rules.equipment_stats(a, state.items)
    attack = a.attacks["instrument"]
    assert attack.expression == "2d6+1d4"
    assert rules.check_modifier(a, "wisdom", skill, state.ruleset) == rules.modifier(
        a.abilities["wisdom"]
    )
    ResourceEngine.spend_attack(a, attack)
    assert a.resources[resource] == 2 and a.item_resources["instrument"] == 0
    with pytest.raises(ValueError, match="перезарядка"):
        ResourceEngine.spend_attack(a, attack)
    assert ResourceEngine.reload(a, state.items, "instrument") == 3
    assert a.inventory[1].quantity == 2
    assert average(attack.expression) == 9.5


def test_setting_versions_restart_and_reject_broken_reference(tmp_path):
    repo = TabletopRepository(tmp_path / "games.db")
    worlds = SettingRepository(repo)
    saved = worlds.save(setting(), confirm=True)
    s = setting()
    s.name = "Другой мир"
    worlds.save(s, saved["revision"])
    assert worlds.get(s.id, 0)["definition"]["name"] != s.name
    assert (
        SettingRepository(TabletopRepository(repo.path)).get(s.id)["definition"]["name"]
        == s.name
    )
    s.content.archetypes["fighter"].skills = ["missing"]
    with pytest.raises(CampaignValidationError) as exc:
        worlds.save(s, 1)
    assert any(
        i.code == "missing_content_reference" and i.target_id == "missing"
        for i in exc.value.issues
    )
    assert worlds.get(s.id)["revision"] == 1


def test_creatures_take_stats_from_template():
    d = campaign()
    c = d.setting_definition.content
    c.creatures["echo"] = CreatureTemplate(
        id="echo",
        name="Эхо",
        attributes={a: 12 for a in load_ruleset().abilities},
        base_hp=21,
        base_armor=13,
        attacks=[
            dict(
                id="pulse",
                name="Импульс",
                damage_type="physical",
                damage_expression="2d4",
            )
        ],
    )
    d.creature_instances = [
        CreatureInstance(
            id="echo_one",
            name="Первое эхо",
            template_id="echo",
            location_id=d.starting_location,
            faction_id=d.factions[0].id,
        )
    ]
    state = CampaignCompiler().compile(d)
    actor = state.actor("echo_one")
    assert actor.hp == 21 and actor.armor_class == 13
    assert actor.attacks["pulse"].expression == "2d4"
    assert "attributes" not in d.creature_instances[0].model_dump()
    state.party.append("echo_one")
    from backend.tabletop.projection import public_state

    assert (
        public_state(state)["characters"]["echo_one"]["progression"]["available"]
        is False
    )


def test_multiple_semantic_issues_have_exact_entities():
    d = gameplay_definition()
    d.checks[0].success[0].target = "rune_clue"
    d.checks[0].ability = "strength"
    d.secrets[-1].disclosure = "never"
    with pytest.raises(CampaignValidationError) as exc:
        CampaignCompiler().validate(d)
    codes = {i.code for i in exc.value.issues}
    assert {"invalid_skill_ability", "forbidden_disclosure"} <= codes
    assert all(
        i.entity_id and i.field and i.stage == "semantic" for i in exc.value.issues
    )


class ScriptedDM:
    config = {"provider": "local"}

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def call(self, id, stage, messages, structured):
        import json

        self.calls.append((stage, messages))
        return json.dumps(next(self.replies))


def test_campaign_stages_validate_before_game_creation():
    from backend.tabletop.campaign_generation import CampaignGenerator2, CampaignOptions
    from semantic_fixture import campaign_blueprint as semantic_campaign

    dm = ScriptedDM([semantic_campaign()])
    result = CampaignGenerator2(dm).generate(
        "generation", setting(), CampaignOptions(idea="Unknown universe")
    )
    assert len(dm.calls) == 1 and result.player_slot
    assert result.setting_definition.id == setting().id
    CampaignCompiler().validate(result)
    with pytest.raises(ValueError, match="Создай персонажа"):
        CampaignCompiler().compile(result)


def test_authoring_retry_is_bounded_and_reports_failed_stage():
    from backend.tabletop.setting_generation import StagedAuthor, AuthoringFailure
    from backend.tabletop.content import SettingFoundation

    dm = ScriptedDM([{"name": "bad"}, {"name": "still bad"}])
    with pytest.raises(AuthoringFailure) as exc:
        StagedAuthor(dm).run(
            "id", "foundation", SettingFoundation, {}, lambda value: value, "contract"
        )
    assert len(dm.calls) == 2 and exc.value.stage == "foundation"
    assert exc.value.issues[0].field == "id"
    assert "previous_issues" in dm.calls[1][1][-1]["content"]


def test_authoring_recovers_only_failed_stage():
    from backend.tabletop.setting_generation import StagedAuthor
    from backend.tabletop.content import SettingFoundation

    dm = ScriptedDM([{"name": "bad"}, {"id": "world", "name": "Good"}])
    result = StagedAuthor(dm).run(
        "id",
        "foundation",
        SettingFoundation,
        {"previous": "fixed"},
        lambda value: value,
        "contract",
    )
    assert result.id == "world" and len(dm.calls) == 2


@pytest.mark.parametrize("multiplier,expected", [(0, 0), (0.5, 3), (1.5, 10)])
def test_custom_damage_multipliers_round_down(multiplier, expected):
    d = campaign()
    state = CampaignCompiler().compile(d)
    a = state.actor(state.party[0])
    a.hp = a.max_hp = 50
    a.damage_modifiers = {"custom": multiplier}
    TabletopRuntime().combat.damage(state, a, 7, False, [], "custom")
    assert a.hp == 50 - expected


def test_declarative_effects_resources_discovery_and_expiry():
    from backend.tabletop.features import FeatureEffect
    from backend.tabletop.effects import EffectsEngine

    d = campaign()
    d.setting_definition.content.resources["focus"] = ResourceDefinition(
        id="focus", name="Фокус", maximum=5, initial=5
    )
    state = CampaignCompiler().compile(d)
    actor = state.actor(state.party[0])
    actor.resources["focus"] = 5
    runtime = TabletopRuntime()
    events = []

    def apply(kind, **kw):
        EffectsEngine.apply(
            runtime, state, actor, actor, FeatureEffect(type=kind, **kw), events
        )

    apply("spend_resource", key="focus", value=2)
    assert actor.resources["focus"] == 3
    apply("restore_resource", key="focus", value=9)
    assert actor.resources["focus"] == 5
    before = runtime.rules.check_modifier(
        actor, "intelligence", "investigation", state.ruleset
    )
    apply("modify_check", key="investigation", value=2, duration=1)
    assert (
        runtime.rules.check_modifier(
            actor, "intelligence", "investigation", state.ruleset
        )
        == before + 2
    )
    state.game_time += 2
    EffectsEngine.expire(state)
    assert (
        runtime.rules.check_modifier(
            actor, "intelligence", "investigation", state.ruleset
        )
        == before
    )
    apply("reveal_knowledge", key="room_clue")
    assert state.player_knowledge["room_clue"]
    apply("spawn_object", key="coin", value=2)
    assert any(o.name == state.items["coin"].name for o in state.definition.objects)
    with pytest.raises(ValueError, match="чувствами"):
        apply("modify_relationship", value=10)


def test_contextual_action_checks_inventory_and_player_knowledge():
    from backend.tabletop.context_actions import ContextAction, eligible

    d = campaign()
    d.context_actions = [
        ContextAction(
            id="read_trace",
            name="Прочитать след",
            location_id=d.starting_location,
            check_id="investigation_check",
            requirements={"items": ["coin"]},
        )
    ]
    state = CampaignCompiler().compile(d)
    actor = state.actor(state.party[0])
    action = d.context_actions[0]
    assert not eligible(state, actor, action)
    from backend.tabletop.definitions import InventoryEntry

    actor.inventory.append(InventoryEntry(item_id="coin"))
    assert eligible(state, actor, action)
    after, _ = TabletopRuntime().execute(
        state, Command(type="context_action", action_id=action.id)
    )
    assert after.session_state.pending.check_id == "investigation_check"
    assert (
        sum(after.session_state.pending.modifier_breakdown.values())
        == after.session_state.pending.modifier
    )


def test_foundation_regeneration_preserves_registry_and_revision():
    from backend.tabletop.setting_generation import SettingGenerator
    from backend.tabletop.procedural_content import ProceduralContentCompiler
    from semantic_fixture import world_blueprint as semantic_world
    from backend.tabletop.blueprints import WorldBlueprint
    from backend.tabletop.procedural_world import ProceduralWorldGenerator
    from backend.tabletop.generation_config import GenerationConfig

    world = ProceduralWorldGenerator().generate(
        "world",
        WorldBlueprint.model_validate(semantic_world()),
        GenerationConfig(),
        revision=7,
    )
    result = SettingGenerator(ScriptedDM([{"name": "Новое название"}])).generate(
        world.id, "Новое описание", world, "foundation"
    )
    assert result.name == "Новое название"
    assert result.content == world.content and result.revision == 7
    assert world.name != result.name


def test_foundation_regeneration_rejects_changed_identity():
    from backend.tabletop.setting_generation import SettingGenerator, AuthoringFailure
    from backend.tabletop.procedural_content import ProceduralContentCompiler
    from semantic_fixture import world_blueprint as semantic_world
    from backend.tabletop.blueprints import WorldBlueprint
    from backend.tabletop.procedural_world import ProceduralWorldGenerator
    from backend.tabletop.generation_config import GenerationConfig

    world = ProceduralWorldGenerator().generate(
        "world", WorldBlueprint.model_validate(semantic_world()), GenerationConfig()
    )
    reply = {"name": "Other", "id": "different"}
    with pytest.raises(AuthoringFailure) as exc:
        SettingGenerator(ScriptedDM([reply, reply])).generate(
            world.id, "Change", world, "foundation"
        )
    assert any(i.code == "schema_error" and i.field == "id" for i in exc.value.issues)


def test_duplicate_attack_resource_cost_is_validated_as_total():
    from backend.tabletop.models import Attack
    from backend.tabletop.content import ResourceCost

    state = CampaignCompiler().compile(campaign())
    actor = state.actor(state.party[0])
    actor.resources["charge"] = 3
    attack = Attack(
        name="Импульс",
        resource_usage=[ResourceCost(resource_id="charge", amount=2)] * 2,
    )
    with pytest.raises(ValueError, match="Недостаточно ресурса"):
        ResourceEngine.spend_attack(actor, attack)
    assert actor.resources["charge"] == 3
    actor.resources["charge"] = 4
    ResourceEngine.spend_attack(actor, attack)
    assert actor.resources["charge"] == 0


def test_overlapping_feature_costs_reject_atomically():
    from backend.tabletop.features import FeatureDefinition

    state = CampaignCompiler().compile(campaign())
    actor = state.actor(state.party[0])
    state.ruleset.features["cost_test"] = FeatureDefinition(
        id="cost_test",
        name="Стоимость",
        description="Проверка суммарной стоимости",
        activation="ACTION",
        resource="charge",
        resource_cost={"charge": 2},
        effects=[dict(type="heal", value=1)],
    )
    actor.features.append("cost_test")
    actor.resources["charge"] = 2
    before = state.model_dump()
    runtime = TabletopRuntime()
    with pytest.raises(ValueError, match="Недостаточно ресурса"):
        runtime.execute(state, Command(type="use_feature", feature_id="cost_test"))
    assert state.model_dump() == before
    actor.resources["charge"] = 3
    result, _ = runtime.execute(
        state, Command(type="use_feature", feature_id="cost_test")
    )
    assert result.actor(actor.id).resources["charge"] == 0


def test_firing_modes_preview_and_runtime_spend_once():
    from backend.tabletop.models import Encounter, Attack
    from backend.tabletop.content import MagazineComponent
    from backend.tabletop.preview import attack_previews
    from test_tabletop import runtime

    state = CampaignCompiler().compile(campaign())
    actor = state.actor("traveler")
    actor.location = "vault"
    actor.attacks = {
        "test_weapon": Attack(
            name="Импульсник",
            item_id="test_weapon",
            expression="1d4",
            magazine=MagazineComponent(
                ammo_type="cell",
                capacity=6,
                initial=6,
                modes={"single": 1, "burst": 3, "automatic": 6},
            ),
        )
    }
    actor.item_resources["test_weapon"] = 6
    state.encounters["guard_battle"] = Encounter(
        definition_id="guard_battle",
        order=["traveler", "sentinel"],
        initiative={"traveler": 20, "sentinel": 1},
        reaction={"traveler": True, "sentinel": True},
    )
    state.active_encounter = "guard_battle"
    previews = attack_previews(state, actor)
    assert {(p["mode"], p["ammunition_cost"]) for p in previews} == {
        ("single", 1),
        ("burst", 3),
        ("automatic", 6),
    }
    engine = runtime(1)
    state, _ = engine.execute(
        state,
        Command(type="attack", weapon="test_weapon", target="sentinel", mode="burst"),
    )
    assert state.actor("traveler").item_resources["test_weapon"] == 3
    state, _ = engine.resolve_roll(state, state.session_state.pending.id)
    assert state.actor("traveler").item_resources["test_weapon"] == 3
    assert not next(
        p
        for p in attack_previews(state, state.actor("traveler"))
        if p["mode"] == "automatic"
    )["available"]


def test_starting_shop_rejects_registry_unavailable_item():
    from backend.tabletop.rules import RulesEngine
    from backend.tabletop.definitions import InventoryEntry
    from test_tabletop_gameplay import build

    world = setting()
    world.content.items["potion"].starting_available = False
    rules = setting_rules(world)
    with pytest.raises(ValueError, match="нельзя купить"):
        RulesEngine.shop_remaining(
            build(purchases=[InventoryEntry(item_id="potion")]), rules
        )


def test_campaign_retries_invalid_region_at_locations_stage():
    from backend.tabletop.campaign_generation import CampaignGenerator2, CampaignOptions
    from semantic_fixture import campaign_blueprint as semantic_campaign

    valid = semantic_campaign()
    from copy import deepcopy

    invalid = deepcopy(valid)
    invalid["locations"][0]["connections"] = ["Missing location"]
    dm = ScriptedDM([invalid, valid])
    CampaignGenerator2(dm).generate(
        "generation", setting(), CampaignOptions(idea="Чужая вселенная")
    )
    assert [call[0] for call in dm.calls] == ["authoring_campaign_blueprint"] * 2


@pytest.mark.parametrize(
    "world_id,name,skill,damage,resource,role,body",
    [
        (
            "tides",
            "Архипелаг стеклянных приливов",
            "resonance",
            "discord",
            "voice",
            "listener",
            "glassborn",
        ),
        (
            "depths",
            "Кочевые станции под давлением",
            "navigation",
            "pressure",
            "air",
            "navigator",
            "diver",
        ),
        (
            "threads",
            "Живой город из связанных снов",
            "weaving",
            "unravel",
            "thread",
            "weaver",
            "dreamer",
        ),
    ],
)
def test_independent_worlds_compile_play_and_restore_without_fantasy_catalog(
    tmp_path, world_id, name, skill, damage, resource, role, body
):
    from backend.tabletop.content import SettingDefinition
    from backend.tabletop.definitions import CampaignDefinition
    from backend.tabletop.rules import RulesEngine

    world = SettingDefinition.model_validate(
        dict(
            id=world_id,
            name=name,
            content=dict(
                skills={
                    skill: dict(id=skill, name=skill, default_ability="intelligence")
                },
                damage_types={damage: dict(id=damage, name=damage)},
                resources={
                    resource: dict(id=resource, name=resource, maximum=3, initial=3)
                },
                equipment_profiles={
                    "body": dict(
                        id="body",
                        name="Тело",
                        slots=[
                            dict(id="MAIN_HAND", name="Инструмент", position="left")
                        ],
                    )
                },
                species={body: dict(id=body, name=body, equipment_profile="body")},
                archetypes={
                    role: dict(
                        id=role,
                        name=role,
                        skill_count=1,
                        skills=[skill],
                        resources=[resource],
                        equipment=["instrument"],
                    )
                },
                backgrounds={
                    "origin": dict(
                        id="origin", name="Местный", skills=[skill], tags=["local"]
                    )
                },
                items={
                    "instrument": dict(
                        id="instrument",
                        name="Рабочий инструмент",
                        value=5,
                        equipment_slots=["MAIN_HAND"],
                        components=[
                            dict(
                                type="weapon",
                                attack_ability="intelligence",
                                damage_type=damage,
                                damage_expression="1d6",
                                resource_usage=[dict(resource_id=resource)],
                            )
                        ],
                    )
                },
            ),
        )
    )
    world = SettingValidator().validate(world)
    d = CampaignDefinition.model_validate(
        dict(
            id="adventure",
            name=name,
            ruleset_id="d20-core-v1",
            ruleset_version=4,
            setting_definition=world,
            setting=dict(id=world.id, name=name, genre="", technology="", magic=""),
            regions=[dict(id="region", name="Район")],
            locations=[dict(id="home", name="Дом", region_id="region")],
            factions=[dict(id="people", name="Жители")],
            characters=[
                dict(
                    id="hero",
                    name="Герой",
                    location_id="home",
                    faction_id="people",
                    controller="PLAYER",
                    player_id="local",
                    build=dict(
                        character_class=role,
                        species=body,
                        background="origin",
                        skills=[skill],
                        equipment=["instrument"],
                    ),
                )
            ],
            starting_party=["hero"],
            starting_location="home",
            starting_scene="Начало пути",
        )
    )
    state = CampaignCompiler().compile(d)
    actor = state.actor("hero")
    assert set(state.ruleset.classes) == {role}
    assert set(state.ruleset.skills) == {skill}
    assert actor.attacks["instrument"].damage_type == damage
    assert (
        RulesEngine().check_modifier(actor, "intelligence", skill, state.ruleset) == 2
    )
    ResourceEngine.spend_attack(actor, actor.attacks["instrument"])
    repo = TabletopRepository(tmp_path / (world_id + ".db"))
    gid = repo.create(state)
    _, loaded = TabletopRepository(repo.path).load(gid)
    assert loaded.actor("hero").resources[resource] == 2
    assert loaded.definition.setting_definition.content == world.content


def test_custom_equipment_profile_drives_armor_and_hand_conflicts():
    from backend.tabletop.content import EquipmentSlot
    from backend.tabletop.definitions import InventoryEntry
    from backend.tabletop.rules import RulesEngine
    from backend.tabletop.equipment import EquipmentEngine

    d = campaign()
    c = d.setting_definition.content
    profile = c.equipment_profiles["humanoid"]
    mapping = {"MAIN_HAND": "claw_a", "OFF_HAND": "claw_b", "TORSO": "shell"}
    profile.slots = [
        slot.model_copy(update={"id": mapping.get(slot.id, slot.id)})
        for slot in profile.slots
    ]
    for item in c.items.values():
        item.equipment_slots = [
            mapping.get(slot, slot) for slot in item.equipment_slots
        ]
    for actor in d.characters + d.creatures:
        for entry in actor.inventory:
            entry.slot = mapping.get(entry.slot, entry.slot)
    state = CampaignCompiler().compile(d)
    actor = state.actor("traveler")
    actor.inventory = [
        InventoryEntry(item_id="chain", equipped=True, slot="shell"),
        InventoryEntry(item_id="bow"),
        InventoryEntry(item_id="shield", equipped=True, slot="claw_b"),
    ]
    engine = RulesEngine()
    engine.equipment_stats(actor, state.items)
    assert actor.armor_class >= 18
    EquipmentEngine.equip(actor, state.items, actor.inventory[1], "claw_a")
    assert not actor.inventory[2].equipped
    engine.equipment_stats(actor, state.items)
    assert "bow" in actor.attacks


def test_feature_requirements_filter_execution_and_previews():
    from backend.tabletop.features import FeatureDefinition
    from backend.tabletop.preview import usable_actions

    state = CampaignCompiler().compile(campaign())
    actor = state.actor("traveler")
    state.ruleset.features["restricted"] = FeatureDefinition(
        id="restricted",
        name="Доступ",
        description="Нужен ключ",
        activation="ACTION",
        requirements={"items": ["manuscript"]},
        effects=[dict(type="heal", value=1)],
    )
    actor.features.append("restricted")
    assert not any(a["id"] == "restricted" for a in usable_actions(state, actor))
    with pytest.raises(ValueError, match="требования"):
        TabletopRuntime().execute(
            state, Command(type="use_feature", feature_id="restricted")
        )
