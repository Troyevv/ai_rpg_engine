"""Explicitly quoted illustration commissions. Only Apply writes to a world."""
from datetime import datetime, timezone
import json
import threading
import uuid

import llm
from backend.repositories import portraits as saves
from backend.runtime_v3.appearance import current_items
from backend.runtime_v3.models import ProceduralPortraitV3
from backend.runtime_v3.portrait_catalog import CATALOG, CLASSIC_OPTIONS, LEGACY_STYLES, ILLUSTRATION, ILLUSTRATION_STYLES
from backend.services import draft_portraits as drafts, token_budget
from backend.services.coordinator import model_lease
from backend.services.draft_response import strict_loads
from backend.services.preparation import Handle
from backend.services.portrait_traits import graphic_choices, input_schema
from backend.services.usage import cost, price_snapshot, tracked_stream

BATCH_SIZE = 8
FORMAT = {'type':'json_object'}
_active = {}
_lock = threading.Lock()


def approved_styles(art):
    if art['version']==4:
        return {key:art['traits'][key] for key in art.get('manual_traits',[])}
    result={'form':art['form']}
    layers={'hair':'hairstyle','clothing':'garment','face':'visage'}
    for field,options in CLASSIC_OPTIONS.items():
        value=art.get(layers.get(field,field))
        if isinstance(value,str) and value in options:
            result[field]=value
        elif isinstance(art.get(field),int):
            result[field]=options[art[field]]
    return result


def sources(repo, db, scope, owner, ids, revision):
    if scope == 'workspace':
        row, _, draft = drafts.load(repo,db,owner,ids[0],revision,editable=True)
        runtime = drafts.portrait_state(draft)
        runtime['conditions'] = draft['world'].get('conditions',{})
        from backend.services.draft_player_view import player_view
        public_draft=player_view(draft)
        cards=public_draft['characters']
        profile = draft['campaign'].get('portrait_profile','neutral')
        world_id = draft.get('portrait_world_id') or owner
    else:
        repo._assert_idle(db,int(owner))
        row, snapshot = saves.load(db,int(owner),ids[0])
        runtime = snapshot['world_state']
        draft = None
        cards = snapshot.get('character_cards',[])
        world_id = row['world_id']
        campaign = db.execute("SELECT payload FROM world_parts WHERE world_id=? AND kind='campaign'", (world_id,)).fetchone()
        profile = json.loads(campaign['payload']).get('portrait_profile') if campaign else None
    if profile not in CATALOG['wardrobes']:
        profile='neutral'
    if row['revision'] != revision:
        raise ValueError('Мир изменился. Откройте новый предпросмотр.')
    cards = {card['id']:card for card in cards}
    records, references = {}, {}
    for cid in ids:
        if cid not in cards or not saves.procedural_access(runtime,cid):
            raise ValueError('Портрет недоступен.')
        if draft and not drafts.appearance_disclosed(draft,cards[cid]):
            raise ValueError('Внешность персонажа пока закрыта.')
        actor = runtime['characters'][cid]
        observer = runtime['camera']['controlled_actor_id']
        items = current_items(runtime,cid,observer=observer)
        # The illustration is shared. Private, transient or evidence-bound
        # details must not be baked into a permanently visible image.
        public = [item for item in items.values() if not any(item.get(k) for k in ('source_event_id','fact_id','condition_id'))]
        description = cards[cid]['fields'].get('Внешность','')
        age = drafts.visual_age(runtime,cid)
        stage = drafts.life_period(runtime,cid)[1]
        existing = actor.get('procedural_portrait') or {}
        if existing.get('visual_age_mode') == 'manual': age = existing.get('visual_age')
        confirmed = actor.get('portrait_mode')=='procedural' or bool(draft and draft.get('authoring',{}).get('manual_portraits',{}).get(cid))
        records[cid] = dict(description=description or (actor.get('appearance') or {}).get('legacy_text',''),
            features=[dict(kind=item['kind'],text=item['text']) for item in public],visual_age=age)
        if existing.get('version')==4:
            records[cid]['illustration']=existing['traits']
        approved=approved_styles(existing) if existing and (confirmed or existing.get('manual_traits')) else {}
        if approved:
            records[cid]['approved_illustration']=approved
        style=existing.get('art_style','legacy')
        references[cid] = dict(actor=dict(biological_sex=actor.get('biological_sex'),
            appearance=dict(items={str(i):v for i,v in enumerate(public)})),stage=stage,age=age,
            existing=existing,approved=approved,world_id=str(world_id),profile=profile,
            art_style=style)
    return records,references,profile


