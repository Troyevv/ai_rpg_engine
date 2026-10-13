"""Evidence-bound continuity objects inside Runtime v3.

History owns chronology; Knowledge owns perception. Neither title nor physical
custody grants omniscience. No prices, slots, equipment or automatic movement.
"""
import json
import logging
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel, SignificantPossession, identity

FIELDS = ('owner_id', 'holder_id', 'location_id', 'status')


class PossessionDelta(StrictModel):
    item_id: str = Field(min_length=1, max_length=100)
    operation: Literal['introduce', 'acquire', 'transfer', 'gift', 'sell', 'lose', 'recover', 'return', 'destroy', 'relocate']
    name: str | None = Field(default=None, min_length=1, max_length=160)
    kind: str | None = Field(default=None, min_length=1, max_length=80)
    updates: dict[Literal['owner_id', 'holder_id', 'location_id', 'status'], str | None]
    expected_revision: int = Field(ge=0)
    assertion: Literal['completed_outcome']
    significance: Literal['continuity_required']
    transition: Literal['voluntary', 'involuntary', 'established']
    decision_actor_id: str | None = None
    source_event_id: str
    fact_id: str
    evidence: str = Field(min_length=1, max_length=1000)
    player_evidence: str = ''
    player_assertion: Literal['explicit_choice'] | None = None


def validate_record(row, state):
    for field in ('owner_id', 'holder_id'):
        if row[field] is not None and row[field] not in state['characters']:
            raise ValueError('Неизвестный персонаж вещи.')
    if row['location_id'] is not None and row['location_id'] not in state['locations']:
        raise ValueError('Неизвестное место вещи.')
    if row['status'] in ('lost', 'destroyed') and row['holder_id'] is not None:
        raise ValueError('У потерянной/уничтоженной вещи нет установленного держателя.')
    if any(fid not in state['facts'] for fid in [row['fact_id'], *row['field_facts'].values(), *row['applied'].values()] if fid):
        raise ValueError('Нет факта provenance вещи.')


def salvage_possessions(state):
    """Optional read migration only; never discover items in old prose."""
    raw = state.get('possessions', {})
    valid = {}
    for key, value in (raw.items() if isinstance(raw, dict) else []):
        try:
            row = SignificantPossession.model_validate(value).model_dump()
            if key != row['id']: raise ValueError('Конфликт ID вещи.')
            validate_record(row, state)
            valid[key] = row
        except (ValueError, TypeError):
            logging.getLogger(__name__).warning('Ignoring malformed optional possession %s', key)
    state['possessions'] = valid


def _transition(old, c):
    op, updates = c['operation'], c['updates']
    if not updates: raise ValueError('Пустое изменение вещи.')
    if op == 'introduce':
        if old or not c['name'] or not c['kind']:
            raise ValueError('Новая вещь требует отдельной подтверждённой идентичности.')
        return SignificantPossession(id=c['item_id'], name=c['name'], kind=c['kind'], **updates).model_dump()
    if not old: raise ValueError('Нужно использовать существующий canonical ID вещи.')
    if c['name'] is not None or c['kind'] is not None:
        raise ValueError('Переименование идентичности не является переходом владения.')
    if old['status'] == 'destroyed': raise ValueError('Уничтоженную вещь нельзя восстановить сменой владельца/места.')
    if c['transition'] == 'established': raise ValueError('Изменение требует совершившегося действия/последствия.')
    after = SignificantPossession.model_validate(dict(old, **updates)).model_dump()
    owner_changed = after['owner_id'] != old['owner_id']
    if op in ('sell', 'gift') and c['transition'] != 'voluntary':
        raise ValueError('Продажа/подарок требуют добровольного решения владельца.')
    if op in ('sell', 'gift', 'acquire'):
        if not owner_changed or after['owner_id'] is None:
            raise ValueError('Приобретение/продажа/подарок требуют нового владельца.')
    elif op != 'transfer' and owner_changed:
        raise ValueError('Потеря, возврат держателю и перемещение не меняют собственность.')
    if owner_changed and not {'holder_id', 'location_id'} <= updates.keys():
        raise ValueError('Передача собственности требует явного держателя и места, допустим null.')
    if after['holder_id'] != old['holder_id'] and 'location_id' not in updates:
        raise ValueError('Смена держателя требует места или явного null; не переносить старое место.')
    if op == 'lose':
        if old['status'] == 'lost' or after['status'] != 'lost' or after['holder_id'] is not None:
            raise ValueError('Потеря должна прекратить физическое обладание.')
        if 'location_id' not in updates: raise ValueError('Место после потери должно быть установлено явно или неизвестно.')
    elif op == 'destroy':
        if after['status'] != 'destroyed' or after['holder_id'] is not None:
            raise ValueError('Уничтожение прекращает физическое обладание.')
    elif op == 'recover':
        if old['status'] != 'lost' or after['status'] != 'available':
            raise ValueError('Найти можно потерянную вещь; результат должен быть available.')
        if after['holder_id'] is None and after['location_id'] is None:
            raise ValueError('Обнаружение требует подтверждённого держателя или места.')
    elif old['status'] == 'lost':
        raise ValueError('Сначала требуется подтверждённое обнаружение потерянной вещи.')
    elif after['status'] in ('lost', 'destroyed'):
        raise ValueError('Для потери/уничтожения нужна соответствующая операция.')
    if op == 'return' and (after['holder_id'] is None or after['holder_id'] != old['owner_id']):
        raise ValueError('Возврат требует передачи установленному владельцу без смены собственности.')
    if op == 'relocate' and set(updates) != {'location_id'}:
        raise ValueError('Перемещение меняет только место.')
    if all(after[k] == old[k] for k in FIELDS): raise ValueError('Нет изменения состояния вещи.')
    return after


