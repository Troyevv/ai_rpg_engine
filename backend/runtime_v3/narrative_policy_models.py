"""Small canonical configuration; presets are values, never translated labels."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


PACING_PRESETS = {
    'calm': dict(intensity=.2, quiet_minutes=1440, pressure_limit=1., disruption=.1, escalation=.2, thread_cap=2, candidate_budget=1, relevance_floor=.8),
    'moderate': dict(intensity=.45, quiet_minutes=360, pressure_limit=1.5, disruption=.3, escalation=.4, thread_cap=4, candidate_budget=2, relevance_floor=.6),
    'dynamic': dict(intensity=.7, quiet_minutes=120, pressure_limit=2., disruption=.55, escalation=.65, thread_cap=6, candidate_budget=3, relevance_floor=.4),
    'intense': dict(intensity=.9, quiet_minutes=60, pressure_limit=2.5, disruption=.75, escalation=.85, thread_cap=8, candidate_budget=4, relevance_floor=.25),
}


class NarrativePacingProfile(PolicyModel):
    preset: Literal['calm','moderate','dynamic','intense','custom'] = 'moderate'
    intensity: float = Field(default=.45, ge=0, le=1)
    quiet_minutes: int = Field(default=360, ge=0, le=43200)
    pressure_limit: float = Field(default=1.5, ge=.1, le=4)
    disruption: float = Field(default=.3, ge=0, le=1)
    escalation: float = Field(default=.4, ge=0, le=1)
    thread_cap: int = Field(default=4, ge=1, le=12)
    candidate_budget: int = Field(default=2, ge=0, le=6)
    relevance_floor: float = Field(default=.6, ge=0, le=1)
    # No dedicated semantic call is needed: the existing scene request proposes.
    extra_llm_calls: Literal[0] = 0

    @model_validator(mode='before')
    @classmethod
    def preset_values(cls, value):
        if isinstance(value,dict) and value.get('preset','moderate') in PACING_PRESETS:
            return {**value, **PACING_PRESETS[value.get('preset','moderate')]}
        return value


RISK_FIELDS = ('minor_illness','serious_illness','injury','permanent_injury',
    'relationship_loss','career_loss','life_role_loss','major_accident','npc_death','protagonist_death')
RISK_PRESETS = {
    'safe': dict.fromkeys(RISK_FIELDS,False) | dict(minor_illness=True),
    'realistic': dict.fromkeys(RISK_FIELDS,True) | dict(permanent_injury=False,protagonist_death=False),
    'harsh': dict.fromkeys(RISK_FIELDS,True) | dict(protagonist_death=False),
    'unrestricted': dict.fromkeys(RISK_FIELDS,True),
}


class NarrativeRiskProfile(PolicyModel):
    preset: Literal['safe','realistic','harsh','unrestricted','custom'] = 'realistic'
    minor_illness: bool = True
    serious_illness: bool = True
    injury: bool = True
    permanent_injury: bool = False
    relationship_loss: bool = True
    career_loss: bool = True
    life_role_loss: bool = True
    major_accident: bool = True
    npc_death: bool = True
    protagonist_death: bool = False

    @model_validator(mode='before')
    @classmethod
    def preset_values(cls, value):
        if isinstance(value,dict) and value.get('preset','realistic') in RISK_PRESETS:
            return {**value, **RISK_PRESETS[value.get('preset','realistic')]}
        return value


OutcomePreference = Literal['natural','prefer_happy','guaranteed_happy_path']
CandidateFamily = Literal['life_opportunity','existing_thread','external_disruption']
ConsequenceKind = Literal['minor_illness','serious_illness','injury','permanent_injury',
    'relationship_loss','career_loss','life_role_loss','major_accident','npc_death','protagonist_death']


class PacingRecord(PolicyModel):
    source_event_id: str | None = None
    source_id: str
    family: CandidateFamily
    minute: int = Field(ge=0)
    weight: float = Field(ge=0,le=1)


class FavorablePath(PolicyModel):
    opportunity: str = Field(min_length=1,max_length=500)
    next_step: str = Field(min_length=1,max_length=300)
    # A possible route, not an accepted action or promised universal survival.
    basis_ids: list[str] = Field(min_length=1,max_length=8)


class NarrativeDevelopment(PolicyModel):
    escalation: float = Field(default=0.,ge=0,le=1)
    candidate_id: str
    source_event_id: str
    evidence: str = Field(default="",max_length=2000)
    assertion: Literal['established']


class ConsequenceClaim(PolicyModel):
    candidate_id: str | None = None
    player_assertion: Literal["explicit_choice"] | None = None
    player_evidence: str | None = None
    kind: ConsequenceKind
    actor_id: str
    source_event_id: str
    basis_ids: list[str] = Field(min_length=1,max_length=8)
    evidence: str = Field(default="",max_length=2000)
