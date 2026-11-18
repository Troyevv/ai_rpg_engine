"""Read one complete JSON object. Recorded contracts reject duplicate keys."""
import json
from itertools import chain


class DuplicateKey(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey('Duplicate JSON key')
        result[key] = value
    return result


def _decode(payload, hook):
    normalization = None
    if isinstance(payload, str):
        text = payload.strip()
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0] in ('```', '```json') and lines[-1] == '```':
            text = '\n'.join(lines[1:-1])
            normalization = 'single_json_fence'
        payload = json.loads(text, object_pairs_hook=hook)
    return payload, normalization


def object_payload(payload):
    value, normalization = _decode(payload, _unique)
    if not isinstance(value, dict):
        raise ValueError('Expected one JSON object')
    return value, normalization


def consequence_payload(payload, list_sections):
    try:
        value, normalization = object_payload(payload)
        return value, normalization, []
    except DuplicateKey:
        pass

    class Pairs(list):
        """Distinguish an object with repeated keys from a JSON array."""

    def unpack(value):
        if isinstance(value, Pairs):
            return _unique((k, unpack(v)) for k, v in value)
        if isinstance(value, list):
            return [unpack(item) for item in value]
        return value

    pairs, normalization = _decode(payload, Pairs)
    if not isinstance(pairs, Pairs):
        raise ValueError('Expected one JSON object')
    grouped = {}
    for key, value in pairs:
        grouped.setdefault(key, []).append(value)
    result, warnings = {}, []
    for key, values in grouped.items():
        if key in list_sections and all(type(value) is list for value in values):
            # Arrays are proposals in response order. The normal section limits,
            # canonical ID checks and dependency groups still apply to the union.
            rows = []
            if len(values)>1:
                warnings.append(dict(section=key,code='repeated_section',action='combine_records'))
            for index, item in enumerate(chain.from_iterable(values)):
                try:
                    rows.append(unpack(item))
                except DuplicateKey:
                    warnings.append(dict(section=key, index=index, code='duplicate_record_key', action='skip_record'))
                    # Positional step identities and choice indices must survive
                    # until the compiler assigns IDs and validates each group.
                    if key in ('scene_steps', 'choices'):
                        rows.append(None)
            result[key] = rows
        else:
            try:
                if len(values)!=1:
                    raise DuplicateKey()
                result[key] = unpack(values[0])
            except DuplicateKey:
                warnings.append(dict(section=key,code='duplicate_record_key',action='skip_section'))
    return result, normalization, warnings
