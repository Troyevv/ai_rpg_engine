"""Structured preparation using the existing provider, accounting and job lifecycle."""
import json
import time
from backend.services import draft_world as domain
from backend.services.continuation import stream_document
from backend.services.usage import tracked_stream


def messages_for(repo,job,config):
    task=config['_draft_task'];wid=job['workspace_id']
    if task=='world':
        instructions=('Исходная идея пользователя (высший приоритет):\n'+config['_draft_input']) if config['_draft_input'].strip() else ''
        if config.get('_use_idea'):
            scenario=repo.workspace(wid)['idea'].strip()
            if not scenario:raise ValueError('Сначала создай сценарий в режиме Сценариста.')
            instructions+='\nСценарная концепция для творческого завершения в полноценный мир:\n'+scenario
        instructions+='\nРазработай пригодный для немедленной игры мир. Недостающие детали концепции дополни обоснованно; не считай её исчерпывающей спецификацией.'
        return [{'role':'system','content':config['_prompts']['draft_world_prompt.md']['content']},
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
    original=repo.draft(job['workspace_id'],author=True)['state'];text='';last=0.0;stage='draft_world'
    context=config['context_length']
    if loaded:context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    def generate(messages,limit):
        return tracked_stream(repo,stream_fn,jid,stage,config,messages,model=config['model'],provider=config['provider'],api_key=api_key,
            temperature=config['temperature'],max_tokens=limit,require_complete=True,cancel_event=handle.cancel,on_stream=opened)
    repo.draft_phase(jid,'world' if config['_draft_task']=='world' else 'editing')
    messages=messages_for(repo,job,config)
    last=0.0
    for chunk in stream_document(messages,context,config['max_tokens'],generate,handle.cancel,format_hint='json'):
        if handle.cancel.is_set():return
        text+=chunk
        if time.monotonic()-last>.1:repo.preparation_progress(jid,text);last=time.monotonic()
    if handle.cancel.is_set():return
    state=decode_result(text,original,config)
    report=domain.validate(state)
    if config['_draft_task']!='world' and report['errors']:raise ValueError('Изменение нарушает структуру: '+'; '.join(report['errors']))
    if config['_draft_task']!='world' and report['warnings'] and not config.get('_warnings_ack'):
        raise ValueError('Возможные связанные противоречия: '+'; '.join(report['warnings'])+'. Повтори с явным подтверждением.')
    repo.preparation_progress(jid,text)
    repo.finish_draft_job(jid,state)
