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
    @app.get("/api/saves/{sid}/correspondence")
    def correspondence(sid: int):
        from backend.runtime_v3.remote import correspondence_projection
        return correspondence_projection(repo.get_snapshot(sid))

    @app.post("/api/saves/{sid}/correspondence")
    def correspondence_action(sid: int, body: Command):
        from backend.runtime_v3.remote import correspondence_projection
        from backend.runtime_v3.remote_models import HISTORICAL_CHANNELS
        snapshot = repo.get_snapshot(sid)
        cmd = body.command
        event = snapshot['world_state']['remote_events'].get(cmd.event_id, {})
        if not (cmd.action == 'send' and cmd.channel in HISTORICAL_CHANNELS or
                cmd.action == 'read' and event.get('channel') in HISTORICAL_CHANNELS):
            raise ValueError('Ожидается отправка или открытие письма.')
        repo.remote_action(sid, body.revision, cmd.model_dump())
        return correspondence_projection(repo.get_snapshot(sid))

    @app.post("/api/saves/{sid}/phone")
    def action(sid: int, body: Command):
        repo.remote_action(sid, body.revision, body.command.model_dump())
        return repo.get_save(sid)


def install_jobs(app, repo, credentials, public_job):
    @app.get('/api/saves/{sid}/phone/diagnostics/{jid}')
    def communication_diagnostics(sid: int, jid: str):
        import json
        snapshot = repo.get_snapshot(sid)
        job = repo.get_job(jid)
        if job['save_id'] != sid or job['kind'] != 'communication':
            raise ValueError('Операция связи недоступна в этом прохождении.')
        config = json.loads(job['config_json'])
        if config.get('communication',{}).get('owner_id') != snapshot['world_state']['camera']['controlled_actor_id']:
            raise ValueError('Диагностика телефона другого персонажа недоступна.')
        return dict(job_id=jid, source=config.get('communication'),
                    attempt_epoch=job['attempt_epoch'], status=job['status'],
                    frames=json.loads(job['context_json'] or '[]'),
                    requests=[{k: row.get(k) for k in ('id','stage','status','model','input_tokens','output_tokens','cached_input_tokens','cost_usd','duration','finish_reason')}
                              for row in repo.request_log(job_id=jid)])

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
