"""Bounded proposal generation. A completed job never modifies the draft."""
import json
from copy import deepcopy
from backend.services.world_builder import READ_ONLY
from backend.runtime_v3.models import PersonalityProfile, WorldStateV3
from pydantic import ValidationError
from backend.services.usage import tracked_stream
from backend.services.continuation import request_context


def target(snapshot,path):
    if not path or path[0] not in ('world_state','campaign','character_cards'):raise ValueError('Недоступное поле.')
    value=snapshot
    for key in path:
        if key in READ_ONLY or key.endswith('_id') or key.endswith('_ids'):raise ValueError('Ссылки не генерируются.')
        try:value=value[int(key)] if isinstance(value,list) else value[key]
        except (KeyError,IndexError,TypeError,ValueError) as exc:raise ValueError('Поле отсутствует. Сохраните карточку перед генерацией.') from exc
    if value is None and path[-1]=='display_name':value=''
    if not isinstance(value,(str,dict)):raise ValueError('Выберите текстовое поле или карточку.')
    return value


def template(snapshot,path):
    value=deepcopy(target(snapshot,path))
    if len(path)==3 and path[:2]==['world_state','characters']:
        if value.get('display_name') is None:value['display_name']=''
        if value.get('personality') is None:
            fields=('traits','communication','habits','strengths','weaknesses','fears','preferences','temperament')
            value['personality']=PersonalityProfile().model_dump()
            value['personality']['items']={f:{'field':f,'text':'','revision':0,'source_ids':[],'witnesses':[],'fact_ids':[]} for f in fields}
    return value


def verify(before,after,key=''):
    """Providers can rewrite prose only, never references, enums or topology."""
    if isinstance(before,dict):
        if not isinstance(after,dict) or before.keys()!=after.keys():raise ValueError('Изменена структура карточки.')
        for k,v in before.items():verify(v,after[k],k)
    elif isinstance(before,str) and key not in READ_ONLY and not key.endswith(('_id','_ids')) and key not in {
        'status','kind','mode','visibility','category','field','system','channel','life_status','developmental_stage','reproductive_capability','biological_sex','type','outcome','duration','protection','start_date','date','birth_date'}:
        if not isinstance(after,str) or len(after)>30000:raise ValueError('Некорректный текст предложения.')
    elif before!=after:raise ValueError('Предложение меняет технические поля или связанные записи.')


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    repo=preparation.repo;job=repo.preparation_job(jid)
    with repo.connect() as db: snapshot=json.loads(repo._draft_head(db,job['workspace_id'])['content'])['state']
    path=config['_builder_path'];before=template(snapshot,path)
    world=snapshot['world_state']
    selected=path[2] if len(path)>2 and path[0]=='world_state' else None
    related=[]
    if selected:
        from backend.services.world_builder import dependencies
        for reference in dependencies(snapshot,selected)[:24]:
            parts=reference.split('.')
            if len(parts)>1 and isinstance(world.get(parts[0]),dict) and parts[1] in world[parts[0]]:
                item={'section':parts[0],'record':world[parts[0]][parts[1]]}
                if item not in related:related.append(item)
    context={'related':related,'path':path,'value':before,'campaign':snapshot['campaign'],
             'characters':[{ 'id':k,'name':v.get('display_name'),'situation':v.get('situation')} for k,v in world['characters'].items()],
             'locations':world['locations'],'instruction':config['_draft_input']}
    messages=[{'role':'system','content':'Предложи изменение авторского поля RPG. Верни только JSON {"value": ...}. Пиши на языке исходного текста и указаний автора (по умолчанию русский). Сохрани структуру, IDs, ссылки, перечисления и нетекстовые значения. Меняй только содержательный текст выбранного поля или карточки. Не раскрывай секреты в публичном описании.'},
              {'role':'user','content':json.dumps(context,ensure_ascii=False)}]
    messages,limit=request_context(messages,'',config['context_length'],config['max_tokens'],format_hint='json')
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    text='';repo.draft_phase(jid,'editing')
    for chunk in tracked_stream(repo,stream_fn,jid,'builder_proposal',config,messages,
            model=config['model'],provider=config['provider'],api_key=api_key,
            temperature=config['temperature'],max_tokens=limit,require_complete=True,
            cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if config['provider']=='deepseek' else {})):
        if handle.cancel.is_set():return
        text+=chunk;repo.preparation_progress(jid,text)
    answer=json.loads(text)
    if not isinstance(answer,dict) or set(answer)!={'value'}:raise ValueError('Ожидается предложение value.')
    verify(before,answer['value'],path[-1])
    if path[0]=='world_state':
        proposed=deepcopy(world);cursor=proposed
        for part in path[1:-1]:cursor=cursor[int(part)] if isinstance(cursor,list) else cursor[part]
        if isinstance(cursor,list):cursor[int(path[-1])]=answer['value']
        else:cursor[path[-1]]=answer['value']
        try:WorldStateV3.model_validate(proposed)
        except ValidationError as exc:
            relevant=[e for e in exc.errors() if tuple(map(str,e['loc'][:len(path)-1]))==tuple(path[1:])]
            if relevant:raise ValueError('Предложение не соответствует схеме: '+'; '.join(e['msg'] for e in relevant))
    if not handle.cancel.is_set():repo.preparation_progress(jid,text,'saved')
