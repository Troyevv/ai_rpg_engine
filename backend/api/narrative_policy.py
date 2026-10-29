"""Editable future policy; no provider calls or world-domain side effects."""
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile, NarrativeRiskProfile, PACING_PRESETS, RISK_PRESETS


from backend.services.narrative_policy import PolicyUpdate

from backend.api.schemas import Revision
from backend.runtime_v3.models import WeatherProfile
class WeatherSetup(Revision):
    profile: WeatherProfile

def install(app, repo):
    @app.get('/api/saves/{sid}/weather')
    def get_weather(sid:int):
        return repo.get_snapshot(sid)['world_state']['meta'].get('weather')

    @app.put('/api/saves/{sid}/weather')
    def configure_weather(sid:int, body:WeatherSetup):
        repo.configure_weather(sid,body.revision,body.profile.model_dump())
        return repo.get_save(sid)

    @app.get('/api/saves/{sid}/narrative-policy')
    def get_policy(sid: int):
        snapshot=repo.get_snapshot(sid)
        if snapshot.get('mode')=='tabletop' or 'world_state' not in snapshot:
            raise ValueError('Настройки доступны только в Narrative.')
        meta=snapshot['world_state']['meta']
        return dict(current={k:meta[k] for k in ('narrative_pacing','narrative_risk','outcome_preference','genre')},
            pacing_presets={k:NarrativePacingProfile(preset=k).model_dump() for k in PACING_PRESETS},
            risk_presets={k:NarrativeRiskProfile(preset=k).model_dump() for k in RISK_PRESETS},
            schema=PolicyUpdate.model_json_schema())

    @app.put('/api/saves/{sid}/narrative-policy')
    def set_policy(sid: int, body: PolicyUpdate):
        repo.update_narrative_policy(sid,body.revision,body.model_dump(exclude={'revision'} | ({'genre'} if 'genre' not in body.model_fields_set else set())))
        return repo.get_save(sid)
