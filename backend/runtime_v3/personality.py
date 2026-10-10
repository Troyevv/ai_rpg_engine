"""Evidence-bound partial evolution of the existing canonical Character card.

Extraction interprets meaning; Runtime owns provenance, agency, eligibility and
compare-and-set. History owns chronology; no per-turn psychologist or trait scores.
"""
from copy import deepcopy
from typing import Literal
import logging
from pydantic import Field
from backend.runtime_v3.models import (StrictModel, PersonalityProfile, PersonalityItem,
                                      DevelopmentEvidence, identity)

CARD_FIELDS = {'traits':'Характер', 'communication':'Стиль общения', 'habits':'Привычки',
               'strengths':'Сильные стороны', 'weaknesses':'Слабости',
               'fears':'Страхи и уязвимости', 'preferences':'Предпочтения', 'temperament':'Темперамент'}
MAX_EVIDENCE = 32


class EvidenceClaim(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    actor_id: str
    source_event_id: str
    source_kind: Literal['event','milestone'] = 'event'
    meaning: str = Field(min_length=1, max_length=300)
    kind: Literal['behavior', 'experience', 'turning_point']
    assertion: Literal['completed']
    evidence: str = Field(min_length=1, max_length=1000)
    player_evidence: str = ''
    player_assertion: Literal['completed_voluntary_behavior'] | None = None


class Operation(StrictModel):
    item_id: str = Field(min_length=1, max_length=100)
    field: Literal['traits','communication','habits','strengths','weaknesses','fears','preferences','temperament']
    operation: Literal['establish','refine','retire']
    text: str = Field(default='', max_length=600)
    expected_text: str | None
    expected_revision: int = Field(ge=0)


class PersonalityDelta(StrictModel):
    actor_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    rationale: str = Field(min_length=1, max_length=600)
    developmental_fit: Literal['established_capability']
    operations: list[Operation] = Field(min_length=1, max_length=3)
    evidence: str = Field(min_length=1, max_length=1000)


def salvage_profiles(state):
    """Read boundary only; historical JSON is never rewritten."""
    for actor in state.get('characters', {}).values():
        if isinstance(actor, dict) and actor.get('personality') is not None:
            try:
                actor['personality'] = PersonalityProfile.model_validate(actor['personality']).model_dump()
            except (ValueError, TypeError):
                logging.getLogger(__name__).warning('Ignoring malformed optional personality for %s', actor.get('id'))
                actor['personality'] = None


def initialize_profiles(snapshot):
    """Keep legacy prose verbatim, never infer traits, age or parent inheritance."""
    for card in snapshot.get('character_cards', []):
        actor = snapshot['world_state']['characters'].get(card['id'])
        if actor is None or actor.get('personality') is not None:
            continue
        items = {field: PersonalityItem(field=field, text=card.get('fields', {}).get(label, '')).model_dump()
                 for field, label in CARD_FIELDS.items() if card.get('fields', {}).get(label, '').strip()}
        actor['personality'] = PersonalityProfile(items=items).model_dump()
    return snapshot


def visible_item(state, cid, item, observer):
    if observer == cid or not item.get('source_ids'):
        return True
    return observer in item.get('witnesses',[]) or any(
        state['knowledge'].get(str(observer)+':'+fid, {}).get('status') == 'known'
        for fid in item.get('fact_ids',[]))


def project_card(card, actor, *, state=None, observer=None):
    """Disposable UI/Narrative projection; initial baseline never wins back."""
    result = deepcopy(card)
    profile = actor.get('personality')
    if profile is not None:
        fields = result.setdefault('fields', {})
        for field, label in CARD_FIELDS.items():
            values = [item['text'] for item in profile['items'].values() if item['field'] == field
                      and (state is None or visible_item(state, actor['id'], item, observer))]
            if values or label in fields:
                fields[label] = '\n'.join(values)
    return result


def _player_owned(resolver, claim, event):
    from backend.runtime_v3.resolver import normalized
    quote = normalized(claim.get('player_evidence', ''))
    return (resolver.mode != 'background' and claim['actor_id'] == resolver.protected_actor_id
            and claim.get('player_assertion') == 'completed_voluntary_behavior'
            and claim['kind'] in ('behavior','turning_point') and bool(quote)
            and quote in normalized(resolver.player_input)
            and bool(normalized(event['evidence']))
            and normalized(event['evidence']) in normalized(resolver.narrative))


def _record(resolver, kind, cid, before, after, **extra):
    from backend.runtime_v3.calendar import current_time
    change = dict(kind=kind, entity=cid, before=deepcopy(before), after=deepcopy(after),
                  turn_id=resolver.turn_id, minute=resolver.state['meta']['world_time'],
                  date=current_time(resolver.state)['date'], player_observed=resolver.observed, **extra)
    change['id'] = identity(kind, cid, extra.get('source_ids'), extra.get('operation_ids'))
    resolver.history.state_changes.append(change)


def apply_personality(resolver, raw, events):
    aliases = {}
    for i, row in resolver.records(raw, 'development_evidence'):
        claim = resolver.typed(EvidenceClaim, row, 'development_evidence', i)
        if not claim:
            continue
        cid = claim['actor_id']; actor = resolver.state['characters'].get(cid)
        event = events.get(claim['source_event_id']) if claim['source_kind'] == 'event' else None
        if claim['source_kind'] == 'milestone' and resolver.milestone_query and cid != resolver.protected_actor_id:
            matches = resolver.milestone_query(actor_ids=[cid], milestone_id=claim['source_event_id'], limit=1)
            if matches:
                milestone = matches[0]
                event = dict(id=milestone['id'], participants=milestone['actor_ids'], witnesses=[],
                             fact_ids=[], evidence=claim['evidence'])
        if actor is None or actor['life_status'] == 'dead' or event is None or cid not in event['participants']:
            resolver.warn('development_evidence', i, 'Источник опыта не является принятым событием персонажа.', code='development_source_invalid')
            continue
        owned = _player_owned(resolver, claim, event)
        if cid == resolver.protected_actor_id and not owned:
            resolver.warn('development_evidence', i, 'Нет завершённого добровольного действия EXTERNAL actor из player_input.', code='development_agency_invalid')
            continue
        if actor.get('personality') is None:
            actor['personality'] = PersonalityProfile().model_dump()
        profile = actor['personality']
        # Multiple labels on one canonical event are not multiple experiences.
        eid = identity('development', cid, event['id'])
        aliases[claim['id']] = (cid, eid)
        if eid in profile['evidence'] or eid in profile['seen_sources']:
            continue
        profile['seen_sources'].append(eid)
        entry = DevelopmentEvidence(id=eid, source_event_id=event['id'], source_turn=resolver.turn_id,
            minute=resolver.state['meta']['world_time'], meaning=claim['meaning'], kind=claim['kind'],
            player_owned=owned, evidence=claim['evidence'], witnesses=event['witnesses'], fact_ids=event['fact_ids']).model_dump()
        profile['evidence'][eid] = entry
        _record(resolver, 'development_evidence', cid, None, entry, source_ids=[event['id']])
        while len(profile['evidence']) > MAX_EVIDENCE:
            del profile['evidence'][next(iter(profile['evidence']))]
    touched = set()
    for i, row in resolver.records(raw, 'personality_deltas'):
        claim = resolver.typed(PersonalityDelta, row, 'personality_deltas', i)
        if not claim:
            continue
        cid = claim['actor_id']; actor = resolver.state['characters'].get(cid)
        if actor is None or actor['life_status'] == 'dead' or actor.get('personality') is None:
            resolver.warn('personality_deltas', i, 'Нет canonical профиля персонажа.', code='personality_actor_invalid'); continue
        profile = actor['personality']; sources = []
        for ref in claim['evidence_ids']:
            owner, eid = aliases.get(ref, (cid, ref))
            entry = profile['evidence'].get(eid)
            if entry is None and owner == cid and resolver.development_query:
                archived = resolver.development_query(actor_ids=[cid],kind='development_evidence',evidence_ids=[eid],limit=1)
                if archived:
                    entry = resolver.typed(DevelopmentEvidence, archived[0]['after'], 'personality_deltas', i)
            if owner != cid or entry is None:
                break
            sources.append(entry)
        else:
            sources = list({e['source_event_id']:e for e in sources}.values())
            eligible = len({e['source_turn'] for e in sources}) >= 3 or any(e['kind'] == 'turning_point' for e in sources)
            if cid == resolver.protected_actor_id:
                owned = [e for e in sources if e['player_owned']]
                eligible = eligible and resolver.mode != 'background' and (
                    len({e['source_turn'] for e in owned}) >= 3 or any(e['kind'] == 'turning_point' for e in owned))
            if not eligible:
                resolver.warn('personality_deltas', i, 'Один обычный эпизод/эмоция или течение времени недостаточны.', code='personality_evidence_insufficient'); continue
            if actor.get('developmental_stage') == 'infant' and any(op['field'] != 'temperament' for op in claim['operations']):
                resolver.warn('personality_deltas', i, 'Для младенца допустим только наблюдаемый темперамент.', code='personality_development_invalid'); continue
            ids = sorted(e['id'] for e in sources)
            guards = list(dict.fromkeys(identity('personality_source', cid, op['field'], ids) for op in claim['operations']))
            if all(key in profile['applied'] for key in guards):
                continue
            proposed = deepcopy(profile['items'])
            try:
                if any(key in profile['applied'] for key in guards):
                    raise ValueError('Частично применённая дельта.')
                if len({op['item_id'] for op in claim['operations']}) != len(claim['operations']):
                    raise ValueError('Повторная операция одного поля.')
                for op in claim['operations']:
                    key = op['item_id']; old = proposed.get(key)
                    if (cid, op['field']) in touched:
                        raise ValueError('Конфликтующие дельты одного хода.')
                    if (old or {}).get('text') != op['expected_text'] or (old or {}).get('revision', 0) != op['expected_revision']:
                        raise ValueError('Устаревшее ожидаемое значение профиля.')
                    if op['operation'] == 'establish':
                        if old is not None: raise ValueError('Черта уже установлена.')
                    elif old is None or old['field'] != op['field']:
                        raise ValueError('Изменяемая черта отсутствует или принадлежит другому полю.')
                    if op['operation'] == 'retire':
                        if op['text']: raise ValueError('Удаление не должно задавать новый текст.')
                        del proposed[key]
                    else:
                        if not op['text'].strip(): raise ValueError('Пустая черта.')
                        # Only witnesses of ALL supporting experiences know the
                        # development directly; no broadcast to the entire cast.
                        witnesses = set.intersection(*(set(e['witnesses']) for e in sources))
                        facts = set.intersection(*(set(e['fact_ids']) for e in sources))
                        proposed[key] = PersonalityItem(field=op['field'], text=op['text'],
                            revision=(old or {}).get('revision',0)+1, source_ids=ids,
                            witnesses=sorted(witnesses),fact_ids=sorted(facts)).model_dump()
                if len(proposed) > 48: raise ValueError('Профиль превышает ограничение в 48 характеристик.')
            except ValueError as exc:
                resolver.warn('personality_deltas', i, str(exc), code='personality_conflict'); continue
            before = {op['item_id']:deepcopy(profile['items'].get(op['item_id'])) for op in claim['operations']}
            after = {op['item_id']:deepcopy(proposed.get(op['item_id'])) for op in claim['operations']}
            profile['items'] = proposed
            profile['applied'].extend(guards)
            touched.update((cid, op['field']) for op in claim['operations'])
            _record(resolver, 'personality_delta', cid, before, after, source_ids=ids,
                    operation_ids=guards, evidence=claim['evidence'], rationale=claim['rationale'], sources=deepcopy(sources))
            continue
        resolver.warn('personality_deltas', i, 'Неизвестная ссылка на canonical опыт.', code='personality_source_invalid')


def context_profile(actor, *, evaluation=False):
    """Bounded current projection; no history ledger or invented future profile."""
    profile = actor.get('personality')
    if profile is None:
        return None
    items = {}; budget = 900 if evaluation else 1600
    for key, item in profile['items'].items():
        if len(item['text']) > budget: continue
        items[key] = {k:item[k] for k in ('field','text','revision')}
        budget -= len(item['text'])
    result = dict(items=items)
    if evaluation:
        result['evidence'] = []; budget += 1400
        for entry in reversed(list(profile['evidence'].values())):
            record = {k:entry[k] for k in ('id','source_event_id','source_turn','meaning','kind','player_owned')}
            if len(str(record)) > budget: continue
            result['evidence'].append(record); budget -= len(str(record))
            if len(result['evidence']) == 8: break
    return result


def history_query(db, head, *, actor_ids, kind='personality_delta', limit=16, evidence_ids=None):
    """On-demand archive reader for #43/debugging; not a per-turn history scan.

    Query the existing immutable DAG. No second evidence database or copied full
    personality snapshots; sibling branches never enter the selected ancestry.
    """
    import json
    if kind not in ('development_evidence','personality_delta') or not 1 <= limit <= 32:
        raise ValueError('Недопустимый запрос истории развития.')
    actors = sorted(set(actor_ids))
    if not actors or len(actors) > 8: return []
    source_filter = ''
    source_args = []
    if evidence_ids is not None:
        source_args = sorted(set(evidence_ids))
        if not source_args or len(source_args)>8: return []
        source_filter = " AND json_extract(j.value,'$.after.id') IN ("+','.join('?' for _ in source_args)+')'
    sql = '''WITH RECURSIVE lineage(id,depth,path) AS (
        SELECT id,0,','||id||',' FROM world_history_v3 WHERE id=?
        UNION ALL SELECT h.parent_id,l.depth+1,l.path||h.parent_id||',' FROM world_history_v3 h JOIN lineage l ON h.id=l.id
          WHERE h.parent_id IS NOT NULL AND instr(l.path,','||h.parent_id||',')=0
    ) SELECT j.value FROM lineage l JOIN world_history_v3 h ON h.id=l.id,
        json_each(h.payload_json,'$.state_changes') j
        WHERE json_extract(j.value,'$.kind')=? AND json_extract(j.value,'$.entity') IN ('''+','.join('?' for _ in actors)+''')
        '''+source_filter+''' ORDER BY l.depth ASC LIMIT ?'''
    return [json.loads(row[0]) for row in db.execute(sql,(head,kind,*actors,*source_args,limit))]


def historical_context(state, scope, history):
    """Enrich only already-selected causal History, never select extra NPCs."""
    selected_events = {e.get('id') for e in scope.history_events}
    result=[]; budget=2000
    for change in reversed((history or {}).get('state_changes', [])):
        if change.get('kind') != 'personality_delta' or change.get('entity') not in scope.relevant_actor_ids:
            continue
        sources=change.get('sources',[])
        if not selected_events & {e.get('source_event_id') for e in sources}: continue
        known_by=[cid for cid in scope.relevant_actor_ids if cid==change['entity'] or all(
            cid in e.get('witnesses',[]) or any(state['knowledge'].get(cid+':'+fid,{}).get('status')=='known'
                for fid in e.get('fact_ids',[])) for e in sources)]
        record={key:change[key] for key in ('entity','before','after','minute')}
        record['known_by']=known_by
        if len(str(record))>budget: continue
        result.append(record);budget-=len(str(record))
        if len(result)==2:break
    return result


def history_reader(storage, head):
    """Archive access bound to recorded BEFORE lineage, including regeneration."""
    def read(**filters):
        with storage.connect() as db:
            return history_query(db,head,**filters)
    return read
