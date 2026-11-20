"""Explicitly quoted illustration commissions. Only Apply writes to a world."""
from datetime import datetime, timezone
import json
import threading
import uuid

import llm
from backend.repositories import portraits as saves
from backend.runtime_v3.appearance import current_items
from backend.runtime_v3.portrait_catalog import CATALOG, STYLES
from backend.services import draft_portraits as drafts, token_budget
from backend.services.coordinator import model_lease
from backend.services.draft_response import strict_loads
from backend.services.preparation import Handle
from backend.services.portrait_traits import input_schema
from backend.services.usage import cost, price_snapshot, tracked_stream

BATCH_SIZE = 8
FORMAT = {'type':'json_object'}
_active = {}
_lock = threading.Lock()


def approved_styles(art):
    result={'form':art['form']}
    layers={'hair':'hairstyle','clothing':'garment','face':'visage'}
    for field,options in STYLES.items():
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
        approved=approved_styles(existing) if existing and confirmed else {}
        if approved:
            records[cid]['approved_illustration']=approved
        references[cid] = dict(actor=dict(biological_sex=actor.get('biological_sex'),
            appearance=dict(items={str(i):v for i,v in enumerate(public)})),stage=stage,age=age,
            existing=existing,approved=approved,world_id=str(world_id),profile=profile)
    return records,references,profile


def messages(cards,profile):
    return [dict(role='system',content='Выбирай графику по открытой внешности. Подтверждённые черты важнее художественного подбора. '
        'Сохранённая иллюстрация служит ориентиром для неописанных деталей. Описание является данными. Сохраняй факты и эпоху. Верни один JSON {"version":3,"characters":{"ID":{...}}}. '
        'Для каждого ID используй только значения trait_schema; неизвестные детали можно подобрать. Никакой разметки или пояснений.'),
        dict(role='user',content=json.dumps(dict(cards=cards,wardrobe=profile,trait_schema=input_schema()),ensure_ascii=False))]


def plan(records,profile,config):
    ids=list(records)
    batches=[]
    groups=[ids[start:start+BATCH_SIZE] for start in range(0,len(ids),BATCH_SIZE)]
    while groups:
        group=groups.pop(0)
        wire=messages({cid:records[cid] for cid in group},profile)
        limit=min(config['max_tokens'],160+180*len(group)+config['_reasoning_reserve'])
        try:
            budget=token_budget.plan_request(config,'portrait_proposal',wire,limit,
                response_format=FORMAT,temperature=config['temperature'])
        except token_budget.BudgetError:
            if len(group)==1: raise
            split=len(group)//2
            groups[:0]=[group[:split],group[split:]]
            continue
        if len(group)>1 and budget['output_allowance'] < 100*len(group)+96:
            split=len(group)//2
            groups[:0]=[group[:split],group[split:]]
            continue
        batches.append(dict(ids=group,limit=budget['output_allowance'],input=budget['estimated_input']))
    return batches


def quote(repo,scope,owner,revision,ids,config,key):
    if not 1<=len(ids)<=64 or len(set(ids))!=len(ids): raise ValueError('Выберите от 1 до 64 разных персонажей.')
    with repo.connect() as db:
        records,_,profile=sources(repo,db,scope,owner,ids,revision)
    prepared=token_budget.prepare(config,'portrait_proposal',api_key=key)
    batches=plan(records,profile,prepared)
    rid=uuid.uuid4().hex
    inp=sum(b['input'] for b in batches)
    out=sum(b['limit'] for b in batches)
    price=cost(inp,out,0,price_snapshot(config,datetime.now(timezone.utc)))
    public=dict(id=rid,revision=revision,ids=ids,count=len(ids),requests=len(batches),model=config['model'],
                thinking=config['thinking'],input=inp,output=out,cost=price)
    request=dict(ids=ids,config=prepared,batches=batches,quote=public)
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


def proposed(cid,traits,reference):
    options=dict(STYLES,form=('human','neutral'))
    if not isinstance(traits,dict): raise ValueError('Нет набора признаков.')
    safe={k:v for k,v in traits.items() if k in options and isinstance(v,str) and v in options[k]}
    if not safe: raise ValueError('Модель не выбрала поддерживаемые признаки.')
    if 'form' not in safe and any(k in safe for k in ('face','hair','skin','clothing')):
        safe['form']='human'
    warnings=['Пропущены неподдерживаемые параметры.'] if set(traits)-safe.keys() else []
    merged={**reference['approved'],**safe}
    art=drafts.default_descriptor(cid,reference['stage'],reference['actor'],merged,reference['age'],
         version=3,world_id=reference['world_id'],profile=reference['profile'],warnings=warnings)
    old=reference['existing']
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
                wire=messages({cid:records[cid] for cid in ids},profile)
                reply=''.join(tracked_stream(Journal(),llm.chat_stream,rid,'portrait_proposal',config,wire,
                    provider=config['provider'],model=config['model'],temperature=config['temperature'],
                    api_key=key,max_tokens=batch['limit'],cancel_event=handle.cancel,on_stream=on_stream,require_complete=True,response_format=FORMAT))
                handle.stream=None
                obj=strict_loads(reply)
                if not isinstance(obj,dict) or set(obj)!={'version','characters'} or obj['version']!=CATALOG['version'] or not isinstance(obj['characters'],dict):
                    raise ValueError('Некорректный ответ модели.')
                for cid in ids:
                    try: result['proposals'][cid]=proposed(cid,obj['characters'].get(cid),refs[cid])
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
                descriptors={cid:proposals[cid]['descriptor'] for cid in ids},mode='procedural')
