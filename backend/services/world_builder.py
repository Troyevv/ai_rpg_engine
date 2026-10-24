"""Authoring adapter over the canonical snapshot. No alternate runtime schema."""
from copy import deepcopy
import json
import uuid
from pydantic import ValidationError
from backend.runtime_v3.models import WorldStateV3, WorldHistoryV3, Calendar, assert_world_state_v3_invariants
from backend.runtime_v3.calendar import calendar_label

# Runtime bookkeeping is owned by the runtime, never by an author/provider.
READ_ONLY = {'id', 'schema_version', 'turn_id', 'revision', 'applied', 'seen_sources',
             'reviewed_signature', 'review_required', 'pacing_recent', 'protagonist_periods',
             'emotion_source_sequence', 'last_attempt_minute', 'portraits', 'operation_id'}

def schema():
    value = WorldStateV3.model_json_schema()
    from backend.runtime_v3.raw import extraction_schema
    event=deepcopy(extraction_schema()['properties']['events']['items'])
    for key in ('advance_candidate_ids','player_evidence','player_assertion'):
        event['properties'].pop(key,None)
    value['historySchema']={'type':'array','items':event}
    value['readOnlyFields'] = sorted(READ_ONLY)
    return value

def empty(title):
    world = WorldStateV3(camera={'mode':'observer'}, characters={}).model_dump()
    world['meta']['calendar'] = Calendar(start_minute=0, start_weekday=0).model_dump()
    return dict(schema_version=3, world_state=world, character_cards=[],
                campaign={'campaign':{'title':title, 'setting':'', 'era':'', 'genre':'', 'tone':'', 'description':'', 'rules':''}},
                memory={}, history_head=None, initial_history=WorldHistoryV3().to_dict())

def report(snapshot):
    errors=[]
    try:
        # Validate before the read-boundary salvage helpers can drop malformed data.
        state=WorldStateV3.model_validate(snapshot['world_state']).model_dump()
        checked=assert_world_state_v3_invariants(deepcopy(state))
        def changes(a,b,path):
            if isinstance(a,dict) and isinstance(b,dict):
                for key in a.keys()|b.keys():
                    if key not in a or key not in b:errors.append({'path':'.'.join(path+[key]),'message':'Runtime отбросил бы запись: проверьте идентификаторы и ссылки.'})
                    else:changes(a[key],b[key],path+[key])
            elif a!=b:errors.append({'path':'.'.join(path),'message':'Runtime исправил бы значение: проверьте связанные записи.'})
        changes(state,checked,[])
    except ValidationError as exc:
        errors.extend({'path':'.'.join(map(str,e['loc'])), 'message':e['msg']} for e in exc.errors())
    except (ValueError, KeyError, TypeError) as exc:
        path=getattr(exc,'path',{})
        errors.append({'path':'.'.join(str(path[k]) for k in ('section','entity') if k in path) or 'camera', 'message':str(exc)})
    world=snapshot['world_state']
    for cid,actor in world.get('characters',{}).items():
        if not str(actor.get('display_name') or '').strip():
            errors.append({'path':f'characters.{cid}.display_name','message':'Укажите имя персонажа.'})
    for group,field in [('locations','name'),('facts','text'),('threads','description'),('scheduled_events','description')]:
        for eid,row in world.get(group,{}).items():
            if not str(row.get(field) or '').strip():errors.append({'path':f'{group}.{eid}.{field}','message':'Заполните описание или название записи.'})
    events=snapshot.get('initial_history',{}).get('events',[])
    event_ids={e.get('id') for e in events if isinstance(e.get('id'),str)}
    if len(event_ids)!=len(events):errors.append({'path':'initial_history.events','message':'Повтор идентификатора события.'})
    for i,event in enumerate(events):
        from backend.runtime_v3.history import INFORMATION_MEDIA
        if event.get('medium','action') not in INFORMATION_MEDIA|{'action'}:errors.append({'path':f'initial_history.events.{i}.medium','message':'Выберите допустимый источник события.'})
        if event.get('location_id') and event['location_id'] not in world.get('locations',{}):errors.append({'path':f'initial_history.events.{i}.location_id','message':'Неизвестное место события.'})
        for key in ('minute','order'):
            if key in event and (type(event[key]) is not int or event[key]<0):errors.append({'path':f'initial_history.events.{i}.{key}','message':'Нужно целое неотрицательное число.'})
        for field,known in [('participants',world.get('characters',{})),('witnesses',world.get('characters',{})),('fact_ids',world.get('facts',{}))]:
            if not isinstance(event.get(field,[]),list) or any(not isinstance(x,str) or x not in known for x in event.get(field,[])):
                errors.append({'path':f'initial_history.events.{i}.{field}','message':'Неизвестная ссылка.'})
        if not isinstance(event.get('text'),str) or not event['text'].strip():errors.append({'path':f'initial_history.events.{i}.text','message':'Нужно описание события.'})
        if type(event.get('minute',0)) is int and type(world['meta'].get('world_time')) is int and event.get('minute',0)>world['meta']['world_time']:errors.append({'path':f'initial_history.events.{i}.minute','message':'История не может происходить после начала игры.'})
    def event_refs(value,path):
        if isinstance(value,dict):
            for k,v in value.items():
                if k=='source_event_id' and v and (not isinstance(v,str) or v not in event_ids and v not in world.get('remote_events',{})):errors.append({'path':'.'.join(path+[k]),'message':'Неизвестное событие-источник.'})
                else:event_refs(v,path+[k])
        elif isinstance(value,list):
            for i,v in enumerate(value):event_refs(v,path+[str(i)])
    event_refs(world,[])
    return {'errors':errors,'warnings':[]}

