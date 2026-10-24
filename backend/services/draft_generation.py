"""Structured preparation using the existing provider, accounting and job lifecycle."""
import json
import time
from backend.services import draft_world as domain
from backend.services.continuation import stream_document
from backend.services.usage import tracked_stream
from backend.services.draft_schema import world_state_schema
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
        system=(config['_prompts']['draft_world_prompt.md']['content']
                +'\n\nКаноническая JSON Schema WorldState для ПЕРВОНАЧАЛЬНОЙ генерации (не заполняй саму схему; верни объект по ней):\n'
                +json.dumps(world_state_schema(),ensure_ascii=False,separators=(',',':')))
        return [{'role':'system','content':system},
                {'role':'user','content':instructions}]
    draft=repo.draft(wid,author=True);state=draft['state']
    if not state:raise ValueError('Сначала создай черновик.')
    target=config['_draft_target'];item=domain.entity(state,target['kind'],target['id'])
    system=('Ты редактор RPG. Верни ровно JSON {"value": новое значение}. Никаких других ключей. '
            'Сохрани explicit данные и тип значения. Не изменяй соседние поля, отношения, знания или IDs. '
            'Учитывай пользовательскую инструкцию. Если инструкции нет — предложи новый подходящий вариант.')
    if task=='character':
        from backend.services.world import CARD_FIELDS
        system+=(' value содержит только name, aliases, fields карточки. В fields верни все постоянные поля: '
                 +', '.join(CARD_FIELDS)+'. Стиль общения должен быть пригоден для написания узнаваемых реплик. '
                 'Сохрани дополнительные поля карточки, если они есть. ID и динамическое состояние мира неизменны.')
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
        from backend.services.world import CARD_FIELDS
        if not isinstance(card['fields'],dict) or not set(CARD_FIELDS)<=card['fields'].keys():
            raise ValueError('Перегенерация должна вернуть все постоянные поля карточки.')
        for field,new in card.items():state=domain.patch(state,'character',target['id'],field,new)
        return domain.prepare(state)
    return domain.prepare(domain.patch(state,target['kind'],target['id'],target['field'],value['value']))


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    if config['_draft_task']=='world_staged':
        from backend.services.world_generation import run as generate_staged
        return generate_staged(preparation,jid,config,api_key,handle,loaded,stream_fn)
    if config['_draft_task']=='interpret':
        from backend.services.world_interpretation import run as interpret
        return interpret(preparation,jid,config,api_key,handle,loaded,stream_fn)
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


# The normal creation path follows master's single-response contract. The
# existing durable executor owns transport, leases, cancellation and accounting.
SINGLE_VERSION = 'world-single-1'


def compact_schema(value):
    """Remove annotation noise, never validation keywords or domain fields."""
    if isinstance(value, dict):
        return {k: ({name: compact_schema(schema) for name, schema in v.items()}
                    if k in ('properties', '$defs') else compact_schema(v))
                for k, v in value.items() if k not in ('title', 'default')}
    if isinstance(value, list):
        return [compact_schema(v) for v in value]
    return value


def request_budget(messages, ceiling, context):
    from context_builder import estimate
    from backend.services.author_budget import MARGIN
    from backend.services.world_authoring_compiler import CompileError
    available = min(ceiling, context - estimate(messages) - MARGIN)
    if available < 1024:
        raise CompileError('author/request/world',
            f'Полный исходник и схема не оставляют места для мира: вход ≈{estimate(messages)}, '
            f'контекст {context}, лимит ответа {ceiling}, доступно {max(0, available)} токенов.',
            'Запрос не отправлен. Увеличьте доступный контекст/ответ в пределах модели. Исходник не обрезан.')
    return available


def capture_world(brief, config):
    from backend.services import world_authoring as a, author_budget as b
    from backend.services.world_creation_settings import CreationSettings
    # Generated from the same author model accepted by the compiler/editor.
    prompt = dict(version=SINGLE_VERSION, budget_version=1,
        rules=a.AUTHOR_RULES.replace('its analysis\nand creation settings', 'creation settings') +
        '\nReturn ONE complete world, not a plan. Populate meaningful character biographies, appearance, personality and voice. '
        'Use creation settings for genre, geography, cast and presentation. Explicit named characters always survive cast targets. '
        'Omit unused optional fields. The original idea is authoritative. A parental marriage plan is not a marriage or consent. '
        'Resolve knowledge chronologically: a discovery yesterday changes only its supported holders. '
        'Opening time uses clock plus date or weekday (Monday=0). Never infer exact birth dates from age.',
        schemas={'author_document':compact_schema(a.Document.model_json_schema())})
    creation=CreationSettings.model_validate(config.get('_creation', {})).model_dump()
    inputs=dict(brief=brief, constraint_revision=1, creation=creation, prompt=prompt)
    context,ceiling,_=b.limits(config)
    request_budget(b.messages(prompt,'author_document',world_request(inputs)),ceiling,context)
    return inputs


def world_request(inputs):
    from backend.services.world_creation_settings import CreationSettings
    return dict(original_source=inputs['brief'], creation_settings=inputs['creation'],
        cast_targets=CreationSettings.model_validate(inputs['creation']).cast_targets([]))


