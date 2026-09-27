"""Canonical, source-backed changes to the live WorldState."""
from copy import deepcopy
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.services.world import identity, CARD_FIELDS
from backend.services.timeline import current_time
from backend.services.world_delta_errors import SecondaryDeltaError, StructuralDeltaError
from backend.services.player_agency import PLAYER_FIELDS, PLAYER_SOURCE_DESCRIPTION, supported_player_field

RELATION_DIMENSIONS=('trust','affection','attraction','irritation','fear','jealousy','respect')

KNOWLEDGE_CHANNELS=('observation','conversation','message','testimony','discovery')
KNOWLEDGE_CONTRACT = ('Knowledge requires Fact -> Event -> Witness -> Knowledge: source_event_id must reference '
    'an Event in this WorldDelta; fact_id must be in that Event.fact_ids; actor_id must be in '
    'that Event.witnesses; medium must be observation, conversation, message, testimony or discovery, never action. '
    'If the complete path is not supported by the narrative, omit Knowledge.')
RELATION_CONTRACT = ('relationships.dimensions is a closed set: '+', '.join(RELATION_DIMENSIONS)+
    '. Never invent dimension names. Put meaning that does not fit these dimensions in relationship.context.')

def dimensions_schema(schema):
    schema.update(type='object', properties={key:{'type':'number','minimum':-100,'maximum':100}
        for key in RELATION_DIMENSIONS}, additionalProperties=False)

