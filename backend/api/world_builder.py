"""Manual authoring endpoints; revisions and history use the existing draft journal."""
from typing import Any
from pydantic import Field
from backend.api.schemas import Revision, Credential, ModelConfig
from backend.services import world_builder as builder

class Save(Revision):
    world: dict[str,Any]
    campaign: dict[str,str]
    cards: list[dict[str,Any]] = Field(default_factory=list)
    history: dict[str,Any] | None = None

class Dismiss(Revision):
    job_id: str

class Suggest(Revision,Credential):
    path: list[str]
    instruction: str = Field(default='',max_length=10000)
    config: ModelConfig


def install(app,repo,preparation,credentials,job):
    @app.get('/api/world-builder/workspaces')
    def workspaces():return repo.builder_workspaces()

    @app.get('/api/world-builder/schema')
    def schema():return builder.schema()

    @app.post('/api/workspaces/{wid}/builder')
    def create(wid:str,body:Revision):return repo.create_builder(wid,body.revision)

    @app.get('/api/workspaces/{wid}/builder')
    def read(wid:str):return repo.builder(wid)

    @app.post('/api/workspaces/{wid}/builder/validate')
    def validate(wid:str,body:Save):
        current=repo.builder(wid)
        if current['revision']!=body.revision:raise ValueError('Конфликт ревизий.')
        value=builder.update(current['state'],body.world,body.campaign,body.cards,body.history)
        return {'validation':builder.report(value),'calendar_label':builder.time_label(value)}

    @app.put('/api/workspaces/{wid}/builder')
    def save(wid:str,body:Save):
        return repo.save_builder(wid,body.revision,body.world,body.campaign,body.cards,body.history)

    @app.post('/api/workspaces/{wid}/builder/restore/{version}')
    def restore(wid:str,version:int,body:Revision):return repo.restore_builder(wid,body.revision,version)

    @app.post('/api/workspaces/{wid}/builder/proposal/dismiss')
    def dismiss(wid:str,body:Dismiss):return repo.dismiss_builder_proposal(wid,body.revision,body.job_id)

    @app.post('/api/workspaces/{wid}/builder/generate')
    def generate(wid:str,body:Suggest):
        current=read(wid)
        if current['revision']!=body.revision:raise ValueError('Конфликт ревизий.')
        from backend.services.builder_generation import target
        target(current['state'],body.path)
        config={**body.config.model_dump(),'_draft_task':'builder','_builder_path':body.path,'_draft_input':body.instruction}
        jid=preparation.submit(wid,'draft_builder',body.instruction,config,body.revision,credentials.resolve(body.config.provider,body.key()))
        return job(jid)
