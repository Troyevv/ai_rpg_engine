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
    op: Literal['add', 'replace', 'remove']
    path: str
    value: Any
    reason: str = Field(min_length=1)


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    candidate_hash: str
    rationale: str = Field(min_length=1)
    changes: list[Change]
    conflicts: list[str] = Field(default_factory=list)


def preserve(before, after, path):
    try:
        if pointer(before, path) == pointer(after, path):
            return
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    raise ValueError('Предложение меняет защищённое значение: '+path)


def apply_proposal(state, reply, *, editing=False):
    proposal = Proposal.model_validate(strict_loads(reply))
    if proposal.conflicts and not editing:
        raise ValueError('Творческое предложение содержит нерешённые авторские конфликты.')
    if proposal.candidate_hash != candidate_hash(state):
        raise ValueError('Кандидат изменился; творческое предложение устарело.')
    trial = deepcopy(state)
    schema = prompt_schema()['properties']
    sections = set(schema['world']['properties']) - {'version', 'communication', 'scene_records'}
    paths = [c.path for c in proposal.changes if c.path not in ('/characters/-', '/locations/-')]
    if len(set(paths)) != len(paths) or any(a.startswith(b+'/') for a in paths for b in paths if a != b):
        raise ValueError('Пересекающиеся пути предложения.')
    removals = []
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
        if change.op == 'remove':
            if not editing:
                raise ValueError('Удаление разрешено только в предпросмотре AI-редактора.')
            if not (root == 'world' and len(parts) == 3 or root in ('characters', 'locations') and len(parts) == 2):
                raise ValueError('Удалять можно только целые сущности с зависимостями.')
            if pointer(state, path) != change.value:
                raise ValueError('Предусловие удаления не выполнено.')
            if root == 'characters' and change.value.get('id') in (state.get('controlled_actor_id'), state.get('protagonist_id')):
                raise ValueError('Нельзя удалить управляемого персонажа или протагониста.')
            removals.append((parts, path))
            continue
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
    # Array indices always address the frozen base; remove only after assignments.
    for parts, path in sorted(removals, key=lambda item: int(item[0][1]) if item[0][0] in ('characters', 'locations') else -1, reverse=True):
        parent = pointer(trial, path.rsplit('/', 1)[0])
        del parent[int(parts[-1]) if isinstance(parent, list) else parts[-1]]
    normalized = validate_transition(state, trial, editing=editing)
    return normalized, proposal.model_dump()


def validate_removals(before, after):
    """Validate surviving dependencies on the final batch, never cascade history.

    Typed validation covers canonical references. The shared editor dependency
    walk also covers name/alias locations accepted by legacy migration and
    structured references in immutable scene records.
    """
    from backend.services.draft_world import dependencies, GROUPS
    from backend.services.draft_initial import error
    deleted=[]
    for root,kind in (('characters','character'),('locations','location')):
        remaining={row['id'] for row in after[root]}
        deleted.extend((kind,row['id']) for row in before[root] if row['id'] not in remaining)
    kinds={section:kind for kind,section in GROUPS.items()}
    for section,rows in before['world'].items():
        if section=='characters' or not isinstance(rows,dict):continue
        remaining=after['world'].get(section,{})
        deleted.extend((kinds.get(section,section),key) for key in rows if key not in remaining)
    problems=[]
    for kind,eid in deleted:
        for dependency in dependencies(after,kind,eid,original=before):
            path='/world/'+dependency['kind']+'/'+dependency['id'].replace('~','~0').replace('/','~1')
            problems.append(error(path,'Удаляемая сущность '+eid+' всё ещё связана с этой записью. Измените пакет или сохраните сущность.','reference'))
    if problems:raise DraftErrors(problems)


def validate_transition(state, trial, *, editing=False):
    for key in ('controlled_actor_id','protagonist_id','camera','world_clock','creation_settings','authoring'):
        if state.get(key)!=trial.get(key):raise ValueError('Предложение меняет защищённый контекст: '+key)
    # Reject authority minted inside nested objects, not only at patch paths.
    def provenance(old, new):
        if isinstance(new, dict):
            for key, value in new.items():
                previous = old.get(key) if isinstance(old, dict) else None
                if key in ('birth_provenance', 'birth_date_provenance', 'authoring', 'source_turn', 'field_facts', 'revision') and previous != value:
                    raise ValueError('Модель не может назначать серверное происхождение: '+key)
                provenance(previous, value)
        elif isinstance(new, list):
            old_list = old if isinstance(old, list) else []
            by_id = {v['id']:v for v in old_list if isinstance(v,dict) and isinstance(v.get('id'),str)}
            for i, value in enumerate(new):
                previous = by_id.get(value['id']) if isinstance(value,dict) and isinstance(value.get('id'),str) else old_list[i] if i < len(old_list) else None
                provenance(previous, value)
    provenance(state, trial)
    actor = state['controlled_actor_id']
    if actor not in trial['world']['characters']:
        raise ValueError('Нельзя удалить управляемого персонажа.')
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
    if not editing:
        for path in state.get('authoring', {}).get('manual_paths', []):
            preserve(state, trial, path)
    if editing:validate_removals(state,trial)
    normalized, report = inspect_candidate(trial)
    if report['errors']:
        raise DraftErrors(report['diagnostics'])
    if not editing:
        for path in state.get('authoring', {}).get('manual_paths', []):
            preserve(state, normalized, path)
    return normalized
