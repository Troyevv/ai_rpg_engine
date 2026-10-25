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
        instructions+='\nНастройки мира (явные поля календаря/начала приоритетны над идеей; остальные не переопределяют факты идеи): '+json.dumps(settings.model_dump(),ensure_ascii=False)
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


def review_signature(messages, config):
    from backend.services.draft_completeness import CONTRACT_VERSION, RECOVERY_POLICY
    return hashlib.sha256(json.dumps([messages,CONTRACT_VERSION,RECOVERY_POLICY,{k:config.get(k) for k in ('provider','model','max_tokens','context_length')}],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


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
    if 'generation_contract' not in journal:
        from pathlib import Path
        bundled=(Path(__file__).resolve().parents[2]/'prompts/draft_world_prompt.md').read_text()
        journal['generation_contract']={'version':'legacy' if journal.get('messages') or journal.get('responses') else 5,
            'prompt_contract':'bundled' if config['_prompts']['draft_world_prompt.md']['content']==bundled else 'custom_unverified',
            'prompt_sha256':hashlib.sha256(config['_prompts']['draft_world_prompt.md']['content'].encode()).hexdigest()}
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
    recovered_candidate='candidate_text' in journal
    result=journal.get('candidate_text',result)
    epoch=journal.get('recovery_epoch',0)
    patch_failure=None
    for attempt in range(3):
        if handle.cancel.is_set():return
        repo.draft_phase(jid,'validating')
        try:
            raw=strict_loads(result)
            if isinstance(raw,dict):
                if not recovered_candidate:
                    raw['creation_settings']=config.get('_creation_settings',{})
                    raw.pop('authoring',None)  # Model cannot mint server provenance.
                    actors=raw.get('world',{}).get('characters',{}) if isinstance(raw.get('world'),dict) else {}
                    for actor in (actors.values() if isinstance(actors,dict) else []):
                        if isinstance(actor,dict) and isinstance(actor.get('birth_provenance'),dict) and actor['birth_provenance'].get('source') in ('manual','authoring_automatic'):
                            actor['birth_provenance'].pop('source')
                    from backend.services.draft_intake import motivations
                    raw=motivations(raw)
                else:raw.setdefault('creation_settings',config.get('_creation_settings',{}))
                from backend.services.draft_calendar import complete
                raw=complete(raw, config.get('_draft_source',config.get('_draft_input','')), seed=jid)
                if not recovered_candidate:
                    schedules=raw.get('world',{}).get('scheduled_events',{}) if isinstance(raw.get('world'),dict) else {}
                    for event in (schedules.values() if isinstance(schedules,dict) else []):
                        if isinstance(event,dict):
                            event['time_semantics']='explicit'
                            if event.get('time_reference_minute') is None:event['time_reference_minute']=raw['world_clock']['minute']
            state,report=draft_initial.inspect_candidate(raw)
            errors=report['diagnostics']
            if isinstance(state,dict):
                result=json.dumps(state,ensure_ascii=False)
                recovered_candidate=True
                journal['candidate_text']=result;repo.save_response_journal(jid,journal)
                if not patch_failure:repo.save_draft_candidate(jid,state,errors,review=dict(status='not_started',issues=[],contract_version=draft_completeness.CONTRACT_VERSION),epoch=epoch)
        except (ValueError,TypeError,KeyError) as exc:
            errors=exc.errors if isinstance(exc,draft_initial.DraftErrors) else [dict(path='/',category='validation',message=str(exc))]
            if any(e.get('category')=='player_agency' for e in errors):
                journal['candidate_text']=json.dumps(raw,ensure_ascii=False)
                repo.save_response_journal(jid,journal)
                repo.save_draft_candidate(jid,raw,errors,review=dict(status='not_started',issues=[]),epoch=epoch)
        if not errors:
            review_meta=dict(status='running',contract_version=draft_completeness.CONTRACT_VERSION,issues=[])
            if not patch_failure:repo.save_draft_candidate(jid,state,[],review=review_meta,epoch=epoch)
            repo.draft_phase(jid,'reviewing')
            stage='draft_world_validation'
            review_messages=draft_completeness.messages(state,messages[-1]['content'])
            signature=review_signature(review_messages,config)
            review_meta['signature']=signature
            from backend.services.draft_review_recovery import obtain
            def review_call(slot, request_messages):
                return response(repo,jid,journal,slot,request_messages,config,context,generate,handle.cancel)
            try:
                issues=obtain(state,review_messages,signature,journal,review_call,lambda:repo.save_response_journal(jid,journal))
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                partial=journal.get('review_failures',[{}])[-1].get('partial_issues',[]) if journal.get('review_failures') else []
                repo.save_draft_candidate(jid,state,[],review=dict(review_meta,status='failed',reason=str(exc),issues=partial),epoch=epoch)
                raise
            if issues is None:return
            errors=[e for e in issues if e.get('severity','blocker')=='blocker']
            if not patch_failure:repo.save_draft_candidate(jid,state,errors,review=dict(review_meta,status='completed',issues=issues),epoch=epoch)
            if not errors:break
            result=json.dumps(state,ensure_ascii=False)
        journal['errors']=errors;repo.save_response_journal(jid,journal)
        if attempt==2:raise ValueError('Две попытки исправления исчерпаны. Ответ сохранён. '+str(errors))
        repair,paths=draft_repair.request(result,errors,author_context=messages[-1]['content'])
        if patch_failure:repair.append(dict(role='user',content=json.dumps(patch_failure,ensure_ascii=False)))
        repo.draft_phase(jid,'retrying');stage='draft_world_repair'
        repair_input_hash=hashlib.sha256(result.encode()).hexdigest()
        repair_signature=hashlib.sha256(json.dumps([draft_completeness.CONTRACT_VERSION,repair_input_hash,repair],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        slot=f'repair_{repair_signature}_{epoch}_{attempt}'
        if any(item.get('input_hash')==repair_input_hash and item.get('contract_version')==draft_completeness.CONTRACT_VERSION and item.get('policy')==draft_completeness.RECOVERY_POLICY for item in journal.get('no_progress',[])):
            raise ValueError('Автоматическое исправление не дало прогресса. Кандидат сохранён; стратегия для текущей версии исчерпана.')
        reply=response(repo,jid,journal,slot,repair,config,context,generate,handle.cancel)
        if reply is None:return
        try:
            updated=draft_repair.apply(result,reply,paths)
            if paths is not None and strict_loads(updated)==strict_loads(result):
                journal.setdefault('no_progress',[]).append(dict(input_hash=repair_input_hash,slot=slot))
                repo.save_response_journal(jid,journal)
                raise draft_repair.NoProgress('Исправление не изменило кандидат. Повтор одинакового запроса остановлен.')
            history=journal.setdefault('repair_progress',{})
            from backend.services.draft_completeness import pointer
            if paths is not None:
                old_value=strict_loads(result);new_value=strict_loads(updated)
                changes=[]
                for path in paths:
                    def fingerprint(value):
                        try:item=pointer(value,path)
                        except (KeyError,IndexError,TypeError):return '<missing>'
                        if isinstance(item,str):item=' '.join(item.split())
                        return json.dumps(item,sort_keys=True,ensure_ascii=False)
                    before,after=fingerprint(old_value),fingerprint(new_value)
                    if before==after:continue
                    key=path
                    prior=history.get(key) or next((v for k,v in history.items() if k.endswith(':'+path)),[before])
                    if after in prior:raise draft_repair.NoProgress('Цикл значений '+path+'; последний принятый кандидат сохранён.')
                    changes.append((key,prior+[after]))
                if not changes:raise draft_repair.NoProgress('Исправление изменило только оформление; содержательного прогресса нет.')
                for key,values in changes:history[key]=values
            result=updated
            patch_failure=None
            journal['candidate_text']=result;repo.save_response_journal(jid,journal)
        except draft_repair.NoProgress as exc:
            if attempt==0:
                patch_failure=dict(rejected_response=reply,error=str(exc),instruction='Предыдущий пакет не дал содержательного прогресса. Исправь именно диагностированное противоречие в прежнем scope; косметические изменения не подходят.')
                journal.setdefault('repair_failures',[]).append(dict(slot=slot,**patch_failure))
                repo.save_response_journal(jid,journal)
                continue
            journal.setdefault('no_progress',[]).append(dict(input_hash=repair_input_hash,slot=slot,contract_version=draft_completeness.CONTRACT_VERSION,policy=draft_completeness.RECOVERY_POLICY))
            repo.save_response_journal(jid,journal)
            raise
        except ValueError as invalid_patch:
            patch_failure=dict(rejected_response=reply,error=str(invalid_patch),instruction='Исправь формат patch, сохрани требуемые исправления и разрешённые пути.')
            if isinstance(invalid_patch,draft_repair.RejectedTrial):patch_failure['trial']=invalid_patch.details
            journal.setdefault('repair_failures',[]).append(dict(slot=slot,**patch_failure))
            repo.save_response_journal(jid,journal)
            if attempt==1:raise ValueError('Две попытки исправления исчерпаны. '+str(invalid_patch)) from invalid_patch

    if handle.cancel.is_set():return
    from backend.services import draft_quality
    def quality_call(slot, request_messages, request_stage):
        nonlocal stage
        stage=request_stage
        repo.draft_phase(jid,'improving' if request_stage=='draft_world_quality' else 'reviewing')
        return response(repo,jid,journal,slot,request_messages,config,context,generate,handle.cancel)
    enhanced, quality_issues=draft_quality.complete(state,issues,messages[-1]['content'],journal,quality_call)
    if handle.cancel.is_set():
        repo.save_response_journal(jid,journal);return
    if quality_issues is not None:
        state,report=draft_initial.inspect_candidate(enhanced)
        journal['candidate_text']=json.dumps(state,ensure_ascii=False)
        signature=review_signature(draft_completeness.messages(state,messages[-1]['content']),config)
        journal.setdefault('accepted_reviews',{})[signature]=quality_issues
        review_meta['signature']=signature
        repo.save_draft_candidate(jid,state,[],review=dict(review_meta,status='completed',issues=quality_issues),epoch=epoch)
    repo.save_response_journal(jid,journal)
    repo.draft_phase(jid,'saving');repo.finish_draft_job(jid,state,epoch=epoch)
