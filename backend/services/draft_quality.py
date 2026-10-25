"""One optional, atomic completion batch using the existing review and repair."""
import json
from llm import ProviderHTTPError
from backend.repositories.drafts import candidate_hash
from backend.services import draft_completeness as review, draft_repair as repair


def selected(issues):
    # Only explicit reviewer selections: no length quotas and no fabricated needs.
    return [e for e in issues if e.get('severity')=='recommendation'
            and e.get('assertion')=='optional_detail' and e.get('patch_paths')]


def minimum(state, author_context):
    """Detect placeholders, never grade prose length or invent facts in Python."""
    placeholders={'','неизвестно','не указано','не задано','unknown','n/a','—'}
    protected=state.get('authoring',{}).get('manual_paths',[])
    findings=[]
    for i,card in enumerate(state.get('characters',[])):
        if card['id']==state.get('controlled_actor_id'):continue
        fields=card.get('fields',{})
        for name in ('Внешность','Характер','Стиль общения','Привычки','Сильные стороны','Слабости','Биография'):
            value=fields.get(name,'')
            path=f'/characters/{i}/fields/{name}'
            if path in protected or not isinstance(value,str) or value.strip().lower() not in placeholders:continue
            # Explicit author uncertainty is interpreted by the completion model,
            # using the intact source; the detector grants no fact authority.
            findings.append(dict(path=path,message='Проверь намеренную неизвестность по авторскому контексту. Если она не задана автором, дополни полезную для игры черту NPC.',severity='recommendation',assertion='optional_detail',category='semantic_completeness',patch_paths=[path],minimum=True))
    return findings


def complete(state, issues, author_context, journal, call):
    chosen=selected(issues)+minimum(state,author_context)
    before=candidate_hash(state)
    key=candidate_hash({'state':state,'policy':2,'author_context':author_context})
    cache=journal.setdefault('quality_attempts',{})
    existing=cache.get(key)
    if not chosen or existing and existing.get('status') in ('accepted','rejected','partial'):return state,None
    if not existing and len({r['before_hash'] for r in cache.values()})>=2:
        journal['quality']=dict(status='partial',warning='Конечный бюджет дополнения исчерпан; минимальное содержание требует проверки.')
        return state,None
    record=existing or dict(status='running',before_hash=before,minimum_paths=[e['path'] for e in chosen if e.get('minimum')])
    cache[key]=record;journal['quality']=record
    try:
        raw=json.dumps(state,ensure_ascii=False)
        messages,scope=repair.request(raw,chosen,author_context)
        messages[0]['content']='Для явно заданной автором неизвестности можно вернуть preserved_unknown:[{path,author_excerpt}] с дословным фрагментом исходного замысла вместо patch этого поля. '+messages[0]['content']
        messages[0]['content']='Один необязательный пакет улучшения выбранных слабых полей. Сохрани хорошие поля и авторские ограничения. '+messages[0]['content']
        answer=call('quality_'+before,messages,'draft_world_quality')
        if answer is None:return state,None
        response=json.loads(answer);preserved=response.pop('preserved_unknown',[])
        allowed={e['path'] for e in chosen if e.get('minimum')};unknown=[]
        for entry in preserved:
            if not isinstance(entry,dict) or set(entry)!={'path','author_excerpt'} or entry['path'] not in allowed or not isinstance(entry['author_excerpt'],str) or len(entry['author_excerpt'].strip())<8 or entry['author_excerpt'] not in author_context:
                raise ValueError('Неизвестность должна иметь основание в исходном авторском тексте.')
            unknown.append(entry['path'])
        trial=json.loads(repair.apply(raw,json.dumps(response,ensure_ascii=False),scope)) if response.get('patches') else state
        if not response.get('patches') and not unknown:raise ValueError('Модель не предложила дополнения или основания неизвестности.')
        from backend.services.draft_completeness import pointer
        if any(pointer(state,path)!=pointer(trial,path) for path in unknown):raise ValueError('Нельзя одновременно изменить и сохранить неизвестность.')
        record['preserved_unknown']=preserved
        from backend.services.draft_initial import inspect_candidate
        trial,report=inspect_candidate(trial)
        if report['errors']:raise ValueError('; '.join(report['errors']))
        signature=candidate_hash(trial)
        # Text can affect distant facts and knowledge: bounded full re-review.
        answer=call('quality_review_'+signature,review.messages(trial,author_context),'draft_world_validation')
        if answer is None:return state,None
        checked=review.parse(answer,trial)
        if any(e.get('severity')=='blocker' for e in checked):
            raise ValueError('Дополнение не прошло повторную смысловую проверку: '+json.dumps(checked,ensure_ascii=False))
        record.update(status='partial' if any(e['path'] not in unknown for e in minimum(trial,author_context)) else 'accepted',after_hash=signature,issues=checked)
        cache[candidate_hash({'state':trial,'policy':2,'author_context':author_context})]=record
        return trial,checked
    except (ValueError,ProviderHTTPError) as exc:
        record.update(status='partial' if record.get('minimum_paths') else 'rejected',warning=str(exc))
        if isinstance(exc,repair.RejectedTrial):record['trial']=exc.details
        return state,None
