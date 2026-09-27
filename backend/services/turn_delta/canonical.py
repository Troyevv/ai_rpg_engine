"""Raw scene/choice boundary and runtime-owned canonical resolution."""
from copy import deepcopy
from dataclasses import dataclass
from backend.services.world_delta_errors import StructuralDeltaError


@dataclass(frozen=True)
class RawExtraction:
    """Untrusted claims; legacy redundant fields have no authority."""
    payload: dict

    @classmethod
    def parse(cls, value):
        import json
        from state_updates import exact_keys
        try:
            payload=json.loads(value) if isinstance(value,str) else deepcopy(value)
        except json.JSONDecodeError as exc:
            raise StructuralDeltaError(str(exc),'schema_invalid') from exc
        exact_keys(payload,('scene','choices','world_delta','derivations'),('scene','choices','world_delta'))
        payload.pop('derivations',None)
        scene=payload['scene']
        if isinstance(scene,dict) and 'elapsed_minutes' in scene:scene.pop('time',None)
        delta=payload['world_delta']
        # Normalize only documented redundant legacy leaves. Other unknown keys,
        # mandatory values and malformed arrays still reach strict schema parsing.
        if isinstance(delta,dict):
            for section,field in (('characters','location'),('transitions','from_location')):
                if isinstance(delta.get(section),list):
                    for record in delta[section]:
                        if isinstance(record,dict):record.pop(field,None)
        return cls(payload)


def prepare_scene(before, payload, kind):
    from state_updates import exact_keys, text
    from backend.services.timeline import label, current_time
    state=deepcopy(before)
    ids=set(state['world']['characters'])
    def known(values):
        if not isinstance(values,list) or any(not isinstance(v,str) or v not in ids for v in values):
            raise StructuralDeltaError('Неизвестный персонаж в сцене.','unknown_character')
        return list(dict.fromkeys(values))
    scene = payload['scene']
    exact_keys(scene, ['text', 'time', 'location', 'present_ids', 'elapsed_minutes'], ['text', 'location', 'present_ids'])
    if 'elapsed_minutes' in scene and (type(scene['elapsed_minutes']) is not int or not 0<=scene['elapsed_minutes']<=10080):
        raise StructuralDeltaError('Некорректная длительность scene.elapsed_minutes.', code='schema_invalid')
    state['scene'] = text(scene['text'], 'scene.text')
    state['sections']['scene'] = state['scene']
    state['scene_meta'] = {'time': text(scene.get('time',label(current_time(before))), 'time', 120), 'location': text(scene['location'], 'location', 200),
                           'present_ids': known(scene['present_ids'])}
    choices = payload['choices']
    expected_choices = 0 if kind=='background' else 6
    if not isinstance(choices,list) or len(choices)!=expected_choices:
        raise StructuralDeltaError('Для закулисной сцены нужен пустой choices.' if kind=='background' else 'Нужно ровно 6 вариантов действий.', code='schema_invalid')
    normalized = []
    for choice in choices:
        exact_keys(choice, ['action', 'speech'], ['action'])
        action = text(choice['action'], 'action', 500)
        speech = choice.get('speech') or ''
        if not isinstance(speech, str) or len(speech) > 1000:
            raise StructuralDeltaError('Некорректная реплика варианта.', code='schema_invalid')
        normalized.append({'action': action, 'speech': speech.strip()})
    if len({(c['action'].casefold(), c['speech'].casefold()) for c in normalized}) != expected_choices:
        raise StructuralDeltaError('Варианты действий повторяются.', code='schema_invalid')
    return state, normalized


@dataclass(frozen=True)
class CanonicalTurnDelta:
    """Runtime-owned resolution, never parsed from LLM JSON."""
    claims: dict
    spatial: dict

    @classmethod
    def resolve(cls, before, prepared, claims, since):
        from .resolver import resolve_final_state
        return cls(deepcopy(claims),resolve_final_state(before,prepared,claims,since))
