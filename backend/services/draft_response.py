"""Bounded, lossless JSON transport for the existing draft request.

The journal lives on preparation_jobs. A pending request has an unknown outcome
until its stream and accounting finish; it is never automatically replayed.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re
from context_builder import estimate
from llm import OutputLimitReached, ProviderHTTPError

MAX_FRAGMENTS = 5
CONTINUE = ('Продолжи тот же JSON строго с места остановки. Не начинай объект заново, '
            'не повторяй уже выведенный текст и не изменяй ранее созданные данные. '
            'Верни только недостающую часть без Markdown и пояснений.')


class TransportError(ValueError):
    pass


class _Incomplete(Exception):
    pass


def prefix_complete(text, schema=None):
    """Validate JSON grammar without completing strings/containers or discarding bytes."""
    i, n = 0, len(text)
    def whitespace():
        nonlocal i
        while i < n and text[i] in ' \t\r\n': i += 1
    def need():
        if i >= n: raise _Incomplete
    def string():
        nonlocal i
        i += 1
        while True:
            need(); ch = text[i]; i += 1
            if ch == '"': return
            if ord(ch) < 32: raise TransportError('Недопустимый символ внутри JSON-строки.')
            if ch == '\\':
                need(); ch = text[i]; i += 1
                if ch == 'u':
                    for _ in range(4):
                        need()
                        if text[i] not in '0123456789abcdefABCDEF': raise TransportError('Повреждён Unicode escape.')
                        i += 1
                elif ch not in '"\\/bfnrt': raise TransportError('Повреждён escape JSON-строки.')
    def child_schema(node, key):
        if not node:return None
        if 'anyOf' in node:
            node=next((x for x in node['anyOf'] if x.get('type')=='object'),{})
        props=node.get('properties',{})
        if key in props:return props[key]
        extra=node.get('additionalProperties')
        if isinstance(extra,dict):return extra
        if props or extra is False:raise TransportError('Неверная вложенность: неизвестный ключ '+key)
        return None
    def value(depth=0, node=None):
        nonlocal i
        if depth > 100: raise TransportError('Слишком глубокая вложенность JSON.')
        whitespace(); need(); ch = text[i]
        if node:
            kinds=[node.get('type')]+[x.get('type') for x in node.get('anyOf',[])]
            expected=[t for x in kinds if x for t in (x if isinstance(x,list) else [x])]
            actual='object' if ch=='{' else 'array' if ch=='[' else 'string' if ch=='"' else 'null' if ch=='n' else 'boolean' if ch in 'tf' else 'number'
            if expected and actual not in expected and not (actual=='number' and 'integer' in expected):
                raise TransportError('Неверная вложенность: ожидался '+str(expected))
        if ch == '"': string(); return
        if ch in '{[':
            close = '}' if ch == '{' else ']'; is_object = ch == '{'; i += 1; keys=set()
            whitespace(); need()
            if text[i] == close: i += 1; return
            while True:
                whitespace(); need()
                if is_object:
                    if text[i] != '"': raise TransportError('Ожидался ключ JSON-объекта.')
                    start=i;string();key=json.loads(text[start:i])
                    if key in keys:raise TransportError('Повтор JSON-ключа: '+key)
                    keys.add(key);child=child_schema(node,key)
                    whitespace(); need()
                    if text[i] != ':': raise TransportError('Ожидалось двоеточие JSON.')
                    i += 1
                value(depth+1,child if is_object else (node or {}).get('items')); whitespace(); need()
                if text[i] == close: i += 1; return
                if text[i] != ',': raise TransportError('Повреждена граница JSON: ожидалась запятая.')
                i += 1
        if ch in '-0123456789':
            start = i
            while i < n and text[i] in '-+0123456789.eE': i += 1
            token = text[start:i]
            if not re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?',token):
                if i == n and re.fullmatch(r'-?(?:0|[1-9]\d*)?(?:\.\d*)?(?:[eE][+-]?\d*)?',token): raise _Incomplete
                raise TransportError('Некорректное JSON-число.')
            return
        for literal in ('true','false','null'):
            if ch == literal[0]:
                tail = text[i:i+len(literal)]
                if not literal.startswith(tail): raise TransportError('Повреждено JSON-значение.')
                if len(tail) < len(literal): raise _Incomplete
                i += len(literal); return
        raise TransportError('Недопустимое начало JSON-значения.')
    try:
        value(node=schema); whitespace()
        if i != n: raise TransportError('Повтор объекта или лишний текст после JSON.')
        return True
    except _Incomplete:
        return False


def strict_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Повтор JSON-ключа: '+key)
            result[key] = value
        return result
    def constant(value): raise ValueError('Недопустимое JSON-число: '+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)


ASSEMBLY_VERSION = 1


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


def overlaps(left,right):
    # Bounded exact candidates; a larger repeated block requires explicit recovery.
    return [n for n in range(1,min(len(left),len(right),4096)+1) if left.endswith(right[:n])]


def join_fragments(parts, manifest=None, *, schema=None, terminal=False):
    """Raw offsets are Python characters; accepted offsets are recorded separately.

    Always prefer valid literal concatenation. Only a uniquely schema-compatible
    overlap may be removed. No missing fields/references are checked on prefixes.
    """
    result='';raw_offset=0;boundaries=[]
    for index,part in enumerate(parts):
        text=part['text']
        if digest(text)!=part['sha256']:raise TransportError('Нарушена целостность сохранённого фрагмента.')
        if part['offset']!=raw_offset:raise TransportError('Пропущен или переставлен фрагмент JSON.')
        raw_offset+=len(text);literal=result+text;remove=0;failures=[]
        if result and prefix_complete(result):raise TransportError('Повтор объекта или лишний фрагмент после полного JSON.')
        try:prefix_complete(literal)
        except TransportError as invalid:
            duplicate='Повтор JSON-ключа' in str(invalid)
            if duplicate and not (terminal and index==len(parts)-1):raise
            candidates=[]
            for count in ([] if duplicate else overlaps(result,text)):
                try:
                    prefix_complete(result+text[count:],schema)
                    candidates.append(count)
                except TransportError as exc:failures.append(dict(overlap=count,reason=str(exc)))
            if len(candidates)==1:remove=candidates[0]
            elif candidates:
                raise TransportError('Неоднозначная граница фрагментов: '+str(candidates)+'. Требуется повтор только последнего продолжения.')
            elif not terminal or index!=len(parts)-1:
                raise TransportError(str(invalid)) from invalid
            # Terminal syntax errors are returned intact to the existing repair.
        boundaries.append(dict(index=index,raw_offset=part['offset'],assembled_offset=len(result),
            removed_prefix=remove,source_sha256=part['sha256'],prefix_sha256=digest(result),rejected=failures))
        result+=text[remove:]
    built=dict(version=ASSEMBLY_VERSION,offset_unit='python_characters',boundaries=boundaries,
        raw_length=raw_offset,assembled_length=len(result),sha256=digest(result))
    if manifest is not None:
        if manifest and manifest!=built:raise TransportError('Нарушена целостность манифеста сборки.')
        manifest.update(built)
    return result


def stage_output_limit(slot, messages, config):
    stage='world' if slot=='world' else 'review' if slot.startswith(('completeness','quality_review')) else 'quality' if slot.startswith('quality') else 'repair'
    # Output size follows candidate/scope size, bounded by the user's ceiling.
    size=estimate(messages)
    target=config['max_tokens'] if stage=='world' else max(1024,int(size*({'review':0.30,'repair':0.75,'quality':0.90}[stage])))
    override=config.get('_draft_stage_output_limits',{}).get(stage)
    return min(config['max_tokens'],target if override is None else override)


def response(repo,jid,journal,slot,messages,config,context,generate,cancel):
    # Provider capability is distinct from the app's intentionally smaller context.
    # Official model catalog, checked 2026-10-24: api-docs.deepseek.com/api/list-models/
    capabilities=config.get('_model_capabilities',{})
    if config.get('provider')=='deepseek' and config.get('model') in ('deepseek-flash','deepseek-v4-flash','deepseek-v4-flash-vision-exp','deepseek-v4-pro'):
        capabilities=dict(context_window=1048576,max_output_tokens=393216)
    context=min(context,capabilities.get('context_window',context))
    output_limit=min(stage_output_limit(slot,messages,config),capabilities.get('max_output_tokens',config['max_tokens']))
    record = journal.setdefault('responses',{}).setdefault(slot,{'parts':[],'complete':False})
    if not record['complete']:record['output_limit']=output_limit
    schema=None
    if slot=='world':
        from backend.services.draft_initial import prompt_schema
        schema=prompt_schema()
    def assemble():
        manifest=record.setdefault('assembly',{})
        try:
            result=join_fragments(record['parts'],manifest,schema=schema,terminal=record['complete'])
        except TransportError as exc:
            record['assembly_error']=str(exc)
            repo.save_response_journal(jid,journal)
            raise
        record.pop('assembly_error',None)
        try:record['document_state']='empty' if record['complete'] and record['parts'] and not result else 'complete' if prefix_complete(result) else 'incomplete'
        except TransportError:record['document_state']='syntax_error'
        repo.save_response_journal(jid,journal)
        return result
    text=assemble()
    if record['complete'] and record['document_state']!='incomplete':return text
    if record['complete']:
        record['complete']=False
        repo.save_response_journal(jid,journal)
    if journal.get('pending'): raise TransportError('Исход прошлого запроса неизвестен; повтор запрещён.')
    def accounting():
        if not hasattr(repo,'request_log'):return {}
        rows=repo.request_log(job_id=jid)
        return rows[0] if rows else {}
    while not cancel.is_set():
        if text and prefix_complete(text):
            record['complete']=True
            repo.save_response_journal(jid,journal)
            return text
        if len(record['parts']) >= MAX_FRAGMENTS: raise TransportError('Исчерпан лимит пяти фрагментов. Ответ сохранён.')
        request = deepcopy(messages)
        if text:
            request += [{'role':'assistant','content':text},{'role':'user','content':CONTINUE}]
            repo.draft_phase(jid,'continuing')
        input_bound = estimate(request)+512
        limit = min(output_limit,context-input_bound)
        if limit < 256: raise TransportError(f'Контекст {context} не вмещает полный запрос: требуется минимум {input_bound+256} токенов. Текст сохранён, запрос не отправлен.')
        # A conservative reserved token envelope bounds even calls with missing
        # provider usage. Accounting remains actual usage in llm_requests.
        budget = config.get('_draft_token_budget',3*MAX_FRAGMENTS*(context+config['max_tokens']))
        reserved = journal.get('reserved_tokens',0)
        if reserved+journal.get('actual_tokens',0)+input_bound+limit > budget: raise TransportError('Исчерпан бюджет токенов генерации. Ответ сохранён.')
        previous_cost=journal.get('reserved_cost','0')
        cap = config.get('_draft_cost_budget_usd')
        if cap is not None:
            from backend.services.usage import price_snapshot
            from datetime import datetime, timezone
            pricing = price_snapshot(config,datetime.now(timezone.utc))
            if pricing is None: raise TransportError('Тариф неизвестен: нельзя гарантировать бюджет расходов.')
            upper = Decimal(0) if pricing['version']=='local' else (input_bound*Decimal(pricing['input'])+limit*Decimal(pricing['output']))/1000000
            cost = Decimal(journal.get('reserved_cost','0'))+upper
            if cost+Decimal(journal.get('actual_cost','0')) > Decimal(str(cap)): raise TransportError('Исчерпан бюджет расходов. Ответ сохранён.')
            journal['reserved_cost'] = str(cost)
        journal['reserved_tokens'] = reserved+input_bound+limit
        journal['pending'] = {'slot':slot,'offset':sum(len(p['text']) for p in record['parts']),'text':''}
        repo.save_response_journal(jid,journal)  # commit BEFORE opening a paid request
        def settle(metadata, rejected=False):
            inp,out=metadata.get('input_tokens'),metadata.get('output_tokens')
            known=type(inp) is int and type(out) is int
            if known or rejected:
                journal['reserved_tokens']=reserved
                if known:journal['actual_tokens']=journal.get('actual_tokens',0)+inp+out
            amount=metadata.get('cost_usd')
            if amount is not None or rejected:
                journal['reserved_cost']=previous_cost
                if amount is not None:journal['actual_cost']=str(Decimal(journal.get('actual_cost','0'))+Decimal(amount))
        fragment = ''; ended = False
        try:
            try:
                for chunk in generate(request,limit):
                    fragment += chunk
                    journal['pending']['text'] = fragment
                    repo.save_response_journal(jid,journal)
                    repo.preparation_progress(jid,text+fragment)
                    if cancel.is_set(): return None
                ended = True
            except OutputLimitReached:
                ended = False
            if cancel.is_set(): return None
        except ProviderHTTPError as exc:
            # A rejected HTTP request before streaming has a known outcome.
            metadata=accounting()
            settle(metadata,rejected=not bool(fragment))
            journal['pending']=None
            journal.setdefault('http_failures',[]).append(dict(slot=slot,status=exc.status_code,reservation_released=not bool(fragment)))
            retries=record.get('http_retries',0)
            record['http_retries']=retries+1
            repo.save_response_journal(jid,journal)
            if exc.status_code in (429,503) and not fragment and retries<2:
                if cancel.wait(min(2**retries,4)):return None
                continue
            raise TransportError(f'Провайдер отклонил запрос: HTTP {exc.status_code}. Ответ сохранён.') from None
        except Exception:
            # Network errors and cancellation have unknown billing/output, even
            # if no visible characters arrived. Do not turn them into a retry.
            raise TransportError('Запрос прерван; его исход неизвестен. Полученный текст сохранён, слепой повтор запрещён.') from None
        metadata=accounting()
        settle(metadata)
        part = dict(provider=config.get('provider'),model=re.sub(r'[^A-Za-z0-9_./:-]','',str(config.get('model','')))[:128],request_id=metadata.get('id'),usage=json.loads(metadata['usage_json']) if metadata.get('usage_json') else None,provider_finish_reason=metadata.get('finish_reason'),text=fragment,sha256=hashlib.sha256(fragment.encode()).hexdigest(),offset=sum(len(p['text']) for p in record['parts']),requested_output_limit=limit,finish_reason='stop' if ended else 'length')
        # Verify the prior manifest before extending it; retain every raw part.
        record.pop('assembly',None)
        record['parts'].append(part)
        record['complete'] = ended
        journal['pending'] = None
        repo.save_response_journal(jid,journal)
        repo.preparation_progress(jid,text+fragment)
        text=assemble()
        repo.preparation_progress(jid,text)
        if record['document_state']!='incomplete' or (ended and not text):
            record['complete']=True
            repo.save_response_journal(jid,journal)
            return text
        record['complete']=False
        repo.save_response_journal(jid,journal)
        if not fragment:raise TransportError('Пустое продолжение: ответ сохранён, автоматический повтор остановлен.')
    return None
