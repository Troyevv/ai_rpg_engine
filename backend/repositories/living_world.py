"""Rebuildable SQLite projection. Canonical snapshots remain variant-local."""
import json
from backend.services.world import normalize, KINDS


def project(db, save_id, state):
    world=normalize(state).get('world',{k:{} for k in KINDS})
    db.execute('DELETE FROM world_entities WHERE save_id=?',(save_id,))
    db.executemany('INSERT INTO world_entities(save_id,kind,entity_id,payload) VALUES(?,?,?,?)',
        [(save_id,kind,key,json.dumps(value,ensure_ascii=False)) for kind in KINDS for key,value in world[kind].items()])


def migrate(storage):
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        db.execute('''CREATE TABLE IF NOT EXISTS world_entities(
            save_id INTEGER NOT NULL REFERENCES saves(id),kind TEXT NOT NULL,entity_id TEXT NOT NULL,payload TEXT NOT NULL,
            PRIMARY KEY(save_id,kind,entity_id))''')
        db.execute('CREATE INDEX IF NOT EXISTS world_entity_kind ON world_entities(kind,save_id)')
        if not db.execute("SELECT 1 FROM schema_migrations WHERE name='living_world_v2'").fetchone():
            for row in db.execute('SELECT id,state_json FROM saves').fetchall():
                state=normalize(json.loads(row['state_json']))
                db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state,ensure_ascii=False),row['id']))
                project(db,row['id'],state)
            db.execute("INSERT INTO schema_migrations(name) VALUES('living_world_v2')")
