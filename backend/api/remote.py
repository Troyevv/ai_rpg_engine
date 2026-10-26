"""Phone controls are explicit commands, never natural-language intent parsing."""

from backend.api.schemas import Revision
from backend.runtime_v3.remote_models import RemoteCommand
from backend.api.schemas import Credential, ModelConfig
from backend.runtime_v3.communication import Continuation
from pydantic import Field, model_validator
import engine


class Command(Revision):
    command: RemoteCommand


class Dispatch(Credential):
    revision: int = Field(ge=0)
    config: ModelConfig
    command: RemoteCommand | None = None
    continuation: Continuation | None = None

    @model_validator(mode='after')
    def one_intent(self):
        if (self.command is None) == (self.continuation is None):
            raise ValueError('Выбери команду или продолжение связи.')
        return self


def install(app, repo):
    @app.post("/api/saves/{sid}/phone")
    def action(sid: int, body: Command):
        repo.remote_action(sid, body.revision, body.command.model_dump())
        return repo.get_save(sid)


def install_jobs(app, repo, credentials, public_job):
    @app.post('/api/saves/{sid}/phone/dispatch')
    def dispatch(sid: int, body: Dispatch):
        settings = dict(body.config.model_dump(), expected_revision=body.revision)
        if body.command:
            settings['remote_command'] = body.command.model_dump()
        else:
            settings['communication'] = body.continuation.model_dump()
        jid = engine.submit(repo, sid, '', 'communication', settings,
                            api_key=credentials.resolve(body.config.provider, body.key()))
        return dict(job=public_job(jid), save=repo.get_save(sid))
