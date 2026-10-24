"""Initial-world additions to master's editable draft, using Runtime models."""
from copy import deepcopy
import re
from pydantic import ValidationError
from backend.runtime_v3 import models as m
from backend.services.world import identity

EXTENSIONS = {
    'objective_relations':m.ObjectiveRelation, 'conditions':m.Condition,
    'organizations':m.Organization, 'residences':m.Residence, 'roles':m.NarrativeRole,
    'possessions':m.SignificantPossession, 'contacts':m.Contact,
    'pregnancies':m.Pregnancy, 'reproductive_events':m.ReproductiveEvent,
    'naming_decisions':m.NamingDecision,
}
ACTOR_FIELDS = ('life_status','birth_date','biological_sex','physical_state','capabilities',
    'developmental_stage','name_history','appearance','personality','values',
    'reproductive_capability','identity_components','life_fact_id','parentage_complete_fact_id')


class DraftErrors(ValueError):
    def __init__(self,errors):
        self.errors = errors
        super().__init__('; '.join(e['path']+': '+e['message'] for e in errors))


def escape(value):return str(value).replace('~','~0').replace('/','~1')


def error(path,message,category='invalid',**extra):
    return dict(path=path,message=message,category=category,**extra)


MOTIVATION_FIELDS = ('goals', 'intentions', 'obligations')


def motivation_records(values, cid, field):
    """Use Runtime's explicit string compatibility and strict Motivation contract.

    No prose inference, regenerated IDs for objects, or removal of lifecycle data.
    """
    try:
        actor=m.Character.model_validate({'id':cid,field:values})
    except ValidationError as exc:
        raise DraftErrors([error('/world/characters/'+escape(cid)+'/'+ '/'.join(escape(p) for p in e['loc']),
            e['msg'],e['type']) for e in exc.errors(include_url=False,include_input=False)]) from exc
    records=[item.model_dump() for item in getattr(actor,field)]
    seen=set();problems=[]
    for index,row in enumerate(records):
        if row['id'] in seen:problems.append(error(f'/world/characters/{escape(cid)}/{field}/{index}/id','Повторный Motivation ID.','duplicate_id'))
        seen.add(row['id'])
    if problems:raise DraftErrors(problems)
    return records


def normalize_motivations(state):
    """Normalize only motivation fields, collecting independent element failures."""
    problems=[]
    for cid,actor in state.get('world',{}).get('characters',{}).items():
        if not isinstance(actor,dict):continue
        for field in MOTIVATION_FIELDS:
            if field not in actor:continue
            try:actor[field]=motivation_records(actor[field],cid,field)
            except DraftErrors as exc:problems.extend(exc.errors)
    if problems:raise DraftErrors(problems)
    return state


def runtime_schema(model):
    schema = model.model_json_schema(); definitions = schema.pop('$defs',{})
    def inline(v):
        if isinstance(v,list): return [inline(x) for x in v]
        if not isinstance(v,dict): return v
        if '$ref' in v: return inline(definitions[v['$ref'].split('/')[-1]])
        return {k:({name:inline(part) for name,part in x.items()} if k=='properties' else inline(x)) for k,x in v.items() if k not in ('title','default')}
    return inline(schema)


