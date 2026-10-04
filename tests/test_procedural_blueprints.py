"""Acceptance at the compact provider boundary and the existing runtime boundary."""

import json
import os
import re
from copy import deepcopy

import pytest
from pydantic import ValidationError

from semantic_fixture import world_blueprint, campaign_blueprint, world, campaign
from backend.tabletop.blueprints import WorldBlueprint, CampaignBlueprint, world_context
from backend.tabletop.setting_generation import SettingGenerator, AuthoringFailure
from backend.tabletop.campaign_generation import CampaignGenerator2, CampaignOptions
from backend.tabletop.generation_config import (
    GenerationConfig,
    CampaignGenerationConfig,
)
from backend.tabletop.procedural_world import ProceduralWorldGenerator
from backend.tabletop.procedural_campaign import ProceduralCampaignGenerator
from backend.tabletop.procedural_content import (
    ProceduralContentCompiler,
    pick,
    stable_id,
)
from backend.tabletop.semantic_campaign import SemanticCampaignCompiler
from backend.tabletop.semantic import SemanticCampaignDTO
from backend.tabletop.compiler import CampaignCompiler
from backend.tabletop.repository import TabletopRepository
from backend.tabletop.authoring_jobs import AuthoringJobs


class Provider:
    config = {"provider": "fixture", "model": "compact"}
    api_key = "test-private-credential"

    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []

    def call(self, *args):
        self.calls.append(args)
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, str) else json.dumps(value)


def generate_world(profile="NORMAL", seed=4, data=None):
    return ProceduralWorldGenerator().generate(
        "world",
        WorldBlueprint.model_validate(data or world_blueprint()),
        GenerationConfig(profile=profile, seed=seed),
    )


def test_profiles_change_only_procedural_work_not_provider_input_or_output():
    prompts = []
    campaigns = []
    worlds = []
    for profile, length in zip(
        ("SMALL", "NORMAL", "LARGE"), ("SHORT", "NORMAL", "LONG")
    ):
        provider = Provider(world_blueprint(), campaign_blueprint())
        setting = SettingGenerator(provider).generate(
            "w", "Голоса", generation=GenerationConfig(profile=profile)
        )
        result = CampaignGenerator2(provider).generate(
            "c",
            setting,
            CampaignOptions(
                idea="Пропажа", generation=CampaignGenerationConfig(profile=length)
            ),
        )
        assert [v[1] for v in provider.calls] == [
            "authoring_setting_blueprint",
            "authoring_campaign_blueprint",
        ]
        prompts.append([v[2] for v in provider.calls])
        worlds.append(len(setting.content.items))
        campaigns.append(len(result.locations))
        CampaignCompiler().validate(result)
        assert (
            result.semantic_source
            == CampaignBlueprint.model_validate(campaign_blueprint()).model_dump()
        )
    assert prompts[0] == prompts[1] == prompts[2]
    assert worlds[0] < worlds[1] < worlds[2]
    assert campaigns == [3, 6, 10]
    serialized = json.dumps(prompts, ensure_ascii=False)
    for forbidden in (
        "FeatureEffect",
        "damage_expression",
        "CharacterBuild",
        "ContentRegistry",
        "coverage_targets",
        '"spell_slots"',
        '"known_secrets"',
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "bad", ["not json", '{"name":"Обрезано"', {**world_blueprint(), "hp": 999}]
)
def test_malformed_response_gets_only_one_small_repair(bad):
    provider = Provider(bad, world_blueprint())
    assert SettingGenerator(provider).generate("w", "Мир").content
    assert len(provider.calls) == 2
    assert json.loads(provider.calls[1][2][1]["content"])["previous_issues"]
    provider = Provider(bad, bad, world_blueprint())
    with pytest.raises(AuthoringFailure):
        SettingGenerator(provider).generate("w", "Мир")
    assert len(provider.calls) == 2


