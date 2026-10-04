import json
import pytest
from pydantic import ValidationError
from semantic_fixture import world, campaign, world_blueprint, campaign_blueprint
from backend.tabletop.semantic import (
    SemanticSettingDTO,
    SemanticCampaignDTO,
    SemanticNPC,
)
from backend.tabletop.procedural_content import ProceduralContentCompiler, stable_id
from backend.tabletop.semantic_campaign import SemanticCampaignCompiler, NPCBuildFactory
from backend.tabletop.campaign_generation import CampaignOptions, CampaignGenerator2
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.content_registry import setting_rules
from backend.tabletop.rules import RulesEngine
from backend.tabletop.setting_generation import SettingGenerator, AuthoringFailure


def setting():
    return ProceduralContentCompiler().compile("world", world())


@pytest.mark.parametrize(
    "path,bad",
    [
        ("items", {"damage_expression": "999d999"}),
        ("professions", {"build": {}}),
        ("species", {"id": "owned"}),
    ],
)
def test_mechanics_cannot_cross_semantic_boundary(path, bad):
    data = world()
    data[path][0].update(bad)
    with pytest.raises(ValidationError):
        SemanticSettingDTO.model_validate(data)


def test_deterministic_and_legal_factories():
    a, b = setting(), setting()
    assert a.model_dump_json() == b.model_dump_json()
    rules = setting_rules(a)
    for cls in a.content.archetypes.values():
        npc = SemanticNPC(
            name="NPC", location="Площадь", faction="Хранители", profession=cls.name
        )
        build = NPCBuildFactory().build(npc, a, [])
        RulesEngine().validate_build(build, rules)
        if cls.id in rules.spellcasting:
            assert build.spells and build.prepared_spells
            assert rules.spellcasting[cls.id].slots == {"1": 2}
    for c in a.content.creatures.values():
        assert c.threat > 0


def test_unknown_ability_fallback_does_not_invent_effects():
    data = world()
    data["professions"][0]["abilities"].append(
        dict(name="Переписать время", intent="unsupported")
    )
    result = ProceduralContentCompiler().compile("world", data)
    assert any(d["code"] == "narrative_only" for d in result.diagnostics)
    f = next(
        f for f in result.content.features.values() if f.name == "Переписать время"
    )
    assert f.effects == []


def test_campaign_has_no_player_build_until_character_creator():
    s = setting()
    d = SemanticCampaignCompiler().compile(
        "campaign", campaign(), s, CampaignOptions(idea="Исчезновение")
    )
    assert d.player_slot and not d.starting_party
    assert all(c.controller == "AI" for c in d.characters)
    CampaignCompiler().validate(d.model_dump())
    with pytest.raises(ValueError, match="Создай персонажа"):
        CampaignCompiler().compile(d)
    build = d.characters[0].build.model_copy(update={"name": "Мой герой"})
    state = CampaignCompiler().compile(d, build)
    assert state.actor("player_slot").name == "Мой герой"
    assert d.player_slot and not d.starting_party
    assert state.player_knowledge.get(stable_id("secret", "След")) is None
    assert state.encounters == {}
    assert state.definition.encounters


class DM:
    config = True

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def call(self, *args):
        self.calls.append(args)
        return json.dumps(next(self.replies))


def test_generators_only_request_semantics_and_bound_repair():
    bad = world_blueprint()
    bad["equipment_families"][0]["damage_expression"] = "1d999"
    dm = DM([bad, world_blueprint()])
    s = SettingGenerator(dm).generate("world", "Новый мир")
    assert len(dm.calls) == 2
    prompt = dm.calls[0][2][0]["content"]
    for forbidden in (
        "FeatureEffect",
        "CharacterBuild",
        "damage_expression",
        "activation",
        "resource_cost",
    ):
        assert forbidden not in prompt
    dm = DM([campaign_blueprint()])
    d = CampaignGenerator2(dm).generate("c", s, CampaignOptions(idea="Пропажа"))
    assert d.player_slot and len(dm.calls) == 1
    assert "damage_expression" not in json.dumps(dm.calls)


def test_compiler_failure_does_not_retry_model_and_resume_uses_dto(
    tmp_path, monkeypatch
):
    from backend.tabletop.repository import TabletopRepository
    from backend.tabletop.authoring_jobs import AuthoringJobs

    jobs = AuthoringJobs(TabletopRepository(tmp_path / "jobs.db"))
    dm = DM([world_blueprint()])
    real = ProceduralContentCompiler.compile

    def fail(*args, **kwargs):
        raise ValueError("Compiler failure")

    monkeypatch.setattr(ProceduralContentCompiler, "compile", fail)
    with pytest.raises(ValueError):
        with jobs.run("job", "setting", {"concept": "мир"}) as cp:
            SettingGenerator(dm, checkpoint=cp).generate("world", "мир")
    assert len(dm.calls) == 1
    assert "setting_blueprint" in jobs.get("job")["outputs"]
    monkeypatch.setattr(ProceduralContentCompiler, "compile", real)
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "jobs.db"))
    with jobs.run("job", "setting", {"concept": "мир"}) as cp:
        result = SettingGenerator(dm, checkpoint=cp).generate("world", "мир")
    assert result.content and len(dm.calls) == 1


