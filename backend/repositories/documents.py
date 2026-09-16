"""Append-only documents with active heads and reversible removal."""
import json
from pathlib import Path

PROMPT_NAMES = ('game_system_prompt.md','state_update_prompt.md','idea_prompt.md','summary_prompt.md',
                'summary_template.md','background_prompt.md','memory_prompt.md','world_state_prompt.md')
ROOT = Path(__file__).resolve().parents[2] / 'prompts'


class DocumentStorage:
    def init_documents(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS document_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, owner TEXT NOT NULL,
              content TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 1,
              reason TEXT NOT NULL, source_version_id INTEGER,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS document_heads (
              kind TEXT NOT NULL, owner TEXT NOT NULL, version_id INTEGER NOT NULL,
              PRIMARY KEY(kind,owner));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns={r['name'] for r in db.execute('PRAGMA table_info(worlds)')}
            if 'deleted' not in columns:
                db.execute('ALTER TABLE worlds ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
            for name in PROMPT_NAMES:
                if not db.execute("SELECT 1 FROM document_heads WHERE kind='prompt' AND owner=?",(name,)).fetchone():
                    self._record_document(db,'prompt',name,(ROOT/name).read_text(encoding='utf-8'),True,'initial')

    def _record_document(self,db,kind,owner,content,complete=True,reason='edit',source=None):
        row=db.execute('SELECT v.* FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind=? AND h.owner=?',(kind,str(owner))).fetchone()
        if row and row['content']==content and bool(row['complete'])==bool(complete) and source is None:
            return row['id']
        vid=db.execute('INSERT INTO document_versions(kind,owner,content,complete,reason,source_version_id) VALUES(?,?,?,?,?,?)',
                       (kind,str(owner),content,int(complete),reason,source)).lastrowid
        db.execute('INSERT INTO document_heads VALUES(?,?,?) ON CONFLICT(kind,owner) DO UPDATE SET version_id=excluded.version_id',(kind,str(owner),vid))
        return vid

    def prompt_snapshot(self,db=None):
        if db is None:
            with self.connect() as conn:
                return self.prompt_snapshot(conn)
        return {r['owner']:{'id':r['id'],'content':r['content']} for r in db.execute("SELECT v.* FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind='prompt'")}

    def document_history(self,kind,owner):
        if kind not in ('idea','summary','prompt'):
            raise ValueError('Неизвестный документ.')
        with self.connect() as db:
            head=db.execute('SELECT version_id FROM document_heads WHERE kind=? AND owner=?',(kind,owner)).fetchone()
            return {'active_id':head[0] if head else None,'versions':[dict(r) for r in db.execute('SELECT * FROM document_versions WHERE kind=? AND owner=? ORDER BY id DESC',(kind,owner))]}

    def change_document(self,kind,owner,content,expected_head,source_id=None):
        if kind not in ('idea','summary','prompt') or (kind=='prompt' and owner not in PROMPT_NAMES):
            raise ValueError('Неизвестный документ.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            head=db.execute('SELECT version_id FROM document_heads WHERE kind=? AND owner=?',(kind,owner)).fetchone()
            if (head[0] if head else None)!=expected_head:
                raise ValueError('Версия уже изменилась. Обнови историю.')
            complete=True
            if source_id is not None:
                row=db.execute('SELECT * FROM document_versions WHERE id=? AND kind=? AND owner=?',(source_id,kind,owner)).fetchone()
                if not row:
                    raise ValueError('Версия не принадлежит документу.')
                content,complete=row['content'],bool(row['complete'])
            if kind=='prompt' and not content.strip():
                raise ValueError('Промпт не может быть пустым.')
            if kind in ('idea','summary'):
                w=db.execute('SELECT * FROM preparation_workspaces WHERE id=? AND deleted=0',(owner,)).fetchone()
                if not w:
                    raise ValueError('Сценарий удалён или не найден.')
                if db.execute("SELECT 1 FROM preparation_jobs WHERE workspace_id=? AND status='generating'",(owner,)).fetchone():
                    raise ValueError('Сначала останови генерацию.')
                if kind=='summary' and content.strip() and complete:
                    from world_parser import parse_summary
                    parse_summary(content)
                if kind=='idea':
                    self._record_document(db,'summary',owner,'',False,'idea_changed')
                    db.execute("UPDATE preparation_workspaces SET idea=?,summary='',summary_complete=0,messages_json='[]',revision=revision+1 WHERE id=?",(content,owner))
                else:
                    db.execute('UPDATE preparation_workspaces SET summary=?,summary_complete=?,revision=revision+1 WHERE id=?',(content,int(bool(content.strip()) and complete),owner))
            self._record_document(db,kind,owner,content,complete and bool(content.strip()),'restore' if source_id else 'edit',source_id)
        return self.document_history(kind,owner)

    def remove_workspace(self,wid,revision,deleted=True):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM preparation_jobs WHERE workspace_id=? AND status='generating'",(wid,)).fetchone():
                raise ValueError('Сначала останови генерацию.')
            cursor=db.execute('UPDATE preparation_workspaces SET deleted=?,revision=revision+1 WHERE id=? AND revision=?',(int(deleted),wid,revision))
            if not cursor.rowcount:
                raise ValueError('Сценарий изменился или не найден.')

    def remove_world(self,wid,deleted=True):
        with self.connect() as db:
            cursor=db.execute('UPDATE worlds SET deleted=? WHERE id=?',(int(deleted),wid))
            if not cursor.rowcount:
                raise ValueError('Мир не найден.')
