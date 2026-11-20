from typing import Literal
from pydantic import Field
from backend.api.schemas import Credential,ModelConfig,Revision
from backend.services import portrait_proposals as service


class Selection(Revision):
    ids:list[str]=Field(min_length=1,max_length=64)


class Quote(Selection, Credential):
    config:ModelConfig


def install(app,repo,credentials):
    base='/api/portrait-proposals/{scope}/{owner}'
    Scope=Literal['workspace','save']

    @app.post(base)
    def quote(scope:Scope,owner:str,body:Quote):
        key=credentials.resolve(body.config.provider,body.key())
        return service.quote(repo,scope,owner,body.revision,body.ids,body.config.model_dump(),key)

    @app.post(base+'/{rid}/generate')
    def generate(scope:Scope,owner:str,rid:str,body:Credential):
        return service.generate(repo,scope,owner,rid,credentials,body.key())

    @app.get(base+'/{rid}')
    def status(scope:Scope,owner:str,rid:str):
        return service.inspect(repo,scope,owner,rid)

    @app.post(base+'/{rid}/cancel')
    def cancel(scope:Scope,owner:str,rid:str):
        return service.cancel(repo,scope,owner,rid)

    @app.post(base+'/{rid}/apply')
    def apply(scope:Scope,owner:str,rid:str,body:Selection):
        return service.apply(repo,scope,owner,rid,body.ids)
