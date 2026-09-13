"""SQLite worlds are immutable revisions; saves own independent snapshots."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from world_parser import parse_summary
from engine_storage import EngineStorage

DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'rpg.sqlite3'


class Storage(EngineStorage):
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('RPG_DB_PATH', DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS worlds (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
                    version INTEGER NOT NULL, source_md TEXT NOT NULL, digest TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(name_key, version), UNIQUE(name_key, digest));
                CREATE TABLE IF NOT EXISTS world_parts (
                    world_id INTEGER NOT NULL REFERENCES worlds(id),
                    kind TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(world_id, kind));
                CREATE TABLE IF NOT EXISTS saves (
                    id INTEGER PRIMARY KEY, world_id INTEGER NOT NULL REFERENCES worlds(id),
                    name TEXT NOT NULL, state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL REFERENCES saves(id),
                    sequence INTEGER NOT NULL, user_text TEXT NOT NULL, assistant_text TEXT NOT NULL,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL,
                    UNIQUE(save_id, sequence));
            ''')

        self.init_engine()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_world(self, name, markdown):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Название мира должно содержать от 1 до 120 символов.')
        state = parse_summary(markdown)
        digest = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM worlds WHERE name_key=? AND digest=?', (name.casefold(), digest)).fetchone()
            if existing:
                return existing['id']
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM worlds WHERE name_key=?', (name.casefold(),)).fetchone()[0]
            world_id = db.execute('INSERT INTO worlds(name,name_key,version,source_md,digest) VALUES(?,?,?,?,?)',
                                  (name, name.casefold(), version, markdown, digest)).lastrowid
            db.executemany('INSERT INTO world_parts VALUES(?,?,?)',
                           [(world_id, key, json.dumps(value, ensure_ascii=False)) for key, value in state.items()])
        return world_id

    def list_worlds(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name,version,created_at FROM worlds ORDER BY id DESC')]

    def get_world(self, world_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM worlds WHERE id=?', (world_id,)).fetchone()
            if row is None:
                raise ValueError('Мир не найден.')
            result = dict(row)
            result['state'] = {row['kind']: json.loads(row['payload']) for row in db.execute(
                'SELECT kind,payload FROM world_parts WHERE world_id=?', (world_id,))}
            return result

    def create_save(self, world_id, name):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Название прохождения должно содержать от 1 до 120 символов.')
        world = self.get_world(world_id)
        with self.connect() as db:
            return db.execute('INSERT INTO saves(world_id,name,state_json) VALUES(?,?,?)',
                              (world_id, name, json.dumps(world['state'], ensure_ascii=False))).lastrowid

    def list_saves(self, world_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,name,created_at,updated_at FROM saves WHERE world_id=? ORDER BY id DESC', (world_id,))]

    def get_save(self, save_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM saves WHERE id=?', (save_id,)).fetchone()
            if row is None:
                raise ValueError('Прохождение не найдено.')
            result = dict(row)
            result['state'] = json.loads(result.pop('state_json'))
            return result

    def list_turns(self, save_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,sequence,user_text,assistant_text,kind,choices_json,changes_json FROM turns WHERE save_id=? ORDER BY sequence', (save_id,))]

    def update_scene_meta(self, save_id, metadata):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            row = db.execute('SELECT state_json FROM saves WHERE id=?', (save_id,)).fetchone()
            if row is None:
                raise ValueError('Прохождение не найдено.')
            state = json.loads(row['state_json'])
            known = {c['id'] for c in state['characters']}
            if any(cid not in known for cid in metadata['present_ids']):
                raise ValueError('В сцене указан неизвестный персонаж.')
            state['scene_meta'] = metadata
            db.execute("UPDATE saves SET state_json=?, revision=revision+1, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                       (json.dumps(state, ensure_ascii=False), save_id))
