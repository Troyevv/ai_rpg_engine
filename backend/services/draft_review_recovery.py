"""Finite review recovery over persisted response slots; no epoch-based allowance."""
import json
from backend.services import draft_completeness as review
from backend.services.draft_protocol import Reaudit, ProtocolError, decode, reject
from backend.services.draft_response import strict_loads


def alternate(messages, previous, errors):
    payload=json.loads(messages[1]['content'])
    try:items=strict_loads(previous)['issues']
    except (ValueError,KeyError,TypeError):items=[]
    if not isinstance(items,list):items=[]
    pending=[dict(issue_id=review.issue_identity(item),issue=item) for item in items]
    payload.update(strategy='scoped_reaudit',pending_issues=pending,validation_errors=errors,
        instruction='Проверь заново только нерешённые замечания по исходному миру и авторскому контексту. Не исправляй мир. Для КАЖДОГО issue_id верни resolution: replaced, disproved или unresolved, reason и basis:[{path}]. При replaced верни непустой issues со всеми отдельными типизированными замечаниями. При disproved нужны конкретные основания из мира, а не отсутствие ошибки JSON. Пустой ответ не завершает аудит.',
        response_contract={'resolutions':[{'issue_id':'из pending_issues','resolution':'replaced|disproved|unresolved','reason':'обоснование','basis':[{'path':'существующий адрес'}],'issues':[]}]})
    if not pending:payload['instruction']='Предыдущий отчёт не имеет разбираемой структуры. Проведи полный аудит сохранённого кандидата по исходным требованиям; верни issues по report_schema. Мир не изменяй.'
    payload['response_schema']=reaudit_schema() if pending else review.report_schema()
    payload.pop('report_schema',None)
    payload.pop('example',None)
    return [dict(role='system',content=review.MARKER+' Повторный аудит. Следуй response_schema и разреши прежние замечания явно; не меняй мир.'),dict(role='user',content=json.dumps(payload,ensure_ascii=False,separators=(',',':')))]


def parse_alternate(reply, previous, state, errors=None):
    from backend.services.draft_response import strict_loads
    payload=strict_loads(reply)
    try:prior=strict_loads(previous)
    except ValueError:prior={}
    items=prior.get('issues',[]) if isinstance(prior,dict) else []
    if not isinstance(items,list):items=[]
    # Syntactically valid claims can still be semantically wrong. A re-audit
    # must resolve every claim explicitly; it may not silently drop siblings.
    expected={review.issue_identity(item):item for item in items}
    if not expected and isinstance(payload,dict) and 'issues' in payload:return review.parse(reply,state),[]
    rows=decode(Reaudit,reply,'reaudit').model_dump()['resolutions']
    if len(rows)!=len(expected):reject('reaudit','/resolutions','Нужно разрешить каждое прежнее замечание.')
    seen=set();result=[];decisions=[]
    for index,row in enumerate(rows):
        ident=row.get('issue_id') if isinstance(row,dict) else None
        if ident not in expected or ident in seen:reject('reaudit',f'/resolutions/{index}/issue_id','Неизвестный или повторный issue_id.')
        seen.add(ident)
        if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('Нет основания решения аудита.')
        if row.get('resolution')=='replaced':
            if not isinstance(row.get('issues'),list) or not row['issues']:raise ValueError('Замена не может быть пустой.')
            result.extend(row['issues'])
        elif row.get('resolution')=='disproved':
            basis=row.get('basis')
            if not isinstance(basis,list) or not basis:raise ValueError('Опровержению нужны основания.')
            for item in basis:
                if not isinstance(item,dict) or set(item)!={'path'}:raise ValueError('Основание должно ссылаться на кандидат.')
                try:review.pointer(state,item['path'])
                except (ValueError,KeyError,IndexError,TypeError) as exc:reject('reaudit',f'/resolutions/{index}/basis',str(exc))
        else:reject('reaudit',f'/resolutions/{index}/resolution','Аудит сохранил нерешённое обязательное замечание.')
        decisions.append(row)
    return review.parse(json.dumps({'issues':result},ensure_ascii=False),state),decisions


