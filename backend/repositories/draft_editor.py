"""Editorial lifecycle in existing preparation jobs and document versions."""
import json


class DraftEditorStorage:
    def _begin_world_edit(self,db,wid,config,revision):
        from backend.services.draft_initial import inspect_candidate
        from backend.repositories.drafts import candidate_hash
        head=self._draft_head(db,wid)
        if not head:raise ValueError('Сначала создайте мир.')
        base=json.loads(head['content'])
        _,report=inspect_candidate(base['state'])
        if report['errors']:raise ValueError('Сначала исправьте структурные ошибки черновика: '+'; '.join(report['errors']))
        # A reservation consumes the revision even if the provider returns fast.
        db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
        return dict(editor=dict(status='running',base=base,base_version=head['id'],base_revision=revision+1,
            before_hash=candidate_hash(base['state']),instruction=config['_draft_input'],
            request_id=config['_editor_request_id'],slot='editor_proposal'))

    def finish_world_edit(self,jid,epoch):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            journal=json.loads(job['response_journal'])
            if job['status']!='generating' or journal.get('recovery_epoch',0)!=epoch:return
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            db.execute("UPDATE preparation_jobs SET status='saved',phase='preview' WHERE id=?",(jid,))

    def world_edits(self,wid,author=False):
        with self.connect() as db:
            w=self._draft_workspace(db,wid,idle=False);head=self._draft_head(db,wid)
            started=bool(db.execute("SELECT 1 FROM document_versions WHERE kind='draft_save' AND owner LIKE ?",(wid+':%',)).fetchone())
            # Same explicit author projection as draft(); never expose even old
            # rejected instructions, reviews or reference labels to player views.
            if not author:return dict(edits=[],started=started)
            result=[]
            for row in db.execute("SELECT * FROM preparation_jobs WHERE workspace_id=? AND kind='draft_editor' ORDER BY rowid DESC",(wid,)):
                edit=json.loads(row['response_journal']).get('editor',{})
                item={key:edit.get(key) for key in ('status','instruction','base_version','base_revision','proposal','diff','review','conflicts','applied_version')}
                item.update(id=row['id'],job_status=row['status'],error=row['error'],
                    stale=not head or head['id']!=edit.get('base_version') or w['revision']!=edit.get('base_revision'))
                if item['status']=='running' and row['status'] in ('error','stopped'):item['status']=row['status']
                if edit.get('candidate'):
                    from backend.services.draft_editor import references
                    item['references']=references(edit['base']['state'],edit['candidate'])
                item['requests']=[dict(r) for r in db.execute('SELECT id,stage,status,input_tokens,output_tokens,cost_usd FROM llm_requests WHERE job_id=? ORDER BY rowid',(row['id'],))]
                result.append(item)
            return dict(edits=result,started=started)

    def decide_world_edit(self,wid,jid,revision,decision,accept_conflicts=False,accept_warnings=False):
        from backend.repositories.drafts import candidate_hash
        from backend.services.draft_editor import accepted_state,manual_conflicts,differences
        from backend.services.draft_changes import validate_candidate
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute("SELECT * FROM preparation_jobs WHERE id=? AND workspace_id=? AND kind='draft_editor'",(jid,wid)).fetchone()
            if not job:raise ValueError('Предложение не принадлежит черновику.')
            journal=json.loads(job['response_journal']);edit=journal['editor']
            if edit['status'] in ('accepted','rejected'):
                if edit['status']!=('accepted' if decision=='accept' else 'rejected'):raise ValueError('Решение уже принято.')
                return
            self._draft_workspace(db,wid,revision)
            if decision=='reject':
                edit['status']='rejected'
            else:
                head=self._draft_head(db,wid)
                if not head or head['id']!=edit['base_version'] or revision!=edit['base_revision']:
                    raise ValueError('Предпросмотр устарел: мир изменился. Создайте новое предложение.')
                if job['status']!='saved' or edit['status']!='preview':raise ValueError('Предложение ещё не проверено.')
                current=json.loads(head['content'])
                if candidate_hash(current['state'])!=edit['before_hash']:raise ValueError('Кандидат изменился.')
                trial=validate_candidate(current['state'],edit['candidate'],editing=True)
                if differences(current['state'],trial)!=edit['diff']:raise ValueError('Предпросмотр изменился.')
                if edit.get('proposal',{}).get('conflicts'):raise ValueError('Уточните инструкцию: в предложении есть нерешённые авторские конфликты.')
                review=edit.get('review',{})
                if review.get('status')!='completed' or review.get('candidate_hash')!=candidate_hash(trial):raise ValueError('Проверка предложения не завершена.')
                if any(i.get('severity','blocker')=='blocker' for i in review.get('issues',[])):
                    raise ValueError('Сначала разрешите противоречия: уточните инструкцию.')
                if review.get('issues') and not accept_warnings:raise ValueError('Подтвердите предупреждения проверки.')
                conflicts=manual_conflicts(current['state'],trial)
                if (conflicts or any(d['operation']=='remove' for d in edit['diff'])) and not accept_conflicts:
                    raise ValueError('Подтвердите удаления и замену ручных авторских решений.')
                current['state']=accepted_state(current['state'],trial,edit['instruction'],jid)
                current.update(candidate=True,diagnostics=[],review=dict(review,candidate_hash=candidate_hash(current['state'])))
                self._record_document(db,'world_draft',wid,json.dumps(current,ensure_ascii=False),True,'ai_edit',head['id'])
                edit.update(status='accepted',applied_version=self._draft_head(db,wid)['id'])
                db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
            db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(json.dumps(journal,ensure_ascii=False),jid))