def extend_schema(schema):
    from backend.services.draft_schema import entries
    world = schema['properties']['world']['properties']
    for section,model in EXTENSIONS.items():
        part = runtime_schema(model)
        for technical in ('source_turn','revision','applied','field_facts','remote_source_ids'):
            part.get('properties',{}).pop(technical,None)
        if 'id' in part.get('required',[]):part['required'].remove('id')
        world[section] = entries(part,'Необязательно; только обоснованные начальные данные. ID записи задаёт ключ.')
    actor = world['characters']['additionalProperties']
    canonical = runtime_schema(m.Character)['properties']
    actor['properties'].update({k:canonical[k] for k in ('situation','goals','intentions','emotion','obligations')})
    actor['properties'].update({k:canonical[k] for k in ACTOR_FIELDS if k not in ('appearance','personality','values','identity_components')})
    world['facts']['additionalProperties']['properties']['claim'] = runtime_schema(m.Claim)
    world['knowledge']['additionalProperties']['properties'].update({k:v for k,v in runtime_schema(m.Knowledge)['properties'].items() if k not in ('actor_id','fact_id')})
    world['communication'] = runtime_schema(m.CommunicationCapabilities)
    place = schema['properties']['locations']['items']['properties']
    place.update({k:v for k,v in runtime_schema(m.Location)['properties'].items() if k in ('parent_id','kind','aliases')})
    # Technical defaults do not require model output. Keep the same draft shape.
    for part in (schema, schema['properties']['world']):
        part['required'] = [k for k in part.get('required',[]) if k not in ('schema_version','version')]
    schema['properties']['world_clock']['required'] = ['minute']
    calendar=schema['properties']['world_clock']['properties']['calendar']
    calendar['required']=[k for k in calendar.get('required',[]) if k not in ('start_minute','start_weekday')]
    actor['required'] = ['situation']
    for name in ('facts','scenes','events','threads'):
        part=world[name]['additionalProperties']
        part['required']=[k for k in part.get('required',[]) if k!='id']
    profile=calendar['properties']['profile']
    profile['allOf']=[{'if':{'properties':{'system':{'const':'custom'}},'required':['system']},
        'then':{'properties':{'month_lengths':{'minItems':1,'items':{'type':'integer','minimum':1,'maximum':99}}},'required':['month_lengths']},
        'else':{'properties':{'month_lengths':{'maxItems':0},'weekday_names':{'oneOf':[{'maxItems':0},{'minItems':7,'maxItems':7}]}}}}]
    effects=world['conditions']['additionalProperties']['properties']['effects']['properties']
    for effect in effects.values():
        effect.clear();effect.update({'enum':[False,None]})
    return schema