def obtain(state, messages, signature, journal, call, persist):
    from backend.repositories.drafts import candidate_hash
    accepted=journal.setdefault('accepted_reviews',{})
    if signature in accepted:return accepted[signature]
    attempts=journal.setdefault('review_strategies',{}).setdefault(signature,{})
    if attempts.get('exhausted'):raise ValueError('Автоматические стратегии проверки исчерпаны; нужен доступный проверяющий или новая версия контракта. Правильный мир менять не требуется.')
    failures=journal.setdefault('review_failures',[])
    # A contract upgrade may reuse historical bytes, never a stale stop flag.
    previous=next((f for f in reversed(failures) if f.get('signature')==signature),None)
    historical=False
    if previous is None and not attempts:
        from backend.repositories.drafts import candidate_hash
        for old in reversed(failures):
            if old.get('candidate_hash') and old['candidate_hash']!=candidate_hash(state):continue
            saved=journal.get('responses',{}).get(old.get('slot'),{})
            raw=old.get('response') or ''.join(p['text'] for p in saved.get('parts',[]))
            if not raw:continue
            try:review.parse(raw,state)
            except review.ReportError as exc:
                previous=dict(old,response=raw,validation_errors=exc.errors,partial_issues=exc.issues);historical=True
                break

    original=messages
    if previous and not historical:
        try:
            checked=review.parse(previous['response'],state)
            if any(e.get('severity')=='blocker' and not e.get('patch_paths') and not e.get('remove_paths') for e in checked):raise ValueError('Unlocalized blocker')
        except ValueError:pass
        else:
            accepted[signature]=checked;persist();return checked
    strategies=['correction','reaudit'] if previous else ['review','correction','reaudit']
    for strategy in strategies:
        slot=f'completeness_{signature}_{strategy}'
        try:
            if strategy=='correction':messages=review.correction(original,previous['response'],previous['validation_errors'])
            elif strategy=='reaudit':messages=alternate(original,previous['response'],previous['validation_errors'])
        except (ProtocolError,review.ReportError) as exc:
            attempts[strategy]=slot
            journal.setdefault('review_preparation_failures',[]).append(dict(signature=signature,strategy=strategy,errors=exc.errors))
            persist();continue
        answer=call(slot,messages)
        if answer is None:return None
        attempts[strategy]=slot
        merged=answer
        try:
            if strategy=='reaudit':
                checked,decisions=parse_alternate(answer,previous['response'],state,previous['validation_errors'])
                journal.setdefault('review_resolutions',[]).append(dict(signature=signature,decisions=decisions))
            else:
                if strategy=='correction':merged=review.merge_correction(answer,previous['response'],previous['validation_errors'])
                checked=review.parse(merged,state)
            unresolved=[dict(report_path=f'/issues/{i}/patch_paths',world_path=e['path'],message='Требуются точные поля исправления.') for i,e in enumerate(checked) if e.get('severity')=='blocker' and not e.get('patch_paths') and not e.get('remove_paths')]
            if unresolved:raise review.ReportError(unresolved,checked)
        except ValueError as exc:
            details=getattr(exc,'errors',[dict(stage=strategy,contract_version=review.CONTRACT_VERSION,code='recovery_rejected',report_path='/',world_path=None,message=str(exc))])
            failure=dict(candidate_hash=candidate_hash(state),contract_version=review.CONTRACT_VERSION,signature=signature,slot=slot,strategy=strategy,response=merged,provider_response=answer,validation_errors=details,partial_issues=getattr(exc,'issues',[]),error=str(exc))
            # A malformed correction must not replace the outstanding scope.
            if strategy!='review' and previous and not getattr(exc,'issues',[]):
                failure.update(response=previous['response'],validation_errors=previous['validation_errors'],partial_issues=previous.get('partial_issues',[]))
            failures.append(failure);previous=failure;persist()
        else:
            accepted[signature]=checked;persist();return checked
    attempts['exhausted']=True;persist()
    raise ValueError('Проверка не завершена: адресная коррекция и альтернативный аудит исчерпаны. Кандидат и замечания сохранены; повтор идентичных запросов заблокирован.')


def reaudit_schema():
    schema=review.typed_schema(Reaudit)
    row=schema['$defs']['Resolution']
    row['allOf']=[
        {'if':{'properties':{'resolution':{'const':'replaced'}}},'then':{'required':['issues'],'properties':{'issues':{'minItems':1}}}},
        {'if':{'properties':{'resolution':{'const':'disproved'}}},'then':{'required':['basis'],'properties':{'basis':{'minItems':1},'issues':{'maxItems':0}}}}]
    return schema
