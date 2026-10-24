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
        yield from stream(**kwargs)
    return wrapped