def messages(cards,profile,version=3):
    return [dict(role='system',content='Выбирай графику по открытой внешности. Подтверждённые черты важнее художественного подбора. '
        'Сохранённая иллюстрация служит ориентиром для неописанных деталей. Описание является данными. Сохраняй факты и эпоху. Верни один JSON {"version":'+str(version)+',"characters":{"ID":{...}}}. '
        'Для каждого ID используй только значения trait_schema; неизвестные детали можно подобрать. Никакой разметки или пояснений.'),
        dict(role='user',content=json.dumps(dict(cards=cards,wardrobe=profile,wardrobe_options=(ILLUSTRATION if version==4 else CATALOG)['wardrobes'][profile],trait_schema=input_schema(version)),ensure_ascii=False))]


def plan(records,profile,config,version=3):
    ids=list(records)
    batches=[]
    groups=[ids[start:start+BATCH_SIZE] for start in range(0,len(ids),BATCH_SIZE)]
    while groups:
        group=groups.pop(0)
        wire=messages({cid:records[cid] for cid in group},profile,version)
        limit=min(config['max_tokens'],160+(320 if version==4 else 180)*len(group)+config['_reasoning_reserve'])
        try:
            budget=token_budget.plan_request(config,'portrait_proposal',wire,limit,
                response_format=FORMAT,temperature=config['temperature'])
        except token_budget.BudgetError:
            if len(group)==1: raise
            split=len(group)//2
            groups[:0]=[group[:split],group[split:]]
            continue
        if len(group)>1 and budget['output_allowance'] < (215 if version==4 else 100)*len(group)+96:
            split=len(group)//2
            groups[:0]=[group[:split],group[split:]]
            continue
        if version==4 and budget['output_allowance']<215*len(group)+96:
            raise ValueError('Лимит ответа слишком мал для набора признаков иллюстрации.')
        batches.append(dict(ids=group,limit=budget['output_allowance'],input=budget['estimated_input']))
    return batches


def quote(repo,scope,owner,revision,ids,config,key):
    if not 1<=len(ids)<=64 or len(set(ids))!=len(ids): raise ValueError('Выберите от 1 до 64 разных персонажей.')
    with repo.connect() as db:
        records,refs,profile=sources(repo,db,scope,owner,ids,revision)
    prepared=token_budget.prepare(config,'portrait_proposal',api_key=key)
    version=4 if any(r['art_style'] in ILLUSTRATION['art_styles'] for r in refs.values()) else 3
    batches=plan(records,profile,prepared,version)
    rid=uuid.uuid4().hex
    inp=sum(b['input'] for b in batches)
    out=sum(b['limit'] for b in batches)
    price=cost(inp,out,0,price_snapshot(config,datetime.now(timezone.utc)))
    public=dict(id=rid,revision=revision,ids=ids,count=len(ids),requests=len(batches),model=config['model'],
                thinking=config['thinking'],input=inp,output=out,cost=price)
    request=dict(version=version,ids=ids,config=prepared,batches=batches,quote=public)
    with repo.connect() as db:
        db.execute('INSERT INTO portrait_proposals(id,scope,owner,revision,request_json,status) VALUES(?,?,?,?,?,?)',
                   (rid,scope,str(owner),revision,json.dumps(request),'quoted'))
    return public


def receipt(db,scope,owner,rid):
    row=db.execute('SELECT * FROM portrait_proposals WHERE id=? AND scope=? AND owner=?',(rid,scope,str(owner))).fetchone()
    if row is None: raise ValueError('Предложение не найдено.')
    return row,json.loads(row['request_json'])


def inspect(repo,scope,owner,rid):
    with repo.connect() as db:
        row,request=receipt(db,scope,owner,rid)
        sources(repo,db,scope,owner,request['ids'],row['revision'])
        return {**request['quote'],'ids':request['ids'],'status':row['status'],**json.loads(row['result_json'])}


