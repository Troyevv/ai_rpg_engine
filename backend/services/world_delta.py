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

class Event(Record):
    minute: int|None=Field(default=None,ge=0)
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
    location: str|None=None
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
            raise ValueError('Новая роль повторяет существующего персонажа.')
        state['characters'].append({'id':p['id'],'name':p['name'],'aliases':[],'is_player':False,'fields':p['fields']})
        state['world']['characters'][p['id']]={'id':p['id'],'location':None,'situation':p['situation'],
            'goals':p['goals'],'intentions':p['intentions'],'obligations':p['obligations'],
            'emotion':p['emotion'],'minute':None,'scene_id':None,'last_event_id':None}
    return state


def apply_delta(state, payload, narrative, user_text, sequence, since=None, promotions_prepared=False):
    from state_updates import normalized_evidence, EvidenceError
    delta=WorldDelta.model_validate(payload).model_dump(exclude_none=True)
    state=deepcopy(state) if promotions_prepared else add_promotions(state,delta['promotions'],narrative,user_text)
    world=state['world']
    for previous in world['relationships'].values():
        previous.pop('change',None)
    camera=world['scenes'][state['camera']['scene_id']]
    present=set(camera['participants'])
    actors=set(world['characters'])
    sources=[normalized_evidence(narrative),normalized_evidence(user_text)]
    now=current_time(state)
    def require(ok,message):
        if not ok:raise StructuralDeltaError('World Delta: '+message)
    def refs(values):
        require(set(values)<=actors,'неизвестный персонаж')
    # Check identity conflicts before applying any candidate changes.
    for section,entries in delta.items():
        seen=set()
        for index,item in enumerate(entries):
            key=item.get('id')
            if key is None:key=(item['actor_id'],item['fact_id']) if 'actor_id' in item else (item['source_id'],item['target_id'])
            require(key not in seen,'повтор сущности в delta')
            seen.add(key)
    for promotion in delta['promotions']:
        require(promotion['id'] in present,'новый NPC не участвует в текущей сцене')
    for f in delta['facts']:
        refs(f['character_ids'])
        old=world['facts'].get(f['id'])
        if old and old['text']!=f['text']:
            # Knowledge of a previous formulation must not silently become knowledge of a new fact.
            for k in world['knowledge'].values():
                if k['fact_id']==f['id']:k['status']='unknown'
        world['facts'][f['id']]={**f,'evidence':[f['evidence']]}
    new_events={}
    for e in delta['events']:
        refs(e['participants']); refs(e['witnesses'])
        require(e['id'] not in world['events'],'event id уже существует')
        require(set(e['participants'])<=present and set(e['witnesses'])<=present,'событие или свидетель вне текущей сцены')
        require(set(e['fact_ids'])<=set(world['facts']),'неизвестный факт события')
        minute=e.get('minute',now)
        require((since if since is not None else now)<=minute<=now,'событие вне подтверждаемого интервала сцены')
        if camera.get('start_minute') is None or minute<camera['start_minute']:
            camera['start_minute']=minute
        record=dict(e,minute=minute,scene_id=camera['id'],source_sequence=sequence,player_observed=True)
        world['events'][e['id']]=record
        new_events[e['id']]=record
        camera['event_ids'].append(e['id'])
        for cid in e['participants']:world['characters'][cid]['last_event_id']=e['id']
    for index,k in enumerate(delta['knowledge']):
        refs([k['actor_id']])
        require(k['fact_id'] in world['facts'],'неизвестный факт знания')
        event=new_events.get(k['source_event_id'])
        if (event is None or k['actor_id'] not in event['witnesses']
                or k['fact_id'] not in event['fact_ids'] or event['medium'] not in KNOWLEDGE_CHANNELS):
            raise SecondaryDeltaError('knowledge',index,'нет подтверждённого пути передачи знания',entity=k['actor_id']+':'+k['fact_id'])
        world['knowledge'][k['actor_id']+':'+k['fact_id']]=k
    for index,c in enumerate(delta['characters']):
        refs([c['id']]); require(c['id'] in present,'состояние отсутствующего NPC без сцены')
        if 'location' in c:require(c['location']==camera['location'],'место участника не совпадает со сценой')
        if c['id']==state['controlled_actor_id']:
            for field in PLAYER_FIELDS:
                if field not in c:continue
                evidence=c.get('player_evidence',{}).get(field,c['evidence'])
                if not supported_player_field(field,c[field],world['characters'][c['id']].get(field),user_text,evidence):
                    reason=('Внутреннее состояние controlled actor не задано игроком' if field=='emotion'
                        else 'Обязательство controlled actor не задано игроком' if field=='obligations'
                        else 'Решение controlled actor не задано игроком')
                    raise SecondaryDeltaError('characters',index,reason,field,c['id'])
        updates={k:v for k,v in c.items() if k not in ('id','evidence','player_evidence')}
        if updates:
            world['characters'][c['id']].update(updates)
            world['characters'][c['id']]['minute']=now
    for index,r in enumerate(delta['relationships']):
        refs([r['source_id'],r['target_id']])
        require(r['source_id']!=r['target_id'] and r['source_id'] in present,'недопустимая направленная связь')
        import math
        require(all(math.isfinite(v) and -100<=v<=100 for v in r['dimensions'].values()),'аспекты должны быть в диапазоне -100..100')
        for dimension in r['dimensions']:
            if dimension not in RELATION_DIMENSIONS:
                raise SecondaryDeltaError('relationships',index,'неизвестное измерение отношений',
                    'dimensions.'+dimension,r['source_id']+':'+r['target_id'],path=('dimensions',dimension))
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
            if e['status']=='resolved':require(new_events[e['resolved_event_id']]['minute']>=world['scheduled_events'][e['id']]['due_minute'],'событие завершено раньше срока')
        world['scheduled_events'][e['id']]=e
    # Validate semantic structure first, so an unsupported quote cannot mask a
    # fatal ID, scene or time error in the same record. Mutations are on a copy.
    for section,entries in delta.items():
        for index,item in enumerate(entries):
            if not any(normalized_evidence(item['evidence']) in s for s in sources):
                if section=='promotions':
                    raise EvidenceError(f'Изменение world_delta.{section}[{index}].evidence не подтверждено цитатой из хода.')
                entity=item.get('id') or item.get('actor_id') or item.get('source_id')
                raise SecondaryDeltaError(section,index,'Нет подтверждённой цитаты текущего хода',entity=entity,cause_field='evidence')
    return state