def test_snapshot_roundtrip_and_revision_isolation(tmp_path):
    from backend.tabletop.repository import TabletopRepository
    from backend.tabletop.setting_repository import SettingRepository

    repo = TabletopRepository(tmp_path / "snapshots.db")
    worlds = SettingRepository(repo)
    s = setting()
    worlds.save(s)
    d = SemanticCampaignCompiler().compile(
        "c", campaign(), s, CampaignOptions(idea="Пропажа")
    )
    saved = repo.save_draft(d)
    s.name = "Другой мир"
    worlds.save(s, expected_revision=0)
    loaded = CampaignCompiler().validate(repo.draft(saved["id"])["definition"])
    assert loaded.setting_definition.name != s.name
    assert loaded.setting_definition.revision == 0
    state = CampaignCompiler().compile(loaded, loaded.characters[0].build)
    gid = repo.create(state)
    _, restored = repo.load(gid)
    assert (
        restored.definition.setting_definition.content
        == loaded.setting_definition.content
    )


@pytest.mark.parametrize(
    "genre,skill,weapon,species",
    [
        ("Тёмное фэнтези", "Следопытство", "Костяной клинок", "Люди"),
        ("Киберпанк без магии", "Электроника", "Пистолет", "Модифицированные люди"),
        (
            "Летающие острова, живые кристаллы",
            "Резонанс",
            "Кристалл",
            "Облачные жители",
        ),
        ("НИИ изучает экзоматерию", "Стабилизация", "Изолятор", "Исследователи"),
    ],
)
def test_universal_seeded_worlds_coverage_and_campaign(genre, skill, weapon, species):
    from backend.tabletop.generation_config import (
        GenerationConfig,
        CampaignGenerationConfig,
    )
    from backend.tabletop.semantic import SemanticSettingDTO

    data = world()
    data["genre"] = genre
    data["name"] = genre
    original_skill = data["skills"][0]["name"]
    original_weapon = data["items"][0]["name"]
    data = json.loads(
        json.dumps(data, ensure_ascii=False)
        .replace(original_skill, skill)
        .replace(original_weapon, weapon)
    )
    data["skills"][0]["name"] = skill
    data["items"][0]["name"] = weapon
    data["species"][0]["name"] = species
    if genre == "Киберпанк без магии":
        for role in data["professions"]:
            role["casting"] = "none"
            role["resource"] = dict(name="Батарея", model="battery", recovery="daily")
        data["items"][0].update(supply="ammunition", supply_concept="Патроны")

    config = GenerationConfig(seed=37)
    a = ProceduralContentCompiler().compile("w", data, generation=config)
    b = ProceduralContentCompiler().compile("w", data, generation=config)
    assert a.model_dump() == b.model_dump()
    other = ProceduralContentCompiler().compile(
        "w", data, generation=config.model_copy(update={"seed": 38})
    )
    assert a.content != other.content
    assert len(a.content.archetypes) >= config.targets["professions"]
    assert len(a.content.backgrounds) >= config.targets["backgrounds"]
    assert len(a.content.creatures) >= config.targets["creatures"]
    assert len(a.content.items) >= sum(
        config.targets[k] for k in ("weapons", "armor", "medical", "utility")
    )
    assert a.generation_config.seed == 37 and a.generation_metadata
    if genre == "Киберпанк без магии":
        assert not a.content.powers and not a.content.spellcasting

    opts = CampaignOptions(
        idea="Исследование",
        party_size=2,
        generation=CampaignGenerationConfig(seed=61, profile="SHORT"),
    )
    campaign_data = json.loads(
        json.dumps(campaign(), ensure_ascii=False).replace("Слух", skill)
    )
    first = SemanticCampaignCompiler().compile("c", campaign_data, a, opts)
    second = SemanticCampaignCompiler().compile("c", campaign_data, a, opts)
    assert first.model_dump() == second.model_dump()
    assert len(first.locations) == len(
        campaign()["locations"]
    )  # Legacy DTO compiles as authored; blueprint owns coverage.
    state = CampaignCompiler().compile(first, first.characters[0].build)
    assert len(state.party) == 2
    from backend.tabletop.commands import Command
    from backend.tabletop.runtime import TabletopRuntime

    encounter = state.definition.encounters[0]
    for aid in state.party:
        state.actor(aid).location = encounter.location_id
    state, _ = TabletopRuntime().execute(
        state, Command(type="start_encounter", target=encounter.id)
    )
    assert state.encounter or state.session_state.pending