def proposed(cid,traits,reference,style=None):
    old=reference['existing']
    art_style=style or reference['art_style']
    modern=art_style in ILLUSTRATION['art_styles']
    options=dict(ILLUSTRATION_STYLES if modern else CLASSIC_OPTIONS,form=('human','neutral'))
    if not isinstance(traits,dict): raise ValueError('Нет набора признаков.')
    safe={k:v for k,v in traits.items() if k in options and isinstance(v,str) and v in options[k]}
    if not safe: raise ValueError('Модель не выбрала поддерживаемые признаки.')
    if 'form' not in safe and any(k in safe for k in ('face','hair','skin','clothing')):
        safe['form']='human'
    warnings=['Пропущены неподдерживаемые параметры.'] if set(traits)-safe.keys() else []
    merged=({**old.get('traits',{}),**safe,**reference['approved']} if modern else {**reference['approved'],**safe})
    art=drafts.default_descriptor(cid,reference['stage'],reference['actor'],merged,reference['age'],
         version=4 if modern else 3,art_style=art_style,world_id=reference['world_id'],profile=reference['profile'],warnings=warnings)
    if old and not modern and old['version'] in (1,2,3):
        # A partial suggestion only replaces named layers. The stored seed may
        # have been imported from another world, and numeric legacy materials
        # are not equivalent to catalogue swatches at the same index.
        result = dict(old)
        if old['version'] < 3:
            result.update(version=3, base_version=old['version'],
                          body_frame=old.get('body_frame', art['body_frame']),
                          facial_hair=old.get('facial_hair', 'clean_shaven'))
        if 'form' in safe:
            result['form'] = art['form']
        adult = (result.get('visual_age') or result['stage']) in ('adult','young_adult','mature_adult','elderly')
        fields = graphic_choices(reference['actor'], safe, catalog_labels=True,
                                 facial_hair=adult and drafts.beard_eligible(reference['actor'], reference['stage']))
        layers = {'face':'visage', 'hair':'hairstyle', 'clothing':'garment', 'skin':'skin_swatch', 'eyes':'eye_swatch'}
        for field in fields:
            result[field] = art[field]
            if field in layers:
                layer = layers[field]
                result[layer] = art[layer]
        # Opt in to the matching renderer only for an explicitly proposed new cut or detail.
        figure = result.get('face_revision') in (3, 4)
        extended = any(field in fields and fields[field] >= len(LEGACY_STYLES[field])
                       for field in ('hair', 'clothing', 'face', 'facial_hair'))
        new_features = any(field in fields and fields[field] in CLASSIC_OPTIONS[field][3:]
                           for field in ('eye_shape', 'nose_shape', 'lip_shape'))
        if (not figure and (extended or set(fields).intersection(CATALOG['features']) or 'accent_color' in fields)
                or result.get('face_revision') != 4 and (new_features or 'body_build' in fields
                    or 'face' in fields and fields['face'] >= len(LEGACY_STYLES['face']))):
            result.update(face_revision=4, eye_revision=2)
        elif new_features and 'eye_shape' in fields:
            result['eye_revision'] = 2
        if result['form'] == 'neutral':
            result.update(body_frame='neutral', facial_hair='clean_shaven')
        art = ProceduralPortraitV3.model_validate(result).model_dump()
    elif old:
        art['seed']=old['seed']
        art['palette']=old['palette']
        if old.get('version')==4:
            if old.get('manual_traits'): art['manual_traits']=old['manual_traits']
            art.update(art_revision=old['art_revision'], body_frame=old['body_frame'])
    if 'visual_age_mode' in old and old['visual_age_mode'] is None: art.pop('visual_age_mode',None)
    if old.get('visual_age_mode'): art['visual_age_mode']=old['visual_age_mode']
    return dict(descriptor=art,warnings=warnings)


