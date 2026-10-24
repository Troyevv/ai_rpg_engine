"""Additive storage for preparation workspaces and UI preference profiles."""
import json
import uuid
from storage import Storage
from backend.repositories.drafts import DraftStorage


from backend.repositories.presentation import PresentationStorage


class Repository(PresentationStorage, DraftStorage, Storage):
    def __init__(self, path=None):
        super().__init__(path)
        self.init_presentation()
        from backend.repositories.portraits import initialize as initialize_portraits
        with self.connect() as db: initialize_portraits(db)
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
            if 'phase' not in {r['name'] for r in db.execute('PRAGMA table_info(preparation_jobs)')}:
                db.execute("ALTER TABLE preparation_jobs ADD COLUMN phase TEXT NOT NULL DEFAULT ''")
            if 'response_journal' not in {r['name'] for r in db.execute('PRAGMA table_info(preparation_jobs)')}:
                db.execute("ALTER TABLE preparation_jobs ADD COLUMN response_journal TEXT NOT NULL DEFAULT '{}'")
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
        journal = json.loads(job.get('response_journal') or '{}')
        world=journal.get('responses',{}).get('world',{})
        assembly_error=world.get('assembly_error','')
        retry_boundary=bool(assembly_error and len(world.get('parts',[]))>=2 and not any(word in assembly_error for word in ('целостность','Пропущен')))
        job = {**job, 'fragment_recovery':retry_boundary, 'transport_blocked':bool(assembly_error and not retry_boundary),
               'transport_incomplete':bool(world and not journal.get('candidate_text')),
               'unknown_outcome':bool(journal.get('pending')),
               'resumable':bool(journal and not journal.get('pending') and job.get('status') in ('error','stopped'))}
        if assembly_error:job['error']='Не удалось собрать сохранённые части ответа. Диагностика доступна автору.'
        staged = json.loads(job.get('memory_before_json') or '{}').get('_remote_batch')
        if staged and job.get('status') != 'saved':
            job = {**job, 'narrative': ''}
        if job.get('kind','').startswith('draft_'):
            job={**job,'narrative':'','progress_chars':len(job.get('narrative',''))}
            if job.get('error','').startswith('Две попытки'):job['error']='Две попытки исправления исчерпаны. Мир сохранён; подробности доступны автору.'
        return {k: v for k, v in job.items() if k not in ('config_json', 'before_json', 'context_json', 'memory_before_json', 'warnings_json', 'response_journal')}

    def save_response_journal(self, jid, journal):
        """Private response transport state; no new checkpoint table or world format."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT response_journal FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if current and json.loads(current[0] or '{}').get('recovery_epoch',0)!=journal.get('recovery_epoch',0):
                raise ValueError('Устаревший работник генерации: результат не принят.')
            db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',
                       (json.dumps(journal,ensure_ascii=False),jid))

    def resume_draft_response(self, jid, *, revision=None, config_changes=None, acknowledge_unknown=False, retry_last_fragment=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = dict(db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone())
            journal = json.loads(job['response_journal'])
            if job['kind'] != 'draft_world' or job['status'] not in ('error','stopped','saved') or not journal:
                raise ValueError('Нет сохранённого ответа для продолжения.')
            if journal.get('pending') and not acknowledge_unknown:
                raise ValueError('Исход прерванного запроса неизвестен. Автоматический повтор запрещён; полученный текст сохранён.')
            self._draft_workspace(db,job['workspace_id'],job['revision'] if revision is None else revision)
            config=json.loads(job['config_json'])
            if config_changes:
                journal.setdefault('config_history',[]).append(config.copy())
                config.update(config_changes)
            if journal.get('pending'):
                journal.setdefault('unknown_attempts',[]).append(journal.pop('pending'))
            if retry_last_fragment:
                from backend.services.draft_response import digest,join_fragments
                record=journal.get('responses',{}).get('world',{})
                parts=record.get('parts',[])
                if not record.get('assembly_error') or len(parts)<2:
                    raise ValueError('Нет проблемного продолжения для повтора.')
                offset=0
                for part in parts:
                    if part['sha256']!=digest(part['text']) or part['offset']!=offset:
                        raise ValueError('Повреждена целостность исходных фрагментов; повтор не разрешён.')
                    offset+=len(part['text'])
                if record.get('assembly'):
                    from backend.services.draft_initial import prompt_schema
                    join_fragments(parts,dict(record['assembly']),schema=prompt_schema(),terminal=record.get('complete',False))
                journal.setdefault('fragment_recoveries',[]).append(dict(part=parts.pop(),assembly=record.pop('assembly',None),reason=record.pop('assembly_error'),epoch=journal.get('recovery_epoch',0)))
                record['complete']=False
            if revision is not None:
                head=self._draft_head(db,job['workspace_id'])
                if head:
                    record=json.loads(head['content'])
                    owned=record.get('origin_job')==jid
                    if not record.get('origin_job') and journal.get('candidate_text') and journal.get('responses',{}).get('world',{}).get('complete'):
                        # Legacy jobs must prove an accepted candidate, never adopt
                        # an arbitrary workspace head merely because a revision matched.
                        try:
                            accepted=json.loads(journal['candidate_text']);ancestor=head
                            while ancestor:
                                content=json.loads(ancestor['content'])
                                if content.get('origin_job') not in (None,jid):break
                                if content.get('state')==accepted and content.get('source','')==config.get('_draft_source',config.get('_draft_input','')):
                                    owned=True;break
                                if ancestor['reason']=='restore':
                                    ancestor=db.execute("SELECT * FROM document_versions WHERE id=? AND owner=? AND kind='world_draft'",(ancestor['source_version_id'],job['workspace_id'])).fetchone()
                                elif ancestor['reason'] in ('patch','add','remove','candidate_patch'):
                                    ancestor=db.execute("SELECT * FROM document_versions WHERE id<? AND owner=? AND kind='world_draft' ORDER BY id DESC LIMIT 1",(ancestor['id'],job['workspace_id'])).fetchone()
                                else:break
                        except (ValueError,KeyError):owned=False
                    if owned:
                        journal['candidate_text']=json.dumps(record['state'],ensure_ascii=False)
                        journal['candidate_job']=jid
                    else:
                        journal.pop('candidate_text',None)
                        journal.pop('candidate_job',None)
                db.execute('UPDATE preparation_jobs SET revision=? WHERE id=?',(revision,jid))
            db.execute('UPDATE preparation_jobs SET config_json=? WHERE id=?',(json.dumps(config,ensure_ascii=False),jid))
            journal['recovery_epoch']=journal.get('recovery_epoch',0)+1
            db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(json.dumps(journal,ensure_ascii=False),jid))
            db.execute("UPDATE preparation_jobs SET status='generating',error='' WHERE id=?",(jid,))
            return config

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
            if config.get('_draft_task')=='world':
                config['_draft_source']=config.get('_draft_input','')
                if config.get('_use_idea'):config['_draft_source']+='\n\n'+w['idea']
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