def test_lazy_content_uses_factories_atomic_overlay_and_survives_restart(tmp_path):
    from backend.tabletop.semantic import SemanticExpansionDTO
    from backend.tabletop.semantic_expansion import LazyContentCompiler
    from backend.tabletop.repository import TabletopRepository

    s = setting()
    d = SemanticCampaignCompiler().compile(
        "c", campaign(), s, CampaignOptions(idea="Архив")
    )
    before = CampaignCompiler().compile(d, d.characters[0].build)
    dto = SemanticExpansionDTO.model_validate(
        dict(
            items=[dict(name="Новый прибор", category="weapon", style="ranged")],
            locations=[dict(name="Лаборатория", connections=["Площадь"])],
            objects=[
                dict(
                    name="Шкаф",
                    location="Лаборатория",
                    capabilities=["container"],
                    loot=[dict(category="weapon", item="Новый прибор")],
                )
            ],
        )
    )
    after, mutation = LazyContentCompiler().compile(dto, before)
    assert after.definition.setting_definition == before.definition.setting_definition
    assert (
        after.definition.content_overlay.items
        and not before.definition.content_overlay.items
    )
    assert after.definition.expansion_blueprints
    assert mutation.registry_additions and after.definition.objects[-1].contents
    repo = TabletopRepository(tmp_path / "lazy.db")
    gid = repo.create(after)
    _, restored = TabletopRepository(repo.path).load(gid)
    assert restored.definition.content_overlay == after.definition.content_overlay
    assert restored.items == after.items
    invalid = dto.model_copy(deep=True)
    invalid.locations[0].connections = ["Missing"]
    original = before.model_dump_json()
    with pytest.raises(ValueError):
        LazyContentCompiler().compile(invalid, before)
    assert before.model_dump_json() == original


def test_api_world_campaign_character_shop_start(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.tabletop.dm import DMAgent

    calls = []

    def call(self, id, stage, messages, structured):
        calls.append(stage)
        return json.dumps(
            world_blueprint()
            if stage == "authoring_setting_blueprint"
            else campaign_blueprint()
        )

    monkeypatch.setattr(DMAgent, "call", call)
    monkeypatch.setattr(DMAgent, "narrate", lambda *args: "Начало приключения")
    path = tmp_path / "flow.db"
    with TestClient(create_app(path)) as client:
        w = client.post(
            "/api/tabletop/settings/worlds/generate",
            json={
                "concept": "Совершенно новый мир",
                "generation": {"seed": 73, "profile": "SMALL"},
                "config": {"model": "fixture"},
            },
        )
        assert w.status_code == 200, w.text
        response = client.post(
            "/api/tabletop/generate",
            json={
                "setting_id": w.json()["id"],
                "options": {
                    "idea": "Потеря архивов",
                    "generation": {"seed": 91, "profile": "SHORT"},
                },
                "config": {"model": "fixture"},
            },
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        catalog = client.get(
            "/api/tabletop/catalog", params={"draft_id": draft["id"]}
        ).json()
        build = catalog["default_build"]
        build.update(
            name="Выбранный игрок",
            ability_method="standard_array",
            abilities=dict(zip(catalog["abilities"], catalog["ability_array"])),
        )
        item = next(
            v
            for v in catalog["items"]
            if v["type"] == "weapon"
            and v["starting_available"]
            and v["value"] <= catalog["starting_gold"]
        )
        build["purchases"] = [dict(item_id=item["id"], equipped=True, slot="MAIN_HAND")]
        assert (
            client.post(
                "/api/tabletop/build/validate",
                json={"draft_id": draft["id"], "build": build},
            ).status_code
            == 200
        )
        response = client.post(
            "/api/tabletop/games",
            json={
                "draft_id": draft["id"],
                "draft_revision": draft["revision"],
                "character": build,
                "config": {"provider": "local", "model": "fixture"},
            },
        )
        assert response.status_code == 200, response.text
        gid = response.json()["id"]
        assert calls == ["authoring_setting_blueprint", "authoring_campaign_blueprint"]
    with TestClient(create_app(path)) as client:
        response = client.get("/api/tabletop/games/" + gid)
        assert response.status_code == 200
        hero = response.json()["state"]["characters"]["player_slot"]
        assert hero["name"] == "Выбранный игрок"
        assert any(v["item_id"] == item["id"] for v in hero["inventory"])


def test_generated_ammunition_and_devices_have_supported_components():
    data = world()
    data["items"][0].update(supply="ammunition", supply_concept="Ячейки")
    data["items"].append(
        dict(
            name="Контроллер",
            category="device",
            capabilities=[
                dict(name="Импульс", intent="damage", damage_concept="Резонанс")
            ],
        )
    )
    result = ProceduralContentCompiler().compile("world", data)
    weapon = result.content.items[stable_id("item", "Резонатор")]
    magazine = next(c for c in weapon.components if c.type == "magazine")
    assert any(
        c.type == "ammo" and c.ammo_type == magazine.ammo_type
        for item in result.content.items.values()
        for c in item.components
    )
    assert result.content.items[stable_id("item", "Контроллер")].effects
