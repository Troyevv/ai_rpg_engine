"""One optional, atomic completion batch using the existing review and repair."""
import json
from backend.services.draft_response import strict_loads
from backend.services.draft_protocol import QualityReply, QualityAudit, ProtocolError,decode,reject
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
    key=candidate_hash({'state':state,'policy':3,'author_context':author_context})
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
        payload=json.loads(messages[1]['content'])
        payload['response_schema']=quality_schema(payload['response_schema'])
        messages[1]['content']=json.dumps(payload,ensure_ascii=False)
        messages[0]['content']='Один необязательный пакет улучшения выбранных слабых полей. Верни patches по response_schema. Для явно заданной неизвестности конкретного поля конкретного персонажа разрешён preserved_unknown:[{path,author_excerpt}] вместо patch; выдержка должна содержать относящееся к этому полю пожелание автора. Можно patches=[] только с preserved_unknown. Сохрани хорошие поля и авторские ограничения.'
        answer=call('quality_'+before,messages,'draft_world_quality')
        if answer is None:
            record.update(status='cancelled',warning='Дополнение прервано; проверенный мир сохранён.');return state,None
        record['response']=answer
        response=decode(QualityReply,answer,'quality').model_dump(exclude_unset=True);preserved=response.pop('preserved_unknown',[])
        allowed={e['path'] for e in chosen if e.get('minimum')};unknown=[]
        for entry in preserved:
            if not isinstance(entry,dict) or set(entry)!={'path','author_excerpt'} or entry['path'] not in allowed or not isinstance(entry['author_excerpt'],str) or len(entry['author_excerpt'].strip())<8 or entry['author_excerpt'] not in author_context:
                raise ValueError('Неизвестность должна иметь основание в исходном авторском тексте.')
            if entry['path'] in unknown:reject('quality','/preserved_unknown','Повторный путь неизвестности.')
            unknown.append(entry['path'])
        trial=json.loads(repair.apply(raw,json.dumps(response,ensure_ascii=False),scope)) if response.get('patches') else state
        if not response.get('patches') and not unknown:raise ValueError('Модель не предложила дополнения или основания неизвестности.')
        from backend.services.draft_completeness import pointer
        if any(p['path']==u or p['path'].startswith(u+'/') or u.startswith(p['path']+'/') for p in response['patches'] for u in unknown):reject('quality','/patches','Нельзя изменять и сохранять один путь.')
        if any(pointer(state,path)!=pointer(trial,path) for path in unknown):raise ValueError('Нельзя одновременно изменить и сохранить неизвестность.')
        record['preserved_unknown']=preserved
        from backend.services.draft_initial import inspect_candidate
        trial,report=inspect_candidate(trial)
        if report['errors']:raise ValueError(json.dumps(report['errors'],ensure_ascii=False))
        signature=candidate_hash(trial)
        # Text can affect distant facts and knowledge: bounded full re-review.
        audit_messages=review.messages(trial,author_context)
        expected={}
        if unknown:
            for path in unknown:
                parts=path.split('/')
                if len(parts)!=5 or parts[1]!='characters' or parts[3]!='fields':reject('quality','/preserved_unknown','Нужен точный путь поля карточки.')
                card=state['characters'][int(parts[2])]
                expected[path]=dict(actor_id=card['id'],field=parts[4])
            audit_payload=json.loads(audit_messages[1]['content'])
            audit_payload.pop('report_schema',None);audit_payload.pop('example',None)
            audit_payload.update(response_schema=review.typed_schema(QualityAudit),preserved_unknown=preserved,unknown_subjects=expected)
            audit_messages=[dict(role='system',content=review.MARKER+' Проверь мир и каждое сохранение неизвестности по response_schema. unknown_confirmations: явно проверь, что пожелание автора относится именно к указанному персонажу и полю; чужое имя, общее упоминание или неоднозначность => unresolved. Верни reason с обоснованием. Не считай произвольную подстроку доказательством.'),dict(role='user',content=json.dumps(audit_payload,ensure_ascii=False))]
        answer=call('quality_review_'+signature,audit_messages,'draft_world_validation')
        if answer is None:
            record.update(status='cancelled',warning='Повторная проверка прервана; trial не принят.');return state,None
        record['review_response']=answer
        if unknown:
            audit=decode(QualityAudit,answer,'quality_review').model_dump()
            confirmations=audit['unknown_confirmations'];seen=set()
            for row in confirmations:
                path=row['path']
                if path not in expected or path in seen or row['decision']!='preserve' or any(row[k]!=v for k,v in expected[path].items()):reject('quality_review','/unknown_confirmations','Неизвестность конкретного поля не подтверждена.')
                seen.add(path)
            if seen!=set(unknown):reject('quality_review','/unknown_confirmations','Не все поля подтверждены.')
            answer=json.dumps({'issues':audit['issues']},ensure_ascii=False)
        checked=review.parse(answer,trial)
        if any(e.get('severity')=='blocker' for e in checked):
            raise ValueError('Дополнение не прошло повторную смысловую проверку: '+json.dumps(checked,ensure_ascii=False))
        record.update(status='partial' if any(e['path'] not in unknown for e in minimum(trial,author_context)) else 'accepted',after_hash=signature,issues=checked)
        cache[candidate_hash({'state':trial,'policy':3,'author_context':author_context})]=record
        return trial,checked
    except (ValueError,ProviderHTTPError) as exc:
        record.update(status='partial' if record.get('minimum_paths') else 'rejected',warning=str(exc))
        record['diagnostics']=getattr(exc,'errors',[dict(stage='quality',contract_version=3,code='quality_rejected',report_path='/',world_path=None,message=str(exc))])
        if isinstance(exc,repair.RejectedTrial):record['trial']=exc.details
        return state,None


def quality_schema(repair_schema):
    from copy import deepcopy
    schema=deepcopy(repair_schema)
    schema['properties']['patches']['minItems']=0
    schema['properties']['preserved_unknown']=QualityReply.model_json_schema()['properties']['preserved_unknown']
    schema['$defs']=QualityReply.model_json_schema()['$defs']
    schema['anyOf']=[{'properties':{'patches':{'minItems':1}}},
                     {'required':['preserved_unknown'],'properties':{'preserved_unknown':{'minItems':1}}}]
    return schema
