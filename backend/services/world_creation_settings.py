"""Optional creation constraints; they never manufacture Runtime life events."""
from typing import Literal
from pydantic import Field, model_validator
from backend.runtime_v3.models import StrictModel, NarrativePacingProfile, NarrativeRiskProfile, CalendarProfile

from backend.runtime_v3.genre import GenreConfig

Expressiveness = Literal['realistic','expressive','hyperbolized']
CAST_PRESETS = {'small':(3,5),'medium':(6,12),'large':(10,25)}


class CalendarPresets(StrictModel):
    holidays: Literal['auto','country','none','custom'] = 'auto'
    country: str | None = None
    subdivision: str | None = None
    observed: bool = False
    seasons: Literal['auto','north','south','none','custom'] = 'auto'


class CalendarStart(StrictModel):
    presets: CalendarPresets | None = None
    mode: Literal['auto','gregorian','custom'] = 'auto'
    date: str | None = None
    time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    weekday: int | None = Field(default=None, ge=0, le=13)
    profile: CalendarProfile | None = None

    @model_validator(mode='after')
    def valid_start(self):
        from backend.runtime_v3.calendar import date_parts
        if self.mode == 'custom' and (not self.profile or self.profile.system != 'custom'):
            raise ValueError('Свой календарь: задайте месяцы и длины месяцев.')
        if self.date:
            date_parts(self.date, self.profile.model_dump() if self.mode == 'custom' else {})
        if self.weekday is not None and self.weekday >= len((self.profile.weekday_names if self.profile else []) or range(7)):
            raise ValueError('День недели вне выбранного календаря.')
        return self


class CreationSettings(GenreConfig):
    calendar_start: CalendarStart = Field(default_factory=CalendarStart)
    narrative_pacing: NarrativePacingProfile = Field(default_factory=NarrativePacingProfile)
    narrative_risk: NarrativeRiskProfile = Field(default_factory=NarrativeRiskProfile)
    npc_expressiveness: Expressiveness = 'expressive'
    cast_preset: Literal['small','medium','large','custom'] = 'medium'
    core_npcs: int = Field(default=6,ge=1,le=15)
    secondary_npcs: int = Field(default=12,ge=0,le=40)
    world_type: Literal['unspecified','real_world','fictional','alternate'] = 'unspecified'
    geography: str = Field(default='',max_length=5000)

    def cast_targets(self,entities):
        core,secondary=CAST_PRESETS.get(self.cast_preset,(self.core_npcs,self.secondary_npcs))
        specified=[row for row in entities if row['kind']=='character' and row.get('tier')!='protagonist']
        fixed_secondary=sum(row.get('tier')=='secondary' for row in specified)
        fixed_core=len(specified)-fixed_secondary
        return dict(core=max(core,fixed_core),secondary=max(secondary,fixed_secondary),
                    user_entities_over_target=fixed_core>core or fixed_secondary>secondary)


def presentation_rule(mode):
    if mode=='realistic': return ''
    styles={'expressive':'Distinct, lively but plausible speech, gestures and emotions.',
            'hyperbolized':'Heightened, anime-like emotional contrast and theatrical or comic reactions where character-appropriate.'}
    return '\nNPC presentation: '+styles[mode]+' Presentation never changes established traits, intelligence, values, goals, knowledge, agency or consent. Do not apply it to player decisions.'
