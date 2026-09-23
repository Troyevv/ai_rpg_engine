"""Pre-game operations on the existing runtime aggregate, never a second world model."""
from copy import deepcopy
import base64
import hashlib
import json
import re
import uuid
from backend.services.world import normalize, KINDS
from backend.services.timeline import label

GROUPS={'actor':'characters','relationship':'relationships','fact':'facts','knowledge':'knowledge',
        'thread':'threads','scene':'scenes','event':'events'}
FIELDS={
 'campaign':{'title','setting','era','genre','tone','description','public_description','rules'},
 'character':{'name','aliases','fields'},
 'actor':{'location','situation','goals','intentions','emotion','obligations'},
 'relationship':{'source_id','target_id','context','dimensions','visible_to_ids'},
 'location':{'name','text'},
 'fact':{'text','secret','owner_id','character_ids','evidence'},
 'knowledge':{'actor_id','fact_id','status','source_event_id'},
 'thread':{'description','state','public_state','status','character_ids','relevance','visible_to_ids'},
 'scene':{'location','participants','text','start_minute','end_minute','status'},
 'event':{'text','participants','witnesses','minute','fact_ids','player_observed'},
 'start':{'protagonist_id','controlled_actor_id','scene_id','minute'},
}


def prepare(original):
    if not isinstance(original,dict) or not isinstance(original.get('characters'),list):
        raise ValueError('Мир должен содержать список Characters.')
    for card in original['characters']:
        if not isinstance(card,dict) or not isinstance(card.get('id'),str) or not isinstance(card.get('name'),str) or not isinstance(card.get('fields'),dict):
            raise ValueError('Некорректная карточка персонажа.')
        if any(not isinstance(v,str) for v in card['fields'].values()):
            raise ValueError('Поля карточки должны быть текстом.')
    original=deepcopy(original)
    if isinstance(original.get('world'),dict) and original['world'].get('version')==2:
        for kind in KINDS:
            original['world'].setdefault(kind,{})
            if not isinstance(original['world'][kind],dict) or any(not isinstance(v,dict) for v in original['world'][kind].values()):
                raise ValueError(f'Некорректный раздел {kind}.')
    if not isinstance(original.get('locations',[]),list) or any(not isinstance(x,dict) for x in original.get('locations',[])):
        raise ValueError('Места должны быть списком объектов.')
    original.setdefault('locations',[])
    for card in original['characters']:
        if not isinstance(card.get('aliases',[]),list) or any(not isinstance(x,str) for x in card.get('aliases',[])):
            raise ValueError('Другие имена должны быть списком строк.')
    for key in ('world_clock','camera','sections','campaign'):
        if key in original and not isinstance(original[key],dict):raise ValueError(f'{key}: нужен объект.')
    clock=original.get('world_clock',{}).get('minute')
    if clock is not None and (type(clock) is not int or clock<0):raise ValueError('Игровое время должно быть неотрицательным целым числом.')
    state=normalize(original)
    from backend.services.timeline import current_time
    minute=current_time(state)
    state.setdefault('world_clock',{'minute':minute,'last_event_time':label(minute)})
    state.setdefault('campaign',{'title':'Новый мир','setting':'','era':'','genre':'',
        'tone':state.get('sections',{}).get('tone',''),'description':'','rules':state.get('story_notes','')})
    for i,loc in enumerate(state.get('locations',[])):
        loc.setdefault('id',f'location_{i+1}')
    for kind in KINDS:
        if not isinstance(state['world'].get(kind),dict):raise ValueError(f'Некорректный раздел {kind}.')
    if not isinstance(state['campaign'],dict) or any(not isinstance(v,str) for v in state['campaign'].values()):
        raise ValueError('Поля кампании должны быть текстом.')
    for c in state['world']['characters'].values():
        for field in ('goals','intentions','obligations'):
            if not isinstance(c.get(field,[]),list) or any(not isinstance(v,str) for v in c.get(field,[])):
                raise ValueError(f'{field}: нужен список строк.')
    for kind in KINDS:
        for key,item in state['world'][kind].items():
            if kind not in ('relationships','knowledge'):item.setdefault('id',key)
            for field,value in item.items():
                if field.endswith('_id') and value is not None and not isinstance(value,str):raise ValueError(f'{kind}/{key}/{field}: нужна строковая ссылка.')
                if field in ('participants','witnesses','fact_ids','character_ids','event_ids') and (not isinstance(value,list) or any(not isinstance(x,str) for x in value)):
                    raise ValueError(f'{kind}/{key}/{field}: нужен список ссылок.')
    return sync(state)


