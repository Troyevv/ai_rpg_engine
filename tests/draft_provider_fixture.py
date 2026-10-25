"""Explicit semantic acceptance stub for tests of transport/editor mechanics only.

These tests do not measure semantic recall. test_draft_completeness exercises the
review/repair contract with the unabridged real DeepSeek response separately.
"""
from functools import wraps
from backend.services.draft_completeness import MARKER


def accept_semantics_unchecked(stream):
    @wraps(stream)
    def wrapped(**kwargs):
        if kwargs['messages'][0]['content'].startswith(MARKER):
            yield '{"issues":[]}'
            return
        if kwargs['messages'][0]['content'].startswith('Один необязательный пакет'):
            # Transport-only tests explicitly reject optional completion.
            # They do not claim narrative-quality acceptance.
            yield '{"patches":[]}'
            return
        yield from stream(**kwargs)
    return wrapped


_protocol_attempts={}
def protocol_review(request):
    """Shared browser/API fixture: malformed report, correction, alternate audit."""
    import json
    source=request.get('author_context','')
    if 'TEST_REVIEW_PROTOCOL' not in source and 'TEST_REVIEW_AUTOMATIC' not in source:return None
    count=_protocol_attempts.get(source,0);_protocol_attempts[source]=count+1
    if count<2:return '{"issues":[{"path":"/world/world/roles/missing","message":"Неверный корень отчёта"}]}'
    if request.get('strategy')=='scoped_reaudit':
        if count==2 and 'TEST_REVIEW_PROTOCOL' in source:
            from llm import ProviderHTTPError
            raise ProviderHTTPError('Controlled temporary reviewer outage',502)
        return json.dumps({'resolutions':[dict(issue_id=p['issue_id'],resolution='replaced',reason='Проверка исходных ролей завершена; блокирующего противоречия нет.',issues=[dict(message='Необязательное уточнение роли',severity='recommendation')]) for p in request['pending_issues']]})
    return '{"issues":[{"message":"Необязательное уточнение роли","severity":"recommendation"}]}'
