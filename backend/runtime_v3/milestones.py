"""Compact immutable index over accepted History transitions, never current truth.

SQLite recursive CTEs traverse only History links (not thousands of JSON batches).
The caller owns the transaction. Ancestor membership isolates variants and saves.
"""
from hashlib import sha256
import json
import logging

from pydantic import BaseModel, ConfigDict, Field


class Milestone(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str
    category: str
    actor_ids: list[str]
    entity_ids: list[str]
    minute: int | None = Field(default=None, ge=0)
    date: str | None = None
    source_transition_id: str
    source_record_id: str | None = None
    source_event_id: str | None = None
    source_process_id: str | None = None
    fact_id: str | None = None
    summary: str = Field(max_length=400)
    names: dict[str, str] = Field(default_factory=dict)
    location_ids: list[str] = Field(default_factory=list)


def stable_id(prefix, value):
    return prefix + '_' + sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                          separators=(',', ':')).encode()).hexdigest()[:32]


def transition_provenance(resolver, item, actors):
    """References are optional; a bad causal link cannot invalidate valid truth."""
    result = {}
    event_id = item.get('source_event_id')
    if event_id is not None:
        event = next((e for e in resolver.history.events if event_id in (e['id'], e.get('local_id'))
                      and set(actors) & set(e.get('participants', []))), None)
        if event:
            result['source_event_id'] = event['id']
        else:
            resolver.warn('provenance', None, 'Неизвестное или несвязанное событие-источник.',
                          code='causal_reference_invalid')
    process = item.get('source_process_id')
    if process is not None:
        row = resolver.state.get('conditions', {}).get(process) if isinstance(process, str) else None
        plan = resolver.state.get('scheduled_events', {}).get(process) if isinstance(process, str) else None
        if row and row['actor_id'] in actors or plan and set(actors) & set(plan['character_ids']):
            result['source_process_id'] = process
        else:
            resolver.warn('provenance', None, 'Неизвестный или несвязанный процесс-источник.',
                          code='causal_reference_invalid')
    return result