def sync(state):
    """Update compatibility projections from canonical data; no parsing or LLM."""
    world=state['world'];campaign=state.get('campaign',{})
    state.setdefault('sections',{})['tone']=campaign.get('tone','')
    state['story_notes']=campaign.get('rules','')
    for c in state['characters']:
        c['is_player']=c['id']==state.get('protagonist_id')
        a=world['characters'].get(c['id'],{})
        if 'goals' in a:a['short_goal']='\n\n'.join(a['goals'])
        for key,field in [('short_goal','Чего хочет'),('situation','Сейчас')]:
            if key in a:c['fields'][field]=a[key]
        if 'intentions' in a:c['fields']['Намерения']='\n\n'.join(a['intentions'])
    state['relationships']=[dict(source_id=r.get('source_id',''),target_id=r.get('target_id',''),text=r.get('context','')) for r in world['relationships'].values()]
    scene=world['scenes'].get(state.get('camera',{}).get('scene_id'))
    if scene:
        state['scene']=scene.get('text','')
        minute=state.get('world_clock',{}).get('minute')
        state['scene_meta']={'time':label(minute) if type(minute) is int else '', 'location':scene.get('location',''), 'present_ids':scene.get('participants',[])}
    return state


def validate(state):
    errors=[];warnings=[];world=state['world']
    cards=state['characters'];ids={c['id'] for c in cards}
    def require(ok,message):
        if not ok:errors.append(message)
    require(len(ids)==len(cards),'Повтор Character ID.')
    require(all(re.fullmatch(r'[\w-]{1,100}',cid) for cid in ids),'Некорректный Character ID.')
    require(len({c['name'].strip().casefold() for c in cards})==len(cards),'Повтор имени: проверь identities персонажей.')
    require(bool(cards) and all(c['name'].strip() for c in cards),'Нужны персонажи с именами.')
    require(state.get('protagonist_id') in ids,'Не выбран protagonist.')
    require(state.get('controlled_actor_id') in ids,'Не выбран controlled actor для старта.')
    require(set(world['characters'])==ids,'Character cards и character state не совпадают.')
    minute=state.get('world_clock',{}).get('minute')
    require(type(minute) is int and minute>=0,'Нужно игровое время (минута от начала недели).')
    require(state.get('camera',{}).get('scene_id') in world['scenes'],'Не выбрана стартовая сцена.')
    def refs(values,known,where):
        require(isinstance(values,list) and all(isinstance(v,str) and v in known for v in values),f'Некорректные ссылки: {where}.')
    for kind in KINDS:
        for key,item in world[kind].items():
            require(isinstance(key,str) and bool(key),f'Пустой ID в {kind}.')
            require(isinstance(item,dict),f'Некорректная сущность {kind}/{key}.')
            if not isinstance(item,dict):continue
            if 'id' in item:require(item['id']==key,f'ID не совпадает: {kind}/{key}.')
    for rid,r in world['relationships'].items():
        require(r.get('source_id') in ids and r.get('target_id') in ids,f'Отношение {rid}: неизвестный персонаж.')
        require(isinstance(r.get('context',''),str) and isinstance(r.get('dimensions',{}),dict),f'Отношение {rid}: некорректные поля.')
        if 'visible_to_ids' in r:refs(r['visible_to_ids'],ids,f'relationship visibility {rid}')
    for fid,f in world['facts'].items():
        require(isinstance(f.get('text'),str) and bool(f['text'].strip()),f'Факт {fid}: нужен текст.')
        refs(f.get('character_ids',[]),ids,f'fact {fid}')
        if f.get('owner_id') is not None:require(isinstance(f['owner_id'],str) and f['owner_id'] in ids,f'Факт {fid}: неизвестный владелец тайны.')
    for kid,k in world['knowledge'].items():
        require(k.get('actor_id') in ids and k.get('fact_id') in world['facts'],f'Знание {kid}: ссылка не существует.')
        require(k.get('status') in ('known','suspected','unknown'),f'Знание {kid}: некорректный статус.')
        require(not k.get('source_event_id') or k['source_event_id'] in world['events'],f'Знание {kid}: неизвестный источник.')
    for sid,s in world['scenes'].items():
        refs(s.get('participants',[]),ids,f'scene {sid}')
        require(isinstance(s.get('location'),str) and bool(s['location'].strip()),f'Сцена {sid}: нужно место.')
        require(isinstance(s.get('text',''),str),f'Сцена {sid}: некорректное описание.')
        start,end=s.get('start_minute'),s.get('end_minute')
        require(type(start) is int and type(end) is int and 0<=start<=end,f'Сцена {sid}: некорректный интервал.')
    for tid,t in world['threads'].items():
        refs(t.get('character_ids',[]),ids,f'thread {tid}')
        if 'visible_to_ids' in t:refs(t['visible_to_ids'],ids,f'thread visibility {tid}')
        require(t.get('status') in ('active','developing','dormant','resolved'),f'Линия {tid}: некорректный статус.')
    for eid,e in world['events'].items():
        refs(e.get('participants',[]),ids,f'event {eid}')
        refs(e.get('witnesses',[]),ids,f'witnesses {eid}')
        refs(e.get('fact_ids',[]),set(world['facts']),f'event facts {eid}')
    for cid,c in world['characters'].items():
        require(not c.get('scene_id') or c['scene_id'] in world['scenes'],f'Персонаж {cid}: неизвестная сцена.')
        for field in ('goals','intentions','obligations'):
            require(isinstance(c.get(field,[]),list) and all(isinstance(x,str) for x in c.get(field,[])),f'{cid}/{field}: нужен список строк.')
    for rid,r in world['relationships'].items():
        require(isinstance(r.get('dimensions',{}),dict) and all(isinstance(v,(int,float)) and not isinstance(v,bool) and -100<=v<=100 for v in r.get('dimensions',{}).values()),f'Отношение {rid}: показатели должны быть числами от -100 до 100.')
    for tid,t in world['threads'].items():
        require(isinstance(t.get('relevance'),(int,float)) and not isinstance(t.get('relevance'),bool) and 0<=t['relevance']<=1,f'Линия {tid}: значимость от 0 до 1.')
        require(isinstance(t.get('description'),str) and isinstance(t.get('state'),str),f'Линия {tid}: нужны описание и состояние.')
        require(not t.get('last_event_id') or t['last_event_id'] in world['events'],f'Линия {tid}: неизвестное последнее событие.')
    for eid,e in world['scheduled_events'].items():
        refs(e.get('participants',[]),ids,f'scheduled {eid}')
        require(type(e.get('due_minute')) is int and e['due_minute']>=0,f'Отложенное событие {eid}: нужен срок.')
        require(e.get('status') in ('pending','resolved','cancelled'),f'Отложенное событие {eid}: некорректный статус.')
        require(isinstance(e.get('description'),str),f'Отложенное событие {eid}: нужно описание.')
        require(not e.get('resolved_event_id') or e['resolved_event_id'] in world['events'],f'Отложенное событие {eid}: неизвестное событие завершения.')
    for cid,c in world['characters'].items():
        require(c.get('location') is None or isinstance(c['location'],str),f'Персонаж {cid}: некорректное место.')
        require(isinstance(c.get('situation',''),str),f'Персонаж {cid}: некорректная ситуация.')
        require(c.get('minute') is None or type(c['minute']) is int and type(minute) is int and c['minute']<=minute,f'Персонаж {cid}: временная точка в будущем.')
    locs=state.get('locations',[])
    require(len({loc.get('id') for loc in locs})==len(locs),'Повтор ID места.')
    for loc in locs:require(isinstance(loc.get('name'),str) and bool(loc['name'].strip()) and isinstance(loc.get('text'),str),'Месту нужны название и описание.')
    for eid,e in world['events'].items():
        require(e.get('minute') is None or type(e['minute']) is int and e['minute']>=0,f'Событие {eid}: некорректное время.')
        require(not e.get('scene_id') or e['scene_id'] in world['scenes'],f'Событие {eid}: неизвестная сцена.')
    for sid,scene in world['scenes'].items():refs(scene.get('event_ids',[]),set(world['events']),f'scene events {sid}')
    for cid,c in world['characters'].items():
        require(c.get('minute') is None or type(c['minute']) is int and c['minute']>=0,f'Персонаж {cid}: некорректное время.')
        require(not c.get('last_event_id') or c['last_event_id'] in world['events'],f'Персонаж {cid}: неизвестное последнее событие.')
    start=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    require(state.get('controlled_actor_id') in start.get('participants',[]),'Управляемый персонаж должен присутствовать в стартовой сцене.')
    require(type(start.get('end_minute')) is int and type(minute) is int and start['end_minute']<=minute,'Стартовая сцена находится позже часов мира.')
    if not isinstance(start.get('text'),str) or not start['text'].strip():warnings.append('Стартовая ситуация пока не описана.')
    for c in cards:
        age=re.search(r'\b(\d{1,3})\s*(?:лет|год)',c['fields'].get('Возраст','')+' '+c['fields'].get('Статус',''))
        if age and int(age[1])<18 and re.search(r'врач|университет|женат|замуж',json.dumps(c,ensure_ascii=False),re.I):
            warnings.append(f"{c['id']}: возраст может противоречить профессии или биографии. Проверь связанные факты и события.")
    return {'errors':errors,'warnings':warnings}


