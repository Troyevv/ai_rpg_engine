from pydantic import Field
from backend.runtime_v3.narrative_policy_models import PolicyModel
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile, NarrativeRiskProfile, OutcomePreference


class PolicyUpdate(PolicyModel):
    revision: int = Field(ge=0)
    narrative_pacing: NarrativePacingProfile
    narrative_risk: NarrativeRiskProfile
    outcome_preference: OutcomePreference

