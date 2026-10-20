"""Optional creation constraints; they never manufacture Runtime life events."""
from typing import Literal
from pydantic import Field, model_validator
from backend.runtime_v3.models import StrictModel

Genre = Literal['slice_of_life','family_saga','romance','drama','detective','thriller',
    'science_fiction','fantasy','horror','adventure','post_apocalyptic','historical','custom']
Expressiveness = Literal['realistic','expressive','hyperbolized']
CAST_PRESETS = {'small':(3,5),'medium':(6,12),'large':(10,25)}


class CreationSettings(StrictModel):
    primary_genre: Genre | None = None
    secondary_genres: list[Genre] = Field(default_factory=list,max_length=3)
    custom_genre: str = Field(default='',max_length=2000)
    npc_expressiveness: Expressiveness = 'expressive'
    cast_preset: Literal['small','medium','large','custom'] = 'medium'
    core_npcs: int = Field(default=6,ge=1,le=15)
    secondary_npcs: int = Field(default=12,ge=0,le=40)
    world_type: Literal['unspecified','real_world','fictional','alternate'] = 'unspecified'
    geography: str = Field(default='',max_length=5000)

    @model_validator(mode='after')
    def consistent(self):
        if len(set(self.secondary_genres))!=len(self.secondary_genres):
            raise ValueError('secondary genres must be distinct')
        if self.primary_genre in self.secondary_genres:
            raise ValueError('primary genre cannot also be secondary')
        if 'custom' in [self.primary_genre,*self.secondary_genres] and not self.custom_genre.strip():
            raise ValueError('custom genre requires a description')
        return self

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