def review_initial(state,source=''):
    """Advisory completeness/coherence check for generated drafts, never imported worlds."""
    warnings=[];world=state['world'];cards=state['characters'];ids={c['id'] for c in cards}
    scene=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    actor=state.get('controlled_actor_id')
    if len(cards)>1 and not world['relationships']:
        warnings.append('Между значимыми персонажами не описано ни одного отношения. Проверь, достаточно ли связей для начала игры.')
    if len(cards)>2 and not world['threads']:
        warnings.append('Не создано открытых сюжетных линий. Проверь, есть ли у мира естественный потенциал для развития.')
    connected=set(scene.get('participants',[]));secrets=secret_holders(state)
    connected.update(cid for r in world['relationships'].values() for cid in (r.get('source_id'),r.get('target_id')))
    connected.update(cid for t in world['threads'].values() for cid in t.get('character_ids',[]))
    for card in cards:
        cid=card['id'];fields=card['fields'];character=world['characters'].get(cid,{})
        weak=[field for field in DETAIL_MIN if weak_card_field(fields.get(field,''),field,source)]
        if weak:warnings.append(f"{card['name']}: недостаточно раскрыты поля карточки ({', '.join(weak)}).")
        if len(fields.get('Суть','').strip())<35 and len(fields.get('Биография','').strip())<35:
            warnings.append(f"{card['name']}: мало информации о личности важного персонажа.")
        if cid!=actor and not (character.get('goals') or character.get('intentions')):
            warnings.append(f"{card['name']}: не задана цель или намерение для самостоятельных действий.")
        if cid not in secrets:
            warnings.append(f"{card['name']}: не задана личная тайна с указанием того, кто о ней знает.")
    for r in world['relationships'].values():
        if r.get('source_id') in ids and r.get('target_id') in ids and len(r.get('context','').strip())<25:
            warnings.append('Связь между персонажами описана слишком кратко: добавь мотив и динамику.')
            break
    if scene and actor in scene.get('participants',[]):
        point=world['characters'].get(actor,{})
        if point.get('location') and point['location']!=scene.get('location'):
            warnings.append('Стартовое местоположение управляемого героя отличается от места стартовой сцены.')
        if not (point.get('situation') or scene.get('text')):
            warnings.append('У героя нет описания занятия и непосредственной стартовой ситуации.')
    return warnings


