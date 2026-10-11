"""Knowledge lifecycle within the existing resolver and append-only History.

Facts are immutable assertions, not pointers to mutable Character attributes.
A claim is an explicitly exclusive (subject, predicate, scope) slot. No NLP
matching, world-truth refresh, time decay, or fact × character propagation.
"""
from collections import defaultdict
from copy import deepcopy
from pydantic import ValidationError
from backend.runtime_v3.models import Claim, Knowledge, identity
from backend.runtime_v3.history import INFORMATION_MEDIA

CURRENT = frozenset(('known', 'suspected'))
RETIRED = frozenset(('outdated', 'refuted', 'superseded'))


def slot(fact):
    claim = fact.get('claim')
    return (claim['subject_id'], claim['predicate'], claim.get('scope', '')) if claim else None


def salvage(state):
    """Only optional metadata; never reconstruct beliefs from objective truth."""
    state = deepcopy(state)
    for fact in state.get('facts', {}).values():
        if not isinstance(fact, dict) or fact.get('claim') is None: continue
        try: fact['claim'] = Claim.model_validate(fact['claim']).model_dump()
        except ValidationError: fact['claim'] = None
    defaults = Knowledge(actor_id='_', fact_id='_').model_dump()
    for row in state.get('knowledge', {}).values():
        if not isinstance(row, dict): continue
        for key in ('revision', 'source_event_id', 'evidence', 'source_turn', 'replaced_by'):
            try: Knowledge(actor_id='_', fact_id='_', **{key:row.get(key, defaults[key])})
            except ValidationError: row[key] = defaults[key]
        if row.get('replaced_by') not in state.get('facts', {}): row['replaced_by'] = None
    return state