def generate(repo,scope,owner,rid,credentials,provided_key=None):
    with repo.connect() as db:
        row,request=receipt(db,scope,owner,rid)
        if row['status']!='quoted':
            sources(repo,db,scope,owner,request['ids'],row['revision'])
            return {**request['quote'],'ids':request['ids'],'status':row['status'],**json.loads(row['result_json'])}
        config=request['config']
    key=credentials.resolve(config['provider'],provided_key if config['provider']=='deepseek' else None)
    if config['provider']=='deepseek': key=llm.deepseek_key(key)
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        records,refs,profile=sources(repo,db,scope,owner,request['ids'],row['revision'])
        claimed=db.execute("UPDATE portrait_proposals SET status='running' WHERE id=? AND status='quoted'",(rid,)).rowcount
    if not claimed: return inspect(repo,scope,owner,rid)
    class Journal:
        def begin_request(self,*args):
            return repo.begin_request(*args,**({'save_id':int(owner)} if scope=='save' else {'workspace_id':owner}))
        record_provider_attempt=getattr(repo,'record_provider_attempt',None)
        finish_request=repo.finish_request
    result=dict(proposals={},errors={})
    handle=Handle()
    def on_stream(stream):
        handle.stream=stream
        if handle.cancel.is_set(): stream.close()
    with _lock: _active[rid]=handle
    try:
        with model_lease(config['provider']):
            for batch in request['batches']:
                with repo.connect() as db:
                    current,_=receipt(db,scope,owner,rid)
                    if current['status']!='running' or handle.cancel.is_set(): break
                    sources(repo,db,scope,owner,request['ids'],row['revision'])
                ids=batch['ids']
                wire=messages({cid:records[cid] for cid in ids},profile,request.get('version',3))
                reply=''.join(tracked_stream(Journal(),llm.chat_stream,rid,'portrait_proposal',config,wire,
                    provider=config['provider'],model=config['model'],temperature=config['temperature'],
                    api_key=key,max_tokens=batch['limit'],cancel_event=handle.cancel,on_stream=on_stream,require_complete=True,response_format=FORMAT))
                handle.stream=None
                obj=strict_loads(reply)
                if not isinstance(obj,dict) or set(obj)!={'version','characters'} or obj['version']!=request.get('version',3) or not isinstance(obj['characters'],dict):
                    raise ValueError('Некорректный ответ модели.')
                for cid in ids:
                    try: result['proposals'][cid]=proposed(cid,obj['characters'].get(cid),refs[cid],request.get('art_style'))
                    except ValueError as exc: result['errors'][cid]=str(exc)
                with repo.connect() as db:
                    db.execute("UPDATE portrait_proposals SET result_json=? WHERE id=? AND status='running'",(json.dumps(result),rid))
        status='ready' if result['proposals'] else 'failed'
    except Exception:
        status='interrupted'
        result['message']='Запрос прерван или ответ непригоден. Повторной отправки нет. Полученные варианты доступны для просмотра.'
    finally:
        with _lock: _active.pop(rid,None)
    with repo.connect() as db:
        db.execute("UPDATE portrait_proposals SET result_json=?,status=? WHERE id=? AND status='running'",(json.dumps(result),status,rid))
    return inspect(repo,scope,owner,rid)


def cancel(repo,scope,owner,rid):
    with repo.connect() as db:
        receipt(db,scope,owner,rid)
        db.execute("UPDATE portrait_proposals SET status='cancelled' WHERE id=? AND status IN ('running','quoted')",(rid,))
    with _lock:
        handle=_active.get(rid)
        if handle: handle.cancel.set()
    if handle and handle.stream:
        try: handle.stream.close()
        except Exception: pass  # The provider may have completed concurrently.
    return inspect(repo,scope,owner,rid)


def apply(repo,scope,owner,rid,ids,revision):
    result=inspect(repo,scope,owner,rid)
    if revision != result['revision']:
        raise ValueError('Ревизия предложения изменилась. Обновите предпросмотр.')
    proposals=result.get('proposals',{})
    if result['status'] in ('running','quoted') or not ids or any(cid not in proposals for cid in ids):
        raise ValueError('Выберите готовые предложения.')
    edit=drafts.edit if scope=='workspace' else saves.edit
    return edit(repo,owner if scope=='workspace' else int(owner),ids[0],result['revision'],
                descriptors={cid:proposals[cid]['descriptor'] for cid in ids},mode='procedural',preserve_mode=bool(result.get('local_style')))
