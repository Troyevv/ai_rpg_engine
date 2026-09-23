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


def completion_messages(state,gaps):
    """Small follow-up only when the generated aggregate omitted playable essentials."""
    world=state['world']
    cards={c['id']:{'name':c['name'],'fields':c['fields'], 'state':world['characters'].get(c['id'],{})} for c in state['characters']}
    brief={'campaign':state.get('campaign',{}),'characters':cards,
           'relationships':{k:{'source_id':v.get('source_id'),'target_id':v.get('target_id'),'context':v.get('context')} for k,v in world['relationships'].items()},
           'threads':world['threads'],'existing_secrets':[
               {'text':v['text'],'owner_id':v.get('owner_id'),'character_ids':v.get('character_ids',[])} for v in world['facts'].values() if v.get('secret')],
           'scene':world['scenes'].get(state.get('camera',{}).get('scene_id'),{}),'gaps':gaps}
    system=('Ты дополняешь уже созданный игровой мир. Верни ТОЛЬКО JSON-объект с нужными ключами: '
            '{"characters":{"id":{"goals":["..."],"intentions":["..."]}},'
            '"secrets":{"id":{"text":"конкретная личная тайна", "about_ids":[], "known_by_ids":[]}},'
            '"relationships":{"существующий ID":"полная осмысленная динамика"},'
            '"new_relationships":[{"source_id":"...","target_id":"...","context":"..."}],'
            '"threads":[{"description":"открытая проблема","state":"текущее положение","character_ids":["..."]}]}. '
            'Заполняй только пункты gaps; незапрошенные ключи можно опустить. Для каждого secret_ids придумай '
            'РАЗНУЮ правдоподобную тайну данного персонажа, не повторяй уже существующую. Тайна известна '
            'самому владельцу; known_by_ids добавляй только при конкретном обосновании. Не выдавай её герою '
            'без события, не переписывай заданные пользователем факты и не навязывай герою новых важных решений. '
            'Для motivation_ids создай конкретную сегодняшнюю цель и намерение, согласованные с характером. '
            'Для shallow_relationship_ids допиши историю, причины и направленный взгляд без принудительного романа. '
            'Создавай сюжетные предпосылки, не предопределённые будущие ходы. Все ID должны существовать.')
    return [{'role':'system','content':system},{'role':'user','content':json.dumps(brief,ensure_ascii=False)}]


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
    if config['_draft_task']=='world':
        state=domain.repair_scene_interval(state)
        gaps=domain.completion_gaps(state)
        if any(gaps.values()):
            stage='draft_world_completion';repo.draft_phase(jid,'completing')
            extra=''
            for chunk in stream_document(completion_messages(state,gaps),context,config['max_tokens'],generate,handle.cancel,format_hint='json'):
                if handle.cancel.is_set():return
                extra+=chunk
            if handle.cancel.is_set():return
            try:state=domain.apply_completion(state,json.loads(extra))
            except (json.JSONDecodeError,TypeError) as exc:raise ValueError('Модель не завершила доработку мира. Предыдущая версия сохранена.') from exc
        # A weak model may ignore some requested fields. Never present such a draft as complete.
        remaining=domain.completion_gaps(state)
        if any(remaining.values()):
            raise ValueError('Модель не заполнила важные части мира (цели, отношения или личные тайны). Попробуй другую модель либо увеличь контекст. Предыдущая версия сохранена.')
    report=domain.validate(state)
    if config['_draft_task']=='world' and report['errors']:
        raise ValueError('Модель создала мир с ошибками: '+'; '.join(report['errors'])+'. Предыдущая версия сохранена.')
    if config['_draft_task']!='world' and report['errors']:raise ValueError('Изменение нарушает структуру: '+'; '.join(report['errors']))
    if config['_draft_task']!='world' and report['warnings'] and not config.get('_warnings_ack'):
        raise ValueError('Возможные связанные противоречия: '+'; '.join(report['warnings'])+'. Повтори с явным подтверждением.')
    repo.preparation_progress(jid,text)
    repo.finish_draft_job(jid,state)
