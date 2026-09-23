"""Draft lifecycle reuses preparation workspaces and append-only document versions."""
import hashlib
import json
from backend.services import draft_world as domain


def dump(value):return json.dumps(value,ensure_ascii=False)


class DraftStorage:
    def _draft_head(self,db,wid):
        return db.execute("SELECT v.* FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind='world_draft' AND h.owner=?",(wid,)).fetchone()

    def _draft_workspace(self,db,wid,revision=None,idle=True):
        w=db.execute('SELECT * FROM preparation_workspaces WHERE id=? AND deleted=0',(wid,)).fetchone()
        if not w:raise ValueError('Черновик не найден.')
        if revision is not None and w['revision']!=revision:raise ValueError('Конфликт ревизий. Обнови черновик перед изменением.')
        if idle and db.execute("SELECT 1 FROM preparation_jobs WHERE workspace_id=? AND status='generating'",(wid,)).fetchone():raise ValueError('Сначала останови генерацию.')
        return w

    def draft(self,wid,author=False):
        with self.connect() as db:
            w=self._draft_workspace(db,wid,idle=False);head=self._draft_head(db,wid)
            record=json.loads(head['content']) if head else None
            state=record['state'] if record else None
            history=[dict(r) for r in db.execute("SELECT id,reason,created_at FROM document_versions WHERE kind='world_draft' AND owner=? ORDER BY id DESC",(wid,))]
            latest=db.execute('SELECT * FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1',(wid,)).fetchone()
            return {'id':wid,'name':w['name'],'revision':w['revision'],'version_id':head['id'] if head else None,
                'state':state if author or state is None else domain.player_view(state),
                'validation':domain.validate(state) if state else {'errors':[],'warnings':[]},
                'import_warnings':record.get('warnings',[]) if record and author else [],
                'source_text':record.get('source','') if record and author else '',
                'outline':record.get('outline','') if record and author else '',
                'history':history,'job':self.public_job(dict(latest)) if latest else None,'author':author}

    def _write_draft(self,db,wid,state,reason,source='',warnings=None,source_id=None,outline=''):
        state=domain.prepare(state)
        self._record_document(db,'world_draft',wid,dump({'state':state,'source':source,'warnings':warnings or [],'outline':outline}),True,reason,source_id)
        db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def import_draft(self,wid,text,revision):
        from world_parser import parse_summary
        state=domain.prepare(parse_summary(text.lstrip('\ufeff')))
        # Legacy unknown prose is retained; holders are never guessed.
        warnings=['Исходные разделы сохранены. Знания без явных маркеров владельцев и отношения с неразрешёнными именами требуют проверки автора.'] if 'AI_RPG_STATE_V2' not in text else []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');w=self._draft_workspace(db,wid,revision)
            if state['campaign']['title']=='Новый мир':state['campaign']['title']=w['name']
            self._write_draft(db,wid,state,'import',text,warnings)

    def edit_draft(self,wid,revision,operation,kind='',eid='',field='',value=None,source_id=None,ack=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Сначала создай или импортируй мир.')
            record=json.loads(head['content']);state=record['state'];before=domain.validate(state)
            if operation=='restore':
                old=db.execute("SELECT * FROM document_versions WHERE id=? AND kind='world_draft' AND owner=?",(source_id,wid)).fetchone()
                if not old:raise ValueError('Версия не принадлежит черновику.')
                record=json.loads(old['content']);state=record['state']
            elif operation=='patch':state=domain.patch(state,kind,eid,field,value)
            elif operation=='add':state,eid=domain.add(state,kind)
            elif operation=='remove':state=domain.remove(state,kind,eid)
            else:raise ValueError('Неизвестная операция.')
            state=domain.prepare(state);after=domain.validate(state)
            new_warnings=set(after['warnings'])-set(before['warnings'])
            if new_warnings and not ack:raise ValueError('Возможные связанные противоречия: '+'; '.join(new_warnings)+'. Подтверди «Изменить всё равно».')
            self._write_draft(db,wid,state,operation,record.get('source',''),record.get('warnings',[]),source_id,record.get('outline',''))
        return eid

    def finish_draft_job(self,jid,state,outline=''):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if not job or job['status']!='generating':return
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            config=json.loads(job['config_json']);old=self._draft_head(db,job['workspace_id'])
            record=json.loads(old['content']) if old else {}
            self._write_draft(db,job['workspace_id'],state,job['kind'],config.get('_draft_input','') if config['_draft_task']=='world' else record.get('source',''),record.get('warnings',[]),outline=outline or record.get('outline',''))
            db.execute("UPDATE preparation_jobs SET status='saved' WHERE id=?",(jid,))

    def confirm_draft(self,wid,revision,version_id):
        from backend.repositories.living_world import project
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Idempotency lives in the existing immutable document journal.
            owner=f'{wid}:{version_id}'
            done=db.execute("SELECT v.content FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind='draft_save' AND h.owner=?",(owner,)).fetchone()
            if done:return json.loads(done[0])
            w=self._draft_workspace(db,wid,revision);head=self._draft_head(db,wid)
            if not head or head['id']!=version_id:raise ValueError('Подтверждённая версия устарела.')
            state=json.loads(head['content'])['state'];report=domain.validate(state)
            if report['errors']:raise ValueError('Нельзя начать игру: '+'; '.join(report['errors']))
            name=state['campaign']['title'].strip() or w['name'];source=domain.export_markdown(state)
            digest=hashlib.sha256(dump(state).encode()).hexdigest()
            existing=db.execute('SELECT id FROM worlds WHERE name_key=? AND digest=?',(name.casefold(),digest)).fetchone()
            if existing:world_id=existing[0]
            else:
                version=db.execute('SELECT COALESCE(MAX(version),0)+1 FROM worlds WHERE name_key=?',(name.casefold(),)).fetchone()[0]
                world_id=db.execute('INSERT INTO worlds(name,name_key,version,source_md,digest) VALUES(?,?,?,?,?)',(name,name.casefold(),version,source,digest)).lastrowid
                db.executemany('INSERT INTO world_parts VALUES(?,?,?)',[(world_id,k,dump(v)) for k,v in state.items()])
            sid=db.execute('INSERT INTO saves(world_id,name,state_json) VALUES(?,?,?)',(world_id,'Новое прохождение',dump(state))).lastrowid
            project(db,sid,state)
            result={'world':world_id,'save':sid,'version_id':version_id}
            self._record_document(db,'draft_save',owner,dump(result),True,'confirmed')
            return result
