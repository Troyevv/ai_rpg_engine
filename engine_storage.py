"""Durable drafts and optimistic, atomic game turns."""
import json
import sqlite3
import uuid

ACTIVE = ('generating', 'extracting', 'validating')


class EngineStorage:
    def init_engine(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table, additions in {
                'saves': {'revision': 'INTEGER NOT NULL DEFAULT 0'},
                'turns': {'kind': "TEXT NOT NULL DEFAULT 'turn'", 'choices_json': "TEXT NOT NULL DEFAULT '[]'",
                          'changes_json': "TEXT NOT NULL DEFAULT '{}'"},
            }.items():
                columns = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for name, declaration in additions.items():
                    if name not in columns:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
            db.execute('''CREATE TABLE IF NOT EXISTS game_jobs (
                id TEXT PRIMARY KEY, save_id INTEGER NOT NULL REFERENCES saves(id),
                revision INTEGER NOT NULL, before_json TEXT NOT NULL, user_text TEXT NOT NULL,
                kind TEXT NOT NULL, replaces_id INTEGER, status TEXT NOT NULL,
                narrative TEXT NOT NULL DEFAULT '', narrative_complete INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '', config_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))''')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_game_job ON game_jobs(save_id) WHERE status IN ('generating','extracting','validating')")
            db.execute('''CREATE TABLE IF NOT EXISTS archived_turns (
                id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, reason TEXT NOT NULL, payload TEXT NOT NULL)''')

    def latest_job(self, save_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM game_jobs WHERE save_id=? ORDER BY rowid DESC LIMIT 1', (save_id,)).fetchone()
            return dict(row) if row else None

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ValueError('Черновик не найден.')
            return dict(row)

    def begin_job(self, save_id, user_text, kind, config):
        if kind not in ('start', 'turn', 'regenerate'):
            raise ValueError('Неизвестный тип хода.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            save = db.execute('SELECT * FROM saves WHERE id=?', (save_id,)).fetchone()
            if save is None:
                raise ValueError('Прохождение не найдено.')
            if config.get('expected_revision', save['revision']) != save['revision']:
                raise ValueError('Сейв уже изменился. Обнови страницу перед следующим действием.')
            last = db.execute('SELECT * FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1', (save_id,)).fetchone()
            if kind == 'start' and last:
                raise ValueError('Игра уже начата.')
            if kind != 'start' and last is None:
                raise ValueError('Сначала начни игру.')
            before, replaces = save['state_json'], None
            if kind == 'regenerate':
                before, replaces, user_text, kind = last['before_json'], last['id'], last['user_text'], last['kind']
            if kind == 'turn' and not user_text.strip():
                raise ValueError('Напиши действие.')
            job_id = uuid.uuid4().hex
            db.execute('''INSERT INTO game_jobs(id,save_id,revision,before_json,user_text,kind,replaces_id,status,config_json)
                          VALUES(?,?,?,?,?,?,?,'generating',?)''',
                       (job_id, save_id, save['revision'], before, user_text, kind, replaces, json.dumps(config)))
        return job_id

    @staticmethod
    def _assert_idle(db, save_id):
        if db.execute("SELECT 1 FROM game_jobs WHERE save_id=? AND status IN ('generating','extracting','validating')", (save_id,)).fetchone():
            raise ValueError('Для этого прохождения уже выполняется ход.')

    def job_progress(self, job_id, status, narrative=None, complete=False, error=''):
        if status not in (*ACTIVE, 'error', 'stopped'):
            raise ValueError('Некорректный статус.')
        with self.connect() as db:
            db.execute("""UPDATE game_jobs SET status=?, narrative=COALESCE(?,narrative),
                        narrative_complete=MAX(narrative_complete,?), error=?
                        WHERE id=? AND status IN ('generating','extracting','validating')""",
                       (status, narrative, int(complete), error, job_id))

    def retry_job(self, job_id, config=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if job is None or not job['narrative_complete'] or job['status'] not in ('error', 'stopped'):
                raise ValueError('Нет завершённого текста для повторной обработки.')
            self._assert_idle(db, job['save_id'])
            revision = db.execute('SELECT revision FROM saves WHERE id=?', (job['save_id'],)).fetchone()[0]
            if revision != job['revision']:
                raise ValueError('Сейв изменился. Этот черновик устарел.')
            db.execute("UPDATE game_jobs SET status='extracting',error='',config_json=? WHERE id=?", (json.dumps(config) if config else job['config_json'], job_id))

    def commit_job(self, job_id, state, choices, changes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if job is None or job['status'] != 'validating':
                raise ValueError('Ход остановлен или уже сохранён.')
            save = db.execute('SELECT revision FROM saves WHERE id=?', (job['save_id'],)).fetchone()
            if save['revision'] != job['revision']:
                raise ValueError('Состояние сейва изменилось во время генерации.')
            if job['replaces_id'] is not None:
                old = db.execute('SELECT * FROM turns WHERE id=? AND save_id=?', (job['replaces_id'], job['save_id'])).fetchone()
                if old is None:
                    raise ValueError('Исходный ход уже изменён.')
                db.execute('INSERT INTO archived_turns(save_id,reason,payload) VALUES(?,?,?)',
                           (job['save_id'], 'regenerate', json.dumps(dict(old), ensure_ascii=False)))
                db.execute('DELETE FROM turns WHERE id=?', (old['id'],))
            sequence = db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM turns WHERE save_id=?', (job['save_id'],)).fetchone()[0]
            after = json.dumps(state, ensure_ascii=False)
            db.execute('''INSERT INTO turns(save_id,sequence,user_text,assistant_text,before_json,after_json,kind,choices_json,changes_json)
                          VALUES(?,?,?,?,?,?,?,?,?)''', (job['save_id'], sequence, job['user_text'], job['narrative'], job['before_json'], after,
                                                       job['kind'], json.dumps(choices, ensure_ascii=False), json.dumps(changes, ensure_ascii=False)))
            db.execute("UPDATE saves SET state_json=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (after, job['save_id']))
            db.execute("UPDATE game_jobs SET status='saved' WHERE id=?", (job_id,))

    def rollback_last(self, save_id, expected_revision=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            current = db.execute('SELECT revision FROM saves WHERE id=?', (save_id,)).fetchone()
            if expected_revision is not None and (current is None or current['revision'] != expected_revision):
                raise ValueError('Сейв изменился. Обнови страницу перед откатом.')
            last = db.execute('SELECT * FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1', (save_id,)).fetchone()
            if last is None:
                raise ValueError('Нет ходов для отката.')
            db.execute('INSERT INTO archived_turns(save_id,reason,payload) VALUES(?,?,?)', (save_id, 'rollback', json.dumps(dict(last), ensure_ascii=False)))
            db.execute('DELETE FROM turns WHERE id=?', (last['id'],))
            db.execute("UPDATE saves SET state_json=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (last['before_json'], save_id))