def apply_knowledge(resolver, raw, events):
    from backend.runtime_v3.resolver import normalized
    r, s = resolver, resolver.state
    candidates = []
    # Ground and schema-check before considering conflicts: an invalid proposal
    # must not retire a valid belief or prevent another grounded acquisition.
    for i, item in r.records(raw, 'knowledge_gained'):
        def reject(reason, code='knowledge_path_invalid'):
            r.warn('knowledge_gained', i, reason, code=code)
        actor, fid = item.get('actor_id'), item.get('fact_id')
        eid = item.get('source_event_id')
        event = events.get(eid) if isinstance(eid, str) else None
        if (not isinstance(actor, str) or not isinstance(fid, str) or
            actor not in s['characters'] or fid not in s['facts'] or not event or
            actor not in event['witnesses'] or fid not in event['fact_ids'] or
            event['medium'] not in INFORMATION_MEDIA or
            normalized(item['evidence']) not in normalized(r.narrative) or
            normalized(event['evidence']) not in normalized(r.narrative)):
            reject('Нет подтверждённого восприятия в завершённом повествовании.'); continue
        if (not r.observed or r.mode == 'background') and actor in r.protected_knowledge_actor_ids:
            reject('Фоновое событие не меняет знания участников основной сцены.'); continue
        from backend.runtime_v3.life import capabilities
        if not capabilities(s, actor)['can_perceive']:
            reject('Персонаж не способен воспринять источник.'); continue
        prior = s['knowledge'].get(actor+':'+fid)
        expected = item.get('expected_revision')
        if expected is not None and (type(expected) is not int or expected < 0):
            reject('Устаревшая ревизия знания.', 'knowledge_revision_conflict'); continue
        status = item.get('status', 'known')
        if not isinstance(status, str):
            reject('Некорректный статус знания.'); continue
        if prior and prior['status'] in RETIRED and status in CURRENT and expected is None:
            reject('Повторное установление убеждения требует его ревизии.', 'knowledge_revision_conflict'); continue
        supersedes = item.get('supersedes', [])
        if (not isinstance(supersedes, list) or len(supersedes) > 16 or
            any(not isinstance(old, str) or old == fid or old not in s['facts'] or
                old not in event['fact_ids'] for old in supersedes) or
            (supersedes and status != 'known')):
            reject('Исправление требует прежних fact_id в том же событии.'); continue
        entry = r.typed(Knowledge, dict(actor_id=actor, fact_id=fid, status=status), 'knowledge_gained', i)
        if entry: candidates.append((i, item, event, entry))

    if not candidates: return

    # Index once, including only actors actually receiving evidence. This is
    # O(K + proposals), never facts × NPCs. Suspicions may coexist.
    actors = {entry['actor_id'] for _, _, _, entry in candidates}
    known = defaultdict(set)
    for key, row in s['knowledge'].items():
        claim_slot = slot(s['facts'][row['fact_id']])
        if row['actor_id'] in actors and row['status'] == 'known' and claim_slot:
            known[(row['actor_id'], claim_slot)].add(key)

    groups = defaultdict(list)
    for candidate in candidates:
        _, _, _, entry = candidate
        # All transitions of one fact must also have unambiguous chronology.
        groups[('fact', entry['actor_id'], entry['fact_id'])].append(candidate)
        claim_slot = slot(s['facts'][entry['fact_id']])
        if claim_slot and entry['status'] == 'known':
            groups[('slot', entry['actor_id'], claim_slot)].append(candidate)
    ambiguous = set()
    for group in groups.values():
        if len(group) < 2: continue
        orders = [event.get('order') for _, _, event, _ in group]
        if any(type(order) is not int for order in orders) or len(set(orders)) != len(orders):
            ambiguous.update(i for i, _, _, _ in group)
    for i in sorted(ambiguous):
        r.warn('knowledge_gained', i, 'Противоречивые изменения требуют порядка событий.', code='knowledge_order_ambiguous')
    candidates.sort(key=lambda c: (c[2].get('order', 0), c[0]))

    def transition(entry, prior, event, item, trigger):
        entry.update(revision=(prior or {}).get('revision', 0)+1,
                     source_event_id=event['id'], evidence=item['evidence'], source_turn=r.turn_id)
        key = entry['actor_id']+':'+entry['fact_id']
        s['knowledge'][key] = entry
        r.history.knowledge_acquisitions.append(dict(deepcopy(entry), turn_id=r.turn_id,
            trigger_fact_id=trigger, before=deepcopy(prior), after=deepcopy(entry)))
        r.history.state_changes.append(dict(id=identity('knowledge', r.turn_id, event['id'], key, entry['revision']),
            kind='knowledge_transition', entity=key, actor_id=entry['actor_id'],
            before=deepcopy(prior), after=deepcopy(entry), source_event_id=event['id'],
            evidence=item['evidence'], minute=s['meta']['world_time'], turn_id=r.turn_id))

    for i, item, event, entry in candidates:
        if i in ambiguous: continue
        actor, fid = entry['actor_id'], entry['fact_id']
        key = actor+':'+fid
        prior = s['knowledge'].get(key)
        if entry['status'] in RETIRED and not prior:
            r.warn('knowledge_gained', i, 'Нет прежнего убеждения для опровержения.', code='knowledge_path_invalid'); continue
        if any(actor+':'+old not in s['knowledge'] for old in item.get('supersedes', [])):
            r.warn('knowledge_gained', i, 'Нет исправляемого убеждения у персонажа.', code='knowledge_path_invalid'); continue
        # Compare against the evolving state after earlier ordered events.
        if item.get('expected_revision') is not None and item['expected_revision'] != (prior or {}).get('revision', 0):
            r.warn('knowledge_gained', i, 'Ревизия изменилась в ходе.', code='knowledge_revision_conflict'); continue
        if prior and prior['status'] in RETIRED and entry['status'] in CURRENT and item.get('expected_revision') is None:
            r.warn('knowledge_gained', i, 'Повторное установление требует ревизии.', code='knowledge_revision_conflict'); continue
        if prior and prior['status'] == entry['status'] and not item.get('supersedes'):
            continue  # Replay does not manufacture a new historical transition.
        claim_slot = slot(s['facts'][fid])
        index = (actor, claim_slot)
        retire = {actor+':'+old for old in item.get('supersedes', [])}
        if entry['status'] == 'known' and claim_slot:
            retire |= {old for old in known[index] if old != key and
                       s['facts'][s['knowledge'][old]['fact_id']]['claim']['value'] != s['facts'][fid]['claim']['value']}
        for old in sorted(retire):
            old_row = s['knowledge'][old]
            if old_row['status'] not in CURRENT: continue
            replacement = dict(old_row, status='superseded', replaced_by=fid)
            transition(replacement, old_row, event, item, fid)
            known[(actor, slot(s['facts'][old_row['fact_id']]))].discard(old)
        transition(entry, prior, event, item, fid)
        if claim_slot:
            known[index].discard(key)
            if entry['status'] == 'known': known[index].add(key)


def context_rows(state, keys, *, extraction=False):
    """Small current projection. Historical evidence stays in History, not prompts."""
    rows = []
    for key in keys:
        row = state['knowledge'][key]
        if row['status'] not in CURRENT | {'unknown'} and not extraction: continue
        fields = ('actor_id', 'fact_id', 'status', 'revision') if extraction else ('actor_id', 'fact_id', 'status')
        result = {field:row.get(field, 0 if field == 'revision' else None) for field in fields}
        # Retired entries are only useful for explicit re-establishment in extraction.
        if extraction and row.get('replaced_by'): result['replaced_by'] = row['replaced_by']
        rows.append(result)
    return rows
