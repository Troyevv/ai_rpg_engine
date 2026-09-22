"""Additive storage for preparation workspaces and UI preference profiles."""
import json
import uuid
from storage import Storage


class Repository(Storage):
    def __init__(self, path=None):
        super().__init__(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS preparation_workspaces (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, idea TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT '', summary_complete INTEGER NOT NULL DEFAULT 0,
              messages_json TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS preparation_jobs (
              id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES preparation_workspaces(id),
              kind TEXT NOT NULL, status TEXT NOT NULL, narrative TEXT NOT NULL DEFAULT '',
              error TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL, config_json TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS active_preparation_job ON preparation_jobs(workspace_id)
              WHERE status='generating';
            CREATE TABLE IF NOT EXISTS client_settings (profile TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if 'deleted' not in {r['name'] for r in db.execute('PRAGMA table_info(preparation_workspaces)')}:
                db.execute('ALTER TABLE preparation_workspaces ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
            for w in db.execute('SELECT * FROM preparation_workspaces').fetchall():
                for kind in ('idea','summary'):
                    if not db.execute('SELECT 1 FROM document_heads WHERE kind=? AND owner=?',(kind,w['id'])).fetchone():
                        self._record_document(db,kind,w['id'],w[kind],bool(w['summary_complete']) if kind=='summary' else bool(w[kind]),'migration')

    def list_workspaces(self, deleted=False):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,revision FROM preparation_workspaces WHERE deleted=? ORDER BY rowid DESC',(int(deleted),))]

    def create_workspace(self, name):
        wid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO preparation_workspaces(id,name) VALUES(?,?)', (wid, name))
            for kind in ('idea','summary'):
                self._record_document(db,kind,wid,'',False,'created')
        return self.workspace(wid)

    def workspace(self, wid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM preparation_workspaces WHERE id=?', (wid,)).fetchone()
            if row is None:
                raise ValueError('Подготовка не найдена.')
            result = dict(row)
            result['messages'] = json.loads(result.pop('messages_json'))
            job = db.execute('SELECT * FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1', (wid,)).fetchone()
            result['job'] = self.public_job(dict(job)) if job else None
            return result

    @staticmethod
    def public_job(job):
        return {k: v for k, v in job.items() if k not in ('config_json', 'before_json', 'context_json', 'memory_before_json', 'warnings_json')}

    def preparation_job(self, jid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM preparation_jobs WHERE id=?', (jid,)).fetchone()
            if row is None:
                raise ValueError('Задача не найдена.')
            return dict(row)

    def begin_preparation(self, wid, kind, text, config, revision):
        jid = 'prep_' + uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            w = db.execute('SELECT * FROM preparation_workspaces WHERE id=?', (wid,)).fetchone()
            if not w or w['deleted'] or w['revision'] != revision:
                raise ValueError('Подготовка изменилась. Обнови её перед запросом.')
            if db.execute("SELECT 1 FROM preparation_jobs WHERE workspace_id=? AND status='generating'", (wid,)).fetchone():
                raise ValueError('Подготовка уже выполняется.')
            if kind == 'summary' and not w['idea'].strip():
                raise ValueError('Сначала создай сценарий.')
            if kind == 'summary':
                db.execute('UPDATE preparation_workspaces SET summary_complete=0 WHERE id=?', (wid,))
            if kind == 'idea':
                messages = json.loads(w['messages_json']) + [{'role': 'user', 'content': text}]
                db.execute('UPDATE preparation_workspaces SET messages_json=? WHERE id=?', (json.dumps(messages, ensure_ascii=False), wid))
            config = dict(config, _prompts=self.prompt_snapshot(db))
            db.execute("INSERT INTO preparation_jobs(id,workspace_id,kind,status,revision,config_json) VALUES(?,?,?,'generating',?,?)",
                       (jid, wid, kind, revision, json.dumps(config)))
        return jid

    def preparation_progress(self, jid, narrative, status='generating', error=''):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM preparation_jobs WHERE id=?', (jid,)).fetchone()
            if job and job['status']=='stopped' and status=='stopped' and narrative.startswith(job['narrative']):
                # A worker may have received a final chunk after the timed UI flush.
                # Keep it in the stopped draft without rewriting a newer workspace.
                db.execute('UPDATE preparation_jobs SET narrative=? WHERE id=?',(narrative,jid))
                return
            if not job or job['status'] != 'generating':
                return
            if status=='saved' and job['kind']=='summary':
                from world_parser import parse_summary
                parse_summary(narrative)
            db.execute('UPDATE preparation_jobs SET narrative=?,status=?,error=? WHERE id=?', (narrative, status, error, jid))
            if status in ('saved', 'stopped'):
                w = db.execute('SELECT * FROM preparation_workspaces WHERE id=?', (job['workspace_id'],)).fetchone()
                if w['revision'] != job['revision']:
                    raise ValueError('Подготовка изменилась во время генерации.')
                if job['kind'] == 'idea' and narrative.strip():
                    self._record_document(db,'idea',w['id'],narrative,status=='saved','generation')
                    self._record_document(db,'summary',w['id'],'',False,'idea_changed')
                    db.execute("UPDATE preparation_workspaces SET idea=?,summary='',summary_complete=0,revision=revision+1 WHERE id=?", (narrative, w['id']))
                elif job['kind'] == 'summary':
                    self._record_document(db,'summary',w['id'],narrative,status=='saved','generation')
                    db.execute('UPDATE preparation_workspaces SET summary=?,summary_complete=?,revision=revision+1 WHERE id=?', (narrative, int(status == 'saved'), w['id']))

    def reset_workspace(self, wid, revision):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM preparation_jobs WHERE workspace_id=? AND status='generating'", (wid,)).fetchone():
                raise ValueError('Сначала останови генерацию.')
            cursor = db.execute("UPDATE preparation_workspaces SET idea='',summary='',summary_complete=0,messages_json='[]',revision=revision+1 WHERE id=? AND revision=?", (wid, revision))
            if not cursor.rowcount:
                raise ValueError('Подготовка изменилась.')
            for kind in ('idea','summary'):
                self._record_document(db,kind,wid,'',False,'reset')

    def get_settings(self, profile):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM client_settings WHERE profile=?', (profile,)).fetchone()
            return json.loads(row['payload']) if row else {}

    def save_settings(self, profile, payload):
        with self.connect() as db:
            db.execute('INSERT INTO client_settings VALUES(?,?) ON CONFLICT(profile) DO UPDATE SET payload=excluded.payload', (profile, json.dumps(payload)))
