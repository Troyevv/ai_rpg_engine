"""Thin control/draft API. No LLM calls on selection, validation or confirmation."""
from typing import Literal
from pydantic import Field
from backend.api.schemas import Revision, Credential, ModelConfig
from backend.services.protagonist_creation import empty_draft
from backend.runtime_v3.selectors import ui_view


class Transition(Revision):
    operation_id: str = Field(min_length=8,max_length=100)
    operation: Literal['permanent','temporary','observe','resume']
    actor_id: str | None = None
    pov_actor_id: str | None = None
    draft: dict | None = None
    preview: bool = False


class Generate(Revision,Credential):
    draft: dict
    path: str = Field(default='',max_length=300)
    instruction: str = Field(default='',max_length=8000)
    config: ModelConfig


def install(app,repo,credentials):
    @app.get('/api/saves/{sid}/protagonist/draft')
    def draft(sid:int,operation_id:str):
        if not 8<=len(operation_id)<=100: raise ValueError('Некорректный ID черновика.')
        snapshot=repo.get_snapshot(sid)
        from backend.services.protagonist_creation import editor_schema,editor_context
        schema,proposals=editor_schema()
        from backend.runtime_v3.repository import read_history
        with repo.connect() as db: history,_=read_history(db,snapshot.get('history_head'))
        return dict(draft=empty_draft(snapshot,operation_id),schema=schema,proposal_schemas=proposals,context=editor_context(snapshot,history))

    @app.post('/api/saves/{sid}/protagonist')
    def transition(sid:int,body:Transition):
        after=repo.transition_protagonist(sid,**body.model_dump())
        return dict(preview=ui_view(after)) if body.preview else repo.get_save(sid)

    @app.post('/api/saves/{sid}/protagonist/generate')
    def generate(sid:int,body:Generate):
        if repo.get_save(sid)['revision']!=body.revision: raise ValueError('Сейв изменился. Обнови контекст создания.')
        from backend.services.protagonist_generation import generate as run
        key=credentials.resolve(body.config.provider,body.key())
        return dict(draft=run(repo,sid,body.draft,body.path,body.instruction,body.config.model_dump(),key))
