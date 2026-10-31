"""NPC review HTTP adapter; domain and transaction rules live in the service."""
from typing import Literal
from pydantic import Field, StrictStr
from backend.api.schemas import Revision, Credential, ModelConfig
from backend.services import npc_review


class Edit(Revision):
    review_revision: int = Field(ge=0)
    operation_id: str = Field(min_length=8, max_length=100)
    fields: dict[str, StrictStr]
    character: dict = Field(default_factory=dict)
    proposals: dict[str, StrictStr] = Field(default_factory=dict)
    action: Literal['save', 'defer', 'confirm'] = 'save'


class Generate(Revision, Credential):
    review_revision: int = Field(ge=0)
    field: str
    config: ModelConfig


def install(app, repo, credentials):
    @app.post('/api/saves/{sid}/npc-reviews/{cid}')
    def edit(sid: int, cid: str, body: Edit):
        npc_review.edit(repo, sid, cid, **body.model_dump())
        return repo.get_save(sid)

    @app.post('/api/saves/{sid}/npc-reviews/{cid}/generate')
    def generate(sid: int, cid: str, body: Generate):
        return npc_review.generate(repo, sid, cid, field=body.field, revision=body.revision,
            review_revision=body.review_revision, config=body.config.model_dump(),
            api_key=credentials.resolve(body.config.provider, body.key()))