def derive(batch):
    """Conservative backfill: typed before/after only, never interpret old prose."""
    records = batch.get('state_changes', [])
    if not isinstance(records, list):
        return []
    found = {}
    for change in records:
        try:
            if not isinstance(change, dict):
                continue
            before, after = change.get('before'), change.get('after')
            if not isinstance(after, dict) or before is not None and not isinstance(before, dict):
                continue
            kind, entity = change.get('kind'), change.get('entity')
            if not isinstance(entity, str) or not entity or after.get('id', entity) != entity:
                continue
            old = before or {}
            actors, categories, locations = [], [], []
            fact = after.get('fact_id')
            opened = old.get('status') != 'active' and after.get('status') == 'active'
            closed = old.get('status') == 'active' and after.get('status') == 'closed'
            if kind == 'life_changes':
                actors = [entity]
                if old.get('life_status') != 'dead' and after.get('life_status') == 'dead':
                    categories.append('death'); fact = after.get('life_fact_id')
                if after.get('display_name') and old.get('display_name') != after['display_name'] and after.get('name_history'):
                    categories.append('name_change'); fact = after['name_history'][-1].get('fact_id')
            elif kind == 'birth_date_established':
                # Learning a birthday indexes the established birth, not a new birth now.
                if old.get('birth_date') is None and after.get('birth_date'):
                    actors = [entity]; categories.append('birth')
            elif kind in ('social_relation_changes', 'objective_relations'):
                actors = [after['source_id'], after['target_id']]
                relation = after.get('kind')
                if opened and relation in ('spouse', 'engaged', 'adoptive_parent', 'guardian', 'foster_parent'):
                    categories.append({'spouse':'marriage', 'engaged':'engagement'}.get(relation, relation))
                if closed and relation in ('spouse', 'engaged', 'adoptive_parent', 'guardian', 'foster_parent'):
                    categories.append('divorce' if relation == 'spouse' and after.get('outcome') == 'divorced'
                                      else relation + '_ended')
                if closed: fact = after.get('closure_fact_id')
            elif kind == 'residences':
                actors = [after['actor_id']]; locations = [after['location_id']]
                if opened: categories.append('relocation')
                elif closed: categories.append('residence_ended'); fact = after.get('closure_fact_id')
            elif kind == 'roles':
                actors = [after['actor_id']]
                if change.get('significance') != 'routine' and (change.get('significance') == 'major' or
                        after.get('kind') in ('employment', 'education', 'training', 'office', 'profession', 'retirement')):
                    if opened: categories.append('role_started')
                    elif closed: categories.append('role_ended'); fact = after.get('closure_fact_id')
            elif kind == 'protagonist_transition':
                # Explicit Runtime boundary for #42; POV/camera switches are NOT this.
                if old.get('actor_id') != after.get('actor_id') and after.get('actor_id'):
                    actors = [c for c in (old.get('actor_id'), after['actor_id']) if c]
                    categories.append('protagonist_transition')
            if not categories or any(not isinstance(a, str) or not a for a in actors):
                continue
            minute = change.get('minute')
            if minute is not None and (type(minute) is not int or minute < 0):
                continue
            for category in categories:
                date = after['birth_date'] if category == 'birth' else change.get('date')
                transition_id = change.get('id') or stable_id('transition', change)
                # The accepted transition is the idempotency key, not its summary.
                # Distinct transitions at the same minute must remain distinct.
                mid = stable_id('milestone', [category, entity, date] if category == 'birth'
                                else [category, transition_id])
                summary = change.get('evidence') or after.get('context') or ''
                if not isinstance(summary, str): continue
                record = Milestone(id=mid, category=category, actor_ids=actors,
                    entity_ids=list(dict.fromkeys([entity, *([after['organization_id']] if after.get('organization_id') else [])])),
                    minute=None if category == 'birth' else minute, date=date,
                    source_transition_id=transition_id,
                    source_record_id=change.get('source_record_id'),
                    source_event_id=change.get('source_event_id'), source_process_id=change.get('source_process_id'),
                    fact_id=fact, summary=summary[:400], names=change.get('names', {}), location_ids=locations)
                found.setdefault(mid, record.model_dump())
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            logging.getLogger(__name__).warning('Skipped malformed structured milestone source')
    return list(found.values())


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS world_milestones_v3 (
        history_id TEXT NOT NULL, id TEXT NOT NULL, category TEXT NOT NULL,
        minute INTEGER, date TEXT, fact_id TEXT, source_event_id TEXT, source_process_id TEXT,
        payload_json TEXT NOT NULL, PRIMARY KEY(history_id,id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS world_milestone_actors_v3 (
        history_id TEXT NOT NULL, milestone_id TEXT NOT NULL, actor_id TEXT NOT NULL,
        PRIMARY KEY(actor_id,history_id,milestone_id))''')
    db.execute('CREATE INDEX IF NOT EXISTS milestone_category_time ON world_milestones_v3(category,minute)')
    db.execute('CREATE INDEX IF NOT EXISTS milestone_time ON world_milestones_v3(minute,date)')
    db.execute('CREATE INDEX IF NOT EXISTS milestone_event ON world_milestones_v3(source_event_id)')
    db.execute('CREATE INDEX IF NOT EXISTS milestone_process ON world_milestones_v3(source_process_id)')
    db.execute('CREATE TABLE IF NOT EXISTS world_milestone_versions_v3 (version INTEGER PRIMARY KEY)')
    if not db.execute('SELECT 1 FROM world_milestone_versions_v3 WHERE version=1').fetchone():
        for hid, payload in db.execute('SELECT id,payload_json FROM world_history_v3'):
            try: batch = json.loads(payload)
            except (ValueError, TypeError): continue
            if isinstance(batch, dict): index_batch(db, hid, batch)
        db.execute('INSERT INTO world_milestone_versions_v3 VALUES(1)')


def index_batch(db, history_id, batch):
    for row in derive(batch):
        # A replay appended later in the same lineage reuses the original index
        # entry. Siblings may index independently; neither can see the other.
        exists = db.execute('''WITH RECURSIVE lineage(id) AS (
            SELECT ? UNION SELECT h.parent_id FROM world_history_v3 h
            JOIN lineage l ON h.id=l.id WHERE h.parent_id IS NOT NULL
        ) SELECT 1 FROM world_milestones_v3 m JOIN lineage l ON m.history_id=l.id
          WHERE m.id=? LIMIT 1''', (history_id,row['id'])).fetchone()
        if exists: continue
        inserted = db.execute('INSERT OR IGNORE INTO world_milestones_v3 VALUES(?,?,?,?,?,?,?,?,?)',
            (history_id, row['id'], row['category'], row['minute'], row['date'], row['fact_id'],
             row['source_event_id'], row['source_process_id'], json.dumps(row, ensure_ascii=False)))
        if not inserted.rowcount: continue
        db.executemany('INSERT OR IGNORE INTO world_milestone_actors_v3 VALUES(?,?,?)',
            [(history_id, row['id'], actor) for actor in row['actor_ids']])


def query(db, head, *, actor_ids=None, category=None, start_minute=None, end_minute=None,
          start_date=None, end_date=None, source_event_id=None, source_process_id=None,
          known_fact_ids=None, latest_per_category=False, limit=32, offset=0):
    """Bounded paginated results, unbounded ancestry; UNION terminates damaged cycles.

    known_fact_ids=None is an internal GM query. Public callers MUST pass an
    observer's known facts; filtering happens before ordering/pagination/counts.
    """
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError('Недопустимый размер страницы milestones.')
    if start_minute is not None and end_minute is not None and start_minute > end_minute or start_date and end_date and start_date > end_date:
        raise ValueError('Начало диапазона позже конца.')
    where, args = [], [head]
    for column, op, value in (('category','=',category), ('minute','>=',start_minute), ('minute','<=',end_minute),
            ('date','>=',start_date), ('date','<=',end_date), ('source_event_id','=',source_event_id),
            ('source_process_id','=',source_process_id)):
        if value is not None: where.append(f'm.{column}{op}?'); args.append(value)
    if actor_ids is not None:
        ids = sorted(set(actor_ids))
        if not ids: return []
        where.append('EXISTS (SELECT 1 FROM world_milestone_actors_v3 a WHERE a.history_id=m.history_id '
                     'AND a.milestone_id=m.id AND a.actor_id IN ('+','.join('?' for _ in ids)+'))')
        args.extend(ids)
    if known_fact_ids is not None:
        ids = sorted(set(known_fact_ids))
        if not ids: return []
        where.append('m.fact_id IN ('+','.join('?' for _ in ids)+')'); args.extend(ids)
    condition = ' AND '.join(where) or '1'
    rows = db.execute('''WITH RECURSIVE lineage(id) AS (
        SELECT id FROM world_history_v3 WHERE id=?
        UNION SELECT h.parent_id FROM world_history_v3 h JOIN lineage l ON h.id=l.id WHERE h.parent_id IS NOT NULL
    ), selected AS (
        SELECT m.*, ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY m.history_id) AS duplicate
        FROM world_milestones_v3 m JOIN lineage l ON m.history_id=l.id WHERE '''+condition+'''
    ), ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY category ORDER BY minute DESC,date DESC,id) AS category_rank
        FROM selected WHERE duplicate=1
    ) SELECT history_id,payload_json FROM ranked WHERE (?=0 OR category_rank=1)
      ORDER BY minute DESC, date DESC, id LIMIT ? OFFSET ?''', (*args, int(latest_per_category), limit, offset))
    result = []
    for hid, payload in rows:
        try:
            result.append(dict(Milestone.model_validate_json(payload).model_dump(), history_id=hid))
        except (ValueError, TypeError):
            logging.getLogger(__name__).warning('Skipped malformed milestone index record in %s', hid)
    return result


def reader(storage, head):
    """Bind to the recorded BEFORE head; regeneration cannot see a later branch."""
    def read(**filters):
        with storage.connect() as db:
            return query(db, head, **filters)
    return read


def visible_query(storage, snapshot, **filters):
    state = snapshot['world_state']; observer = state['camera']['controlled_actor_id']
    known = {k['fact_id'] for k in state['knowledge'].values()
             if k['actor_id'] == observer and k['status'] == 'known'}
    rows = reader(storage, snapshot.get('history_head'))(known_fact_ids=known, **filters)
    # Causal IDs and historical names may reveal unrelated secrets; keep them GM-only.
    return [{k:r[k] for k in ('id','category','actor_ids','minute','date')}
            | {'summary':state['facts'][r['fact_id']]['text'][:400]} for r in rows]


def select_context(state, scope, read, budget=1600):
    """A few relevant actors, at most two records each; archives cannot add actors."""
    if read is None: return []
    core = sorted(scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids)
    explicit = sorted((scope.structural_actor_ids & scope.relevant_actor_ids) - set(core))
    selected, used = {}, 0
    for actor in (core + explicit)[:8]:
        from backend.runtime_v3.scope import words
        candidates = read(actor_ids=[actor], latest_per_category=True, limit=32)
        # One representative per category prevents repeated career changes from
        # burying a much older marriage/birth. Explicit topical overlap wins.
        priorities = {'death':6,'protagonist_transition':6,'birth':5,'divorce':5,'marriage':4,'relocation':3}
        candidates.sort(key=lambda row: (-len(scope.query_words & words(row['summary']+' '+row['category'])),
            -priorities.get(row['category'],2), -(row['minute'] or 0), row['id']))
        for row in candidates[:2]:
            if row['id'] in selected: continue
            compact = {k:v for k,v in row.items() if v is not None and k != 'history_id'}
            # A historical marriage is not a current marriage; expose diagnostics
            # for genuinely impossible contradictions, never repair canonical truth.
            if row['category']=='death' and any(state['characters'].get(cid,{}).get('life_status')=='alive' for cid in row['actor_ids']):
                compact['diagnostic'] = 'milestone_conflicts_with_current_life_status'
            compact['known_by'] = [cid for cid in core if row.get('fact_id') and
                state['knowledge'].get(cid+':'+row['fact_id'],{}).get('status')=='known']
            cost = (len(json.dumps(compact,ensure_ascii=False).encode())+1)//2+4
            if used + cost <= budget:
                selected[row['id']] = compact; used += cost
    return list(selected.values())