def test_missing_optional_sections_world_without_monsters_and_campaign_without_factions():
    provider = Provider(
        dict(name="Станция", premise="Люди исследуют пустую станцию."),
        dict(
            name="Сигнал",
            premise="Потеря связи",
            starting_situation="У входа обнаружен сигнал.",
        ),
    )
    setting = SettingGenerator(provider).generate("w", "Станция")
    assert not setting.content.creatures
    d = CampaignGenerator2(provider).generate(
        "c", setting, CampaignOptions(idea="Сигнал", party_size=2)
    )
    assert not d.factions and not d.encounters
    assert d.player_slot.faction_id is None
    assert all(a.faction_id is None for a in d.characters)
    state = CampaignCompiler().compile(d, d.characters[0].build)
    assert state.allied(*state.party)
    assert state.allied(state.party[0], state.party[0])
    assert state.relation(None, None) == "NEUTRAL"
    assert not state.hostile(*state.party)


@pytest.mark.parametrize(
    "exception,code",
    [
        (TimeoutError("timeout"), "provider_error"),
        (RuntimeError("provider refused"), "provider_response_error"),
        (TypeError("bad adapter argument"), "authoring_internal_error"),
    ],
)
def test_provider_errors_keep_diagnostics_and_do_not_retry(tmp_path, exception, code):
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "errors.db"))
    provider = Provider(exception)
    with pytest.raises(AuthoringFailure):
        with jobs.run("job", "setting", {}) as cp:
            SettingGenerator(provider, checkpoint=cp).generate("w", "Мир")
    issue = jobs.get("job")["issues"][0]
    assert issue["code"] == code
    assert issue["context"] == dict(
        exception_type=type(exception).__name__,
        provider="fixture",
        model="compact",
        stage="setting_blueprint",
        original_message=str(exception),
        attempt=1,
    )
    assert len(provider.calls) == 1


def test_provider_error_redacts_secrets_headers_and_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPATIBLE_API_KEY", "env-private-value")
    provider = Provider(
        RuntimeError(
            "timeout test-private-credential env-private-value Authorization: Bearer abc123\nhttps://name:password@example.org/?token=private"
        )
    )
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "secrets.db"))
    with pytest.raises(AuthoringFailure):
        with jobs.run("job", "setting", {}) as cp:
            SettingGenerator(provider, checkpoint=cp).generate("w", "Мир")
    saved = json.dumps(jobs.get("job"))
    for secret in (
        "test-private-credential",
        "env-private-value",
        "abc123",
        "name:password",
        "token=private",
    ):
        assert secret not in saved
    assert "timeout" in saved


def test_graph_ids_survive_display_renames_and_general_knowledge_is_not_a_secret():
    setting = generate_world()
    opts = CampaignOptions(idea="Пропажа")
    dto = ProceduralCampaignGenerator().semantics(
        CampaignBlueprint.model_validate(campaign_blueprint()), setting, opts
    )
    original = SemanticCampaignCompiler().compile("c", dto, setting, opts)
    renamed = dto.model_copy(deep=True)
    for group in (
        "locations",
        "npcs",
        "secrets",
        "quests",
        "factions",
        "objects",
        "encounters",
        "checks",
    ):
        for row in getattr(renamed, group):
            row.name = "Другое отображаемое имя"
    compiled = SemanticCampaignCompiler().compile("c", renamed, setting, opts)
    for group in (
        "locations",
        "characters",
        "secrets",
        "quests",
        "objects",
        "encounters",
        "checks",
    ):
        assert [v.id for v in getattr(original, group)] == [
            v.id for v in getattr(compiled, group)
        ]
    assert "История деревни" in compiled.characters[0].public_lore
    assert "История деревни" not in compiled.characters[0].knowledge
    assert set(compiled.characters[0].knowledge) <= {s.id for s in compiled.secrets}
    # Legacy runtime storage remains secret IDs; new semantics explicitly separate the fields.
    dto.npcs[0].known_secrets = ["Missing secret"]
    with pytest.raises(ValidationError, match="Unknown secrets"):
        SemanticCampaignDTO.model_validate(dto.model_dump())


def test_strict_registry_references_are_never_substituted():
    setting = generate_world()
    for group in ("skills", "items", "archetypes", "species", "creatures"):
        with pytest.raises(ValueError, match="Unknown"):
            pick(getattr(setting.content, group), "несуществующий", [])
    diagnostics = []
    assert (
        pick(setting.content.skills, diagnostics=diagnostics) in setting.content.skills
    )
    assert diagnostics[0]["code"] == "default_selection"


