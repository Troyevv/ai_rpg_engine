import json
import pytest
from backend.tabletop.authoring import stage_schema, AuthoringCompiler
from backend.tabletop.definitions import CampaignDefinition
from backend.tabletop.content import ContentRegistry
from backend.tabletop.setting_generation import StagedAuthor, AuthoringFailure


class DM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call(self, id, stage, messages, structured):
        self.calls.append(messages)
        return json.dumps(self.response)


def response():
    return dict(
        objects=[
            dict(
                id=f"case_{i}",
                name=f"Case {i}",
                location_id="room",
                container_capacity=12,
                contents=[],
            )
            for i in range(4)
        ],
        context_actions=[
            dict(
                id=f"open_{i}",
                name=f"Open {i}",
                location_id="room",
                operation="interact",
                reference_id=f"case_{i}",
            )
            for i in range(4)
        ],
    )


def test_multiple_actions_and_containers_compile_without_domain_union():
    schema = stage_schema(
        "ActionsAndObjects", CampaignDefinition, ["objects", "context_actions"]
    )
    dm = DM(response())
    result = StagedAuthor(dm).run(
        "generation", "objects", schema, {}, AuthoringCompiler.stage, "contract"
    )
    assert len(result["objects"]) == len(result["context_actions"]) == 4
    assert all(o["components"][0]["capacity"] == 12 for o in result["objects"])
    assert all(
        a["interaction"] and a["object_id"] == f"case_{i}"
        for i, a in enumerate(result["context_actions"])
    )
    assert len(dm.calls) == 1


@pytest.mark.parametrize("capacity", [0, "12", None])
def test_invalid_authoring_has_exact_field_and_entity(capacity):
    data = response()
    data["objects"][2]["container_capacity"] = capacity
    if capacity is None:  # absence is meaningful: not a container, never guessed
        result = AuthoringCompiler.stage(
            stage_schema(
                "S", CampaignDefinition, ["objects", "context_actions"]
            ).model_validate(data)
        )
        assert result["objects"][2]["components"] == []
        return
    schema = stage_schema("S", CampaignDefinition, ["objects", "context_actions"])
    dm = DM(data)
    with pytest.raises(AuthoringFailure) as caught:
        StagedAuthor(dm).run(
            "generation", "objects", schema, {}, AuthoringCompiler.stage, "contract"
        )
    issue = caught.value.issues[0]
    assert issue.field == "objects.2.container_capacity" and issue.entity_id == "case_2"
    assert len(dm.calls) == 2
    assert (
        json.loads(dm.calls[1][-1]["content"])["previous_issues"][0]["field"]
        == issue.field
    )


def test_item_authoring_has_named_components_and_preserves_every_component():
    schema = stage_schema("Equipment", ContentRegistry, ["items"])
    assert "discriminator" not in json.dumps(schema.model_json_schema())
    value = schema.model_validate(
        dict(
            items={
                "case": dict(
                    id="case",
                    name="Case",
                    container_capacity=12,
                    tool=dict(skill_id="medicine", modifier=2),
                )
            }
        )
    )
    item = AuthoringCompiler.stage(value)["items"]["case"]
    assert {c["type"] for c in item["components"]} == {"container", "tool"}


def test_failed_stage_resumes_after_repository_restart_without_repeating_llm(tmp_path):
    from backend.tabletop.authoring_jobs import AuthoringJobs
    from backend.tabletop.repository import TabletopRepository
    from backend.tabletop.content import SettingFoundation

    path = tmp_path / "jobs.db"
    jobs = AuthoringJobs(TabletopRepository(path))
    source = {"concept": "A new universe"}
    with pytest.raises(AuthoringFailure):
        with jobs.run("job", "setting", source) as checkpoint:
            StagedAuthor(
                DM({"id": "world", "name": "World"}), checkpoint=checkpoint
            ).run("job", "foundation", SettingFoundation, {}, lambda x: x, "contract")
            StagedAuthor(DM({"id": "world"}), checkpoint=checkpoint).run(
                "job", "society", SettingFoundation, {}, lambda x: x, "contract"
            )
    restarted = AuthoringJobs(TabletopRepository(path))
    assert restarted.public("job")["status"] == "FAILED"
    dm = DM({"id": "different", "name": "Should not be used"})
    with restarted.run("job", "setting", source) as checkpoint:
        value = StagedAuthor(dm, checkpoint=checkpoint).run(
            "job", "foundation", SettingFoundation, {}, lambda x: x, "contract"
        )
        assert value.id == "world" and dm.calls == []
        good = DM({"id": "society", "name": "Complete"})
        StagedAuthor(good, checkpoint=checkpoint).run(
            "job", "society", SettingFoundation, {}, lambda x: x, "contract"
        )
        checkpoint.complete({"id": "world"})
    assert restarted.public("job")["status"] == "COMPLETE"
    assert restarted.public("job")["completed_stages"] == ["foundation", "society"]


def test_api_resume_preserves_stages_and_does_not_persist_credentials(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.tabletop.dm import DMAgent
    from backend.tabletop.procedural_content import ProceduralContentCompiler
    from semantic_fixture import world

    calls = []

    def call(self, id, stage, messages, structured):
        calls.append(stage)
        return json.dumps(world())

    monkeypatch.setattr(DMAgent, "call", call)
    real = ProceduralContentCompiler.compile

    def fail(*args, **kwargs):
        raise ValueError("Injected compiler failure")

    monkeypatch.setattr(ProceduralContentCompiler, "compile", fail)
    path = tmp_path / "resume.db"
    request = dict(
        authoring_id="resume-world",
        concept="Мир стеклянных приливов",
        config={"model": "fixture"},
        api_key="test-key-never-persist",
    )
    with TestClient(create_app(path)) as client:
        response = client.post("/api/tabletop/settings/worlds/generate", json=request)
        assert response.status_code == 409
        job = client.get("/api/tabletop/authoring/resume-world").json()
        assert job["status"] == "FAILED" and job["stage"] == "setting_compile"
        assert job["completed_stages"] == ["setting_semantics"]
        assert "test-key-never-persist" not in json.dumps(job)
    monkeypatch.setattr(ProceduralContentCompiler, "compile", real)
    with TestClient(create_app(path)) as client:
        response = client.post("/api/tabletop/settings/worlds/generate", json=request)
        assert response.status_code == 200, response.text
        assert calls == ["authoring_setting_semantics"]
        assert (
            client.post("/api/tabletop/settings/worlds/generate", json=request).json()
            == response.json()
        )
        assert len(calls) == 1


def test_late_stage_context_uses_reference_index_without_changing_registry():
    from test_universal_content import setting
    from backend.tabletop.setting_generation import setting_authoring_context

    world = setting()
    before = world.model_dump_json()
    context = setting_authoring_context(world, ("creatures",))
    assert set(context["content"]["features"]) == set(world.content.features)
    assert all(
        set(v) == {"id", "name"} for v in context["content"]["features"].values()
    )
    assert world.model_dump_json() == before
