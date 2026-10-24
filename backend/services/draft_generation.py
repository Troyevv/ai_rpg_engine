"""Structured preparation using the existing provider, accounting and job lifecycle."""
import json
import hashlib
from backend.services import draft_world as domain
from backend.services.continuation import stream_document
from backend.services.usage import tracked_stream



def idea_text(repo,job,config):
    if '_draft_source' in config:
        if not config['_draft_source'].strip():raise ValueError('Опиши мир или сначала создай сценарий.')
        return 'Исходная идея пользователя (высший приоритет):\n'+config['_draft_source']
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
        from backend.services.world_creation_settings import CreationSettings
        settings=CreationSettings.model_validate(config.get('_creation_settings',{}))
        instructions+='\nНастройки мира (не переопределяют явные факты идеи): '+json.dumps(settings.model_dump(),ensure_ascii=False)
        instructions+='\nЦелевой состав NPC: '+json.dumps(settings.cast_targets([]),ensure_ascii=False)
        instructions+='\nЧисла NPC — ориентир, не квота. Именованные NPC входят в состав. Выразительность меняет подачу, а не характер. Темп и риск не создают предысторию.'
        instructions+='\nРазработай пригодный для немедленной игры мир. Недостающие детали концепции дополни самостоятельно; исходная идея не является исчерпывающей спецификацией.'
        from backend.services.draft_initial import prompt_schema
        system=(config['_prompts']['draft_world_prompt.md']['content']
                +'\n\nКаноническая JSON Schema WorldState для ПЕРВОНАЧАЛЬНОЙ генерации (не заполняй саму схему; верни объект по ней):\n'
                +json.dumps(prompt_schema(),ensure_ascii=False,separators=(',',':')))
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
    from backend.services.draft_response import response, strict_loads
    from backend.services import draft_initial, draft_repair, draft_completeness
    repo=preparation.repo;job=repo.preparation_job(jid)
    original=repo.draft(job['workspace_id'],author=True)['state']
    context=config['context_length']
    if loaded: context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    stage='draft_world'
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    def generate(messages,limit):
        structured=config['provider']=='deepseek' and not any(m['role']=='assistant' for m in messages)
        return tracked_stream(repo,stream_fn,jid,stage,config,messages,model=config['model'],provider=config['provider'],api_key=api_key,
            temperature=config['temperature'],max_tokens=limit,require_complete=True,cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if structured else {}))
    if config['_draft_task']!='world':
        repo.draft_phase(jid,'editing',reset_progress=True)
        result=''
        for chunk in stream_document(messages_for(repo,job,config),context,config['max_tokens'],generate,handle.cancel,format_hint='json'):
            result+=chunk;repo.preparation_progress(jid,result)
        if handle.cancel.is_set():return
        state=decode_result(result,original,config);report=domain.validate(state)
        if report['errors']:raise ValueError('; '.join(report['errors']))
        if report['warnings'] and not config.get('_warnings_ack'):raise ValueError('; '.join(report['warnings']))
        repo.finish_draft_job(jid,state);return
    journal=json.loads(job.get('response_journal') or '{}')
    repo.draft_phase(jid,'world')
    messages=journal.setdefault('messages',messages_for(repo,job,config))
    result=response(repo,jid,journal,'world',messages,config,context,generate,handle.cancel)
    if result is None:return
    result=journal.get('candidate_text',result)
    epoch=journal.get('recovery_epoch',0)
    for attempt in range(3):
        if handle.cancel.is_set():return
        repo.draft_phase(jid,'validating')
        try:
            raw=strict_loads(result)
            state,report=draft_initial.inspect_candidate(raw)
            errors=report['diagnostics']
            if isinstance(state,dict):
                result=json.dumps(state,ensure_ascii=False)
                journal['candidate_text']=result;repo.save_response_journal(jid,journal)
                repo.save_draft_candidate(jid,state,errors)
        except (ValueError,TypeError,KeyError) as exc:
            errors=exc.errors if isinstance(exc,draft_initial.DraftErrors) else [dict(path='/',category='validation',message=str(exc))]
        if not errors:
            repo.save_draft_candidate(jid,state,[dict(path='/',category='review_incomplete',message='Смысловая проверка не завершена.')])
            state['creation_settings']=config.get('_creation_settings',{})
            stage='draft_world_validation'
            review_messages=draft_completeness.messages(state,messages[-1]['content'])
            signature=hashlib.sha256(json.dumps(review_messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            accepted=journal.setdefault('accepted_reviews',{})
            if signature in accepted:
                try:
                    cached=[{k:v for k,v in e.items() if k in ('path','message','related_paths','severity')} for e in accepted[signature]]
                    draft_completeness.parse(json.dumps({'issues':cached}),state)
                except (ValueError,TypeError,KeyError,IndexError,AttributeError):
                    journal.setdefault('invalid_cached_reviews',[]).append(accepted.pop(signature))
            if signature in accepted:
                issues=accepted[signature]
            else:
                # A malformed report is a failed check, never a bad world or a success.
                for review_attempt in range(2):
                    slot='completeness_'+signature if epoch==0 and review_attempt==0 else f'completeness_{signature}_{epoch}_{review_attempt}'
                    review=response(repo,jid,journal,slot,review_messages,config,context,generate,handle.cancel)
                    if review is None:return
                    try:issues=draft_completeness.parse(review,state)
                    except (ValueError,TypeError,KeyError,IndexError) as exc:
                        journal.setdefault('review_failures',[]).append(dict(slot=slot,error=str(exc)))
                        repo.save_response_journal(jid,journal)
                        if review_attempt==1:raise ValueError('Проверка не завершена: неверный отчёт. Кандидат доступен автору; Resume повторит только проверку.') from exc
                    else:
                        accepted[signature]=issues;repo.save_response_journal(jid,journal);break
            errors=[e for e in issues if e.get('severity','blocker')=='blocker']
            repo.save_draft_candidate(jid,state,errors)
            if not errors:break
            result=json.dumps(state,ensure_ascii=False)
        journal['errors']=errors;repo.save_response_journal(jid,journal)
        if attempt==2:raise ValueError('Две попытки исправления исчерпаны. Ответ сохранён. '+str(errors))
        repair,paths=draft_repair.request(result,errors,author_context=messages[-1]['content'])
        repo.draft_phase(jid,'retrying');stage='draft_world_repair'
        slot='repair_'+str(attempt+1)+(f'_resume_{epoch}' if epoch else '')
        reply=response(repo,jid,journal,slot,repair,config,context,generate,handle.cancel)
        if reply is None:return
        try:
            result=draft_repair.apply(result,reply,paths)
            journal['candidate_text']=result;repo.save_response_journal(jid,journal)
        except ValueError as invalid_patch:
            journal.setdefault('repair_failures',[]).append(dict(slot=slot,error=str(invalid_patch)))
            repo.save_response_journal(jid,journal)
            if attempt==1:raise ValueError('Две попытки исправления исчерпаны. '+str(invalid_patch)) from invalid_patch

    if handle.cancel.is_set():return
    repo.draft_phase(jid,'saving');repo.finish_draft_job(jid,state)
