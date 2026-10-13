"""Explicit, single-call draft generation using the normal provider and accounting."""
import json
import uuid
from copy import deepcopy
from backend.services.protagonist_creation import CharacterDraft, creation_context, editor_schema
from backend.services.usage import tracked_stream
from backend.services.coordinator import model_lease
from context_builder import estimate
import llm


def generate(repo,save_id,draft,path,instruction,config,api_key):
    snapshot=repo.get_snapshot(save_id)
    # One exact selected path is the write boundary, including root for full generation.
    current=draft
    parts=path.split('.') if path else []
    for part in parts:
        if isinstance(current,list) and part.isdigit() and int(part)<len(current): current=current[int(part)]
        elif isinstance(current,dict) and part in current: current=current[part]
        else: raise ValueError('Неизвестное редактируемое поле.')
    if parts and parts[0] not in CharacterDraft.model_fields: raise ValueError('Неизвестный раздел.')
    context=creation_context(snapshot)
    schema,proposal_schemas=editor_schema()
    if parts:
        root=schema;selected=schema;schema_path=parts
        if parts[0]=='proposals' and len(parts)>=3 and parts[1].isdigit() and parts[2]=='value':
            selected=proposal_schemas.get(draft['proposals'][int(parts[1])]['kind'],{})
            schema_path=parts[3:]
        for part in schema_path:
            while '$ref' in selected: selected=root['$defs'][selected['$ref'].split('/')[-1]]
            if 'anyOf' in selected: selected=next(x for x in selected['anyOf'] if x.get('type')!='null')
            while '$ref' in selected: selected=root['$defs'][selected['$ref'].split('/')[-1]]
            selected=selected.get('items',{}) if part.isdigit() else selected.get('properties',{}).get(part,selected.get('additionalProperties',{}))
            if not isinstance(selected,dict): selected={}
        # Keep only definitions reachable from the selected field/section.
        definitions={}
        def references(node):
            if isinstance(node,dict):
                if '$ref' in node:
                    key=node['$ref'].split('/')[-1]
                    if key not in definitions:
                        definitions[key]=root['$defs'][key];references(definitions[key])
                for value in node.values(): references(value)
            elif isinstance(node,list):
                for value in node: references(value)
        references(selected);schema=dict(selected)
        if definitions: schema['$defs']=definitions
        if parts[0]=='proposals' and len(parts)<3: schema['proposal_schemas']=proposal_schemas
    else:
        schema['proposal_schemas']=proposal_schemas
    messages=[dict(role='system',content='Ты редактор черновика Character. Верни JSON {"value": ...}. '
        'Только выбранное поле/раздел; соседние поля неизменны. Сохрани character.id. '
        'Никаких изменений мира: связи/места/организации только proposals с approved=false. '
        'newcomer: никаких знакомств по умолчанию. integrated: предложи согласованные связи с реальными ID. '
        'Знания необязательны; не придумывай знание скрытых тайн NPC. Новые тайны только о собственном прошлом. '
        'starting_scene описывает место и обстоятельства без добровольных действий, мыслей и реплик EXTERNAL. '
        'Все тексты на языке активной игры; если язык не задан — русский.'),
        dict(role='user',content=json.dumps(dict(path=path or 'whole_draft',draft=draft,context=context,
            schema=schema,instruction=instruction,language=snapshot.get('campaign',{}).get('campaign',{}).get('language','ru')),ensure_ascii=False))]
    budget=min(config['max_tokens'],12000)
    if estimate(messages)+budget>config['context_length']: raise ValueError('Черновик не помещается в выбранный контекст. Увеличь лимит или выбери отдельное поле.')
    class Accounting:
        def begin_request(self,jid,stage,cfg,msg,diag):
            return repo.begin_request(jid,stage,cfg,msg,diag,save_id=save_id)
        def finish_request(self,*args,**kwargs): return repo.finish_request(*args,**kwargs)
    with model_lease(config['provider']):
        result=''.join(tracked_stream(Accounting(),llm.chat_stream,uuid.uuid4().hex,'character_draft',config,messages,
            model=config['model'],provider=config['provider'],api_key=api_key,temperature=config.get('temperature',0.8),
            max_tokens=budget,require_complete=True,response_format={'type':'json_object'}))
    try:
        decoded=json.loads(result)
        if not isinstance(decoded,dict) or set(decoded)!={'value'}: raise ValueError()
    except (ValueError,TypeError): raise ValueError('Модель вернула некорректный JSON; исходный черновик сохранён.')
    candidate=deepcopy(draft)
    if not parts: candidate=decoded['value']
    else:
        target=candidate
        for part in parts[:-1]: target=target[int(part)] if isinstance(target,list) else target[part]
        target[int(parts[-1]) if isinstance(target,list) else parts[-1]]=decoded['value']
    if not isinstance(candidate,dict) or not isinstance(candidate.get('character'),dict) or candidate['character'].get('id')!=draft.get('character',{}).get('id'):
        raise ValueError('Модель изменила ID; исходный черновик сохранён.')
    from pydantic import ValidationError
    try: CharacterDraft.model_validate(candidate)
    except ValidationError as exc:
        errors=[e for e in exc.errors(include_url=False) if not parts or list(map(str,e['loc']))[:len(parts)]==parts]
        if errors: raise ValueError('; '.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in errors)) from exc
    # Generation may propose data; it can never approve its own proposals.
    for field in ('proposals','knowledge','secrets'):
        if not parts or parts[0]==field:
            records=candidate.get(field,[])
            if parts and len(parts)>1 and parts[1].isdigit(): records=records[int(parts[1]):int(parts[1])+1]
            for record in records: record['approved']=False
    return candidate