class Record(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    evidence: str=Field(min_length=1,max_length=12000)

class Fact(Record):
    id: str=Field(min_length=1,max_length=120)
    text: str=Field(min_length=1,max_length=12000)
    secret: bool=False
    character_ids: list[str]=Field(default_factory=list,max_length=50)

class Transition(Record):
    actor_id: str
    minute: int|None=Field(default=None,ge=0,description='Optional known time; not required for movement.')
    order: int|None=Field(default=None,ge=0,description='Relative movement order. Use distinct values for multiple movements of one actor.')
    from_location: str|None=Field(default=None,description='Deprecated input, ignored by Runtime.')

    @staticmethod
    def _schema(schema):
        schema.get('properties',{}).pop('from_location',None)

    model_config=ConfigDict(extra='forbid',strict=True,json_schema_extra=_schema)
    to_location: str=Field(min_length=1,max_length=200,pattern=r'\S',description='Destination, not a body movement inside the same room.')

class Event(Record):
    order: int|None=Field(default=None,ge=0,description='Optional known relative order; omit when unknown.')
    location: str|None=Field(default=None,min_length=1,max_length=200,description='Event location if known from its source. Omit when unknown; do not infer from final camera.')
    minute: int|None=Field(default=None,ge=0,description="Optional known event minute. Omit rather than invent a precise time.")
    id: str=Field(min_length=1,max_length=120)
    text: str=Field(min_length=1,max_length=12000)
    participants: list[str]=Field(max_length=50)
    witnesses: list[str]=Field(max_length=50,description="Recipients/observers who actually received information. "+KNOWLEDGE_CONTRACT)
    fact_ids: list[str]=Field(default_factory=list,max_length=50,description=KNOWLEDGE_CONTRACT)
    medium: Literal['observation','conversation','message','testimony','discovery','action']

class Knowledge(Record):
    actor_id: str
    fact_id: str
    status: Literal['known','suspected','unknown']
    source_event_id: str=Field(description=KNOWLEDGE_CONTRACT)

class PlayerEvidence(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    goals: list[str]|None=Field(default=None,max_length=20,description='Полные цитаты player_input, по одной на каждую новую цель.')
    intentions: list[str]|None=Field(default=None,max_length=20,description='Полные цитаты player_input, по одной на каждое новое намерение.')
    emotion: str|None=Field(default=None,description='Полная цитата player_input, явно называющая внутреннее состояние.')
    obligations: list[str]|None=Field(default=None,max_length=20,description='Полные цитаты явных обещаний игрока, по одной на новое обязательство.')

class Character(Record):
    id: str
    location: str|None=Field(default=None,min_length=1,max_length=200,description="Final location of THIS character, not necessarily the camera. Must agree with transitions.")
    situation: str|None=None
    goals: list[str]|None=Field(default=None,max_length=20,description=PLAYER_SOURCE_DESCRIPTION)
    intentions: list[str]|None=Field(default=None,max_length=20,description=PLAYER_SOURCE_DESCRIPTION)
    emotion: str|None=Field(default=None,description=PLAYER_SOURCE_DESCRIPTION)
    obligations: list[str]|None=Field(default=None,max_length=20,description=PLAYER_SOURCE_DESCRIPTION)
    player_evidence: PlayerEvidence|None=Field(default=None,description=PLAYER_SOURCE_DESCRIPTION)

class Promotion(Record):
    id: str=Field(min_length=1,max_length=120)
    name: str=Field(min_length=1,max_length=120)
    fields: dict[str,str]
    goals: list[str]=Field(default_factory=list,max_length=20)
    intentions: list[str]=Field(default_factory=list,max_length=20)
    obligations: list[str]=Field(default_factory=list,max_length=20)
    situation: str=''
    emotion: str=''

    @model_validator(mode='after')
    def complete_card(self):
        if set(self.fields)!=set(CARD_FIELDS) or any(not value.strip() for value in self.fields.values()):
            raise ValueError('Новая значимая роль требует полную постоянную карточку персонажа.')
        return self

class Relationship(Record):
    source_id: str
    target_id: str
    # Keep raw keys through parsing to classify unknown numeric keys as isolated
    # leaf errors. The advertised schema remains closed and uses the same registry.
    dimensions: dict[str,Annotated[float,Field(ge=-100,le=100,allow_inf_nan=False)]]=Field(default_factory=dict,max_length=20,description=RELATION_CONTRACT,json_schema_extra=dimensions_schema)
    context: str=Field(min_length=1,max_length=12000)

class Thread(Record):
    id: str=Field(min_length=1,max_length=120)
    description: str=Field(min_length=1,max_length=12000)
    character_ids: list[str]=Field(max_length=50)
    status: Literal['active','developing','dormant','resolved']
    state: str=Field(max_length=12000)
    relevance: float=Field(ge=0,le=1)
    last_event_id: str

class Scheduled(Record):
    id: str=Field(min_length=1,max_length=120)
    due_minute: int=Field(ge=0)
    type: str=Field(min_length=1,max_length=80)
    participants: list[str]=Field(max_length=50)
    description: str=Field(min_length=1,max_length=12000)
    status: Literal['pending','resolved','cancelled']='pending'
    resolved_event_id: str|None=None

class WorldDelta(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    transitions: list[Transition]=Field(default_factory=list,max_length=100,description="Source-backed location changes. actor_id, to_location, evidence; relative order only for multiple movements.")
    promotions: list[Promotion]=Field(default_factory=list,max_length=10)
    facts: list[Fact]=Field(default_factory=list,max_length=50)
    events: list[Event]=Field(default_factory=list,max_length=50)
    knowledge: list[Knowledge]=Field(default_factory=list,max_length=50,description=KNOWLEDGE_CONTRACT)
    characters: list[Character]=Field(default_factory=list,max_length=50)
    relationships: list[Relationship]=Field(default_factory=list,max_length=50)
    threads: list[Thread]=Field(default_factory=list,max_length=50)
    scheduled_events: list[Scheduled]=Field(default_factory=list,max_length=50)


def add_promotions(state, promotions, narrative, user_text):
    """Seed validated new cast members before scene membership is checked."""
    from state_updates import normalized_evidence, EvidenceError
    state=deepcopy(state)
    sources=[normalized_evidence(narrative),normalized_evidence(user_text)]
    for index,entry in enumerate(promotions):
        p=Promotion.model_validate(entry).model_dump()
        if not any(normalized_evidence(p['evidence']) in source for source in sources):
            raise EvidenceError(f'Изменение world_delta.promotions[{index}].evidence не подтверждено цитатой из хода.')
        if p['id'] in state['world']['characters'] or any(c['name'].casefold()==p['name'].casefold() for c in state['characters']):
            raise StructuralDeltaError('Новая роль повторяет существующего персонажа.','canonical_id_conflict')
        state['characters'].append({'id':p['id'],'name':p['name'],'aliases':[],'is_player':False,'fields':p['fields']})
        state['world']['characters'][p['id']]={'id':p['id'],'location':None,'situation':p['situation'],
            'goals':p['goals'],'intentions':p['intentions'],'obligations':p['obligations'],
            'emotion':p['emotion'],'minute':None,'scene_id':None,'last_event_id':None}
    return state


def apply_delta(state, payload, narrative, user_text, sequence, since=None, promotions_prepared=False, before_state=None, movement_plan=None):
    delta=WorldDelta.model_validate(payload).model_dump(exclude_none=True)
    state=deepcopy(state) if promotions_prepared else add_promotions(state,delta['promotions'],narrative,user_text)
    world=state['world']
    for previous in world['relationships'].values():
        previous.pop('change',None)
    actors=set(world['characters'])
    from backend.services.turn_delta.references import validate_references, require
    from backend.services.turn_delta.provenance import validate_provenance
    from backend.services.turn_delta.movement import derive_movements
    validate_references(state,delta)
    validate_provenance(delta,narrative,user_text)
    movement_plan=movement_plan or derive_movements(before_state or state,state,delta,since)
    involved=movement_plan['involved']
    now=current_time(state)
    def refs(values):require(set(values)<=actors,'неизвестный персонаж','unknown_character')
    for promotion in delta['promotions']:
        require(promotion['id'] in involved,'новый NPC не участвует в текущей сцене')
    for f in delta['facts']:
        refs(f['character_ids'])
        old=world['facts'].get(f['id'])
        if old and old['text']!=f['text']:
            # Knowledge of a previous formulation must not silently become knowledge of a new fact.
            for k in world['knowledge'].values():
                if k['fact_id']==f['id']:k['status']='unknown'
        world['facts'][f['id']]={**f,'evidence':[f['evidence']]}
    from backend.services.turn_delta.events import apply_events
    from backend.services.turn_delta.knowledge import apply_knowledge
    from backend.services.turn_delta.scene_sync import apply_locations
    new_events=apply_events(state,before_state or state,delta['events'],sequence,since)
    apply_knowledge(world,delta['knowledge'],new_events,KNOWLEDGE_CHANNELS)
    apply_locations(state,movement_plan,sequence)
    for index,c in enumerate(delta['characters']):
        refs([c['id']]); require(c['id'] in involved,'персонаж не участвовал в текущем ходе','character_not_involved')
        if c['id']==state['controlled_actor_id']:
            for field in PLAYER_FIELDS:
                if field not in c:continue
                evidence=c.get('player_evidence',{}).get(field,c['evidence'])
                if not supported_player_field(field,c[field],world['characters'][c['id']].get(field),user_text,evidence):
                    reason=('Внутреннее состояние controlled actor не задано игроком' if field=='emotion'
                        else 'Обязательство controlled actor не задано игроком' if field=='obligations'
                        else 'Решение controlled actor не задано игроком')
                    raise SecondaryDeltaError('characters',index,reason,field,c['id'],code='controlled_actor_'+field+'_unsupported')
        updates={k:v for k,v in c.items() if k not in ('id','evidence','player_evidence')}
        if updates:
            world['characters'][c['id']].update(updates)
            world['characters'][c['id']]['minute']=now
    for index,r in enumerate(delta['relationships']):
        refs([r['source_id'],r['target_id']])
        require(r['source_id']!=r['target_id'] and r['source_id'] in involved,'недопустимая направленная связь')
        import math
        require(all(math.isfinite(v) and -100<=v<=100 for v in r['dimensions'].values()),'аспекты должны быть в диапазоне -100..100')
        for dimension in r['dimensions']:
            if dimension not in RELATION_DIMENSIONS:
                raise SecondaryDeltaError('relationships',index,'неизвестное измерение отношений',
                    'dimensions.'+dimension,r['source_id']+':'+r['target_id'],path=('dimensions',dimension),code='relationship_dimension_unknown')
        key=r['source_id']+':'+r['target_id']
        old=world['relationships'].setdefault(key,dict(source_id=r['source_id'],target_id=r['target_id'],dimensions={}))
        previous=old['dimensions'].copy()
        old['dimensions'].update(r['dimensions']); old['context']=r['context']
        old['provenance']={'source':'extraction','quote':r['evidence'],'sequence':sequence}
        movement=sum(value-previous.get(key,0) for key,value in r['dimensions'].items())
        if movement:
            old['change']={'direction':'up' if movement>0 else 'down','reason':r['context'],'turn':sequence}
    for t in delta['threads']:
        refs(t['character_ids']); require(t['last_event_id'] in new_events,'развитие линии требует события этого хода')
        world['threads'][t['id']]=t
    for e in delta['scheduled_events']:
        refs(e['participants'])
        if e['status']=='pending':
            require(e['due_minute']>=now,'новое отложенное событие в прошлом')
            require(not e.get('resolved_event_id'),'ожидающее событие уже разрешено')
        else:
            require(e['id'] in world['scheduled_events'],'неизвестное отложенное событие')
            require(e.get('resolved_event_id') in new_events,'завершение требует события текущего хода')
            require(bool(set(world['scheduled_events'][e['id']]['participants']).intersection(new_events[e['resolved_event_id']]['participants'])),'событие не связано с участниками обязательства')
            if e['status']=='resolved':require((new_events[e['resolved_event_id']]['minute'] if new_events[e['resolved_event_id']]['minute'] is not None else now)>=world['scheduled_events'][e['id']]['due_minute'],'событие завершено раньше срока')
        world['scheduled_events'][e['id']]=e
    from backend.services.turn_delta.final_state import validate_final_state
    validate_final_state(before_state or state,state,movement_plan)
    return state
