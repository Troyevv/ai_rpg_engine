"""Editable future policy; no provider calls or world-domain side effects."""
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile, NarrativeRiskProfile, PACING_PRESETS, RISK_PRESETS


from backend.services.narrative_policy import PolicyUpdate

def install(app, repo):
    @app.get('/api/saves/{sid}/narrative-policy')
    def get_policy(sid: int):
        snapshot=repo.get_snapshot(sid)
        if snapshot.get('mode')=='tabletop' or 'world_state' not in snapshot:
            raise ValueError('Настройки доступны только в Narrative.')
        meta=snapshot['world_state']['meta']
        return dict(current={k:meta[k] for k in ('narrative_pacing','narrative_risk','outcome_preference','npc_expressiveness')},
            pacing_presets={k:NarrativePacingProfile(preset=k).model_dump() for k in PACING_PRESETS},
            risk_presets={k:NarrativeRiskProfile(preset=k).model_dump() for k in RISK_PRESETS},
            schema=PolicyUpdate.model_json_schema())

    @app.put('/api/saves/{sid}/narrative-policy')
    def set_policy(sid: int, body: PolicyUpdate):
        repo.update_narrative_policy(sid,body.revision,body.model_dump(exclude={'revision'}))
        return repo.get_save(sid)