@pytest.mark.parametrize("profile", ["SMALL", "NORMAL", "LARGE"])
def test_role_coverage_is_thematic_mechanically_varied_and_deterministic(profile):
    a = generate_world(profile)
    assert a == generate_world(profile)
    other = generate_world(profile, seed=5)
    assert other.content != a.content
    assert set(a.content.species) == set(other.content.species)
    names = [
        v.name
        for group in ("archetypes", "backgrounds", "skills", "items", "creatures")
        for v in getattr(a.content, group).values()
    ]
    assert not any(re.search(r"·\s*(?:участок\s*)?\d", n) for n in names)
    weapons = [
        c for v in a.content.items.values() for c in v.components if c.type == "weapon"
    ]
    assert (
        len(
            {(w.damage_expression, w.hands, w.range, w.attack_ability) for w in weapons}
        )
        >= 3
    )
    assert len({v.default_ability for v in a.content.skills.values()}) >= 3
    assert len({tuple(v.primary_abilities) for v in a.content.archetypes.values()}) >= 3
    assert any("Резонатор" in v.name for v in a.content.items.values())


def test_natural_hazard_does_not_become_species_enemy():
    b = world_blueprint()
    b["threat_families"] = [
        dict(
            name="Разрыв экзоматерии",
            nature="phenomenon",
            description="Нестабильная граница материала.",
        )
    ]
    setting = generate_world(data=b)
    assert not setting.content.creatures
    d = ProceduralCampaignGenerator().generate(
        "c",
        CampaignBlueprint.model_validate(campaign_blueprint()),
        setting,
        CampaignOptions(idea="Аномалия"),
    )
    hazard = next(o for o in d.objects if o.name == "Разрыв экзоматерии")
    assert any(c.type == "hazard" for c in hazard.components)
    assert not d.encounters


def test_optional_faction_encounter_uses_existing_runtime_and_restores(tmp_path):
    setting = generate_world()
    d = ProceduralCampaignGenerator().generate(
        "c",
        CampaignBlueprint.model_validate(campaign_blueprint()),
        setting,
        CampaignOptions(idea="Исследование", party_size=2),
    )
    state = CampaignCompiler().compile(d, d.characters[0].build)
    encounter = d.encounters[0]
    for aid in state.party:
        state.actor(aid).location = encounter.location_id
    from backend.tabletop.runtime import TabletopRuntime
    from backend.tabletop.commands import Command

    state, _ = TabletopRuntime().execute(
        state, Command(type="start_encounter", target=encounter.id)
    )
    assert state.encounter or state.session_state.pending
    assert state.hostile(state.party[0], encounter.participants[0])
    repo = TabletopRepository(tmp_path / "optional.db")
    gid = repo.create(state)
    _, restored = TabletopRepository(repo.path).load(gid)
    assert restored.definition == state.definition
    assert restored.actor("player_slot").faction is None


def test_player_faction_requires_explicit_inline_affiliation():
    b = campaign_blueprint()
    b["factions"] = [dict(name="Не игрок")]
    s = generate_world()
    opts = CampaignOptions(idea="Исследование")
    gen = ProceduralCampaignGenerator()
    d = gen.generate("c", CampaignBlueprint.model_validate(b), s, opts)
    assert d.player_slot.faction_id is None
    b["player_affiliation"] = dict(name="Экспедиция", description="Группа игрока")
    d = gen.generate("c", CampaignBlueprint.model_validate(b), s, opts)
    assert (
        next(f.name for f in d.factions if f.id == d.player_slot.faction_id)
        == "Экспедиция"
    )


