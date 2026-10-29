from pydantic import Field
from backend.runtime_v3.narrative_policy_models import PolicyModel
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile, NarrativeRiskProfile, OutcomePreference


from backend.runtime_v3.genre import GenreConfig


class PolicyUpdate(PolicyModel):
    genre: GenreConfig = Field(default_factory=GenreConfig)
    revision: int = Field(ge=0)
    narrative_pacing: NarrativePacingProfile
    narrative_risk: NarrativeRiskProfile
    outcome_preference: OutcomePreference

