"""Structured preparation using the existing provider, accounting and job lifecycle."""
import json
import time
from backend.services import draft_world as domain
from backend.services.continuation import stream_document
from backend.services.usage import tracked_stream
from llm import OutputLimitReached



def idea_text(repo,job,config):
    instructions=('Исходная идея пользователя (высший приоритет):\n'+config['_draft_input']) if config['_draft_input'].strip() else ''
    if config.get('_use_idea'):
        scenario=repo.workspace(job['workspace_id'])['idea'].strip()
        if not scenario:raise ValueError('Сначала создай сценарий в режиме Сценариста.')
        instructions+='\nСценарная концепция для творческого завершения в полноценный мир:\n'+scenario
    return instructions


def messages_for(repo,job,config):
    task=config['_draft_task'];wid=job['workspace_id']
    if task=='world':
        instructions=idea_text(repo,job,config)
        instructions+='\nРазработай пригодный для немедленной игры мир. Недостающие детали концепции дополни самостоятельно; исходная идея не является исчерпывающей спецификацией.'
        system=config['_prompts']['draft_world_prompt.md']['content']+'\n\nТехнический контракт: верни ровно один завершённый JSON-объект World State v2.'
        return [{'role':'system','content':system},
                {'role':'user','content':instructions}]
    draft=repo.draft(wid,author=True);state=draft['state']
    if not state:raise ValueError('Сначала создай черновик.')
    target=config['_draft_target'];item=domain.entity(state,target['kind'],target['id'])
    system=('Ты редактор RPG. Верни ровно JSON {"value": новое значение}. Никаких других ключей. '
            'Сохрани explicit данные и тип значения. Не изменяй соседние поля, отношения, знания или IDs. '
            'Учитывай пользовательскую инструкцию. Если инструкции нет — предложи новый подходящий вариант.')
    if task=='character':system+=' value содержит только name, aliases, fields карточки. ID и состояние мира неизменны.'
    else:system+=' Изменяется только поле '+target['field']+'.'
    deps=domain.dependencies(state,target['kind'],target['id'])
    related=[state['world'][d['kind']][d['id']] for d in deps if d['kind'] in state['world'] and d['id'] in state['world'][d['kind']]][:15]
    return [{'role':'system','content':system},{'role':'user','content':json.dumps({'campaign':state['campaign'],'entity':item,'related':related,'instruction':config['_draft_input']},ensure_ascii=False)}]


def decode_result(text,state,config):
    try:value=json.loads(text)
    except (TypeError,json.JSONDecodeError) as exc:raise ValueError('Модель вернула незавершённый или некорректный JSON. Предыдущая версия сохранена.') from exc
    if config['_draft_task']=='world':return domain.prepare(value)
    if not isinstance(value,dict) or set(value)!={'value'}:raise ValueError('Для поля разрешён только объект {value: ...}.')
    target=config['_draft_target']
    if config['_draft_task']=='character':
        card=value['value']
        if not isinstance(card,dict) or set(card)!={'name','aliases','fields'}:raise ValueError('Некорректная карточка: разрешены name, aliases, fields.')
        for field,new in card.items():state=domain.patch(state,'character',target['id'],field,new)
        return domain.prepare(state)
    return domain.prepare(domain.patch(state,target['kind'],target['id'],target['field'],value['value']))


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    repo=preparation.repo;job=repo.preparation_job(jid)
    original=repo.draft(job['workspace_id'],author=True)['state'];stage='draft_world'
    context=config['context_length']
    if loaded:context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    # The UI's shared context preference may be only 8K, although the
    # DeepSeek models support much more. Draft creation needs room for both
    # the brief and a complete structured answer.
    if config['_draft_task']=='world' and config['provider']=='deepseek':
        context=max(context,32768)
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    def generate(messages,limit):
        structured = config['provider']=='deepseek' and not any(m['role']=='assistant' for m in messages)
        return tracked_stream(repo,stream_fn,jid,stage,config,messages,model=config['model'],provider=config['provider'],api_key=api_key,
            temperature=config['temperature'],max_tokens=limit,require_complete=True,cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if structured else {}))
    world_task=config['_draft_task']=='world'
    repo.draft_phase(jid,'world' if world_task else 'editing',reset_progress=True)
    messages=messages_for(repo,job,config)
    json_budget=max(config['max_tokens'],min(12000,context//2)) if world_task else config['max_tokens']

    def answer(request,one_request=False):
        result='';last=0.0
        # One finished World State must cost exactly one provider request.
        # Do not use stream_document: it can silently issue continuation calls.
        if one_request:
            from backend.services.continuation import request_context
            request,limit=request_context(request,'',context,json_budget,format_hint='json')
            chunks=generate(request,limit)
        else:
            chunks=stream_document(request,context,json_budget,generate,handle.cancel,format_hint='json')
        try:
            for chunk in chunks:
                if handle.cancel.is_set():return ''
                result+=chunk
                if time.monotonic()-last>.25:
                    repo.preparation_progress(jid,result);last=time.monotonic()
        except OutputLimitReached as exc:
            raise ValueError('Ответ не поместился в лимит модели. Увеличь лимит ответа/контекста и повтори; предыдущая версия сохранена.') from exc
        return result

    def checked(result):
        state=decode_result(result,original,config)
        if world_task:state=domain.repair_scene_interval(state)
        report=domain.validate(state)
        if report['errors']:raise ValueError('; '.join(report['errors']))
        return state,report

    result=answer(messages,one_request=world_task)
    if handle.cancel.is_set():return
    repo.draft_phase(jid,'validating')
    try:state,report=checked(result)
    except ValueError as exc:
        if not world_task:raise
        # A single repair may fix syntax/references; it must preserve the
        # generated content and must not invent any new narrative material.
        stage='draft_world_repair';repo.draft_phase(jid,'retrying',reset_progress=True)
        repair=[{'role':'system','content':
            'Ты исправляешь ТОЛЬКО технические ошибки JSON World State. Верни один JSON-объект. '
            'Сохрани всё содержание ответа: персонажей, описания, тайны, факты, время, связи. '
            'Исправь только синтаксис, типы, отсутствующие структурные поля и битые ID/ссылки. '
            'Не придумывай новых персонажей, событий или деталей мира.'},
            {'role':'user','content':json.dumps({'error':str(exc),'response':result},ensure_ascii=False)}]
        repaired=answer(repair,one_request=True)
        if handle.cancel.is_set():return
        repo.draft_phase(jid,'validating')
        try:state,report=checked(repaired)
        except ValueError as final:
            raise ValueError('Модель вернула некорректный World State JSON: '+str(final)+'. Предыдущая версия сохранена.') from final
    if config['_draft_task']!='world' and report['warnings'] and not config.get('_warnings_ack'):
        raise ValueError('Возможные связанные противоречия: '+'; '.join(report['warnings'])+'. Повтори с явным подтверждением.')
    repo.draft_phase(jid,'saving')
    repo.finish_draft_job(jid,state)
