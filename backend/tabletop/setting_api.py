"""Reusable setting authoring endpoints, separate from game mutation."""

from uuid import uuid4
from fastapi import APIRouter
from pydantic import Field
from backend.api.schemas import Credential, ModelConfig
from .content import SettingDefinition
from .content_registry import SettingValidator
from .setting_repository import SettingRepository
from .setting_generation import SettingGenerator
from .validation import CampaignValidationError


class SettingSave(Credential):
    definition: SettingDefinition
    revision: int | None = None
    confirm: bool = False


class SettingGenerate(Credential):
    config: ModelConfig
    concept: str = Field(min_length=3, max_length=12000)
    section: str | None = None
    setting_id: str | None = None


def install(router, repo, agent, validation_response):
    worlds = SettingRepository(repo)

    @router.get("/settings/schema")
    def schema():
        return SettingDefinition.model_json_schema()

    @router.get("/settings/worlds")
    def list_worlds():
        return worlds.list()

    @router.get("/settings/worlds/{id}")
    def get_world(id: str):
        return worlds.get(id)

    @router.post("/settings/worlds")
    def save_world(body: SettingSave):
        try:
            return worlds.save(body.definition, body.revision, body.confirm)
        except CampaignValidationError as exc:
            return validation_response(exc)

    @router.post("/settings/worlds/validate")
    def validate_world(body: SettingSave):
        try:
            setting = SettingValidator().validate(body.definition)
            return {"valid": True, "definition": setting.model_dump(), "issues": []}
        except CampaignValidationError as exc:
            return validation_response(exc)

    @router.post("/settings/worlds/import-catalog")
    def import_world():
        from .catalog import load_ruleset
        from .content_migration import import_catalog

        setting = import_catalog(load_ruleset("d20-fantasy-v2"))
        if any(s["id"] == setting.id for s in worlds.list()):
            return worlds.get(setting.id)
        return worlds.save(setting, confirm=True)

    @router.post("/settings/worlds/generate")
    def generate_world(body: SettingGenerate):
        existing = worlds.get(body.setting_id) if body.setting_id else None
        id = body.setting_id or uuid4().hex
        try:
            definition = SettingGenerator(agent(body)).generate(
                id,
                body.concept,
                (
                    SettingDefinition.model_validate(existing["definition"])
                    if existing
                    else None
                ),
                body.section,
            )
            if not existing:
                definition.id = id
            return worlds.save(definition, existing["revision"] if existing else None)
        except CampaignValidationError as exc:
            return validation_response(exc)