def apply_possessions(r, raw, events):
    from backend.runtime_v3.resolver import normalized
    from backend.runtime_v3.personality import _record
    from backend.runtime_v3.life import capabilities
    items = r.state['possessions']
    # Fact identity is immutable and survives renamed extraction/event/item IDs.
    introductions = {v['fact_id'] for v in items.values() if v['fact_id']}
    proposals = []
    for i, row in r.records(raw, 'possession_deltas'):
        c = r.typed(PossessionDelta, row, 'possession_deltas', i)
        if c: proposals.append((i, c))
    counts = {}
    for _, c in proposals: counts.setdefault(c['item_id'], []).append(c)
    ambiguous = {pid for pid, cs in counts.items() if len(cs) > 1 and (
        any(events.get(c['source_event_id'], {}).get('order') is None for c in cs) or
        len({events.get(c['source_event_id'], {}).get('order') for c in cs}) != len(cs))}
    proposals.sort(key=lambda pair: events.get(pair[1]['source_event_id'], {}).get('order', 0))
    for i, c in proposals:
        try:
            if c['item_id'] in ambiguous: raise ValueError('Несколько переходов одной вещи требуют порядка событий.')
            event = events.get(c['source_event_id'])
            if not event or c['fact_id'] not in event['fact_ids']:
                raise ValueError('Нет принятого Event/Fact вещи.')
            if not normalized(c['evidence']) or normalized(c['evidence']) not in normalized(r.narrative) or normalized(event['evidence']) not in normalized(r.narrative):
                raise ValueError('Требуется совершившийся исход в повествовании.')
            old = items.get(c['item_id'])
            guard = identity('possession', c['fact_id'], c['operation'])
            if old and guard in old['applied']: continue
            if c['operation'] == 'introduce' and c['fact_id'] in introductions: continue
            if (old or {}).get('revision', 0) != c['expected_revision']:
                raise ValueError('Устаревшая ревизия вещи.')
            if c['operation'] == 'introduce' and any(
                normalized(v['name']).casefold() == normalized(c['name'] or '').casefold()
                and v['kind'] == c['kind'] for v in items.values()):
                raise ValueError('Совпадающая значимая вещь уже существует; используй её ID или уточни идентичность.')
            after = _transition(old, c)
            affected = {v for row in (old or {}, after) for k, v in row.items() if k in ('owner_id', 'holder_id') and v}
            if affected and not affected & set(event['participants']):
                raise ValueError('Событие не связано с владельцем/держателем.')
            fact = r.state['facts'][c['fact_id']]
            if affected and not affected & set(fact['character_ids']):
                raise ValueError('Факт не связан с владельцем/держателем.')
            if c['transition'] == 'established' and c['operation'] != 'introduce':
                raise ValueError('Established допустим только для введения вещи.')
            if c['transition'] == 'voluntary':
                decision = c['decision_actor_id']
                if decision not in event['participants'] or decision not in r.state['characters'] or not capabilities(r.state, decision)['can_act']:
                    raise ValueError('Нет дееспособного участника добровольного действия.')
                # An NPC cannot authorize disposal of EXTERNAL-owned property.
                required = set()
                if old:
                    if after['owner_id'] != old['owner_id'] and old['owner_id']:
                        required.add(old['owner_id'])
                        if decision != old['owner_id']: raise ValueError('Передачу собственности решает владелец.')
                    if after['holder_id'] != old['holder_id'] and old['holder_id']:
                        required.add(old['holder_id'])
                    if c['operation'] in ('destroy', 'lose', 'relocate'):
                        required.update(x for x in (old['owner_id'], old['holder_id']) if x)
                else:
                    required.update(x for x in (after['owner_id'], after['holder_id']) if x)
                if c['operation'] in ('acquire', 'sell') and after['owner_id']:
                    required.add(after['owner_id'])
                required.add(decision)
                if r.protected_actor_id in required:
                    quote = normalized(c['player_evidence'])
                    if r.mode == 'background' or c['player_assertion'] != 'explicit_choice' or not quote or quote not in normalized(r.player_input):
                        raise ValueError('Добровольное распоряжение EXTERNAL требует явного действия пользователя.')
            elif c['transition'] == 'involuntary' and event['medium'] not in ('action', 'observation', 'discovery'):
                raise ValueError('Недобровольное изменение требует принятого последствия, не слуха/плана.')
            after.update(revision=c['expected_revision']+1, source_event_id=event['id'], source_turn=r.turn_id)
            if not old: after['fact_id'] = c['fact_id']
            after['field_facts'].update({k:c['fact_id'] for k in c['updates']})
            after['applied'][guard] = c['fact_id']
            validate_record(after, r.state)
            items[c['item_id']] = after
            if not old: introductions.add(c['fact_id'])
            _record(r, 'possession_delta', c['item_id'], old, after,
                source_ids=[event['id']], operation_ids=[guard], source_event_id=event['id'],
                fact_id=c['fact_id'], evidence=c['evidence'], operation=c['operation'])
        except ValueError as exc:
            r.warn('possession_deltas', i, str(exc), code='possession_rejected')