def normalize(snapshot):
    """Only derived projection/keys; incomplete authored values remain intact."""
    result=deepcopy(snapshot);world=result['world_state']
    for section,fields in [('relationships',('source_id','target_id')),('knowledge',('actor_id','fact_id'))]:
        records={}
        for key,row in world.get(section,{}).items():
            new=':'.join(str(row.get(f,'')) for f in fields) if all(row.get(f) for f in fields) else key
            if new in records:raise ValueError(f'{section}: повтор записи между выбранными сущностями.')
            records[new]=row
        world[section]=records
    from backend.runtime_v3.life import SYMMETRIC
    for relation in world.get('objective_relations',{}).values():
        if relation.get('kind') in SYMMETRIC and relation.get('source_id') and relation.get('target_id'):
            relation['source_id'],relation['target_id']=sorted((relation['source_id'],relation['target_id']))
    cal=world.get('meta',{}).get('calendar')
    if cal:
        try:world['meta']['calendar']=Calendar.model_validate(cal).model_dump()
        except ValueError:pass  # an unfinished profile is still saveable
    cards={c['id']:c for c in result.get('character_cards',[])}
    result['character_cards']=[dict(id=cid,name=a.get('display_name') or '',aliases=cards.get(cid,{}).get('aliases',[]),
        fields={'Биография':'','Роль':'',**cards.get(cid,{}).get('fields',{})},is_player=cid==world['meta'].get('current_protagonist_id')) for cid,a in world['characters'].items()]
    return result

def dependencies(snapshot, eid):
    found=[]
    def walk(value,path):
        if isinstance(value,dict):
            for k,v in value.items():
                if k!='id':walk(v,path+[k])
        elif isinstance(value,list):
            for i,v in enumerate(value):walk(v,path+[str(i)])
        elif value==eid:found.append('.'.join(path))
    walk(snapshot['world_state'],[])
    walk(snapshot.get('initial_history',{}),['initial_history'])
    return found

def guard(old,new):
    """Reject forged bookkeeping and dangling references caused by deletion."""
    def walk(a,b,path):
        if isinstance(b,dict):
            a=a if isinstance(a,dict) else {}
            for k,v in b.items():
                if k in READ_ONLY and k in a and a[k]!=v:
                    raise ValueError('.'.join(path+[k])+': служебное поле доступно только для чтения.')
                if k in READ_ONLY-{'id','operation_id','turn_id','revision','schema_version'} and k not in a and v not in (None,[],{},''):
                    raise ValueError('.'.join(path+[k])+': служебное поле заполняет Runtime.')
                if k in ('turn_id','revision') and k not in a and v not in (0,1):
                    raise ValueError('.'.join(path+[k])+': недопустимый служебный счётчик.')
                walk(a.get(k),v,path+[k])
        elif isinstance(b,list):
            previous={v.get('id'):v for v in a if isinstance(v,dict) and v.get('id')} if isinstance(a,list) else {}
            for i,v in enumerate(b):
                walk(previous.get(v.get('id'),{}) if isinstance(v,dict) else None,v,path+[str(i)])
    walk(old['world_state'],new['world_state'],[])
    old_events={e['id'] for e in old.get('initial_history',{}).get('events',[]) if e.get('id')}
    new_events={e['id'] for e in new.get('initial_history',{}).get('events',[]) if e.get('id')}
    for eid in old_events-new_events:
        refs=dependencies(new,eid)
        if refs:raise ValueError('Сначала измените зависимые записи: '+', '.join(refs))
    for group,records in old['world_state'].items():
        if group in ('meta','camera','reproduction_policy') or not isinstance(records,dict):continue
        for eid in records.keys()-new['world_state'].get(group,{}).keys():
            refs=dependencies(new,eid)
            if refs:raise ValueError('Сначала измените зависимые записи: '+', '.join(refs))

