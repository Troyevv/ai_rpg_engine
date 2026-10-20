"""Hybrid controls extend the existing Preparation job surface."""
from backend.api.schemas import Revision, Credential


class Resume(Revision,Credential):
    retry_uncertain: bool = False


def install(app,repo,preparation,credentials,job):
    @app.get('/api/jobs/{jid}/generation')
    def status(jid:str):
        value=repo.generation_status(jid)
        if value is None: raise ValueError('Checkpointed generation not found.')
        return value

    @app.get('/api/jobs/{jid}/generation/checkpoints/{unit}')
    def inspect(jid:str,unit:str,author:bool=False):
        return repo.inspect_generation_checkpoint(jid,unit,author)

    @app.post('/api/jobs/{jid}/generation/pause')
    def pause(jid:str,body:Revision):
        repo.generation_control(jid,'pause',body.revision)
        return job(jid)

    @app.post('/api/jobs/{jid}/generation/resume')
    def resume(jid:str,body:Resume):
        import json
        config=json.loads(repo.preparation_job(jid)['config_json'])
        preparation.resume_generation(jid,credentials.resolve(config['provider'],body.key()),
            body.revision,body.retry_uncertain)
        return job(jid)