def secret_holders(state):
    """Characters who know a private fact about themselves (not merely a rumor about someone else)."""
    world=state['world']
    known={(k.get('actor_id'),k.get('fact_id')) for k in world['knowledge'].values() if k.get('status')=='known'}
    owners=set()
    for fid,fact in world['facts'].items():
        if not fact.get('secret'):continue
        linked=fact.get('character_ids',[])
        owner=fact.get('owner_id') or (linked[0] if len(linked)==1 else None)
        if owner and (owner,fid) in known:owners.add(owner)
    return owners


PLACEHOLDER=re.compile(r'^\s*(?:неизвестно|неизвестен|неизвестна|не указано|не задано|нет данных|\?|[-—–]|n/?a|unknown)(?:\s*[.!])?\s*$',re.I)
DETAIL_MIN={'Возраст':1,'Роль':3,'Статус':3,'Внешность':55,'Суть':65,'Биография':105}


def weak_card_field(value,field,source=''):
    """Catch schema filler and verbatim idea copies; never fabricate missing details in Python."""
    if not isinstance(value,str) or PLACEHOLDER.fullmatch(value) or len(value.strip())<DETAIL_MIN[field]:return True
    if field in ('Внешность','Суть','Биография') and source:
        source_words=set(re.findall(r'[\wё]{4,}',source.casefold()))
        words=set(re.findall(r'[\wё]{4,}',value.casefold()))
        if len(words-source_words)<4:return True
    return False


