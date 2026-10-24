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
from llm import OutputLimitReached

MAX_FRAGMENTS = 5
CONTINUE = ('Продолжи тот же JSON строго с места остановки. Не начинай объект заново, '
            'не повторяй уже выведенный текст и не изменяй ранее созданные данные. '
            'Верни только недостающую часть без Markdown и пояснений.')


class TransportError(ValueError):
    pass


class _Incomplete(Exception):
    pass


def prefix_complete(text):
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
    def value(depth=0):
        nonlocal i
        if depth > 100: raise TransportError('Слишком глубокая вложенность JSON.')
        whitespace(); need(); ch = text[i]
        if ch == '"': string(); return
        if ch in '{[':
            close = '}' if ch == '{' else ']'; is_object = ch == '{'; i += 1
            whitespace(); need()
            if text[i] == close: i += 1; return
            while True:
                whitespace(); need()
                if is_object:
                    if text[i] != '"': raise TransportError('Ожидался ключ JSON-объекта.')
                    string(); whitespace(); need()
                    if text[i] != ':': raise TransportError('Ожидалось двоеточие JSON.')
                    i += 1
                value(depth+1); whitespace(); need()
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
        value(); whitespace()
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


def join_fragments(parts):
    result = ''
    for part in parts:
        text = part['text']
        if hashlib.sha256(text.encode()).hexdigest() != part['sha256']:
            raise TransportError('Нарушена целостность сохранённого фрагмента.')
        if part['offset'] != len(result): raise TransportError('Пропущен или переставлен фрагмент JSON.')
        if result:
            # Ambiguous overlap is rejected, never silently deduplicated. Small
            # punctuation overlaps are normal JSON and are checked by grammar.
            # KMP computes overlap in linear time even for long biographies.
            combined=text+'\x00'+result[-len(text):]
            prefix=[0]*len(combined)
            for i in range(1,len(combined)):
                j=prefix[i-1]
                while j and combined[i]!=combined[j]:j=prefix[j-1]
                if combined[i]==combined[j]:j+=1
                prefix[i]=j
            if prefix and prefix[-1]>=16:
                raise TransportError('Повтор текста на границе фрагментов. Ответ сохранён; склейка неоднозначна.')
        result += text
        prefix_complete(result)
    return result


def response(repo,jid,journal,slot,messages,config,context,generate,cancel):
    record = journal.setdefault('responses',{}).setdefault(slot,{'parts':[],'complete':False})
    # Finished (including syntactically invalid) replies belong to validation,
    # not another request. Preserve them byte-for-byte for bounded repair.
    if record['complete']:
        for part in record['parts']:
            if hashlib.sha256(part['text'].encode()).hexdigest()!=part['sha256']:
                raise TransportError('Нарушена целостность сохранённого ответа.')
        return join_fragments(record['parts']) if len(record['parts'])>1 else ''.join(p['text'] for p in record['parts'])
    text = join_fragments(record['parts'])
    if journal.get('pending'): raise TransportError('Исход прошлого запроса неизвестен; повтор запрещён.')
    while not cancel.is_set():
        if len(record['parts']) >= MAX_FRAGMENTS: raise TransportError('Исчерпан лимит пяти фрагментов. Ответ сохранён.')
        request = deepcopy(messages)
        if text:
            request += [{'role':'assistant','content':text},{'role':'user','content':CONTINUE}]
            repo.draft_phase(jid,'continuing')
        input_bound = estimate(request)+512
        limit = min(config['max_tokens'],context-input_bound)
        if limit < 256: raise TransportError('Контекст не вмещает полный запрос и продолжение. Текст сохранён, запрос не отправлен.')
        # A conservative reserved token envelope bounds even calls with missing
        # provider usage. Accounting remains actual usage in llm_requests.
        budget = config.get('_draft_token_budget',3*MAX_FRAGMENTS*(context+config['max_tokens']))
        reserved = journal.get('reserved_tokens',0)
        if reserved+input_bound+limit > budget: raise TransportError('Исчерпан бюджет токенов генерации. Ответ сохранён.')
        cap = config.get('_draft_cost_budget_usd')
        if cap is not None:
            from backend.services.usage import price_snapshot
            from datetime import datetime, timezone
            pricing = price_snapshot(config,datetime.now(timezone.utc))
            if pricing is None: raise TransportError('Тариф неизвестен: нельзя гарантировать бюджет расходов.')
            upper = Decimal(0) if pricing['version']=='local' else (input_bound*Decimal(pricing['input'])+limit*Decimal(pricing['output']))/1000000
            cost = Decimal(journal.get('reserved_cost','0'))+upper
            if cost > Decimal(str(cap)): raise TransportError('Исчерпан бюджет расходов. Ответ сохранён.')
            journal['reserved_cost'] = str(cost)
        journal['reserved_tokens'] = reserved+input_bound+limit
        journal['pending'] = {'slot':slot,'offset':len(text),'text':''}
        repo.save_response_journal(jid,journal)  # commit BEFORE opening a paid request
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
        except Exception:
            # Network errors and cancellation have unknown billing/output, even
            # if no visible characters arrived. Do not turn them into a retry.
            raise TransportError('Запрос прерван; его исход неизвестен. Полученный текст сохранён, слепой повтор запрещён.') from None
        part = dict(text=fragment,sha256=hashlib.sha256(fragment.encode()).hexdigest(),offset=len(text),finish_reason='stop' if ended else 'length')
        record['parts'].append(part)
        record['complete'] = ended
        journal['pending'] = None
        repo.save_response_journal(jid,journal)
        repo.preparation_progress(jid,text+fragment)
        if ended:
            # Verify continuation boundaries even on the terminal reply. The
            # first full response may instead need syntax repair.
            if text: return join_fragments(record['parts'])
            return fragment
        if not fragment: raise TransportError('Лимит ответа исчерпан без текста. Автоматическое увеличение лимита запрещено.')
        text = join_fragments(record['parts'])
    return None
