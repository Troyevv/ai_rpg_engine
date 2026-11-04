"""Pure, atomic proposals for pre-game drafts; persistence remains DraftStorage.

The proposal is bound to an exact canonical candidate. Operations are evaluated
on a copy, then validated together, so new records may refer to each other.
No partial prefix, server provenance, or model-supplied authority is applied.
"""
from copy import deepcopy
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.repositories.drafts import candidate_hash
from backend.services.draft_response import strict_loads
from backend.services.draft_completeness import pointer
from backend.services.draft_initial import inspect_candidate, prompt_schema, DraftErrors


class ProposalError(ValueError):
    def __init__(self, message, *, proposal_paths=(), world_paths=(), drop_indices=()):
        super().__init__(message)
        self.proposal_paths=list(proposal_paths)
        self.world_paths=list(world_paths)
        self.drop_indices=list(drop_indices)


class Change(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    op: Literal['add', 'replace']
    path: str
    value: Any
    reason: str = Field(min_length=1)


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    candidate_hash: str
    rationale: str = Field(min_length=1)
    changes: list[Change]


def preserve(before, after, path):
    try:
        if pointer(before, path) == pointer(after, path):
            return
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    raise ValueError('Предложение меняет защищённое значение: '+path)


def apply_proposal(state, reply):
    proposal = Proposal.model_validate(strict_loads(reply))
    if proposal.candidate_hash != candidate_hash(state):
        raise ValueError('Кандидат изменился; творческое предложение устарело.')
    trial = deepcopy(state)
    schema = prompt_schema()['properties']
    sections = set(schema['world']['properties']) - {'version', 'communication', 'scene_records'}
    paths = [c.path for c in proposal.changes if c.path not in ('/characters/-', '/locations/-')]
    if len(set(paths)) != len(paths) or any(a.startswith(b+'/') for a in paths for b in paths if a != b):
        raise ValueError('Пересекающиеся пути предложения.')
    for index, change in enumerate(proposal.changes):
        path = change.path
        if not path.startswith('/') or re.search(r'~(?![01])', path):
            raise ValueError('Некорректный JSON Pointer.')
        parts = [p.replace('~1', '/').replace('~0', '~') for p in path[1:].split('/')]
        root = parts[0]
        allowed = (root == 'world' and len(parts) >= 3 and parts[1] in sections
                   or root in ('characters', 'locations') and len(parts) >= 2
                   or root == 'campaign' and len(parts) == 2 and parts[1] in schema['campaign']['properties'])
        if not allowed:
            raise ProposalError('Путь вне разрешённого канона: '+path, proposal_paths=[f'/changes/{index}/path'], drop_indices=[index])
        # Entity-field scope comes from the existing generation schema. Unknown
        # fields must not become invisible side channels around canonical checks.
        record_schema = (schema['world']['properties'][parts[1]].get('additionalProperties', {})
                         if root == 'world' else schema[root].get('items', {}) if root in ('characters', 'locations') else {})
        field_index = 3 if root == 'world' else 2
        if root != 'campaign' and len(parts) > field_index and parts[field_index] not in record_schema.get('properties', {}):
            raise ProposalError('Неизвестное поле сущности: '+path, proposal_paths=[f'/changes/{index}/path'], drop_indices=[index])
        if root in ('characters', 'locations') and len(parts) == 2:
            if change.op != 'add' or parts[1] != '-' or not isinstance(change.value, dict):
                raise ValueError('Карточки добавляются через /-; существующие меняются по полям.')
            ident = change.value.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[\w-]{1,100}', ident) or any(row['id'] == ident for row in trial[root]):
                raise ValueError('Отсутствующий или занятый ID карточки.')
            if root == 'characters' and change.value.get('is_player'):
                raise ValueError('Нельзя передавать управление новому персонажу.')
            trial[root].append(deepcopy(change.value))
            continue
        # A whole record replacement would hide identity/provenance changes.
        if root == 'world' and len(parts) == 3:
            if change.op != 'add' or parts[2] in trial['world'][parts[1]]:
                raise ValueError('Новый ID занят; существующую запись меняйте по полям.')
            if not isinstance(change.value, dict) or change.value.get('id', parts[2]) != parts[2]:
                raise ProposalError('ID не совпадает с адресом записи.', proposal_paths=[f'/changes/{index}/value/id'])
        elif parts[-1] in ('id', 'is_player'):
            raise ValueError('Идентичность неизменна.')
        parent_path = path.rsplit('/', 1)[0]
        try:
            parent = pointer(trial, parent_path)
            key = parts[-1]
            if not isinstance(parent, dict):
                raise ValueError('Меняйте список целиком, без сдвига адресов.')
            if (key in parent) != (change.op == 'replace'):
                raise ProposalError('Предусловие add/replace не выполнено.', proposal_paths=[f'/changes/{index}/op'])
            parent[key] = deepcopy(change.value)
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('Родительский путь не существует: '+path) from exc
    # Reject authority minted inside nested objects, not only at patch paths.
    def provenance(old, new):
        if isinstance(new, dict):
            for key, value in new.items():
                previous = old.get(key) if isinstance(old, dict) else None
                if key in ('birth_provenance', 'birth_date_provenance', 'authoring', 'source_turn', 'field_facts', 'revision') and previous != value:
                    raise ValueError('Модель не может назначать серверное происхождение: '+key)
                provenance(previous, value)
        elif isinstance(new, list):
            for i, value in enumerate(new):
                provenance(old[i] if isinstance(old, list) and i < len(old) else None, value)
    provenance(state, trial)
    actor = state['controlled_actor_id']
    for field in ('goals', 'short_goal', 'intentions', 'obligations', 'emotion'):
        path = '/world/characters/'+actor.replace('~', '~0').replace('/', '~1')+'/'+field
        if field in state['world']['characters'][actor]:
            preserve(state, trial, path)
        elif trial['world']['characters'][actor].get(field):
            raise ValueError('Запрещено принимать решения за игрока.')
    for key, event in trial['world']['scheduled_events'].items():
        prior = state['world']['scheduled_events'].get(key)
        if prior is None:
            if event.get('time_semantics', 'explicit') != 'explicit':
                raise ValueError('Новый план не может использовать legacy-семантику времени.')
            event['time_semantics'] = 'explicit'
            event.setdefault('time_reference_minute', state['world_clock']['minute'])
        elif event.get('time_semantics') != prior.get('time_semantics'):
            raise ValueError('Семантика времени существующего плана защищена.')
        if event.get('commitment') and actor in event.get('participants', []) and event != state['world']['scheduled_events'].get(key):
            raise ValueError('Новое обязательство игрока требует его решения.')
    for path in state.get('authoring', {}).get('manual_paths', []):
        preserve(state, trial, path)
    normalized, report = inspect_candidate(trial)
    if report['errors']:
        raise DraftErrors(report['diagnostics'])
    for path in state.get('authoring', {}).get('manual_paths', []):
        preserve(state, normalized, path)
    return normalized, proposal.model_dump()
