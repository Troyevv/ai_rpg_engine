from typing import Literal
from pydantic import Field
from backend.runtime_v3.narrative_policy_models import PolicyModel
from backend.runtime_v3.narrative_policy_models import NarrativePacingProfile, NarrativeRiskProfile, OutcomePreference


class PolicyUpdate(PolicyModel):
    revision: int = Field(ge=0)
    npc_expressiveness: Literal['realistic','expressive','hyperbolized'] | None = None
    narrative_pacing: NarrativePacingProfile
    narrative_risk: NarrativeRiskProfile
    outcome_preference: OutcomePreference