def test_campaign_compiler_failure_resumes_blueprint_without_provider(
    tmp_path, monkeypatch
):
    s = generate_world()
    provider = Provider(campaign_blueprint())
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "resume.db"))
    real = SemanticCampaignCompiler.compile

    def fail(*args, **kwargs):
        raise ValueError("graph compiler failure")

    monkeypatch.setattr(SemanticCampaignCompiler, "compile", fail)
    with pytest.raises(ValueError):
        with jobs.run("job", "campaign", {}) as cp:
            CampaignGenerator2(provider, checkpoint=cp).generate(
                "c", s, CampaignOptions(idea="Пропажа")
            )
    assert "campaign_blueprint" in jobs.get("job")["outputs"]
    monkeypatch.setattr(SemanticCampaignCompiler, "compile", real)
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "resume.db"))
    with jobs.run("job", "campaign", {}) as cp:
        CampaignGenerator2(provider, checkpoint=cp).generate(
            "c", s, CampaignOptions(idea="Пропажа")
        )
    assert len(provider.calls) == 1


def test_legacy_checkpoint_and_saved_semantics_keep_secret_meaning(tmp_path):
    s = ProceduralContentCompiler().compile("w", world())
    legacy = campaign()
    legacy["npcs"][0]["knowledge"] = legacy["npcs"][0].pop("known_secrets")
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "legacy.db"))
    provider = Provider()
    with jobs.run("job", "campaign", {}) as cp:
        cp.save("campaign_semantics", legacy)
        d = CampaignGenerator2(provider, checkpoint=cp).generate(
            "c", s, CampaignOptions(idea="Пропажа")
        )
    assert not provider.calls
    assert d.characters[0].knowledge == [stable_id("secret", "След")]
    payload = d.model_dump()
    payload["semantic_source"] = legacy
    restored = CampaignCompiler().validate(payload)
    assert restored.semantic_source["npcs"][0]["known_secrets"] == ["След"]
    assert restored.characters[0].knowledge == d.characters[0].knowledge


def test_real_provider_compact_world_campaign_smoke(tmp_path):
    """Opt-in: configure TABLETOP_SMOKE_PROVIDER/MODEL and that provider's key env."""
    import llm

    provider = os.getenv("TABLETOP_SMOKE_PROVIDER")
    model = os.getenv("TABLETOP_SMOKE_MODEL")
    if not provider or not model:
        pytest.skip("No explicit real-provider smoke configuration")
    spec = llm.PROVIDERS.get(provider)
    if spec is None or (spec.key_env and not os.getenv(spec.key_env)):
        pytest.skip("Provider credentials unavailable")
    from backend.tabletop.dm import DMAgent

    repo = TabletopRepository(tmp_path / "smoke.db")

    class SmokeAgent(DMAgent):
        calls = []

        def call(self, *args):
            self.calls.append(args[1])
            return super().call(*args)

    agent = SmokeAgent(
        repo, dict(provider=provider, model=model, max_tokens=6000, temperature=0.5)
    )
    setting = SettingGenerator(agent).generate(
        "smoke_world",
        "НИИ исследует экзоматерию; технологии, аномалии и научная этика, без магии.",
    )
    d = CampaignGenerator2(agent).generate(
        "smoke_campaign",
        setting,
        CampaignOptions(
            idea="Пропавшая экспедиция оставила противоречивые свидетельства"
        ),
    )
    CampaignCompiler().validate(d)
    assert 1 <= agent.calls.count("authoring_setting_blueprint") <= 2
    assert 1 <= agent.calls.count("authoring_campaign_blueprint") <= 2


def test_full_length_creative_fields_remain_compilable():
    b = world_blueprint()
    b["premise"] = "М" * 2000
    b["world_rules"] = ["П" * 120] * 20
    b["lore"] = ["Л" * 2000] * 6
    b["power_traditions"] = [
        dict(name="Источник" + str(i), description="Т" * 2000, practice="technical")
        for i in range(3)
    ]
    s = generate_world(data=b)
    data = campaign_blueprint()
    data["premise"] = "П" * 2000
    data["central_conflict"] = "К" * 2000
    data["developments"] = ["И" * 2000] * 6
    for group in ("locations", "actors", "secret_ideas", "quest_hooks"):
        for entry in data[group]:
            entry["description"] = "О" * 2000
    d = ProceduralCampaignGenerator().generate(
        "c",
        CampaignBlueprint.model_validate(data),
        s,
        CampaignOptions(
            idea="Развёрнутая история",
            generation=CampaignGenerationConfig(profile="LONG"),
        ),
    )
    CampaignCompiler().validate(d)