def technical_report(exc):
    """Private structured repair evidence; never echo raw model input publicly."""
    from pydantic import ValidationError
    current=exc
    while current is not None:
        if isinstance(current, ValidationError):
            return [dict(path='/'+'/'.join(map(str,e['loc'])), reason=e['type'],
                expected=e['msg'], allowed=str(e.get('ctx',{})))
                for e in current.errors(include_input=False,include_url=False)]
        if isinstance(current, json.JSONDecodeError):
            return [dict(path='/',reason='json_syntax',expected='One complete JSON object',
                line=current.lineno,column=current.colno)]
        current=current.__cause__
    diagnostic=getattr(exc,'diagnostic',None)
    if isinstance(diagnostic,dict):
        return [dict(path='/'+diagnostic['path'].removeprefix('author_document/'),
            reason=diagnostic['reason'],expected=diagnostic['action'])]
    return [dict(path='/',reason=str(exc),expected='Canonical Runtime invariants; preserve unrelated data')]


def preserve_unaffected(before, after, report):
    """A technical repair cannot silently rewrite already valid creative fields."""
    from backend.services.world_authoring_compiler import CompileError
    paths=[r['path'].strip('/').split('/') for r in report]
    if any(p==[''] for p in paths):
        raise CompileError('repair/scope', 'Нельзя безопасно локализовать правку; исходный результат сохранён.')
    def allowed(path):
        return any(path[:len(p)]==p for p in paths)
    def walk(left,right,path):
        if allowed(path):return
        if type(left) is not type(right):
            raise CompileError('/'.join(path),'Техническая правка изменила корректные данные.')
        if isinstance(left,dict):
            for key in left.keys() | right.keys():
                if allowed(path+[key]):continue
                if key not in left or key not in right:
                    raise CompileError('/'.join(path+[key]),'Техническая правка добавила или удалила корректное поле.')
                walk(left[key],right[key],path+[key])
        elif isinstance(left,list):
            if len(left)!=len(right):
                raise CompileError('/'.join(path),'Техническая правка изменила состав записей.')
            for i,(l,r) in enumerate(zip(left,right)):
                # Compiler diagnostics address records by key; DTO errors by index.
                key=l.get('key',str(i)) if isinstance(l,dict) else str(i)
                child=path+[str(i)] if any(p[:len(path)+1]==path+[str(i)] for p in paths) else path+[key]
                walk(l,r,child)
        elif left!=right:
            raise CompileError('/'.join(path),'Техническая правка изменила корректное значение.')
    walk(before,after,[])


def run_world(repo,jid,token,inputs,request,execute):
    from backend.services import world_authoring as a
    from backend.services.world_authoring_compiler import compile_document
    from backend.services.world_authoring_pipeline import compiled_hash
    def unit(name,dependencies,outputs):
        return dict(id=name,stage=name,inputs=dependencies,outputs=outputs)
    repo.plan_generation_units(jid,token,[
        unit('author_document',['brief','creation','prompt'],{'author_document':''}),
        unit('compile',['author_document','creation','brief'],{'assembled':'/snapshot','author_compilation':''})])
    previous=None;report=None
    cp=repo.inspect_generation_checkpoint(jid,'author_document',True)
    diagnostic=cp.get('diagnostic',{})
    if diagnostic.get('category')=='technical_repair':
        try:previous=json.loads(diagnostic['raw_response']);report=diagnostic['report']
        except (ValueError,TypeError):pass
    def validate(raw):
        nonlocal previous,report
        if previous is not None:
            try:preserve_unaffected(previous,raw,report)
            except ValueError as exc:
                raise RuntimeError('stage/author_document: repair changed valid content; original result retained') from exc
        try:
            # DTO, reference, family, knowledge, temporal and canonical checks
            # all happen before the document can become a completed checkpoint.
            value=a.Document.model_validate(raw).model_dump()
            compile_document(value,creation=inputs['creation'])
        except ValueError as exc:
            # Preserve the original repair basis if a reply rewrote good fields.
            previous=raw
            report=technical_report(exc)
            raise
        return value
    execute('author_document',lambda:request('author_document',world_request(inputs),a.Document),validate)
    def compile_current():
        document=repo.generation_resources(jid,['author_document'])['author_document']
        result=compile_document(document,creation=inputs['creation'])
        snapshot=result.snapshot
        snapshot['campaign']['initial_world']=dict(version=a.VERSION,brief=inputs['brief'],
            analysis={'entities':[],'observations':[],'ambiguities':[]},source_document=document,
            id_map=result.id_map,compiled_hash=compiled_hash(snapshot),diagnostics=result.diagnostics)
        return dict(snapshot=snapshot,id_map=result.id_map,diagnostics=result.diagnostics,
            transformations=result.transformations)
    execute('compile',compile_current,lambda v:v)
    if repo.generation_boundary(jid,token):
        repo.publish_generation_draft(jid,token,repo.generation_resources(jid,['assembled'])['assembled'])
