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
        if kind not in ('start', 'turn', 'regenerate','background','pov'):
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
            if kind not in ('start','pov') and last is None:
                raise ValueError('Сначала начни игру.')
            before, replaces = save['state_json'], None
            if kind=='pov':
                from backend.services.pov import transition
                target=config.get('actor_id')
                source=config.get('source_turn_id')
                if source is not None and (not last or last['id']!=source or last['kind']!='background' or target not in json.loads(last['audience_json'])):
                    raise ValueError('Выбери участника последней закулисной сцены.')
                transition(json.loads(before),target)  # Validate before starting any paid request.
                config=dict(config,source_node_id=last['node_id'] if source is not None else None)
            context_json, memory_before = None, None
            if kind == 'regenerate':
                target = config.get('target_turn_id')
                if target is not None:
                    last = db.execute('SELECT * FROM turns WHERE id=? AND save_id=?', (target,save_id)).fetchone()
                    if not last:
                        raise ValueError('Исходный ход не найден.')
                    # Keep subsequent turns until a replacement commits successfully.
                    later = db.execute('SELECT 1 FROM turns WHERE save_id=? AND sequence>?', (save_id,last['sequence'])).fetchone()
                    if later and not config.get('rollback_following'):
                        raise ValueError('Подтверди откат последующих ходов.')
                v = db.execute('SELECT context_json,memory_before_json,job_id FROM response_variants WHERE id=?', (last['active_variant_id'],)).fetchone()
                context_json, memory_before = (v[0],v[1]) if v else (None,None)
                if v and v['job_id']:
                    original=db.execute('SELECT config_json FROM game_jobs WHERE id=?',(v['job_id'],)).fetchone()
                    if original and '_prompts' in json.loads(original[0]):
                        config=dict(config,_prompts=json.loads(original[0])['_prompts'])
                        for key in ('actor_id','source_turn_id','source_node_id','camera_actor_id','camera_scene_id','camera_direct'):
                            if key in json.loads(original[0]):config[key]=json.loads(original[0])[key]
                if context_json is None:
                    raise ValueError('У старого хода нет снимка исходного контекста. Точная перегенерация недоступна.')
                before, replaces, user_text, kind = last['before_json'], last['id'], last['user_text'], last['kind']
            from backend.services.pov import controlled
            if kind == 'turn' and controlled(json.loads(before)) is None:
                raise ValueError('Камера наблюдает мир. Выбери персонажа для управления или продолжи наблюдение.')
            if kind == 'background':
                from backend.services.director import observe
                observe(json.loads(before),config.get('camera_actor_id'),config.get('camera_scene_id'),config.get('camera_direct',False))
            if kind == 'turn' and not user_text.strip():
                raise ValueError('Напиши действие.')
            from backend.services.pov import controlled
            config = dict(config)
            config.setdefault('_prompts',self.prompt_snapshot(db))
            job_id = uuid.uuid4().hex
            db.execute('''INSERT INTO game_jobs(id,save_id,revision,before_json,user_text,kind,replaces_id,status,config_json)
                          VALUES(?,?,?,?,?,?,?,'generating',?)''',
                       (job_id, save_id, save['revision'], before, user_text, kind, replaces, json.dumps(config)))
            session_id = self.ensure_session(db, save_id)
            db.execute('UPDATE game_jobs SET context_json=?,memory_before_json=?,session_id=? WHERE id=?', (context_json,memory_before,session_id,job_id))
            db.execute('UPDATE game_jobs SET pov_actor_id=? WHERE id=?',(None if kind=='background' else config.get('actor_id') if kind=='pov' else controlled(json.loads(before)),job_id))
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
            settings = json.loads(job['config_json'])
            if config:
                settings.update({k:v for k,v in config.items() if k not in ('target_turn_id','rollback_following','expected_revision','_prompts','actor_id','source_turn_id','source_node_id')})
            session_id = self.ensure_session(db, job['save_id'])
            db.execute("UPDATE game_jobs SET status='extracting',error='',warnings_json='[]',config_json=?,session_id=? WHERE id=?", (json.dumps(settings),session_id,job_id))

    def commit_job(self, job_id, state, choices, changes, timing=None):
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
                self._rollback_after(db, job['save_id'], old['sequence'], json.loads(job['config_json']).get('rollback_following',False))
            sequence = old['sequence'] if job['replaces_id'] is not None else db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM turns WHERE save_id=?', (job['save_id'],)).fetchone()[0]
            after = json.dumps(state, ensure_ascii=False)
            values = (job['user_text'], job['narrative'], job['before_json'], after, job['kind'],
                      json.dumps(choices,ensure_ascii=False), json.dumps(changes,ensure_ascii=False))
            if job['replaces_id'] is not None:
                tid = old['id']
                db.execute('UPDATE turns SET user_text=?,assistant_text=?,before_json=?,after_json=?,kind=?,choices_json=?,changes_json=? WHERE id=?', (*values,tid))
            else:
                tid = db.execute('INSERT INTO turns(user_text,assistant_text,before_json,after_json,kind,choices_json,changes_json,save_id,sequence) VALUES(?,?,?,?,?,?,?,?,?)', (*values,job['save_id'],sequence)).lastrowid
            db.execute('UPDATE turns SET pov_actor_id=?,audience_json=?,timing_json=? WHERE id=?',(job['pov_actor_id'],job['audience_json'],json.dumps(timing) if timing else None,tid))
            record = dict(db.execute('SELECT * FROM turns WHERE id=?', (tid,)).fetchone())
            self._variant(db, record, job_id, job['context_json'], job['memory_before_json'])
            self._archive_memory(db, job['save_id'], state)
            db.execute("UPDATE saves SET state_json=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (after, job['save_id']))
            db.execute("UPDATE game_jobs SET status='saved',timing_json=? WHERE id=?", (json.dumps(timing) if timing else None,job_id))

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
            self._archive_memory(db, save_id, json.loads(last['before_json']))