def test_lazy_blueprint_has_no_references_and_preserves_general_knowledge():
    from backend.tabletop.semantic_expansion import expand

    s = generate_world()
    d = ProceduralCampaignGenerator().generate(
        "c",
        CampaignBlueprint.model_validate(campaign_blueprint()),
        s,
        CampaignOptions(idea="Пропажа"),
    )
    state = CampaignCompiler().compile(d, d.characters[0].build)
    provider = Provider(
        dict(
            locations=[dict(name="Лаборатория")],
            actors=[dict(name="Исследователь", knowledge=["История деревни"])],
            equipment_families=[dict(name="Сканер", purpose="tool")],
            objects=[dict(name="Стенд")],
        )
    )
    after, _ = expand(provider, "c", state, "Новая лаборатория")
    assert len(provider.calls) == 1
    context = json.loads(provider.calls[0][2][1]["content"])["context"]
    assert "catalog" not in context and "locations" not in context
    new = next(a for a in after.actors().values() if a.name == "Исследователь")
    assert "История деревни" in new.public_lore and new.knowledge == []
    assert new.faction is None
    assert after.definition.setting_definition == state.definition.setting_definition
    assert after.definition.expansion_blueprints[-1]["blueprint"]["actors"][0][
        "knowledge"
    ] == ["История деревни"]


def test_independent_party_can_heal_and_receive_reputation_without_faction():
    from backend.tabletop.runtime import TabletopRuntime
    from backend.tabletop.commands import Command
    from backend.tabletop.features import FeatureDefinition, FeatureEffect
    from backend.tabletop.services.world import WorldService

    s = generate_world()
    d = ProceduralCampaignGenerator().generate(
        "c",
        CampaignBlueprint.model_validate(campaign_blueprint()),
        s,
        CampaignOptions(idea="Пропажа", party_size=2),
    )
    state = CampaignCompiler().compile(d, d.characters[0].build)
    hero = state.actor(state.party[0])
    hero.features.append("test_heal")
    state.ruleset.features["test_heal"] = FeatureDefinition(
        id="test_heal",
        name="Помощь",
        description="Помощь участнику партии",
        activation="ACTION",
        target="ally",
        effects=[FeatureEffect(type="heal", value=1)],
    )
    target = state.actor(state.party[1])
    target.hp -= 1
    before = target.hp
    state, _ = TabletopRuntime().execute(
        state, Command(type="use_feature", feature_id="test_heal", target=target.id)
    )
    assert state.actor(target.id).hp == before + 1
    state.quests[d.quests[0].id] = "completed"
    # Advancing time processes quest reputation, including an independent giver.
    WorldService.advance(state, [])
    assert None not in state.faction_reputation


def test_partial_blueprint_resume_keeps_omitted_fields_and_registry(
    tmp_path, monkeypatch
):
    setting = generate_world()
    provider = Provider({"name": "Новое название"})
    jobs = AuthoringJobs(TabletopRepository(tmp_path / "partial.db"))
    real = ProceduralContentCompiler.compile

    def fail(*args, **kwargs):
        raise ValueError("compiler interrupted")

    monkeypatch.setattr(ProceduralContentCompiler, "compile", fail)
    with pytest.raises(ValueError):
        with jobs.run("partial", "setting", {}) as cp:
            SettingGenerator(provider, checkpoint=cp).generate(
                "w", "Новое имя", setting, "foundation"
            )
    assert jobs.get("partial")["outputs"]["setting_blueprint"] == {
        "name": "Новое название"
    }
    monkeypatch.setattr(ProceduralContentCompiler, "compile", real)
    with jobs.run("partial", "setting", {}) as cp:
        result = SettingGenerator(provider, checkpoint=cp).generate(
            "w", "Новое имя", setting, "foundation"
        )
    assert len(provider.calls) == 1
    assert result.name == "Новое название" and result.content == setting.content
    assert result.semantic_source["premise"] == setting.semantic_source["premise"]
