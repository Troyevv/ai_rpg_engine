"""Manual authoring persistence in the existing workspace/version journal."""
import json
from backend.services import world_builder as builder


class BuilderStorage:
    def builder_workspaces(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT w.id,w.name,w.revision FROM preparation_workspaces w JOIN document_heads h ON h.owner=w.id AND h.kind='world_draft' JOIN document_versions v ON v.id=h.version_id WHERE w.deleted=0 AND json_extract(v.content,'$.state.schema_version')=3 ORDER BY w.rowid DESC")]

    def create_builder(self,wid,revision):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');w=self._draft_workspace(db,wid,revision)
            if self._draft_head(db,wid):raise ValueError('Этот черновик уже содержит мир.')
            self._write_draft(db,wid,builder.empty(w['name']),'manual')
        return self.builder(wid)

    def builder(self,wid):
        with self.connect() as db:
            w=self._draft_workspace(db,wid,idle=False);head=self._draft_head(db,wid)
            if not head:raise ValueError('Черновик не найден.')
            record=json.loads(head['content']);state=record['state']
            if state.get('schema_version')!=3:raise ValueError('Откройте этот мир в исходном редакторе.')
            history=[dict(r) for r in db.execute("SELECT id,reason FROM document_versions WHERE kind='world_draft' AND owner=? ORDER BY id DESC",(wid,))]
            latest=db.execute('SELECT * FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1',(wid,)).fetchone()
            proposal=None
            if latest and latest['status']=='saved' and latest['phase']!='dismissed':
                config=json.loads(latest['config_json'])
                if config.get('_builder_path') and latest['revision']==w['revision']:
                    proposal={'path':config['_builder_path'],'value':json.loads(latest['narrative'])['value']}
            return dict(id=wid,revision=w['revision'],version_id=head['id'],state=state,validation=builder.report(state),
                        calendar_label=builder.time_label(state),history=history,proposal=proposal,job=self.public_job(dict(latest)) if latest else None)

    def save_builder(self,wid,revision,world,campaign,cards,history=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Черновик не найден.')
            old=json.loads(head['content'])['state']
            if old.get('schema_version')!=3:raise ValueError('Нужен ручной черновик.')
            state=builder.update(old,world,campaign,cards,history)
            self._write_draft(db,wid,state,'manual edit')
            title=campaign.get('title','').strip()
            if title:db.execute('UPDATE preparation_workspaces SET name=? WHERE id=?',(title[:120],wid))
        return self.builder(wid)

    def restore_builder(self,wid,revision,version):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            row=db.execute("SELECT content FROM document_versions WHERE id=? AND kind='world_draft' AND owner=?",(version,wid)).fetchone()
            if not row:raise ValueError('Версия не принадлежит черновику.')
            state=json.loads(row[0])['state']
            if state.get('schema_version')!=3:raise ValueError('Нужен ручной черновик.')
            self._write_draft(db,wid,state,'manual restore')
        return self.builder(wid)

    def dismiss_builder_proposal(self,wid,revision,jid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            row=db.execute('SELECT * FROM preparation_jobs WHERE id=? AND workspace_id=?',(jid,wid)).fetchone()
            if not row or row['revision']!=revision or row['kind']!='draft_builder' or row['status']!='saved':raise ValueError('Предложение устарело.')
            db.execute("UPDATE preparation_jobs SET phase='dismissed' WHERE id=?",(jid,))
        return {'dismissed':True}
