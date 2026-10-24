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
    paths=[e['path'] for e in errors if e.get('path') and e['path']!='/']
    if len(paths)!=len(errors):
        raise ValueError('Ошибка требует интерпретации без однозначного пути. Исходный ответ сохранён: '+str(errors))
    fragments={}
    for path in paths:
        parts=path.lstrip('/').split('/')
        # A local record provides context for interdependent fields. Never send
        # its entire containing world just to repair a root/section property.
        scope=parts[:-1] if len(parts)>=3 else parts
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
    if author_context is not None:payload['author_context']=author_context
    return [dict(role='system',content='Исправь только перечисленные технические ошибки. Верни JSON {"patches":[{"path":"/точный/путь","value":новое_значение}]}. Не меняй остальные данные, персонажей, описания и события. Не придумывай сведения. Сохрани явные факты из контекста автора.'),
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
        if not isinstance(patch,dict) or set(patch)!={'path','value'} or patch['path'] not in paths or patch['path'] in used:
            raise ValueError('Исправление затронуло неразрешённый путь.')
        path=patch['path'];used.add(path)
        parts=[p.replace('~1','/').replace('~0','~') for p in path.lstrip('/').split('/')]
        target=value
        try:
            for key in parts[:-1]: target=target[int(key)] if isinstance(target,list) else target[key]
            if isinstance(target,list): target[int(parts[-1])]=deepcopy(patch['value'])
            else: target[parts[-1]]=deepcopy(patch['value'])
        except (KeyError,IndexError,TypeError,ValueError) as exc: raise ValueError('Путь исправления не существует.') from exc
    if not used: raise ValueError('Модель не исправила ни одной ошибки.')
    return json.dumps(value,ensure_ascii=False)
