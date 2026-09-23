"""Thin draft endpoints. All authoritative state and validation are backend-side."""
from typing import Any, Literal
from pydantic import Field
from fastapi.responses import PlainTextResponse
from backend.api.schemas import DTO, Revision, Credential, ModelConfig
from backend.services import draft_world as domain


class Import(Revision):
    text: str = Field(min_length=1,max_length=2000000)

class Change(Revision):
    operation: Literal['patch','add','remove','restore']
    kind: str = ''
    entity_id: str = ''
    field: str = ''
    value: Any = None
    source_id: int | None = None
    warnings_ack: bool = False

class Generate(Revision,Credential):
    task: Literal['world','field','character'] = 'world'
    text: str = Field(default='',max_length=100000)
    use_idea: bool = False
    kind: str = ''
    entity_id: str = ''
    field: str = ''
    warnings_ack: bool = False
    config: ModelConfig

class Confirm(Revision):
    version_id: int


def install(app,repo,preparation,credentials,job):
    @app.get('/api/workspaces/{wid}/draft')
    def draft(wid:str,author:bool=False):return repo.draft(wid,author)

    @app.post('/api/workspaces/{wid}/draft/import')
    def import_world(wid:str,body:Import):
        repo.import_draft(wid,body.text,body.revision)
        return repo.draft(wid)

    @app.patch('/api/workspaces/{wid}/draft')
    def change(wid:str,body:Change):
        eid=repo.edit_draft(wid,body.revision,body.operation,body.kind,body.entity_id,body.field,body.value,body.source_id,body.warnings_ack)
        return {**repo.draft(wid,True),'entity_id':eid}

    @app.get('/api/workspaces/{wid}/draft/dependencies')
    def dependencies(wid:str,kind:str,entity_id:str):
        state=repo.draft(wid,True)['state']
        return domain.dependencies(state,kind,entity_id)

    @app.post('/api/workspaces/{wid}/draft/generate')
    def generate(wid:str,body:Generate):
        if body.task=='world' and not body.text.strip() and not body.use_idea:raise ValueError('Опиши желаемый мир.')
        if body.task!='world':
            state=repo.draft(wid,True)['state']
            domain.entity(state,body.kind,body.entity_id)
            if body.task=='character' and body.kind!='character':raise ValueError('Нужна карточка персонажа.')
            if body.task=='field' and body.field not in domain.FIELDS.get(body.kind,set()) and not(body.kind=='character' and body.field.startswith('fields.')):raise ValueError('Поле недоступно.')
        config={**body.config.model_dump(),'_draft_task':body.task,'_draft_input':body.text,'_use_idea':body.use_idea,
                '_warnings_ack':body.warnings_ack,'_draft_target':{'kind':body.kind,'id':body.entity_id,'field':body.field}}
        jid=preparation.submit(wid,'draft_'+body.task,body.text,config,body.revision,credentials.resolve(body.config.provider,body.key()))
        return job(jid)

    @app.post('/api/workspaces/{wid}/draft/confirm')
    def confirm(wid:str,body:Confirm):return repo.confirm_draft(wid,body.revision,body.version_id)

    @app.get('/api/workspaces/{wid}/draft/export')
    def export(wid:str,version_id:int,format:Literal['md','txt']='md'):
        value=repo.draft(wid,True)
        if value['version_id']!=version_id:raise ValueError('Версия изменилась. Обнови редактор.')
        return PlainTextResponse(domain.export_markdown(value['state']),headers={'Content-Disposition':f'attachment; filename="world.{format}"'})
