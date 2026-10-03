"""Immutable history DAG, owned by the caller's SQLite transaction."""
from copy import deepcopy
import json
import uuid
from backend.runtime_v3.models import WorldHistoryV3, assert_world_state_v3_invariants, fatal
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.history import audit_world_history


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS world_history_v3 (
        id TEXT PRIMARY KEY, parent_id TEXT, payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS world_migrations_v3 (
        source_hash TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, report_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def append_history(db, parent_id, batch):
    # No FK to historical records: imported damaged history must not invalidate
    # otherwise valid current state. Audit reports missing ancestors separately.
    hid = uuid.uuid4().hex
    db.execute('INSERT INTO world_history_v3(id,parent_id,payload_json) VALUES(?,?,?)',
        (hid,parent_id,json.dumps(batch,ensure_ascii=False)))
    return hid


def read_history(db, head, *, limit=64):
    result = WorldHistoryV3().to_dict()
    warnings, visited, batches = [], set(), []
    while head and len(visited)<limit:
        if head in visited:
            warnings.append(dict(section='history',code='history_cycle',reason='цикл исторических ссылок')); break
        visited.add(head)
        row=db.execute('SELECT parent_id,payload_json FROM world_history_v3 WHERE id=?',(head,)).fetchone()
        if row is None:
            warnings.append(dict(section='history',entity=head,code='history_missing',reason='исторический пакет отсутствует')); break
        parent, payload = row
        try:
            batch=json.loads(payload)
        except (TypeError,ValueError):
            batch=None
        if not isinstance(batch,dict):
            warnings.append(dict(section='history',entity=head,code='history_invalid',reason='повреждён исторический пакет'))
        else:
            batches.append(batch)
        head=parent
    for batch in reversed(batches):
        for section in result:
            records=batch.get(section,[])
            if isinstance(records,list):result[section].extend(deepcopy(records))
            else:warnings.append(dict(section=section,code='history_invalid',reason='повреждён исторический список'))
    return result,warnings+audit_world_history(result)


def migrate_snapshot(db, source):
    """Idempotent even when the same before snapshot occurs in many variants."""
    from hashlib import sha256
    if source.get('schema_version')==3:
        assert_world_state_v3_invariants(source['world_state'])
        return deepcopy(source),[]
    digest=sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    row=db.execute('SELECT snapshot_json,report_json FROM world_migrations_v3 WHERE source_hash=?',(digest,)).fetchone()
    if row:return json.loads(row[0]),json.loads(row[1])
    result=migrate_v2(source)
    snapshot=result.snapshot
    snapshot['history_head']=append_history(db,None,result.history)
    db.execute('INSERT INTO world_migrations_v3(source_hash,snapshot_json,report_json) VALUES(?,?,?)',
        (digest,json.dumps(snapshot,ensure_ascii=False),json.dumps(result.report,ensure_ascii=False)))
    return snapshot,result.report


def committed_snapshot(db, before_snapshot, resolved):
    """Caller commits this snapshot, its variant and this batch in ONE transaction."""
    state=assert_world_state_v3_invariants(resolved.state,before_snapshot['world_state'])
    snapshot=deepcopy(before_snapshot)
    snapshot['world_state']=state
    snapshot['character_cards'].extend(deepcopy(resolved.cards))
    snapshot['history_head']=append_history(db,before_snapshot.get('history_head'),resolved.history)
    return snapshot


def migrate_database(storage):
    """One transaction converts all writable snapshots, including inactive variants."""
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        initialize(db)
        if db.execute("SELECT 1 FROM schema_migrations WHERE name='runtime_v3'").fetchone():return
        for table, columns in (('saves',('state_json',)),('turns',('before_json','after_json')),
            ('game_jobs',('before_json','memory_before_json')),('actor_switches',('before_json','after_json'))):
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if not exists:continue
            available={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
            fields=[c for c in columns if c in available]
            for row in db.execute('SELECT rowid AS migration_row,* FROM '+table).fetchall():
                for column in fields:
                    if row[column]:
                        snapshot,_=migrate_snapshot(db,json.loads(row[column]))
                        db.execute('UPDATE '+table+' SET '+column+'=? WHERE rowid=?',(json.dumps(snapshot,ensure_ascii=False),row['migration_row']))
        for table in ('response_variants','archived_turns'):
            for row in db.execute('SELECT rowid AS migration_row,* FROM '+table).fetchall():
                payload=json.loads(row['payload'])
                for field in ('before_json','after_json'):
                    if payload.get(field):payload[field]=json.dumps(migrate_snapshot(db,json.loads(payload[field]))[0],ensure_ascii=False)
                db.execute('UPDATE '+table+' SET payload=? WHERE rowid=?',(json.dumps(payload,ensure_ascii=False),row['migration_row']))
                if table=='response_variants' and row['memory_before_json']:
                    snapshot,_=migrate_snapshot(db,json.loads(row['memory_before_json']))
                    db.execute('UPDATE response_variants SET memory_before_json=? WHERE rowid=?',(json.dumps(snapshot,ensure_ascii=False),row['migration_row']))
        from backend.repositories.living_world import project
        for row in db.execute('SELECT id,state_json FROM saves').fetchall():
            project(db,row['id'],json.loads(row['state_json']))
        db.execute("INSERT INTO schema_migrations(name) VALUES('runtime_v3')")