def normalize_calendar(clock):
    configured=clock.get('calendar')
    if not isinstance(configured,dict):return
    configured.setdefault('start_minute',clock['minute'])
    for field in ('start_minute','start_weekday'):
        value=configured.get(field)
        if isinstance(value,str) and re.fullmatch(r'0|[1-9]\d*',value):configured[field]=int(value)
    profile=configured.get('profile',{})
    if isinstance(profile,dict) and profile.get('system','gregorian')=='gregorian':
        # Gregorian lengths are calculated by datetime, including leap years.
        profile['month_lengths']=[]
    names=profile.get('weekday_names') if isinstance(profile,dict) else None
    week_length=len(names) if isinstance(names,list) and names else 7
    anchor=configured.get('start_minute')
    if type(anchor) is int and anchor>=0:
        configured.setdefault('start_weekday',anchor//1440%week_length)
    try:
        # Canonical defaults and the weekday of an explicit Gregorian date are
        # deterministic. Invalid dates/profiles remain intact for local repair.
        clock['calendar']=m.Calendar.model_validate(configured).model_dump()
    except ValidationError:
        pass


def prompt_schema():
    # Keep the descriptive editor schema; omit duplicate prose from the provider
    # schema. Property names such as title/description are data, not annotations.
    from backend.services.draft_schema import world_state_schema
    def compact(v):
        if isinstance(v,list):return [compact(x) for x in v]
        if not isinstance(v,dict):return v
        return {k:({name:compact(part) for name,part in x.items()} if k=='properties' else compact(x)) for k,x in v.items() if k not in ('description','title','$schema') and not (k=='additionalProperties' and x is True) and not (k=='required' and not x)}
    schema=compact(world_state_schema())
    return schema


def normalize(value):
    """Only unambiguous structural defaults; no creative completion or text clipping."""
    if not isinstance(value,dict): raise DraftErrors([error('/','Ожидался объект мира.','object_type')])
    value=deepcopy(value); problems=[]
    for key,kind in (('characters',list),('campaign',dict),('world',dict),('camera',dict),('world_clock',dict)):
        if not isinstance(value.get(key),kind): problems.append(error('/'+key,'Ожидался '+kind.__name__,'type'))
    if problems: raise DraftErrors(problems)
    world=value['world'];value.setdefault('schema_version',1);world.setdefault('version',2)
    if world['version']!=2: raise DraftErrors([error('/world/version','Ожидалось 2.','literal')])
    from backend.services.world import KINDS
    for section in (*KINDS,*EXTENSIONS):
        world.setdefault(section,{})
        if not isinstance(world[section],dict): problems.append(error('/world/'+section,'Ожидался объект записей.','object_type'))
    if problems: raise DraftErrors(problems)
    for index,card in enumerate(value['characters']):
        if not isinstance(card,dict): raise DraftErrors([error(f'/characters/{index}','Ожидалась карточка.','object_type')])
        card.setdefault('id',identity('character',index,card.get('name','')))
        card.setdefault('fields',{});card.setdefault('aliases',[])
        if not isinstance(card.get('name'),str) or not card['name'].strip():
            problems.append(error(f'/characters/{index}/name','Ожидалось непустое имя.','string_type'))
        if not isinstance(card['fields'],dict):
            problems.append(error(f'/characters/{index}/fields','Ожидался объект текстовых полей.','object_type'))
        else:
            for field,text in card['fields'].items():
                if not isinstance(text,str):problems.append(error(f'/characters/{index}/fields/{field}','Ожидался текст.','string_type'))
    if problems:raise DraftErrors(problems)
    clock=value['world_clock']
    if isinstance(clock.get('minute'),str) and re.fullmatch(r'0|[1-9]\d*',clock['minute']):clock['minute']=int(clock['minute'])
    if type(clock.get('minute')) is not int or clock['minute']<0:
        raise DraftErrors([error('/world_clock/minute','Ожидалось неотрицательное целое число.','int_type')])
    if clock.get('calendar') is None:
        # Same relative Gregorian anchor as Runtime migration; no invented date.
        clock['calendar']=m.Calendar(start_minute=clock['minute'],start_weekday=clock['minute']//1440%7).model_dump()
    normalize_calendar(clock)
    value['camera'].setdefault('mode','actor')
    if 'scene_id' not in value['camera'] and len(world['scenes'])==1:value['camera']['scene_id']=next(iter(world['scenes']))
    for scene in world['scenes'].values():
        if isinstance(scene,dict):
            scene.setdefault('start_minute',clock['minute']);scene.setdefault('end_minute',scene['start_minute'])
            scene.setdefault('event_ids',[]);scene.setdefault('status','active')

    # Map keys already identify these records; no guessing by display names.
    for section in (*KINDS,*EXTENSIONS):
        for key,item in world[section].items():
            if not isinstance(item,dict): problems.append(error('/world/'+section+'/'+key,'Ожидался объект.','object_type'));continue
            if section not in ('relationships','knowledge'): item.setdefault('id',key)
    # Rename invalid technical character IDs consistently, never edit prose.
    remap={c['id']:identity('character',c['id']) for c in value['characters'] if isinstance(c.get('id'),str) and not re.fullmatch(r'[\w-]{1,100}',c['id'])}
    def references(v,field=''):
        if isinstance(v,dict):
            return {remap.get(k,k):references(x,k) for k,x in v.items()}
        if isinstance(v,list): return [references(x,field) for x in v]
        if isinstance(v,str) and (field=='id' or field.endswith('_id') or field.endswith('_ids') or field in ('participants','witnesses')):
            return remap.get(v,v)
        return v
    if remap:
        value=references(value);world=value['world']
    for index,place in enumerate(value.get('locations',[])):
        if isinstance(place,dict):
            place.setdefault('id',identity('location',index,place.get('name','')))
            place.setdefault('kind','unknown')  # preserves explicit IDs during existing migration
    from backend.services.draft_relations import merge
    value=merge(value);world=value['world']
    scene=world['scenes'].get(value['camera'].get('scene_id'),{})
    if isinstance(scene,dict) and isinstance(scene.get('location'),str):
        for cid in scene.get('participants',[]):
            actor=world['characters'].get(cid)
            if isinstance(actor,dict) and actor.get('location') is None:actor['location']=scene['location']
    if problems: raise DraftErrors(problems)
    value['draft_contract']=4
    return normalize_motivations(value)


def validate_typed(state):
    """Validate before legacy migration's conservative salvage can discard input."""
    world=state['world']; problems=[]
    def check(model,record,path):
        try: return model.model_validate(record)
        except ValidationError as exc:
            for e in exc.errors(include_url=False,include_input=False):
                location=e['loc']
                if model is m.Calendar and not location and e['type']=='value_error':
                    location=('start_weekday',) if 'start_weekday' in e['msg'] else ('start_date',)
                suffix='/'.join(str(x).replace('~','~0').replace('/','~1') for x in location)
                problems.append(error(path+('/'+suffix if suffix else ''),e['msg'],e['type']))
    calendar=None
    if state['world_clock'].get('calendar') is not None:
        calendar=check(m.Calendar,state['world_clock']['calendar'],'/world_clock/calendar')
    for section,model in EXTENSIONS.items():
        for key,record in world.get(section,{}).items(): check(model,record,f'/world/{section}/{escape(key)}')
    for cid,record in world['characters'].items():
        check(m.Character,{k:v for k,v in record.items() if k in m.Character.model_fields},'/world/characters/'+escape(cid))
    for key,record in world['knowledge'].items():
        check(m.Knowledge,{k:v for k,v in record.items() if k in m.Knowledge.model_fields},'/world/knowledge/'+escape(key))
    for key,record in world['facts'].items():
        if record.get('claim') is not None: check(m.Claim,record['claim'],'/world/facts/'+escape(key)+'/claim')
    ids={c['id'] for c in state['characters']}; facts=set(world['facts']); locations={p['id'] for p in state['locations']}
    if calendar:
        for index,observance in enumerate(calendar.profile.observances):
            for member,cid in enumerate(observance.character_ids):
                if cid not in ids:
                    problems.append(error(f'/world_clock/calendar/profile/observances/{index}/character_ids/{member}',
                        'Дата календаря ссылается на неизвестного персонажа.','reference',allowed=sorted(ids)))
    if calendar or state['world_clock'].get('calendar') is None:
        from backend.runtime_v3.calendar import date_parts
        profile=calendar.profile.model_dump() if calendar else {}
        for cid,record in world['characters'].items():
            if record.get('birth_date') is not None:
                try: date_parts(record['birth_date'],profile)
                except (ValueError,TypeError,KeyError) as exc:
                    problems.append(error('/world/characters/'+escape(cid)+'/birth_date',str(exc),'calendar_date',expected='YYYY-MM-DD'))
    for field in ('protagonist_id','controlled_actor_id'):
        if (not isinstance(state.get(field),str) or state.get(field) not in ids): problems.append(error('/'+field,'Неизвестный персонаж.','reference',allowed=sorted(ids)))
    for index,place in enumerate(state['locations']):
        check(m.Location,{k:v for k,v in place.items() if k in m.Location.model_fields},f'/locations/{index}')
        if place.get('parent_id') is not None and place['parent_id'] not in locations:
            problems.append(error(f'/locations/{index}/parent_id','Неизвестное родительское место.','reference',allowed=sorted(locations)))
    for index,place in enumerate(state['locations']):
        parents={p['id']:p.get('parent_id') for p in state['locations']}
        seen={place['id']};parent=place.get('parent_id')
        while parent in parents:
            if parent in seen:
                problems.append(error(f'/locations/{index}/parent_id','Цикл иерархии локаций.','cycle'));break
            seen.add(parent);parent=parents[parent]
    for key,fact in world['facts'].items():
        claim=fact.get('claim')
        if claim and claim.get('predicate')=='parent_organization':
            valid=set(world.get('organizations',{}))
            for field in ('subject_id','value'):
                if claim.get(field) not in valid:problems.append(error(f'/world/facts/{escape(key)}/claim/{field}','Неизвестная организация.','reference',allowed=sorted(valid)))
    references={'source_id':ids,'target_id':ids,'actor_id':ids,'owner_id':ids,'holder_id':ids,
        'fact_id':facts,'life_fact_id':facts,'closure_fact_id':facts,'parentage_complete_fact_id':facts,
        'location_id':locations,'organization_id':set(world.get('organizations',{}))}
    for section in (*EXTENSIONS,'characters','knowledge','relationships'):
        for key,record in world.get(section,{}).items():
            for field,valid in references.items():
                if record.get(field) is not None and (not isinstance(record[field],str) or record[field] not in valid):
                    problems.append(error(f'/world/{section}/{escape(key)}/{field}','Ссылка не существует.','reference',allowed=sorted(valid)))
    from backend.services.relation_dimensions import RELATION_DIMENSIONS
    for key,record in world['relationships'].items():
        for name,n in record.get('dimensions',{}).items():
            if name not in RELATION_DIMENSIONS or type(n) not in (float,int) or not -100<=n<=100:
                problems.append(error(f'/world/relationships/{escape(key)}/dimensions/{name}','Ожидалось допустимое измерение и число от -100 до 100.','range'))
    scene=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    place_names={p['id']:p['name'] for p in state['locations']}
    for cid in scene.get('participants',[]):
        point=world['characters'].get(cid,{})
        location=point.get('location')
        if location and place_names.get(location,location)!=place_names.get(scene.get('location'),scene.get('location')):
            problems.append(error('/world/characters/'+escape(cid)+'/location','Место участника не совпадает со стартовой сценой.','scene_position'))
    now=state['world_clock'].get('minute')
    if scene and (scene.get('start_minute')!=now or scene.get('end_minute')!=now):
        sid=state['camera']['scene_id']
        for field in ('start_minute','end_minute'):
            if scene.get(field)!=now:problems.append(error('/world/scenes/'+escape(sid)+'/'+field,'Стартовая сцена должна совпадать с текущей минутой мира.','opening_time'))
    for key,record in world['events'].items():
        if type(now) is int and type(record.get('minute')) is int and record['minute']>now:
            problems.append(error('/world/events/'+escape(key)+'/minute','Событие предыстории находится в будущем.','chronology'))
    for key,record in world['knowledge'].items():
        source=world['events'].get(record.get('source_event_id'))
        if record.get('source_event_id') and source is None:
            problems.append(error('/world/knowledge/'+escape(key)+'/source_event_id','Неизвестное событие получения знания.','reference',allowed=sorted(world['events'])))
        if source and (record['actor_id'] not in source.get('witnesses',[])+source.get('participants',[]) or record['fact_id'] not in source.get('fact_ids',[])):
            problems.append(error('/world/knowledge/'+escape(key)+'/source_event_id','Событие не подтверждает получение этого знания персонажем.','provenance'))
    for key,record in world.get('organizations',{}).items():
        for index,lid in enumerate(record.get('location_ids',[])):
            if not isinstance(lid,str) or lid not in locations:problems.append(error(f'/world/organizations/{escape(key)}/location_ids/{index}','Неизвестная локация организации.','reference',allowed=sorted(locations)))
    for key,record in world['events'].items():
        for field,valid in (('participants',ids),('witnesses',ids),('fact_ids',facts)):
            for index,ref in enumerate(record.get(field,[])):
                if not isinstance(ref,str) or ref not in valid:problems.append(error(f'/world/events/{escape(key)}/{field}/{index}','Ссылка события не существует.','reference',allowed=sorted(valid)))
    problems.extend(cross_record_errors(state))
    if problems: raise DraftErrors(problems)


def canonical_check(state):
    validate_typed(state)
    from backend.runtime_v3.migration import migrate_v2
    result=migrate_v2(state)
    canonical=result.snapshot['world_state'];problems=[]
    def differences(expected,actual,path):
        if expected==actual:return
        if isinstance(expected,dict) and isinstance(actual,dict):
            for key,value in expected.items():differences(value,actual.get(key),path+'/'+escape(key))
        else:problems.append(error(path,'Runtime изменил или отбросил исходные данные.','lossy_normalization'))
    if state['world_clock'].get('calendar') is not None:
        expected=m.Calendar.model_validate(state['world_clock']['calendar']).model_dump()
        if canonical['meta']['calendar']!=expected:
            differences(expected,canonical['meta']['calendar'],'/world_clock/calendar')
    # Invariants include legacy salvage for old saves. New generation must not
    # silently lose supplied extension records or their values through salvage.
    for section,model in EXTENSIONS.items():
        expected={k:model.model_validate(v).model_dump() for k,v in state['world'].get(section,{}).items()}
        if canonical[section]!=expected:
            differences(expected,canonical[section],'/world/'+section)
    for cid,record in state['world']['characters'].items():
        expected=m.Character.model_validate({k:v for k,v in record.items() if k in m.Character.model_fields}).model_dump()
        for field in (*ACTOR_FIELDS,'goals','intentions','obligations'):
            if field in record and record[field] not in (None,{},[]) and canonical['characters'][cid][field]!=expected[field]:
                differences(expected[field],canonical['characters'][cid][field],f'/world/characters/{escape(cid)}/{field}')
    for key,record in state['world']['knowledge'].items():
        expected=m.Knowledge.model_validate({k:v for k,v in record.items() if k in m.Knowledge.model_fields}).model_dump()
        if canonical['knowledge'].get(record['actor_id']+':'+record['fact_id'])!=expected:
            differences(expected,canonical['knowledge'].get(record['actor_id']+':'+record['fact_id']),'/world/knowledge/'+escape(key))
    if problems:raise DraftErrors(problems)
    return result


def cross_record_errors(state):
    """Collect independent cross-record failures before migration can salvage them."""
    world=state['world']; problems=[]
    def ptr(*parts):return '/'+ '/'.join(str(p).replace('~','~0').replace('/','~1') for p in parts)
    ids={c['id'] for c in state['characters']}
    from backend.runtime_v3.life import SYMMETRIC, PARENTAGE
    active={}; graph={}
    for section in (*EXTENSIONS,'characters','facts','events','scenes','threads','scheduled_events'):
        for key,row in world.get(section,{}).items():
            base=ptr('world',section,key)
            if row.get('id')!=key:problems.append(error(base+'/id','ID должен совпадать с ключом записи.','identity',expected=key))
            if section=='conditions':
                for effect,v in row.get('effects',{}).items():
                    if v is True:problems.append(error(base+'/effects/'+effect,'Условие ограничивает возможности, но не предоставляет их.','capability',allowed=[False,None]))
            if section in ('objective_relations','roles','residences','organizations','conditions'):
                since,until=row.get('since'),row.get('until')
                if isinstance(since,int) and isinstance(until,int) and until<since:
                    problems.append(error(base+'/until','Окончание раньше начала.','chronology',related_paths=[base+'/since']))
                if row.get('status','active') in ('active','unknown_outcome'):
                    for field in ('until','until_date','outcome','closure_fact_id'):
                        if row.get(field) not in (None,''):problems.append(error(base+'/'+field,'Активная запись содержит завершение.','chronology',related_paths=[base+'/status'] if 'status' in row else []))
            if section=='objective_relations':
                a,b=row.get('source_id'),row.get('target_id');kind=row.get('kind')
                if isinstance(a,str) and a==b:problems.append(error(base+'/target_id','Связь с самим собой недопустима.','relation',allowed=sorted(ids-{a})))
                endpoints=tuple(sorted((a,b))) if kind in SYMMETRIC and isinstance(a,str) and isinstance(b,str) else (a,b)
                signature=(kind,*endpoints)
                if row.get('status','active')=='active' and isinstance(a,str) and isinstance(b,str):
                    if signature in active:
                        previous=active[signature]
                        other=world['objective_relations'][previous.rsplit('/',1)[-1].replace('~1','/').replace('~0','~')]
                        # Exact differing fields only. Identity, kind, endpoints and status
                        # cannot be changed merely to hide a duplicate.
                        defaults=m.ObjectiveRelation.model_fields
                        fields=[f for f in defaults if f not in ('id','kind','source_id','target_id','status','context','evidence') and row.get(f,defaults[f].default)!=other.get(f,defaults[f].default)]
                        related=[previous,base]
                        for r in (other,row):
                            for field in ('fact_id','closure_fact_id'):
                                if isinstance(r.get(field),str) and r[field] in world['facts']:
                                    related.append(ptr('world','facts',r[field]))
                        related.extend(ptr('characters',i) for i,c in enumerate(state['characters']) if c['id'] in (a,b))
                        related=list(dict.fromkeys(related))
                        if fields:
                            for f in fields:
                                problems.append(error(base+'/'+f,'Различающиеся данные одной активной связи. Согласуйте с другой записью; не закрывайте связь ради удаления дубля.','relation_conflict',related_paths=related,patch_paths=[previous+'/'+f,base+'/'+f]))
                        else:problems.append(error(base,'Повтор одной направленной активной связи требует смыслового уточнения.','duplicate',related_paths=[previous]))
                    active[signature]=base
                if kind in PARENTAGE|{'guardian','foster_parent','step_parent'} and isinstance(a,str) and isinstance(b,str) and a in ids and b in ids:graph.setdefault(b,set()).add(a)
            participants=[row.get('actor_id')] if row.get('actor_id') else [row.get('source_id'),row.get('target_id')] if section=='objective_relations' else []
            for field in ('fact_id','closure_fact_id','life_fact_id','parentage_complete_fact_id'):
                fact=world['facts'].get(row.get(field)) if isinstance(row.get(field),str) else None
                if fact and participants and all(isinstance(x,str) for x in participants) and not set(participants)<=set(fact.get('character_ids',[])):
                    problems.append(error(base+'/'+field,'Факт не относится ко всем участникам.','provenance',related_paths=[ptr('world','facts',row[field],'character_ids')]))
            ref_lists={'participants':ids,'witnesses':ids,'character_ids':ids,'visible_to_ids':ids,'fact_ids':set(world['facts']),'event_ids':set(world['events']),'depends_on':set(world['scheduled_events'])}
            for field,known in ref_lists.items():
                for i,ref in enumerate(row.get(field,[])):
                    if not isinstance(ref,str) or ref not in known:problems.append(error(base+'/'+field+'/'+str(i),'Ссылка не существует.','reference',allowed=sorted(known)))
            for field,known in (('scene_id',world['scenes']),('last_event_id',world['events']),('resolved_event_id',world['events'])):
                if row.get(field) and row[field] not in known:problems.append(error(base+'/'+field,'Ссылка не существует.','reference',allowed=sorted(known)))
    from graphlib import TopologicalSorter,CycleError
    try:tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        cycle=set(exc.args[1])
        for key,row in world['objective_relations'].items():
            if row.get('source_id') in cycle and row.get('target_id') in cycle:problems.append(error(ptr('world','objective_relations',key,'target_id'),'Цикл родства.','cycle'))
    camera=state.get('camera',{});sid=camera.get('scene_id')
    if sid not in world['scenes']:problems.append(error('/camera/scene_id','Неизвестная стартовая сцена.','reference',allowed=sorted(world['scenes'])))
    elif state.get('controlled_actor_id') not in world['scenes'][sid].get('participants',[]):
        problems.append(error(ptr('world','scenes',sid,'participants'),'Управляемый персонаж отсутствует в сцене.','scene',related_paths=['/controlled_actor_id']))
    return problems


def inspect_candidate(raw):
    """Author data stays editable even when normalization/validation cannot finish."""
    from backend.services import draft_world
    state=raw
    try:
        state=normalize(raw)
        # Typed checking precedes legacy preparation, which otherwise hides paths.
        validate_typed(state)
        state=draft_world.prepare(state)
        report=draft_world.validate(state,canonical=False)
        if report['errors']:
            return state,dict(report,diagnostics=[error('/',e,'validation') for e in report['errors']])
        canonical_check(state)
        return state,dict(report,diagnostics=[])
    except (ValueError,TypeError,KeyError,IndexError,AttributeError) as exc:
        diagnostics=exc.errors if isinstance(exc,DraftErrors) else [error('/',str(exc),'validation_incomplete')]
        return state,dict(errors=[e['path']+': '+e['message'] for e in diagnostics],warnings=[],diagnostics=diagnostics)
