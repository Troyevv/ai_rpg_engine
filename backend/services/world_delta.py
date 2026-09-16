"""Typed additions to the established extraction contract; validated before commit."""
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.services.world import identity
from backend.services.timeline import current_time

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
    witnesses: list[str]=Field(max_length=50)
    fact_ids: list[str]=Field(default_factory=list,max_length=50)
    medium: Literal['observation','conversation','message','testimony','discovery','action']

class Knowledge(Record):
    actor_id: str
    fact_id: str
    status: Literal['known','suspected','unknown']
    source_event_id: str

class Character(Record):
    id: str
    location: str|None=None
    situation: str|None=None
    short_goal: str|None=None
    intentions: list[str]|None=Field(default=None,max_length=20)
    emotion: str|None=None
    obligations: list[str]|None=Field(default=None,max_length=20)

class Relationship(Record):
    source_id: str
    target_id: str
    dimensions: dict[str,float]=Field(default_factory=dict,max_length=20)
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
    facts: list[Fact]=Field(default_factory=list,max_length=50)
    events: list[Event]=Field(default_factory=list,max_length=50)
    knowledge: list[Knowledge]=Field(default_factory=list,max_length=50)
    characters: list[Character]=Field(default_factory=list,max_length=50)
    relationships: list[Relationship]=Field(default_factory=list,max_length=50)
    threads: list[Thread]=Field(default_factory=list,max_length=50)
    scheduled_events: list[Scheduled]=Field(default_factory=list,max_length=50)


def apply_delta(state, payload, narrative, user_text, sequence, since=None):
    from state_updates import normalized_evidence
    delta=WorldDelta.model_validate(payload).model_dump(exclude_none=True)
    state=deepcopy(state)
    world=state['world']
    camera=world['scenes'][state['camera']['scene_id']]
    present=set(camera['participants'])
    actors=set(world['characters'])
    sources=[normalized_evidence(narrative),normalized_evidence(user_text)]
    now=current_time(state)
    def require(ok,message):
        if not ok:raise ValueError('World Delta: '+message)
    def refs(values):
        require(set(values)<=actors,'неизвестный персонаж')
    # Structural/evidence failures reject the whole extended delta, never partial knowledge.
    for entries in delta.values():
        seen=set()
        for item in entries:
            require(any(normalized_evidence(item['evidence']) in s for s in sources),'нет цитаты текущего хода')
            key=item.get('id')
            if key is None:key=(item['actor_id'],item['fact_id']) if 'actor_id' in item else (item['source_id'],item['target_id'])
            require(key not in seen,'повтор сущности в delta')
            seen.add(key)
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
    for k in delta['knowledge']:
        refs([k['actor_id']])
        require(k['fact_id'] in world['facts'],'неизвестный факт знания')
        event=new_events.get(k['source_event_id'])
        require(event is not None,'знание требует события этого хода')
        require(k['actor_id'] in event['witnesses'] and k['fact_id'] in event['fact_ids'],'нет пути передачи знания')
        require(event['medium']!='action','укажи канал получения информации')
        world['knowledge'][k['actor_id']+':'+k['fact_id']]=k
    for c in delta['characters']:
        refs([c['id']]); require(c['id'] in present,'состояние отсутствующего NPC без сцены')
        if c['id']==state['controlled_actor_id']:
            require(not set(c).intersection({'short_goal','intentions','emotion'}),'решение или чувство за игрока')
        if 'location' in c:require(c['location']==camera['location'],'место участника не совпадает со сценой')
        world['characters'][c['id']].update({k:v for k,v in c.items() if k not in ('id','evidence')})
        world['characters'][c['id']]['minute']=now
    for r in delta['relationships']:
        refs([r['source_id'],r['target_id']])
        require(r['source_id']!=r['target_id'] and r['source_id'] in present,'недопустимая направленная связь')
        import math
        require(all(math.isfinite(v) and -100<=v<=100 for v in r['dimensions'].values()),'аспекты должны быть в диапазоне -100..100')
        key=r['source_id']+':'+r['target_id']
        old=world['relationships'].setdefault(key,dict(source_id=r['source_id'],target_id=r['target_id'],dimensions={}))
        old['dimensions'].update(r['dimensions']); old['context']=r['context']
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
    return state
