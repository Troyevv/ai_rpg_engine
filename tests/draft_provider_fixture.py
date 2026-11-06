"""Explicit semantic acceptance stub for tests of transport/editor mechanics only.

These tests do not measure semantic recall. test_draft_completeness exercises the
review/repair contract with the unabridged real DeepSeek response separately.
"""
import json
from functools import wraps
from backend.services.draft_creative import MARKER as CREATIVE_MARKER


def creative_noop(messages):
    payload=json.loads(messages[1]["content"])
    return json.dumps(dict(candidate_hash=payload["candidate_hash"], rationale="Transport fixture: retain supplied world; this is not a creative quality evaluation.", changes=[]))


def accept_creative_unchecked(stream):
    @wraps(stream)
    def wrapped(**kwargs):
        if kwargs["messages"][0]["content"].startswith(CREATIVE_MARKER):
            yield creative_noop(kwargs["messages"]);return
        yield from stream(**kwargs)
    return wrapped

from backend.services.draft_completeness import MARKER


def accept_semantics_unchecked(stream):
    @accept_creative_unchecked
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
    if not any(marker in source for marker in ('TEST_REVIEW_PROTOCOL','TEST_REVIEW_AUTOMATIC','TEST_RELEASE_NESTED')):return None
    count=_protocol_attempts.get(source,0);_protocol_attempts[source]=count+1
    if count<2 and 'TEST_RELEASE_NESTED' in source:return '{"issues":[null]}' if count==0 else '{"issues":[{"path":"/campaign/title","message":"x","basis":null}]}'
    if count<2:return '{"issues":[{"path":"/world/world/roles/missing","message":"Неверный корень отчёта"}]}'
    if request.get('strategy')=='scoped_reaudit':
        if count==2 and 'TEST_REVIEW_PROTOCOL' in source:
            from llm import ProviderHTTPError
            raise ProviderHTTPError('Controlled temporary reviewer outage',502)
        return json.dumps({'resolutions':[dict(issue_id=p['issue_id'],resolution='replaced',reason='Проверка исходных ролей завершена; блокирующего противоречия нет.',issues=[dict(message='Необязательное уточнение роли',severity='recommendation')]) for p in request['pending_issues']]})
    return '{"issues":[{"message":"Необязательное уточнение роли","severity":"recommendation"}]}'


def provider_world(state):
    """Adapt a legacy canonical snapshot to the current provider input contract."""
    from copy import deepcopy
    raw=deepcopy(state)
    assert not raw['world'].get('contacts'), 'Do not discard meaningful legacy records'
    raw['world'].pop('contacts',None)
    return json.dumps(raw,ensure_ascii=False)
