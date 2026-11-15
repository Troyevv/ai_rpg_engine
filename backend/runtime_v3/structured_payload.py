"""Decode one complete JSON object, optionally in a single Markdown fence.

Transport completeness is checked by the provider before this parser is called.
No substring extraction, syntax repair, or interpretation of prose.
"""
import json


def object_payload(payload):
    normalization = None
    if isinstance(payload, str):
        text = payload.strip()
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0] in ('```', '```json') and lines[-1] == '```':
            text = '\n'.join(lines[1:-1])
            normalization = 'single_json_fence'
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = value
            return result
        payload = json.loads(text, object_pairs_hook=unique)
    if not isinstance(payload, dict):
        raise ValueError('Expected one JSON object')
    return payload, normalization
