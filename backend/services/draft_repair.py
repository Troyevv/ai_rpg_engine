"""Technical repairs are local assignments; unaffected data never leaves Python."""
from copy import deepcopy
import json
import re
from backend.services.draft_response import strict_loads


def tokens(text):
    # Complete JSON literals survive punctuation-only repairs exactly. A broken
    # string cannot be safely repaired this way and must remain a visible error.
    return re.findall(r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null',text)


class NoProgress(ValueError):
    pass


class RejectedTrial(ValueError):
    def __init__(self, before, after, original, trial):
        from backend.repositories.drafts import candidate_hash
        self.details = dict(before=before, after=after,
                            before_hash=candidate_hash(original), trial_hash=candidate_hash(trial))
        super().__init__('Пробный patch не принят: '+json.dumps(after,ensure_ascii=False))


def validate_trial(original, trial):
    """Never persist a trial before structural and canonical validation.

    An already invalid candidate may retain independent diagnostics. Newly
    revealed validation failures remain unresolved, not attributed to the LLM
    as introduced regressions. No error-count heuristic is used.
    """
    from backend.services.draft_initial import inspect_candidate
    _, before = inspect_candidate(original)
    _, after = inspect_candidate(trial)
    known = {(e['path'],e['category'],e['message']) for e in before['diagnostics']}
    unresolved = [e for e in after['diagnostics']
                  if (e['path'],e['category'],e['message']) not in known]
    if unresolved:raise RejectedTrial(before['diagnostics'],after['diagnostics'],original,trial)


class RepairScope(list):
    def __init__(self, paths, value, residences, removals=()):
        super().__init__(paths)
        from backend.repositories.drafts import candidate_hash
        self.candidate_hash = candidate_hash(value)
        self.residences = residences
        self.removals = set(removals)


def request(raw,errors,author_context=None):
    try: value=strict_loads(raw)
    except ValueError:
        return [dict(role='system',content='Исправь только синтаксическую пунктуацию JSON. Сохрани все ключи, строки, числа и их порядок дословно. Верни полный JSON без Markdown.'),
                dict(role='user',content=json.dumps(dict(response=raw,errors=errors),ensure_ascii=False))],None
    if any(e.get('category')=='player_agency' for e in errors):raise ValueError('Автор должен подтвердить цель управляемого героя; автоматический repair не может принять решение за игрока.')
    if any(e.get('category')=='duplicate' for e in errors):raise ValueError('Конфликт фаз связи требует уточнения автором. Нельзя закрывать связь ради устранения дубля.')
    from backend.services.draft_completeness import pointer
    errors=list(errors)
    for issue in list(errors):
        path=issue.get('path','')
        if issue.get('category')=='calendar_date' and path.rsplit('/',1)[-1] in ('since_date','until_date'):
            try:partial=pointer(value,path)
            except (ValueError,KeyError,TypeError,IndexError):continue
            if isinstance(partial,str) and re.fullmatch(r'\d{4}',partial):
                errors.append(dict(path=path.rsplit('/',1)[0]+'/context',category='date_context',message='Сохрани известный год '+partial+' в context; точная дата неизвестна и должна быть null.'))
    removals={p for e in errors for p in e.get('remove_paths',[])}
    assignments={p for e in errors for p in (e.get('patch_paths',[]) if e.get('category') in ('semantic_completeness','relation_conflict') else [e.get('path')])}
    expanded=[]
    for e in errors:
        if e.get('category') in ('semantic_completeness','relation_conflict'):
            if not e.get('patch_paths') and not e.get('remove_paths'):raise ValueError('Замечание сохранено, но точные поля для автоматического исправления не определены. Повторите проверку или откройте редактор автора.')
            expanded.extend(dict(e,path=p) for p in (e.get('patch_paths',[])+e.get('remove_paths',[])))
        else:expanded.append(e)
    for e in expanded:
        if e.get('category')=='semantic_completeness' and e.get('path','').startswith('/world/residences/') and e['path'].rsplit('/',1)[-1] in ('status','until','until_date','outcome') and len(e.get('basis',[]))<2:
            raise ValueError('Закрытие проживания требует проверяемых несовместимых утверждений; присутствие в другой сцене недостаточно. Замечание сохранено для автора.')
    errors=expanded
    paths=list(dict.fromkeys(e['path'] for e in errors if e.get('path') in assignments and e['path']!='/'))
    if any(not e.get('path') or e['path']=='/' for e in errors):
        raise ValueError('Ошибка требует интерпретации без однозначного пути. Исходный ответ сохранён: '+str(errors))
    fragments={}
    for path in paths:
        parts=path.lstrip('/').split('/')
        # A local record provides context for interdependent fields. Never send
        # its entire containing world just to repair a root/section property.
        semantic=any(e.get('path')==path and e.get('category')=='semantic_completeness' for e in errors)
        scope=parts if semantic and len(parts)==3 and parts[0]=='world' else parts[:-1] if len(parts)>=3 else parts
        scope_path='/'+('/'.join(scope))
        current=value
        try:
            for part in scope:
                key=part.replace('~1','/').replace('~0','~')
                current=current[int(key)] if isinstance(current,list) else current[key]
            fragments[scope_path]={'value':current}
        except (KeyError,IndexError,TypeError,ValueError):
            fragments[scope_path]={'missing':True}
    residence_ids={p.split('/')[3].replace('~1','/').replace('~0','~') for p in list(paths)+list(removals) if p.startswith('/world/residences/') and len(p.split('/'))>=4}
    residence_ids={rid for rid in residence_ids if rid in value.get('world',{}).get('residences',{}) or '/world/residences/'+rid in paths}
    paths=RepairScope(paths,value,residence_ids,removals)
    payload=dict(errors=errors,fragments=fragments,candidate_hash=paths.candidate_hash)
    if residence_ids:
        payload['residence_operations']={'ids':sorted(residence_ids),'remove_paths':sorted(removals),'instructions':'Вместо случайного здания можно удалить только указанную ошибочную residence (op=remove, path записи, expected=точная текущая запись), либо добавить новую локацию (op=add_location, path=/locations/-, value=локация) и исправить location_id той же residence. Передай candidate_hash из запроса. Все операции атомарны. Не удаляй жильё, явно заданное автором. Неизвестное жильё допустимо.'}
        payload['residence_records']={rid:value['world']['residences'][rid] for rid in residence_ids if rid in value['world']['residences']}

    related={}
    for issue in errors:
        for path in issue.get('related_paths',[]):
            from backend.services.draft_completeness import pointer
            related[path]=pointer(value,path)
    if related:payload['related']=related
    if any(e.get('category')=='semantic_completeness' for e in errors):
        from backend.services.draft_initial import prompt_schema
        schema=prompt_schema()
        # Include only the affected section schemas, not the full world schema.
        payload['entities']={
            'characters':[{'id':c['id'],'name':c['name']} for c in value.get('characters',[])],
            'locations':[{'id':p['id'],'name':p['name']} for p in value.get('locations',[])],
            'organizations':[{'id':k,'name':v.get('name','')} for k,v in value.get('world',{}).get('organizations',{}).items()]}
        if residence_ids:payload['location_schema']=schema['properties']['locations']['items']
        sections={p.split('/')[2] for p in paths if p.startswith('/world/')}
        payload['record_schemas']={k:schema['properties']['world']['properties'][k] for k in sections}
        if any(p.startswith('/world_clock/') for p in paths):payload['clock_schema']=schema['properties']['world_clock']
    operations=[{'type':'object','properties':{'path':{'enum':list(paths)},'value':{}},'required':['path','value'],'additionalProperties':False}]
    if removals:operations.append({'type':'object','properties':{'op':{'const':'remove'},'path':{'enum':sorted(removals)},'expected':{'type':'object'}},'required':['op','path','expected'],'additionalProperties':False})
    if residence_ids:operations.append({'type':'object','properties':{'op':{'const':'add_location'},'path':{'const':'/locations/-'},'value':payload.get('location_schema',{'type':'object'})},'required':['op','path','value'],'additionalProperties':False})
    payload['response_schema']={'type':'object','properties':{'candidate_hash':{'const':paths.candidate_hash},'patches':{'type':'array','minItems':1,'items':{'oneOf':operations}}},'required':['patches'],'additionalProperties':False}
    if author_context is not None:payload['author_context']=author_context
    return [dict(role='system',content='Исправь только перечисленные ошибки структуры и смысловой согласованности. Верни JSON {"patches":[{"path":"/точный/путь","value":новое_значение}]}. Для relation_conflict сопоставь обе записи и контекст автора. Исправляй только противоречивые поля, сохраняя существенные сведения. Не меняй status на closed, не выдумывай завершение связи и не меняй её участников или kind ради устранения дубля. Не меняй остальные данные, персонажей, описания и события. Технические ошибки исправляй без новых обстоятельств. При semantic_completeness допустимо смысловое дополнение на основе замысла и уже созданных непротиворечивых фактов, даже отсутствующих в исходном тексте. Сохраняй явные ограничения, знания конкретных участников и свободу будущих действий игрока. При неизвестном точном времени события сохрани text/evidence, minute=null. Не меняй корректные биографии. Сохрани явные факты из контекста автора.'),
            dict(role='user',content=json.dumps(payload,ensure_ascii=False))],paths


def apply(raw,reply,paths):
    repaired=strict_loads(reply)
    if paths is None:
        if tokens(raw)!=tokens(reply): raise ValueError('Исправление синтаксиса изменило содержание; ответ отклонён.')
        return reply
    if not isinstance(repaired,dict) or set(repaired) not in ({'patches'},{'patches','candidate_hash'}) or not isinstance(repaired['patches'],list):
        raise ValueError('Ожидался объект patches.')
    value=strict_loads(raw); original=deepcopy(value); used=set(); linked=False; added=[]
    from backend.repositories.drafts import candidate_hash
    if isinstance(paths,RepairScope) and candidate_hash(value)!=paths.candidate_hash:raise ValueError('Кандидат изменился; patch устарел.')
    if repaired.get('candidate_hash') and repaired['candidate_hash']!=candidate_hash(value):raise ValueError('Кандидат изменился; patch устарел.')

    destinations=[p.get('path') for p in repaired['patches'] if isinstance(p,dict)]
    if len(destinations)!=len(repaired['patches']) or any(not isinstance(p,str) for p in destinations):
        raise ValueError('Некорректный путь patch.')
    if len(set(destinations))!=len(destinations) or any(a.startswith(b+'/') for a in destinations for b in destinations if a!=b):
        raise ValueError('Повторные или пересекающиеся пути patch.')
    for patch in repaired['patches']:
        if isinstance(paths,RepairScope) and (patch['path'].startswith(('/authoring','/creation_settings','/world_clock')) or
                '/birth_provenance' in patch['path'] or patch['path'].endswith(('/birth_date','/time_semantics'))):
            from backend.services.draft_completeness import pointer
            if patch.get('op') or pointer(original,patch['path'])!=patch.get('value'):
                raise ValueError('Календарь и происхождение дат изменяются кодом или автором, не repair.')
        if isinstance(patch,dict) and patch.get('op') in ('remove','add_location'):
            if not isinstance(paths,RepairScope) or not paths.residences or repaired.get('candidate_hash')!=paths.candidate_hash:
                raise ValueError('Связанный пакет требует актуального hash и residence scope.')
            linked=True
            if patch['op']=='remove':
                if set(patch)!={'op','path','expected'}:raise ValueError('Некорректная операция удаления.')
                eligible={'/world/residences/'+rid.replace('~','~0').replace('/','~1'):rid for rid in paths.residences}
                rid=eligible.get(patch['path'])
                if patch['path'] not in paths.removals or not rid or value['world']['residences'].get(rid)!=patch['expected']:raise ValueError('Предусловие удаления не выполнено.')
                del value['world']['residences'][rid]
            else:
                if set(patch)!={'op','path','value'} or patch['path']!='/locations/-':raise ValueError('Некорректная новая локация.')
                place=patch['value']
                if not isinstance(place,dict) or not place.get('id') or any(p.get('id')==place['id'] for p in value['locations']):raise ValueError('ID локации отсутствует или уже занят.')
                value['locations'].append(deepcopy(place));added.append(place['id'])
            used.add(patch['path']);continue
        if not isinstance(patch,dict) or set(patch)!={'path','value'} or not isinstance(patch['path'],str) or patch['path'] not in paths or patch['path'] in used:
            raise ValueError('Исправление затронуло неразрешённый путь.')
        path=patch['path'];used.add(path)
        if not path.startswith('/') or path=='/' or re.search(r'~(?![01])',path):raise ValueError('Некорректный JSON Pointer.')
        parts=[p.replace('~1','/').replace('~0','~') for p in path.lstrip('/').split('/')]
        target=value
        try:
            for key in parts[:-1]:
                if isinstance(target,list) and not re.fullmatch(r'0|[1-9]\d*',key):raise ValueError('Некорректный индекс.')
                target=target[int(key)] if isinstance(target,list) else target[key]
            if isinstance(target,list):
                if not re.fullmatch(r'0|[1-9]\d*',parts[-1]):raise ValueError('Некорректный индекс.')
                target[int(parts[-1])]=deepcopy(patch['value'])
            else: target[parts[-1]]=deepcopy(patch['value'])
        except (KeyError,IndexError,TypeError,ValueError) as exc: raise ValueError('Путь исправления не существует.') from exc
    if not used: raise ValueError('Модель не исправила ни одной ошибки.')
    if linked:
        if any(not any(r.get('location_id')==lid for rid,r in value['world']['residences'].items() if rid in paths.residences) for lid in added):raise ValueError('Новая локация не связана с исправляемым проживанием.')
    if isinstance(paths,RepairScope):
        from backend.services.draft_completeness import pointer
        for path in used:
            if path.rsplit('/',1)[-1] not in ('since_date','until_date'):continue
            try:prior=pointer(original,path)
            except (KeyError,IndexError,TypeError,ValueError):continue
            if isinstance(prior,str) and re.fullmatch(r'\d{4}',prior):
                row=pointer(value,path.rsplit('/',1)[0])
                if pointer(value,path) is not None or not any(prior in str(row.get(f,'')) for f in ('context','evidence')):
                    raise ValueError('Неполный год не задаёт точный день: сохрани год в context/evidence, дату оставь null.')
        validate_trial(original,value)
    return json.dumps(value,ensure_ascii=False)
