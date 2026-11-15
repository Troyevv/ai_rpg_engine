"""Request-local metadata for the existing usage journal (never prompt content).

Context-local routing lets the optional QA Budget attach its reservation without
changing provider wire parameters or adding a second production log.
"""
from contextvars import ContextVar
import hashlib
import re

CURRENT = ContextVar('provider_attempt', default=None)


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value) else None


def emit(**fields):
    current = CURRENT.get()
    if current is not None:
        current['data'].update(fields)
        persist = current.get('persist')
        if persist is not None:
            persist(current['data'])


def identity():
    current = CURRENT.get()
    return {k: v for k, v in (current['data'] if current else {}).items()
            if k in ('request_id', 'job_id', 'stage', 'attempt_epoch', 'reservation_id')}


def failure(exc):
    """No arbitrary exception text: SDK errors may echo headers/body/credentials.

    Retain the original class, causal chain and message digest before adapters
    translate it. Protocol codes are assigned by our parser, not provider text.
    """
    chain = []; seen = set(); item = exc
    while item is not None and id(item) not in seen and len(chain) < 5:
        seen.add(id(item))
        row = dict(type=type(item).__name__,
                   message_sha256=hashlib.sha256(str(item).encode()).hexdigest())
        status = getattr(item, 'status_code', None)
        if type(status) is int and 100 <= status <= 599: row['http_status'] = status
        chain.append(row)
        item = item.__cause__ or item.__context__
    result = dict(type=type(exc).__name__, chain=chain)
    if isinstance(exc, ResponseStreamError): result['code'] = exc.code
    return result


def failed(exc):
    current = CURRENT.get()
    # Keep the first failure, not its user-facing adapter translation.
    if current is not None and 'error' not in current['data']:
        emit(error=failure(exc))


class ResponseStreamError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
