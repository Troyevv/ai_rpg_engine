"""Additive Chat migration and transactional text lineage. No WorldState writes."""
import hashlib
import json
import uuid
from contextlib import contextmanager

from backend.chat.context import assemble, budget, estimate, require_fit


def uid():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def row(db, table, ident, campaign=None):
    # Table names are module constants at call sites, never request parameters.
    value = db.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
    if not value or (campaign and value['campaign_id'] != campaign):
        raise ValueError('Объект не принадлежит этой кампании или не найден.')
    return dict(value)


class ChatRepository:
    def __init__(self, storage):
        self.storage = storage
        self.connect = storage.connect
        self.migrate()

    def migrate(self):
        with self.connect() as db:
            # Explicit additive migration; no legacy rows or snapshots are touched.
            db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS chat_sources (id TEXT PRIMARY KEY, memory TEXT NOT NULL, origin_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_campaigns (
              id TEXT PRIMARY KEY, creation_token TEXT UNIQUE NOT NULL, creation_hash TEXT NOT NULL,
              name TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'chat' CHECK(mode='chat'),
              revision INTEGER NOT NULL DEFAULT 0, active_branch TEXT NOT NULL,
              source_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chat_branches (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              parent_id TEXT, fork_seq INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL,
              head INTEGER NOT NULL DEFAULT 0, memory_id TEXT NOT NULL, config_id TEXT NOT NULL,
              chapter_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_configs (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              branch_id TEXT NOT NULL, parent_id TEXT, applies_after INTEGER NOT NULL,
              payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_memories (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              branch_id TEXT NOT NULL, parent_id TEXT, config_id TEXT NOT NULL,
              cutoff INTEGER NOT NULL, applies_after INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL, source TEXT NOT NULL,
              tail_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chat_chapters (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              branch_id TEXT NOT NULL, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
              start_seq INTEGER NOT NULL, seed_memory TEXT NOT NULL, seed_config TEXT NOT NULL,
              UNIQUE(branch_id,ordinal));
            CREATE TABLE IF NOT EXISTS chat_messages (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
              status TEXT NOT NULL, job_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chat_path (
              branch_id TEXT NOT NULL REFERENCES chat_branches(id), seq INTEGER NOT NULL,
              message_id TEXT NOT NULL REFERENCES chat_messages(id), chapter_id TEXT NOT NULL REFERENCES chat_chapters(id),
              PRIMARY KEY(branch_id,seq), UNIQUE(branch_id,message_id));
            CREATE TABLE IF NOT EXISTS chat_jobs (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              branch_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running',
              source_revision INTEGER NOT NULL, head INTEGER NOT NULL, memory_id TEXT NOT NULL,
              config_id TEXT NOT NULL, context_json TEXT NOT NULL, config_json TEXT NOT NULL,
              response TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
              output_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE UNIQUE INDEX IF NOT EXISTS chat_active_job ON chat_jobs(campaign_id) WHERE status='running';
            CREATE TABLE IF NOT EXISTS chat_drafts (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id),
              branch_id TEXT NOT NULL, source_revision INTEGER NOT NULL, head INTEGER NOT NULL,
              parent_id TEXT NOT NULL, config_id TEXT NOT NULL, cutoff INTEGER NOT NULL,
              text TEXT NOT NULL, original TEXT NOT NULL, status TEXT NOT NULL,
              job_id TEXT, applied_memory TEXT, edit_revision INTEGER NOT NULL DEFAULT 0, next_chapter INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chat_operations (
              campaign_id TEXT NOT NULL REFERENCES chat_campaigns(id), token TEXT NOT NULL,
              fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(campaign_id,token));
            CREATE INDEX IF NOT EXISTS chat_jobs_campaign ON chat_jobs(campaign_id);
            CREATE INDEX IF NOT EXISTS chat_drafts_campaign ON chat_drafts(campaign_id);
            CREATE INDEX IF NOT EXISTS chat_memories_campaign ON chat_memories(campaign_id);
            INSERT OR IGNORE INTO schema_migrations(name) VALUES('chat_mode_v1');
            COMMIT;
            ''')

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            yield db

    def campaign(self, db, cid):
        return row(db, 'chat_campaigns', cid)

    def branch(self, db, cid, bid=None):
        return row(db, 'chat_branches', bid or self.campaign(db, cid)['active_branch'], cid)

    def guard(self, db, cid, revision):
        c = self.campaign(db, cid)
        if c['revision'] != revision:
            raise ValueError('Состояние изменилось. Обновите страницу; черновик не потерян.')
        if db.execute("SELECT 1 FROM chat_jobs WHERE campaign_id=? AND status='running'", (cid,)).fetchone():
            raise ValueError('Сначала остановите или дождитесь текущего запроса.')
        return c

    def operation(self, db, cid, token, payload):
        fingerprint = hashlib.sha256(dump(payload).encode()).hexdigest()
        previous = db.execute('SELECT * FROM chat_operations WHERE campaign_id=? AND token=?', (cid, token)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ValueError('Ключ повтора уже использован для другого действия.')
            return fingerprint, json.loads(previous['result'])
        return fingerprint, None

    def record(self, db, cid, token, fingerprint, result):
        db.execute('INSERT INTO chat_operations VALUES(?,?,?,?)', (cid, token, fingerprint, dump(result)))
        db.execute('UPDATE chat_campaigns SET revision=revision+1 WHERE id=?', (cid,))
        return result

    def create(self, body):
        fingerprint = hashlib.sha256(dump(body).encode()).hexdigest()
        with self.transaction() as db:
            previous = db.execute('SELECT * FROM chat_campaigns WHERE creation_token=?', (body['token'],)).fetchone()
            if previous:
                if previous['creation_hash'] != fingerprint:
                    raise ValueError('Ключ создания уже использован.')
                return previous['id']
            cid, bid, mid, cfg, chapter = [uid() for _ in range(5)]
            settings = body['settings']
            require_fit(assemble(settings, body['memory'], [], []), settings['reply'], reserve=512)
            db.execute('INSERT INTO chat_campaigns(id,creation_token,creation_hash,name,active_branch,source_json) VALUES(?,?,?,?,?,?)',
                       (cid, body['token'], fingerprint, body['name'].strip(), bid, dump(body.get('source'))))
            db.execute('INSERT INTO chat_branches(id,campaign_id,name,memory_id,config_id,chapter_id) VALUES(?,?,?,?,?,?)',
                       (bid, cid, 'Основная ветка', mid, cfg, chapter))
            db.execute('INSERT INTO chat_configs VALUES(?,?,?,?,?,?)', (cfg, cid, bid, None, 0, dump(settings)))
            db.execute('INSERT INTO chat_memories(id,campaign_id,branch_id,config_id,cutoff,text,source) VALUES(?,?,?,?,?,?,?)',
                       (mid, cid, bid, cfg, 0, body['memory'], 'initial'))
            db.execute('INSERT INTO chat_chapters VALUES(?,?,?,?,?,?,?,?)', (chapter, cid, bid, 1, 'Глава 1', 1, mid, cfg))
            return cid

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,mode,revision,created_at FROM chat_campaigns ORDER BY rowid DESC')]

    def messages(self, db, bid, after=0, through=None):
        return [dict(r) for r in db.execute('''SELECT m.*,p.seq,p.chapter_id FROM chat_path p
            JOIN chat_messages m ON m.id=p.message_id WHERE p.branch_id=? AND p.seq>? AND p.seq<=? ORDER BY p.seq''',
            (bid, after, through if through is not None else 2147483647))]

    def inputs(self, db, cid, bid=None, extra=''):
        b = self.branch(db, cid, bid)
        memory = row(db, 'chat_memories', b['memory_id'], cid)
        settings = json.loads(row(db, 'chat_configs', b['config_id'], cid)['payload'])
        messages = self.messages(db, b['id'], memory['cutoff'])
        tail = []
        for ident in json.loads(memory['tail_json']):
            tail.append(row(db, 'chat_messages', ident, cid))
        if extra:
            messages.append({'role': 'user', 'content': extra, 'status': 'complete'})
        return b, memory, settings, tail, messages

    def budgets(self, db, cid, extra=''):
        b, m, s, tail, messages = self.inputs(db, cid, extra=extra)
        reply = budget(assemble(s, m['text'], tail, messages), s['reply'])
        summary = budget(assemble(s, m['text'], [], messages, summary=True), s['summary'])
        return dict(reply=reply, summary=summary,
                    warning=max(reply['ratio'], summary['ratio']) >= s['soft_threshold'],
                    unfinished=any(x['status'] != 'complete' for x in messages))

    def state(self, cid):
        with self.connect() as db:
            c = self.campaign(db, cid)
            b = self.branch(db, cid)
            c['source'] = json.loads(c.pop('source_json'))
            c.pop('creation_hash'); c.pop('creation_token')
            c.update(branch=b, memory=row(db, 'chat_memories', b['memory_id'], cid),
                     settings=json.loads(row(db, 'chat_configs', b['config_id'], cid)['payload']),
                     branches=[dict(r) for r in db.execute('SELECT id,name,head,parent_id FROM chat_branches WHERE campaign_id=? ORDER BY rowid', (cid,))],
                     chapters=[dict(r) for r in db.execute('SELECT * FROM chat_chapters WHERE branch_id=? ORDER BY ordinal', (b['id'],))],
                     budgets=self.budgets(db, cid))
            job = db.execute('SELECT id FROM chat_jobs WHERE campaign_id=? AND branch_id=? ORDER BY rowid DESC LIMIT 1', (cid, b['id'])).fetchone()
            c['job'] = self.job(cid, job['id'], db) if job else None
            c['drafts'] = [dict(r) for r in db.execute('''SELECT d.id,CASE WHEN d.status='running' AND j.status!='running' THEN j.status ELSE d.status END AS status,
                d.source_revision,d.branch_id,d.created_at FROM chat_drafts d LEFT JOIN chat_jobs j ON j.id=d.job_id
                WHERE d.campaign_id=? AND d.branch_id=? AND d.status NOT IN ('applied','cancelled') ORDER BY d.rowid DESC LIMIT 30''', (cid,b['id']))]
            return c

    def page(self, cid, bid=None, chapter=None, before=2147483647, limit=40):
        with self.connect() as db:
            b = self.branch(db, cid, bid)
            if chapter and row(db, 'chat_chapters', chapter, cid)['branch_id'] != b['id']:
                raise ValueError('Глава не принадлежит ветке.')
            rows = [dict(r) for r in db.execute('''SELECT m.*,p.seq,p.chapter_id FROM chat_path p JOIN chat_messages m ON m.id=p.message_id
                WHERE p.branch_id=? AND p.seq<? AND (? IS NULL OR p.chapter_id=?) ORDER BY p.seq DESC LIMIT ?''',
                (b['id'], before, chapter, chapter, limit+1))]
            for message in rows:
                if message['status']=='running' and message['job_id']:
                    journal=row(db,'chat_jobs',message['job_id'],cid)
                    if journal['status']!='running':
                        message.update(content=journal['response'],status=journal['status'])
            return dict(messages=list(reversed(rows[:limit])), more=len(rows)>limit)

    def job(self, cid, jid, db=None):
        if db is None:
            with self.connect() as connection:
                return self.job(cid, jid, connection)
        j = row(db, 'chat_jobs', jid, cid)
        # Request settings/contexts remain immutable in SQLite; public receipts contain no keys.
        for field in ('context_json', 'config_json'):
            j.pop(field)
        j['usage'] = [dict(r) for r in db.execute('''SELECT stage,provider,model,status,input_tokens,output_tokens,
            cached_input_tokens,cost_usd,duration,finish_reason,pricing_json FROM llm_requests WHERE job_id=?''', (jid,))]
        return j

    def add_message(self, db, cid, b, role, content, status='complete', job_id=None):
        ident = uid()
        b['head'] += 1
        db.execute('INSERT INTO chat_messages(id,campaign_id,role,content,status,job_id) VALUES(?,?,?,?,?,?)',
                   (ident, cid, role, content, status, job_id))
        db.execute('INSERT INTO chat_path VALUES(?,?,?,?)', (b['id'], b['head'], ident, b['chapter_id']))
        db.execute('UPDATE chat_branches SET head=? WHERE id=?', (b['head'], b['id']))
        return ident

    def fork(self, db, cid, source, through, *, memory=None, config=None):
        b = self.branch(db, cid, source)
        mid = memory or b['memory_id']
        while row(db, 'chat_memories', mid, cid)['applies_after'] > through:
            mid = row(db, 'chat_memories', mid, cid)['parent_id']
        cfg = config or b['config_id']
        while row(db, 'chat_configs', cfg, cid)['applies_after'] > through:
            cfg = row(db, 'chat_configs', cfg, cid)['parent_id']
        bid = uid()
        ordinal = db.execute('SELECT COUNT(*) FROM chat_branches WHERE campaign_id=?', (cid,)).fetchone()[0] + 1
        db.execute('INSERT INTO chat_branches VALUES(?,?,?,?,?,?,?,?,?)',
                   (bid, cid, source, through, f'Ветка {ordinal}', through, mid, cfg, 'pending'))
        chapters = db.execute('SELECT * FROM chat_chapters WHERE branch_id=? AND start_seq<=? ORDER BY ordinal', (source, through+1)).fetchall()
        for old in chapters:
            chapter = uid()
            db.execute('INSERT INTO chat_chapters VALUES(?,?,?,?,?,?,?,?)',
                       (chapter, cid, bid, old['ordinal'], old['name'], old['start_seq'], old['seed_memory'], old['seed_config']))
            db.execute('''INSERT INTO chat_path SELECT ?,seq,message_id,? FROM chat_path
                WHERE branch_id=? AND seq<=? AND chapter_id=?''', (bid, chapter, source, through, old['id']))
        db.execute('UPDATE chat_branches SET chapter_id=? WHERE id=?', (chapter, bid))
        db.execute('UPDATE chat_campaigns SET active_branch=? WHERE id=?', (bid, cid))
        return self.branch(db, cid, bid)

    def edit(self, cid, body):
        with self.transaction() as db:
            fp, previous = self.operation(db, cid, body['token'], body)
            if previous: return previous
            self.guard(db, cid, body['revision'])
            b = self.branch(db, cid, body['branch'])
            msg = db.execute('SELECT seq FROM chat_path WHERE branch_id=? AND message_id=?', (b['id'], body['message'])).fetchone()
            if not msg: raise ValueError('Сообщение не принадлежит ветке.')
            original = row(db, 'chat_messages', body['message'], cid)
            b = self.fork(db, cid, b['id'], msg['seq']-1)
            self.add_message(db, cid, b, original['role'], body['text'])
            return self.record(db, cid, body['token'], fp, {'branch': b['id']})

    def select(self, cid, body):
        with self.transaction() as db:
            fp, previous = self.operation(db, cid, body['token'], body)
            if previous: return previous
            self.guard(db, cid, body['revision'])
            b = self.branch(db, cid, body['branch'])
            db.execute('UPDATE chat_campaigns SET active_branch=? WHERE id=?', (b['id'], cid))
            return self.record(db, cid, body['token'], fp, {'branch': b['id']})

    def configure(self, cid, body):
        with self.transaction() as db:
            fp, previous = self.operation(db, cid, body['token'], body)
            if previous: return previous
            self.guard(db, cid, body['revision'])
            b = self.branch(db, cid)
            cfg = uid()
            # Allow a smaller model to be saved; preflight then blocks overflowing requests,
            # while memory editor and old messages stay available.
            db.execute('INSERT INTO chat_configs VALUES(?,?,?,?,?,?)', (cfg, cid, b['id'], b['config_id'], b['head'], dump(body['settings'])))
            db.execute('UPDATE chat_branches SET config_id=? WHERE id=?', (cfg, b['id']))
            return self.record(db, cid, body['token'], fp, {'config': cfg})

    def draft(self, cid, ident):
        with self.connect() as db:
            d = row(db, 'chat_drafts', ident, cid)
            c = self.campaign(db, cid)
            d['stale'] = d['source_revision'] != c['revision'] or d['branch_id'] != c['active_branch']
            if d['status']=='running' and d['job_id']:
                journal=row(db,'chat_jobs',d['job_id'],cid)
                if journal['status']!='running':
                    d.update(text=journal['response'],original=journal['response'],status=journal['status'])
            d['previous'] = row(db, 'chat_memories', d['parent_id'], cid)['text']
            return d

    def manual_memory(self, cid, body):
        with self.transaction() as db:
            fp, previous = self.operation(db, cid, body['token'], body)
            if previous: return previous
            self.guard(db, cid, body['revision'])
            b = self.branch(db, cid)
            m = row(db, 'chat_memories', b['memory_id'], cid)
            ident = uid()
            db.execute('''INSERT INTO chat_drafts(id,campaign_id,branch_id,source_revision,head,parent_id,config_id,cutoff,text,original,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (ident,cid,b['id'],body['revision']+1,b['head'],m['id'],b['config_id'],m['cutoff'],body['text'],body['text'],'complete'))
            return self.record(db, cid, body['token'], fp, {'draft': ident})

    def confirm(self, cid, did, body):
        with self.transaction() as db:
            d = row(db, 'chat_drafts', did, cid)
            if d['status'] == 'applied': return {'memory': d['applied_memory']}
            fp, previous = self.operation(db, cid, body['token'], body)
            if previous: return previous
            c = self.guard(db, cid, body['revision'])
            b = self.branch(db, cid)
            if d['status']=='running' and d['job_id']:
                journal=row(db,'chat_jobs',d['job_id'],cid)
                if journal['status']!='running': d['status']=journal['status']
            if d['status'] == 'cancelled' or d['source_revision'] != c['revision'] or d['branch_id'] != b['id']:
                raise ValueError('Черновик устарел: ветка, сообщения или настройки изменились. Создайте новый черновик.')
            if d['edit_revision'] != body.get('draft_revision',0):
                raise ValueError('Черновик отредактирован в другой вкладке. Загрузите сохранённую версию.')
            if d['status'] != 'complete' and not body['accept_partial']:
                raise ValueError('Ответ неполный. Исправьте текст и явно подтвердите принятие частичного ответа.')
            if not body['text'].strip(): raise ValueError('Выжимка пуста.')
            settings = json.loads(row(db, 'chat_configs', b['config_id'], cid)['payload'])
            tail = []
            for m in reversed(self.messages(db, b['id'], max(0,d['cutoff']-8), d['cutoff'])):
                if m['status'] != 'complete' or estimate([m['content']] + [x['content'] for x in tail]) > settings['tail_tokens']: break
                tail.insert(0,m)
            messages = self.messages(db, b['id'], d['cutoff'])
            require_fit(assemble(settings, body['text'], tail, messages), settings['reply'], reserve=512)
            mid = uid()
            db.execute('''INSERT INTO chat_memories(id,campaign_id,branch_id,parent_id,config_id,cutoff,applies_after,text,source,tail_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (mid,cid,b['id'],b['memory_id'],b['config_id'],d['cutoff'],b['head'],body['text'],'summary' if d['job_id'] else 'author',dump([m['id'] for m in tail])))
            chapter = b['chapter_id']
            if body['next_chapter']:
                chapter = uid()
                ordinal = db.execute('SELECT MAX(ordinal)+1 FROM chat_chapters WHERE branch_id=?', (b['id'],)).fetchone()[0]
                db.execute('INSERT INTO chat_chapters VALUES(?,?,?,?,?,?,?,?)',
                           (chapter,cid,b['id'],ordinal,f'Глава {ordinal}',b['head']+1,mid,b['config_id']))
            db.execute('UPDATE chat_branches SET memory_id=?,chapter_id=? WHERE id=?', (mid,chapter,b['id']))
            db.execute("UPDATE chat_drafts SET text=?,status='applied',applied_memory=? WHERE id=?", (body['text'],mid,did))
            return self.record(db, cid, body['token'], fp, {'memory':mid,'chapter':chapter})

    def save_draft(self, cid, did, body):
        with self.transaction() as db:
            fp, previous = self.operation(db,cid,body['token'],dict(body,draft=did))
            if previous: return previous
            d = row(db,'chat_drafts',did,cid)
            self.guard(db,cid,body['revision'])
            if d['status']=='running' and d['job_id']:
                d['status']=row(db,'chat_jobs',d['job_id'],cid)['status']
            if d['status'] in ('applied','cancelled','running'):
                raise ValueError('Этот черновик нельзя изменить.')
            if d['edit_revision'] != body['draft_revision']:
                raise ValueError('Черновик изменён в другой вкладке. Сначала загрузите сохранённую версию.')
            db.execute('UPDATE chat_drafts SET text=?,status=?,edit_revision=edit_revision+1 WHERE id=?',(body['text'],d['status'],did))
            # Draft edits have their own CAS, not a campaign revision: its frozen source remains valid.
            result={'draft':did,'edit_revision':d['edit_revision']+1}
            db.execute('INSERT INTO chat_operations VALUES(?,?,?,?)',(cid,body['token'],fp,dump(result)))
            return result

    def cancel_draft(self, cid, did, revision):
        with self.transaction() as db:
            d = row(db,'chat_drafts',did,cid)
            self.guard(db,cid,revision)
            if d['status']=='running' and d['job_id']:
                d['status']=row(db,'chat_jobs',d['job_id'],cid)['status']
            if d['status'] not in ('applied','running'):
                db.execute("UPDATE chat_drafts SET status='cancelled' WHERE id=?",(did,))

    def versions(self, cid, before=2147483647):
        with self.connect() as db:
            self.campaign(db, cid)
            return [dict(r) for r in db.execute('SELECT rowid AS cursor,* FROM chat_memories WHERE campaign_id=? AND rowid<? ORDER BY rowid DESC LIMIT 30', (cid,before))]
