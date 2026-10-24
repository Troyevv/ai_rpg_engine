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
        instructions+='\nНе выводи пустые технические defaults (dependencies, review_required, reviewed_signature) и производные поля, когда схема позволяет их опустить. Непустые метаданные Motivation, факты, биографии и тайны сохраняй полностью.'
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
    payload={'campaign':state['campaign'],'entity':item,'related':related,'instruction':config['_draft_input']}
    if task=='field' and target['kind']=='actor' and target['field']=='birth_date':
        from backend.runtime_v3.models import Character
        system+=' Для birth_date null можно заменить творчески выбранной датой по схеме, если автор явно просит дополнить поле. Сохрани точный возраст; проверь его на текущую дату мира с учётом anchor и минут. При относительном календаре или приблизительном возрасте не выдумывай точность. Явные ограничения автора приоритетны.'
        payload.update(field_schema=Character.model_json_schema()['properties']['birth_date'],world_clock=state['world_clock'],
                       card=next((c for c in state['characters'] if c['id']==target['id']),None))
    return [{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]


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
    from backend.repositories.drafts import candidate_hash
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
    input_hash=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    binding=dict(job_id=jid,input_hash=input_hash)
    if journal.get('binding',binding)!=binding:raise ValueError('Ответ принадлежит другому заданию или входу.')
    journal['binding']=binding
    # A preflight rejection has no provider outcome to recover, but must retain
    # the original request so Resume can use a larger configured context.
    repo.save_response_journal(jid,journal)
    result=response(repo,jid,journal,'world',messages,config,context,generate,handle.cancel)
    if result is None:return
    result=journal.get('candidate_text',result)
    epoch=journal.get('recovery_epoch',0)
    patch_failure=None
    for attempt in range(3):
        if handle.cancel.is_set():return
        repo.draft_phase(jid,'validating')
        try:
            raw=strict_loads(result)
            if isinstance(raw,dict):raw['creation_settings']=config.get('_creation_settings',{})
            state,report=draft_initial.inspect_candidate(raw)
            errors=report['diagnostics']
            if isinstance(state,dict):
                result=json.dumps(state,ensure_ascii=False)
                journal['candidate_text']=result;repo.save_response_journal(jid,journal)
                repo.save_draft_candidate(jid,state,errors,review=dict(status='not_started',issues=[],contract_version=draft_completeness.CONTRACT_VERSION),epoch=epoch)
        except (ValueError,TypeError,KeyError) as exc:
            errors=exc.errors if isinstance(exc,draft_initial.DraftErrors) else [dict(path='/',category='validation',message=str(exc))]
        if not errors:
            review_meta=dict(status='running',contract_version=draft_completeness.CONTRACT_VERSION,issues=[])
            repo.save_draft_candidate(jid,state,[],review=review_meta,epoch=epoch)
            repo.draft_phase(jid,'reviewing')
            stage='draft_world_validation'
            review_messages=draft_completeness.messages(state,messages[-1]['content'])
            signature=hashlib.sha256(json.dumps(review_messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            review_meta['signature']=signature
            accepted=journal.setdefault('accepted_reviews',{})
            if signature in accepted:
                try:
                    cached=[{k:v for k,v in e.items() if k in ('path','message','related_paths','severity','patch_paths')} for e in accepted[signature]]
                    for e in cached:
                        if not e.get('path'):e['path']=None
                    draft_completeness.parse(json.dumps({'issues':cached}),state)
                except (ValueError,TypeError,KeyError,IndexError,AttributeError):
                    journal.setdefault('invalid_cached_reviews',[]).append(accepted.pop(signature))
            if signature in accepted:
                issues=accepted[signature]
            else:
                previous_failure=next((f for f in reversed(journal.get('review_failures',[])) if f.get('signature')==signature),None)
                if not previous_failure:
                    # Old jobs stored only slot/error; recover the original report from their response journal.
                    for old in reversed(journal.get('review_failures',[])):
                        if 'signature' in old:continue
                        saved=journal.get('responses',{}).get(old.get('slot'),{})
                        rejected=''.join(p['text'] for p in saved.get('parts',[]))
                        if rejected:
                            try:draft_completeness.parse(rejected,state)
                            except draft_completeness.ReportError as exc:
                                previous_failure=dict(response=rejected,validation_errors=exc.errors)
                            break
                # Reparse a completed report locally before spending another request.
                if previous_failure:
                    try:
                        local=draft_completeness.parse(previous_failure['response'],state)
                        if any(e.get('severity')=='blocker' and not e.get('patch_paths') for e in local):raise ValueError('Unlocalized blocker')
                    except (ValueError,TypeError,KeyError,IndexError):pass
                    else:
                        accepted[signature]=local
                        journal.setdefault('review_recoveries',[]).append(dict(signature=signature,result='local_reparse',epoch=epoch))
                        repo.save_response_journal(jid,journal)
                if previous_failure:
                    review_messages=draft_completeness.correction(review_messages,previous_failure['response'],previous_failure['validation_errors'])
                correction_source=previous_failure
                # A malformed report is a failed check, never a bad world or a success.
                for review_attempt in range(0 if signature in accepted else 2):
                    slot='completeness_'+signature if epoch==0 and review_attempt==0 else f'completeness_{signature}_{epoch}_{review_attempt}'
                    try:review=response(repo,jid,journal,slot,review_messages,config,context,generate,handle.cancel)
                    except ValueError as exc:
                        repo.save_draft_candidate(jid,state,[],review=dict(review_meta,status='failed',reason=str(exc)),epoch=epoch)
                        raise
                    if review is None:return
                    provider_review=review;merge_failed=False
                    try:
                        if correction_source:
                            merge_failed=True
                            review=draft_completeness.merge_correction(review,correction_source['response'],correction_source['validation_errors'])
                            merge_failed=False
                        issues=draft_completeness.parse(review,state)
                        unresolved=[dict(report_path=f'/issues/{i}/patch_paths',world_path=e['path'],message='Уточните точные поля для исправления противоречия, сохранив замечание.') for i,e in enumerate(issues) if e.get('severity')=='blocker' and not e.get('patch_paths')]
                        if unresolved:raise draft_completeness.ReportError(unresolved,issues)
                    except (ValueError,TypeError,KeyError,IndexError) as exc:
                        details=getattr(exc,'errors',[dict(report_path='/',world_path=None,message=str(exc))])
                        partial=getattr(exc,'issues',[])
                        failure=dict(candidate_hash=candidate_hash(state),slot=slot,stage=stage,attempt=review_attempt+1,epoch=epoch,signature=signature,contract_version=draft_completeness.CONTRACT_VERSION,response=review,provider_response=provider_review,error=str(exc),validation_errors=details,partial_issues=partial)
                        if merge_failed:
                            failure.update(response=correction_source['response'],validation_errors=correction_source['validation_errors'],correction_format_errors=details,partial_issues=correction_source.get('partial_issues',[]))
                        journal.setdefault('review_failures',[]).append(failure)
                        repo.save_draft_candidate(jid,state,[],review=dict(review_meta,status='failed',reason='Получен отчёт неправильного формата.',issues=partial,validation_errors=details),epoch=epoch)
                        correction_source=failure
                        review_messages=draft_completeness.correction(draft_completeness.messages(state,messages[-1]['content']),failure['response'],failure['validation_errors'])
                        repo.draft_phase(jid,'review_format_repair')
                        repo.save_response_journal(jid,journal)
                        if review_attempt==1 or previous_failure and details==previous_failure.get('validation_errors'):raise ValueError('Проверка не завершена: неверный отчёт. Кандидат доступен автору; Resume повторит только проверку.') from exc
                    else:
                        accepted[signature]=issues
                        journal.setdefault('review_recoveries',[]).append(dict(signature=signature,slot=slot,result='completed',epoch=epoch))
                        repo.save_response_journal(jid,journal);break
            issues=accepted[signature]
            errors=[e for e in issues if e.get('severity','blocker')=='blocker']
            repo.save_draft_candidate(jid,state,errors,review=dict(review_meta,status='completed',issues=issues),epoch=epoch)
            if not errors:break
            result=json.dumps(state,ensure_ascii=False)
        journal['errors']=errors;repo.save_response_journal(jid,journal)
        if attempt==2:raise ValueError('Две попытки исправления исчерпаны. Ответ сохранён. '+str(errors))
        repair,paths=draft_repair.request(result,errors,author_context=messages[-1]['content'])
        if patch_failure:repair.append(dict(role='user',content=json.dumps(patch_failure,ensure_ascii=False)))
        repo.draft_phase(jid,'retrying');stage='draft_world_repair'
        slot='repair_'+str(attempt+1)+(f'_resume_{epoch}' if epoch else '')
        reply=response(repo,jid,journal,slot,repair,config,context,generate,handle.cancel)
        if reply is None:return
        try:
            result=draft_repair.apply(result,reply,paths)
            journal['candidate_text']=result;repo.save_response_journal(jid,journal)
        except ValueError as invalid_patch:
            patch_failure=dict(rejected_response=reply,error=str(invalid_patch),instruction='Исправь формат patch, сохрани требуемые исправления и разрешённые пути.')
            journal.setdefault('repair_failures',[]).append(dict(slot=slot,**patch_failure))
            repo.save_response_journal(jid,journal)
            if attempt==1:raise ValueError('Две попытки исправления исчерпаны. '+str(invalid_patch)) from invalid_patch

    if handle.cancel.is_set():return
    repo.draft_phase(jid,'saving');repo.finish_draft_job(jid,state,epoch=epoch)