def known(state, observer, fid):
    return bool(fid and state['knowledge'].get(str(observer)+':'+fid, {}).get('status') == 'known')


def context_possessions(state, scope, *, extraction=False, query=''):
    """Bounded addition to ContextScope, with field-specific Knowledge gates."""
    from backend.runtime_v3.scope import words, mentions
    rows = []
    observer = scope.pov_actor_id or scope.controlled_actor_id
    for item in state.get('possessions', {}).values():
        if not extraction and not any(known(state, observer, fid) for fid in [item['fact_id'], *item['field_facts'].values()]):
            continue
        row = {k:item[k] for k in ('id', 'name', 'kind')}
        for key in FIELDS:
            if extraction or known(state, observer, item['field_facts'].get(key)):
                row[key] = item[key]
        # Relevance must itself use only visible data, never a secret new holder/place.
        exact = mentions(query, [item['name'], item['id']])
        mentioned = bool(words(query) & words(item['name']+' '+item['id'])) or exact
        related = bool({row.get('owner_id'), row.get('holder_id')} & scope.relevant_actor_ids)
        placed = row.get('location_id') is not None and row['location_id'] in scope.location_ids
        if not (mentioned or related or placed): continue
        if extraction:
            row.update(revision=item['revision'], fact_id=item['fact_id'], field_facts=item['field_facts'])
        if exact: scope.required_possession_ids.add(item['id'])
        row['known_by'] = {key:sorted(cid for cid in scope.relevant_actor_ids if known(state, cid, item['field_facts'].get(key))) for key in FIELDS if key in row}
        rows.append(((-int(exact), -int(mentioned), -int(placed), item['id']), row))
    selected, budget = [], 5998
    for _, row in sorted(rows):
        size = len(json.dumps(row, ensure_ascii=False)) + 2
        if size > budget: continue
        selected.append(row); budget -= size
        if len(selected) == 12: break
    scope.possession_ids = [row['id'] for row in selected]
    return selected


def private_fact_ids(state):
    return {fid for item in state.get('possessions', {}).values()
            for fid in [item['fact_id'], *item['field_facts'].values(), *item['applied'].values()] if fid}
