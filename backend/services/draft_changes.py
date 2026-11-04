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
from backend.services.draft_initial import inspect_candidate, prompt_schema, DraftErrors, SERVER_FIELDS


class ProposalError(ValueError):
    def __init__(self, message, *, proposal_paths=(), world_paths=(), drop_indices=(), remove_paths=()):
        super().__init__(message)
        self.proposal_paths=list(proposal_paths)
        self.world_paths=list(world_paths)
        self.drop_indices=list(drop_indices)
        self.remove_paths=list(remove_paths)


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


def author_value(old, new, path=""):
    """Enforce ownership BEFORE Runtime defaults. Match list records by identity.

    Omitted existing metadata is inherited, never reset by a content-only edit.
    Only exact default echoes in new Motivation/Knowledge records are redundant;
    other assignments must be diagnosed and explicitly corrected.
    """
    from backend.runtime_v3.models import Motivation, Knowledge
    result = deepcopy(new)
    errors, removable = [], []
    def walk(previous, value, at):
        if isinstance(value, dict):
            prior = previous if isinstance(previous, dict) else {}
            model = (Motivation if re.fullmatch(r'/world/characters/[^/]+/(goals|intentions|obligations)/[^/]+', at)
                     else Knowledge if re.fullmatch(r'/world/knowledge/[^/]+', at) else None)
            protected = SERVER_FIELDS | ({'source_event_id'} if model is Motivation else set())
            for key in prior.keys() & protected:
                if key not in value:value[key] = deepcopy(prior[key])
            for key in list(value):
                child = at+'/'+str(key).replace('~','~0').replace('/','~1')
                if key in protected:
                    if key in prior and type(prior[key]) is type(value[key]) and prior[key] == value[key]:continue
                    field = model.model_fields.get(key) if model else None
                    if previous is None and field is not None and not field.is_required():
                        default = field.get_default(call_default_factory=True)
                        if type(default) is type(value[key]) and default == value[key]:
                            del value[key]
                            continue
                    errors.append(child)
                    if previous is None:removable.append(child)
                else:walk(prior.get(key), value[key], child)
        elif isinstance(value, list):
            prior = previous if isinstance(previous, list) else []
            by_id = {v['id']:v for v in prior if isinstance(v,dict) and isinstance(v.get('id'),str)}
            for i, item in enumerate(value):
                prev = by_id.get(item['id']) if isinstance(item,dict) and isinstance(item.get('id'),str) else prior[i] if i < len(prior) else None
                walk(prev, item, at+'/'+str(i))
    # Direct writes to protected fields must not evade the recursive walk.
    key = path.rsplit('/',1)[-1]
    if path and (key in SERVER_FIELDS or key == 'source_event_id' and re.fullmatch(r'/world/characters/[^/]+/(goals|intentions|obligations)/[^/]+/source_event_id', path)):
        if type(old) is not type(new) or old != new:
            raise ProposalError('Модель не может назначать серверное происхождение: '+key, world_paths=[path])
    walk(old, result, path)
    if errors:
        raise ProposalError('Модель не может назначать серверное происхождение: '+', '.join(errors),
                            world_paths=errors, remove_paths=removable)
    return result


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
    problems = []
    append_indices = {root:len(state[root]) for root in ('characters','locations')}
    for index, change in enumerate(proposal.changes):
        try:
            path = change.path
            if not path.startswith('/') or re.search(r'~(?![01])', path):
                raise ProposalError('Некорректный JSON Pointer.', proposal_paths=[f'/changes/{index}/path'])
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
            if root != 'campaign' and len(parts) > field_index and parts[field_index] not in record_schema.get('properties', {}) and parts[field_index] not in SERVER_FIELDS:
                raise ProposalError('Неизвестное поле сущности: '+path, proposal_paths=[f'/changes/{index}/path'], drop_indices=[index])
            value_path = path
            if path in ('/characters/-','/locations/-'):
                value_path = f'/{root}/{append_indices[root]}'
                append_indices[root] += 1
            if change.op != 'remove':
                try: old = pointer(state, path)
                except (KeyError, IndexError, TypeError, ValueError): old = None
                change.value = author_value(old, change.value, value_path)
        except ProposalError as exc:
            problems.append(exc)
    if problems:
        raise ProposalError('; '.join(str(e) for e in problems),
            proposal_paths=[p for e in problems for p in e.proposal_paths],
            world_paths=[p for e in problems for p in e.world_paths],
            drop_indices=[p for e in problems for p in e.drop_indices],
            remove_paths=[p for e in problems for p in e.remove_paths])
    for index, change in enumerate(proposal.changes):
        path = change.path
        parts = [p.replace('~1', '/').replace('~0', '~') for p in path[1:].split('/')]
        root = parts[0]
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
    # Removing a card also removes its draft-only field bindings. A surviving
    # card keeps its bindings and may still block deletion of a referenced fact.
    if removals and 'card_field_facts' in trial:
        remaining={c['id'] for c in trial['characters']}
        trial['card_field_facts']={k:v for k,v in trial['card_field_facts'].items() if k in remaining}
        if not trial['card_field_facts']:trial.pop('card_field_facts')
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
    trial = author_value(state, trial)
    return validate_candidate(state, trial, editing=editing)


def validate_candidate(state, trial, *, editing=False):
    """Validate server-normalized candidates; raw LLM boundaries use author_value.

    No provenance bypass for model replies: proposal/semantic repair entry points
    validate ownership before normalization. Persisted previews are server output.
    """
    trial = deepcopy(trial)
    for key in ('controlled_actor_id','protagonist_id','camera','world_clock','creation_settings','authoring'):
        if state.get(key)!=trial.get(key):raise ValueError('Предложение меняет защищённый контекст: '+key)
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