def repair_scene_interval(state):
    """An unfinished active opening scene is a point in time, not an elapsed event."""
    state=deepcopy(state)
    scene=state['world']['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    now=state.get('world_clock',{}).get('minute')
    if scene.get('status')=='active' and type(now) is int and now>=0:
        # This is a pre-game opening point; no elapsed interval has been played yet.
        scene['start_minute']=now
        scene['end_minute']=now
    return state


def entity(state,kind,eid):
    if kind=='campaign':return state['campaign']
    if kind=='start':return {'protagonist_id':state.get('protagonist_id'),'controlled_actor_id':state.get('controlled_actor_id'),
        'scene_id':state.get('camera',{}).get('scene_id'),'minute':state['world_clock'].get('minute')}
    if kind in ('character','location'):
        values=state['characters' if kind=='character' else 'locations']
        value=next((x for x in values if x['id']==eid),None)
    else:value=state['world'].get(GROUPS.get(kind,''),{}).get(eid)
    if value is None:raise ValueError('Сущность не найдена.')
    return value


def patch(state,kind,eid,field,value):
    state=deepcopy(state);target=entity(state,kind,eid)
    if kind not in FIELDS:raise ValueError('Неизвестная сущность.')
    if kind=='character' and field.startswith('fields.'):
        key=field[7:]
        if not key or '.' in key or len(key)>100 or not isinstance(value,str):raise ValueError('Некорректное поле карточки.')
        target['fields'][key]=value
    elif field in FIELDS[kind]:
        list_fields={'goals','intentions','obligations','aliases','character_ids','participants','witnesses','fact_ids','evidence'}
        if field in list_fields and (not isinstance(value,list) or any(not isinstance(x,str) for x in value)):
            raise ValueError('Нужен список строк.')
        if field in ('minute','start_minute','end_minute') and (type(value) is not int or value<0):raise ValueError('Нужно неотрицательное целое время.')
        if field in ('secret','player_observed') and type(value) is not bool:raise ValueError('Нужно логическое значение.')
        if field=='dimensions' and (not isinstance(value,dict) or any(type(x) not in (int,float) or not -100<=x<=100 for x in value.values())):raise ValueError('Показатели должны быть числами от -100 до 100.')
        old=target.get(field)
        if old is not None and type(value) is not type(old):raise ValueError('Тип поля менять нельзя.')
        if len(json.dumps(value,ensure_ascii=False))>30000:raise ValueError('Поле слишком длинное.')
        target[field]=value
    else:raise ValueError('Поле недоступно для изменения.')
    if kind=='start':
        state.update(protagonist_id=target['protagonist_id'],controlled_actor_id=target['controlled_actor_id'])
        state['camera']={'scene_id':target['scene_id'],'mode':'actor'}
        state['world_clock']={'minute':target['minute'],'last_event_time':label(target['minute'])}
    return sync(state)


def dependencies(state,kind,eid):
    result=[]
    if kind=='location':
        name=entity(state,kind,eid)['name']
        for group in ('characters','scenes'):
            result += [{'kind':group,'id':key} for key,item in state['world'][group].items() if item.get('location')==name]
    for group,items in state['world'].items():
        if not isinstance(items,dict):continue
        for key,item in items.items():
            if group==GROUPS.get(kind) and key==eid:continue
            if isinstance(item,dict) and any(v==eid or isinstance(v,list) and eid in v for k,v in item.items() if k.endswith('_id') or k.endswith('_ids') or k in ('participants','witnesses')):
                result.append({'kind':group,'id':key})
    if kind=='character' and eid in (state.get('protagonist_id'),state.get('controlled_actor_id')):result.append({'kind':'start','id':eid})
    if kind=='scene' and eid==state.get('camera',{}).get('scene_id'):result.append({'kind':'camera','id':eid})
    return result


def remove(state,kind,eid):
    entity(state,kind,eid)
    deps=dependencies(state,kind,eid)
    if deps:raise ValueError('Сначала измени связанные записи: '+', '.join(f"{d['kind']}/{d['id']}" for d in deps))
    state=deepcopy(state)
    if kind in ('character','location'):
        key='characters' if kind=='character' else 'locations';state[key]=[x for x in state[key] if x['id']!=eid]
        if kind=='character':state['world']['characters'].pop(eid,None)
    elif kind in GROUPS and kind!='actor':state['world'][GROUPS[kind]].pop(eid)
    else:raise ValueError('Эту сущность удалять нельзя.')
    return sync(state)


def add(state,kind):
    state=deepcopy(state);eid=kind+'_'+uuid.uuid4().hex[:16]
    actor=state.get('controlled_actor_id');minute=state['world_clock']['minute']
    if kind=='character':
        state['characters'].append({'id':eid,'name':'Новый персонаж '+eid[-4:],'is_player':False,'fields':{'Статус':'','Внешность':'','Суть':'','Биография':''},'aliases':[]})
        state['world']['characters'][eid]={'id':eid,'location':None,'situation':'','goals':[],'short_goal':'','intentions':[],'obligations':[],'emotion':'','minute':minute,'scene_id':None,'last_event_id':None}
    elif kind=='location':state['locations'].append({'id':eid,'name':'Новое место','text':''})
    else:
        templates={
          'relationship':{'source_id':actor,'target_id':next((c['id'] for c in state['characters'] if c['id']!=actor),actor),'context':'','dimensions':{}},
          'thread':{'id':eid,'description':'Новая линия','state':'','status':'active','character_ids':[],'relevance':0.5,'last_event_id':None},
          'fact':{'id':eid,'text':'Новый факт','secret':False,'character_ids':[],'evidence':[]},
          'knowledge':{'actor_id':actor,'fact_id':next(iter(state['world']['facts']),''),'status':'unknown','source_event_id':None},
          'scene':{'id':eid,'participants':[],'location':'Не указано','text':'','start_minute':minute,'end_minute':minute,'status':'active','event_ids':[]},
          'event':{'id':eid,'text':'Новое событие','participants':[],'witnesses':[],'minute':minute,'fact_ids':[],'source_sequence':0,'player_observed':False,'scene_id':None}}
        if kind not in templates:raise ValueError('Тип не поддерживается.')
        state['world'][GROUPS[kind]][eid]=templates[kind]
    return sync(state),eid


def player_view(state):
    """Server-side actor knowledge projection; hidden entries never reach the browser."""
    actor=state['controlled_actor_id'];world=state['world'];meta=state.get('scene_meta',{})
    known={k['fact_id'] for k in world['knowledge'].values() if k['actor_id']==actor and k['status']=='known'}
    def visible(item):return not item.get('director_only') and (not item.get('secret') or actor in item.get('visible_to_ids',[]))
    public=deepcopy({k:state[k] for k in ('campaign','characters','world','locations','protagonist_id','controlled_actor_id','camera','world_clock') if k in state})
    public['sections']={};public['story_notes']='';public.pop('memory',None);public.pop('knowledge',None)
    public.pop('facts',None);public.pop('events',None);public.pop('plans',None)
    public['campaign']['description']=public['campaign'].get('public_description','')
    public['campaign']['rules']=''
    public['world']={**{kind:{} for kind in KINDS},'version':2}
    scene=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    public['scene']=scene.get('text','');public['scene_meta']={**meta,'present_ids':scene.get('participants',[])}
    public['characters']=[c for c in public['characters'] if not c.get('hidden') or c['id']==actor or c['id'] in scene.get('participants',[]) or actor in c.get('visible_to_ids',[])]
    visible_ids={c['id'] for c in public['characters']}
    for c in public['characters']:
        c.pop('text',None)
        c.pop('hidden',None);c.pop('visible_to_ids',None)
        c['fields']={k:v for k,v in c['fields'].items() if k in ('Внешность','Роль','Возраст') or c['id']==actor and k not in ('Секрет','Скрытые мотивы')}
        if c['id']==actor:public['world']['characters'][actor]=deepcopy(world['characters'][actor])
    public['world']['facts']={key:deepcopy(f) for key,f in world['facts'].items() if (key in known or not f.get('secret')) and not f.get('director_only') and set(f.get('character_ids',[]))<=visible_ids}
    # Knowledge records with "unknown" must not expose the existence of their facts.
    public['world']['knowledge']={key:deepcopy(k) for key,k in world['knowledge'].items() if k['actor_id']==actor and k['fact_id'] in public['world']['facts'] and k['status'] in ('known','suspected')}
    public['world']['relationships']={key:deepcopy(r) for key,r in world['relationships'].items() if not r.get('director_only') and (r.get('source_id')==actor or actor in r.get('visible_to_ids',[])) and r.get('source_id') in visible_ids and r.get('target_id') in visible_ids}
    public['relationships']=[dict(source_id=r.get('source_id',''),target_id=r.get('target_id',''),text=r.get('context','')) for r in public['world']['relationships'].values()]
    public['world']['threads']={key:deepcopy(t) for key,t in world['threads'].items() if actor in t.get('visible_to_ids',[]) and not t.get('director_only') and set(t.get('character_ids',[]))<=visible_ids}
    for thread in public['world']['threads'].values():
        thread['state']=thread.get('public_state','')
        thread.pop('last_event_id',None)
        thread.pop('relevance',None)
    public['world']['events']={key:deepcopy(e) for key,e in world['events'].items() if (actor in e.get('participants',[]) or actor in e.get('witnesses',[]) or e.get('player_observed')) and not e.get('director_only')}
    if scene:
        public['world']['scenes'][state['camera']['scene_id']]=deepcopy(scene)
        # An event might reference a hidden fact; remove its links, not its visible text.
        public['world']['scenes'][state['camera']['scene_id']]['event_ids']=[key for key in scene.get('event_ids',[]) if key in public['world']['events']]
    for event in public['world']['events'].values():event['fact_ids']=[key for key in event.get('fact_ids',[]) if key in public['world']['facts']]
    for fact in public['world']['facts'].values():fact['evidence']=[]
    # Explicitly hidden places remain author-only; generator instructions forbid secrets in public place descriptions.
    public['locations']=[loc for loc in public['locations'] if visible(loc)]
    for group in ('facts','relationships','threads','events','scenes'):
        for item in public['world'][group].values():
            for marker in ('director_only','visible_to_ids','secret_intentions','private_notes'):item.pop(marker,None)
    for loc in public['locations']:
        for marker in ('director_only','visible_to_ids'):loc.pop(marker,None)
    return public


def export_markdown(state):
    """Readable projection plus a versioned, integrity-checked round-trip payload."""
    names={c['id']:c['name'] for c in state['characters']}
    def person(cid):return names.get(cid,cid or 'Неизвестно')
    campaign=state['campaign']
    titles={'setting':'Обстановка','era':'Эпоха','genre':'Жанр','tone':'Тон','description':'Описание','public_description':'Аннотация для игрока','rules':'Правила повествования'}
    lines=['# '+campaign['title']]+[f"## {title}\n{campaign.get(key,'')}" for key,title in titles.items() if campaign.get(key)]
    lines += ['## Начало игры', 'Основной герой: '+person(state.get('protagonist_id')),
              'Управление: '+person(state.get('controlled_actor_id')),label(state['world_clock']['minute'])]
    for c in state['characters']:
        lines+=['## '+c['name']]+[f'### {k}\n{v}' for k,v in c['fields'].items()]
        if c.get('aliases'):lines+=['Другие имена: '+', '.join(c['aliases'])]
        actor=state['world']['characters'][c['id']]
        for key,title in [('location','Место'),('emotion','Эмоциональное состояние'),('goals','Цели'),('intentions','Намерения'),('obligations','Обязательства')]:
            value=actor.get(key)
            if value:lines += ['### '+title,'\n'.join('- '+v for v in value) if isinstance(value,list) else str(value)]
    lines+=['## Направленные отношения']
    for r in state['world']['relationships'].values():
        lines += ['### '+person(r['source_id'])+' → '+person(r['target_id']),r.get('context','')]
        lines += ['; '.join(f'{k}: {v}' for k,v in r.get('dimensions',{}).items())]
    lines+=['## Факты и знания']
    for fid,f in state['world']['facts'].items():
        lines += ['### '+('Тайна: ' if f.get('secret') else '')+f['text']]
        for k in state['world']['knowledge'].values():
            if k['fact_id']==fid:lines += ['- '+person(k['actor_id'])+': '+{'known':'знает','suspected':'подозревает','unknown':'не знает'}[k['status']]]
        if f.get('evidence'):lines += ['Основания: '+'; '.join(f['evidence'])]
    for kind,title in [('threads','Сюжетные линии'),('scenes','Сцены'),('events','События'),('scheduled_events','Отложенные события')]:
        lines+=['## '+title]
        for key,item in state['world'][kind].items():
            lines+=['### '+str(item.get('description') or item.get('location') or item.get('text') or key)]
            if item.get('text') and item.get('location'):lines += [item['text']]
            if item.get('state'):lines += [item['state']]
            if item.get('status'):lines += ['Статус: '+item['status']]
            people=item.get('participants',item.get('character_ids',[]))
            if people:lines += ['Участники: '+', '.join(person(cid) for cid in people)]
            for field in ('minute','start_minute','end_minute','due_minute'):
                if type(item.get(field)) is int:lines += [label(item[field])]
    for loc in state['locations']:lines+=['## '+loc['name'],loc['text']]
    body='\n\n'.join(lines)+'\n'
    payload=base64.b64encode(json.dumps(state,ensure_ascii=False).encode()).decode()
    return body+f'\n<!-- AI_RPG_STATE_V2 {hashlib.sha256(body.encode()).hexdigest()} {payload} -->\n'


def exported_state(text):
    m=re.search(r'\n<!-- AI_RPG_STATE_V2 ([a-f0-9]{64}) ([A-Za-z0-9+/=]+) -->\s*$',text)
    if not m:return None
    body=text[:m.start()]
    if hashlib.sha256(body.encode()).hexdigest()!=m[1]:raise ValueError('Текст экспорта изменён вне редактора. Импортируй исходный экспорт и измени поля в редакторе мира.')
    try:state=prepare(json.loads(base64.b64decode(m[2],validate=True)))
    except Exception as exc:raise ValueError('Повреждён структурированный экспорт.') from exc
    return state
