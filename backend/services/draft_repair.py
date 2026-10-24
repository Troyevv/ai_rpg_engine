"""Technical repairs are local assignments; unaffected data never leaves Python."""
from copy import deepcopy
import json
import re
from backend.services.draft_response import strict_loads


def tokens(text):
    # Complete JSON literals survive punctuation-only repairs exactly. A broken
    # string cannot be safely repaired this way and must remain a visible error.
    return re.findall(r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null',text)


def request(raw,errors,author_context=None):
    try: value=strict_loads(raw)
    except ValueError:
        return [dict(role='system',content='Исправь только синтаксическую пунктуацию JSON. Сохрани все ключи, строки, числа и их порядок дословно. Верни полный JSON без Markdown.'),
                dict(role='user',content=json.dumps(dict(response=raw,errors=errors),ensure_ascii=False))],None
    if any(e.get('category')=='duplicate' for e in errors):raise ValueError('Конфликт фаз связи требует уточнения автором. Нельзя закрывать связь ради устранения дубля.')
    expanded=[]
    for e in errors:
        if e.get('category') in ('semantic_completeness','relation_conflict'):
            if not e.get('patch_paths'):raise ValueError('Замечание сохранено, но точные поля для автоматического исправления не определены. Повторите проверку или откройте редактор автора.')
            expanded.extend(dict(e,path=p) for p in e['patch_paths'])
        else:expanded.append(e)
    errors=expanded
    paths=list(dict.fromkeys(e['path'] for e in errors if e.get('path') and e['path']!='/'))
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
    payload=dict(errors=errors,fragments=fragments)
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
        sections={p.split('/')[2] for p in paths if p.startswith('/world/')}
        payload['record_schemas']={k:schema['properties']['world']['properties'][k] for k in sections}
        if any(p.startswith('/world_clock/') for p in paths):payload['clock_schema']=schema['properties']['world_clock']
    if author_context is not None:payload['author_context']=author_context
    return [dict(role='system',content='Исправь только перечисленные ошибки структуры и смысловой согласованности. Верни JSON {"patches":[{"path":"/точный/путь","value":новое_значение}]}. Для relation_conflict сопоставь обе записи и контекст автора. Исправляй только противоречивые поля, сохраняя существенные сведения. Не меняй status на closed, не выдумывай завершение связи и не меняй её участников или kind ради устранения дубля. Не меняй остальные данные, персонажей, описания и события. Технические ошибки исправляй без новых обстоятельств. При semantic_completeness допустимо смысловое дополнение на основе замысла и уже созданных непротиворечивых фактов, даже отсутствующих в исходном тексте. Сохраняй явные ограничения, знания конкретных участников и свободу будущих действий игрока. При неизвестном точном времени события сохрани text/evidence, minute=null. Не меняй корректные биографии. Сохрани явные факты из контекста автора.'),
            dict(role='user',content=json.dumps(payload,ensure_ascii=False))],paths


def apply(raw,reply,paths):
    repaired=strict_loads(reply)
    if paths is None:
        if tokens(raw)!=tokens(reply): raise ValueError('Исправление синтаксиса изменило содержание; ответ отклонён.')
        return reply
    if not isinstance(repaired,dict) or set(repaired)!={'patches'} or not isinstance(repaired['patches'],list):
        raise ValueError('Ожидался объект patches.')
    value=strict_loads(raw); used=set()
    for patch in repaired['patches']:
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
    return json.dumps(value,ensure_ascii=False)
