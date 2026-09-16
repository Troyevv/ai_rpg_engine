"""Immutable generation records; turns is the current canonical projection."""
import json
import uuid
from datetime import datetime, timezone


def dump(value):
    return json.dumps(value, ensure_ascii=False)


class RuntimeStorage:
    def init_runtime(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS actor_switches(id INTEGER PRIMARY KEY,save_id INTEGER NOT NULL,revision INTEGER NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,parent_variant_id TEXT);
            CREATE TABLE IF NOT EXISTS play_sessions (
              id TEXT PRIMARY KEY, save_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS response_variants (
              id TEXT PRIMARY KEY, node_id TEXT NOT NULL, save_id INTEGER NOT NULL,
              parent_variant_id TEXT, ordinal INTEGER NOT NULL, job_id TEXT,
              payload TEXT NOT NULL, context_json TEXT, memory_before_json TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(node_id,ordinal));
            CREATE TABLE IF NOT EXISTS llm_requests (
              id TEXT PRIMARY KEY, job_id TEXT NOT NULL, save_id INTEGER, workspace_id TEXT,
              session_id TEXT, stage TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
              thinking TEXT NOT NULL, context_json TEXT NOT NULL, diagnostics_json TEXT NOT NULL,
              config_json TEXT NOT NULL, pricing_json TEXT, input_tokens INTEGER, output_tokens INTEGER,
              cached_input_tokens INTEGER, cost_usd TEXT, usage_json TEXT,
              status TEXT NOT NULL DEFAULT 'running', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS request_job ON llm_requests(job_id);
            CREATE INDEX IF NOT EXISTS request_save ON llm_requests(save_id, session_id);
            CREATE TABLE IF NOT EXISTS provider_credentials (provider TEXT PRIMARY KEY, encrypted_key BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS memory_versions (
              id TEXT PRIMARY KEY, save_id INTEGER NOT NULL, job_id TEXT NOT NULL,
              through_sequence INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            db.execute('BEGIN IMMEDIATE')
            for table, columns in {
                'turns': {'pov_actor_id':'TEXT', 'audience_json':"TEXT NOT NULL DEFAULT '[]'", 'node_id': 'TEXT', 'active_variant_id': 'TEXT', 'memory_archived': 'INTEGER NOT NULL DEFAULT 0'},
                'game_jobs': {'pov_actor_id':'TEXT', 'audience_json':"TEXT NOT NULL DEFAULT '[]'", 'context_json': 'TEXT', 'memory_before_json': 'TEXT', 'warnings_json': "TEXT NOT NULL DEFAULT '[]'", 'session_id': 'TEXT'},
            }.items():
                existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for name, declaration in columns.items():
                    if name not in existing:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
            # Idempotent backfill: never rewrite legacy before/after JSON.
            for t in db.execute('SELECT * FROM turns WHERE node_id IS NULL ORDER BY save_id,sequence').fetchall():
                self._variant(db, dict(t), None, None, None)

    def _variant(self, db, turn, job_id, context, memory_before):
        node = turn.get('node_id') or uuid.uuid4().hex
        parent = db.execute('SELECT active_variant_id FROM turns WHERE save_id=? AND sequence<? ORDER BY sequence DESC LIMIT 1',
                            (turn['save_id'], turn['sequence'])).fetchone()
        ordinal = db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM response_variants WHERE node_id=?', (node,)).fetchone()[0]
        vid = uuid.uuid4().hex
        turn.update(node_id=node, active_variant_id=vid)
        db.execute('INSERT INTO response_variants(id,node_id,save_id,parent_variant_id,ordinal,job_id,payload,context_json,memory_before_json) VALUES(?,?,?,?,?,?,?,?,?)',
                   (vid, node, turn['save_id'], parent[0] if parent else None, ordinal, job_id, dump(turn), context, memory_before))
        db.execute('UPDATE turns SET node_id=?,active_variant_id=? WHERE id=?', (node, vid, turn['id']))
        return vid

    def variants(self, node):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,ordinal,job_id,created_at,(context_json IS NOT NULL) AS can_regenerate FROM response_variants WHERE node_id=? ORDER BY ordinal', (node,))]

    def start_session(self, save_id):
        self.get_save(save_id)
        with self.connect() as db:
            self._assert_idle(db, save_id)
            sid = uuid.uuid4().hex
            db.execute('INSERT INTO play_sessions(id,save_id) VALUES(?,?)', (sid, save_id))
            return sid

    def ensure_session(self, db, save_id):
        session = db.execute('SELECT id FROM play_sessions WHERE save_id=? ORDER BY rowid DESC LIMIT 1', (save_id,)).fetchone()
        if session:
            return session[0]
        sid = uuid.uuid4().hex
        db.execute('INSERT INTO play_sessions(id,save_id) VALUES(?,?)', (sid, save_id))
        return sid

    def save_context(self, job_id, messages, before):
        with self.connect() as db:
            db.execute('UPDATE game_jobs SET context_json=COALESCE(context_json,?),memory_before_json=COALESCE(memory_before_json,?) WHERE id=?',
                       (dump(messages), dump(before), job_id))

    def begin_request(self, job_id, stage, config, messages, diagnostics):
        from backend.services.usage import price_snapshot
        rid = uuid.uuid4().hex
        with self.connect() as db:
            job = db.execute('SELECT save_id,session_id FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            workspace = None
            if not job:
                workspace = db.execute('SELECT workspace_id FROM preparation_jobs WHERE id=?', (job_id,)).fetchone()[0]
            db.execute('''INSERT INTO llm_requests(id,job_id,save_id,workspace_id,session_id,stage,provider,model,thinking,context_json,diagnostics_json,config_json,pricing_json)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (rid, job_id, job['save_id'] if job else None, workspace,
              job['session_id'] if job else None, stage, config.get('provider','local'), config['model'], config.get('thinking','off'),
              dump(messages), dump(diagnostics), dump(config), dump(price_snapshot(config, datetime.now(timezone.utc)))))
        return rid

    def finish_request(self, rid, status, usage):
        from backend.services.usage import usage_values, cost
        inp, out, cached = usage_values(usage)
        with self.connect() as db:
            pricing = json.loads(db.execute('SELECT pricing_json FROM llm_requests WHERE id=?', (rid,)).fetchone()[0])
            amount = cost(inp, out, cached, pricing)
            db.execute('UPDATE llm_requests SET status=?,usage_json=?,input_tokens=?,output_tokens=?,cached_input_tokens=?,cost_usd=? WHERE id=?',
                       (status, dump(usage) if usage is not None else None, inp, out, cached, amount, rid))

    def request_log(self, save_id=None, workspace_id=None, job_id=None):
        field, value = ('save_id', save_id) if save_id is not None else ('workspace_id', workspace_id) if workspace_id else ('job_id', job_id)
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(f'SELECT * FROM llm_requests WHERE {field}=? ORDER BY rowid DESC', (value,))]
        for r in rows:
            r['diagnostics'] = json.loads(r.pop('diagnostics_json'))
            r['messages'] = json.loads(r.pop('context_json'))
            r['pricing'] = json.loads(r.pop('pricing_json'))
            r.pop('config_json')
        return rows

    def accounting(self, save_id):
        from decimal import Decimal
        rows = self.request_log(save_id=save_id)
        save = self.get_save(save_id)
        with self.connect() as db:
            sid = db.execute('SELECT id FROM play_sessions WHERE save_id=? ORDER BY rowid DESC LIMIT 1', (save_id,)).fetchone()
            world_rows = [dict(r) for r in db.execute('SELECT cost_usd,input_tokens,output_tokens,cached_input_tokens FROM llm_requests WHERE save_id IN (SELECT id FROM saves WHERE world_id=?)', (save['world_id'],))]
        def total(records):
            return {'cost_usd': str(sum((Decimal(r['cost_usd']) for r in records if r['cost_usd'] is not None), Decimal(0))),
                    'unknown_requests': sum(r['cost_usd'] is None for r in records),
                    **{k: sum(r[k] or 0 for r in records) for k in ('input_tokens','output_tokens','cached_input_tokens')}}
        return {'session_id': sid[0] if sid else None, 'session': total([r for r in rows if sid and r['session_id']==sid[0]]),
                'game': total(rows), 'world': total(world_rows), 'requests': rows}

    def select_variant(self, save_id, turn_id, variant_id, revision, rollback=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            save = db.execute('SELECT revision FROM saves WHERE id=?', (save_id,)).fetchone()
            if not save or save[0] != revision:
                raise ValueError('Сейв изменился. Обнови страницу.')
            turn = db.execute('SELECT * FROM turns WHERE id=? AND save_id=?', (turn_id,save_id)).fetchone()
            variant = db.execute('SELECT * FROM response_variants WHERE id=? AND save_id=?', (variant_id,save_id)).fetchone()
            if not turn or not variant or turn['node_id'] != variant['node_id']:
                raise ValueError('Вариант не принадлежит этому ходу.')
            if turn['active_variant_id'] == variant_id:
                return
            self._rollback_after(db, save_id, turn['sequence'], rollback)
            p = json.loads(variant['payload'])
            for key in ('user_text','assistant_text','before_json','after_json','kind','choices_json','changes_json','pov_actor_id','audience_json'):
                db.execute(f'UPDATE turns SET {key}=? WHERE id=?', (p.get(key,'[]' if key=='audience_json' else None),turn_id))
            db.execute('UPDATE turns SET active_variant_id=? WHERE id=?', (variant_id,turn_id))
            db.execute('UPDATE saves SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?', (p['after_json'],save_id))
            self._archive_memory(db, save_id, json.loads(p['after_json']))

    def _rollback_after(self, db, save_id, sequence, confirmed):
        later = db.execute('SELECT * FROM turns WHERE save_id=? AND sequence>? ORDER BY sequence', (save_id,sequence)).fetchall()
        if later and not confirmed:
            raise ValueError('Подтверди откат последующих ходов: их состояние зависит от прежнего ответа.')
        for t in later:
            db.execute('INSERT INTO archived_turns(save_id,reason,payload) VALUES(?,?,?)', (save_id,'variant_switch',dump(dict(t))))
        db.execute('DELETE FROM turns WHERE save_id=? AND sequence>?', (save_id,sequence))

    def _archive_memory(self, db, save_id, state):
        from backend.repositories.living_world import project
        project(db,save_id,state)
        through = state.get('memory',{}).get('through_sequence',-1)
        db.execute('UPDATE turns SET memory_archived=(sequence<=?) WHERE save_id=?', (through,save_id))

    def switch_actor(self,save_id,actor,revision):
        # Compatibility helper. HTTP transitions always use an atomic POV generation job.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db,save_id)
            row=db.execute('SELECT * FROM saves WHERE id=?',(save_id,)).fetchone()
            if not row or row['revision']!=revision:
                raise ValueError('Сейв изменился. Обнови страницу.')
            from backend.services.pov import transition
            state=transition(json.loads(row['state_json']),actor)
            parent=db.execute('SELECT active_variant_id FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1',(save_id,)).fetchone()
            after=dump(state)
            db.execute('INSERT INTO actor_switches(save_id,revision,before_json,after_json,parent_variant_id) VALUES(?,?,?,?,?)',(save_id,revision,row['state_json'],after,parent[0] if parent else None))
            db.execute('UPDATE saves SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(after,save_id))
            from backend.repositories.living_world import project
            project(db,save_id,state)
