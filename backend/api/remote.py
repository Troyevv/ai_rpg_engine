"""Phone controls are explicit commands, never natural-language intent parsing."""
from backend.api.schemas import Revision
from backend.runtime_v3.remote_models import RemoteCommand


class Command(Revision):
    command: RemoteCommand


def install(app, repo):
    @app.post('/api/saves/{sid}/phone')
    def action(sid: int, body: Command):
        repo.remote_action(sid, body.revision, body.command.model_dump())
        return repo.get_save(sid)