def assign_ids(value,node,defs):
    if not isinstance(node,dict):return
    if '$ref' in node:node=defs[node['$ref'].split('/')[-1]]
    if 'anyOf' in node:
        node=next((n for n in node['anyOf'] if n.get('type')!='null'),{})
        if value is None:return
        return assign_ids(value,node,defs)
    if isinstance(value,dict):
        props=node.get('properties',{})
        for key in node.get('required',[]):
            if key in READ_ONLY and key not in value:
                value[key]=0 if props[key].get('type')=='integer' else uuid.uuid4().hex
        if 'id' in props and not value.get('id'):value['id']=uuid.uuid4().hex
        for k,v in value.items():assign_ids(v,props.get(k,node.get('additionalProperties',{})),defs)
    elif isinstance(value,list):
        for v in value:assign_ids(v,node.get('items',{}),defs)

def update(old, world, campaign, cards, history=None):
    if not isinstance(world,dict) or set(world)!=set(old['world_state']):raise ValueError('Состав разделов Runtime менять нельзя.')
    for group,records in world.items():
        if not isinstance(records,dict):raise ValueError(group+': нужен объект.')
        if group not in ('meta','camera','reproduction_policy') and any(not isinstance(row,dict) for row in records.values()):raise ValueError(group+': нужна карточка.')
    value=deepcopy(old);value['world_state']=deepcopy(world)
    if len(json.dumps(value))>2000000:raise ValueError('Мир слишком большой.')
    value['campaign']={'campaign':deepcopy(campaign)}
    value['character_cards']=deepcopy(cards)
    if history is not None:
        if set(history)-set(WorldHistoryV3().to_dict()) or any(not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows) for rows in history.values()):raise ValueError('Некорректные списки History.')
        if any(rows for key,rows in history.items() if key!='events'):raise ValueError('Служебные журналы истории заполняет Runtime.')
        value['initial_history']=deepcopy(history)
        for event in value['initial_history'].get('events',[]):
            event.setdefault('id',uuid.uuid4().hex)
            event['turn_id']=0
            event.setdefault('recorded_minute',event.get('minute',0))
            event.setdefault('player_observed',False)
    guard(old,value)
    spec=schema()
    for group,records in value['world_state'].items():
        node=spec['properties'].get(group,{})
        model=node.get('additionalProperties',{}).get('$ref','').split('/')[-1] if isinstance(node.get('additionalProperties'),dict) else ''
        if model and 'id' in spec['$defs'][model].get('properties',{}):
            for eid,row in records.items():
                if row.get('id') not in (None,'',eid):raise ValueError(group+': ID не совпадает с ключом.')
                row['id']=eid
    assign_ids(value['world_state'],spec,spec['$defs'])
    return normalize(value)

def time_label(snapshot):
    try:
        meta=deepcopy(snapshot['world_state']['meta'])
        if meta.get('calendar'):meta['calendar']=Calendar.model_validate(meta['calendar']).model_dump()
        return calendar_label({'meta':meta})
    except (ValueError,KeyError,TypeError,IndexError):return ''

def launch(snapshot):
    errors=report(snapshot)['errors']
    if errors:raise ValueError('; '.join(e['path']+': '+e['message'] for e in errors))
    result=normalize(snapshot)
    result['world_state']=WorldStateV3.model_validate(result['world_state']).model_dump()
    # Match the ordinary migration boundary's established initialization.
    from backend.runtime_v3.personality import initialize_profiles
    from backend.runtime_v3.protagonist import initialize
    initialize_profiles(result);initialize(result)
    assert_world_state_v3_invariants(result['world_state'])
    return result


def markdown(snapshot):
    """Human-readable source preview; canonical data stays in world_parts."""
    campaign=snapshot['campaign']['campaign']
    lines=['# '+campaign.get('title','Мир')]
    for key in ('setting','era','genre','tone','description','rules'):
        if campaign.get(key):lines.append(campaign[key])
    for card in snapshot['character_cards']:
        lines.append('## '+card['name'])
        lines.extend('### '+k+'\n'+v for k,v in card.get('fields',{}).items() if v)
    lines.extend(['## Начало игры',snapshot['world_state']['camera']['situation']])
    return '\n\n'.join(lines)
