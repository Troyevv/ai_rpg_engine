"""Editorial lifecycle in existing preparation jobs and document versions."""
import json


class DraftEditorStorage:
    def _begin_world_edit(self,db,wid,config,revision):
        from backend.services.draft_initial import inspect_candidate
        from backend.repositories.drafts import candidate_hash
        head=self._draft_head(db,wid)
        if not head:raise ValueError('Сначала создайте мир.')
        base=json.loads(head['content'])
        action=config.get('_review_action')
        _,report=inspect_candidate(base['state'],for_start=True)
        if report['errors']:raise ValueError('Сначала исправьте структурные ошибки черновика: '+'; '.join(report['errors']))
        extra={}
        if action:
            from backend.services.draft_review_actions import findings, saved_reply
            from backend.services.draft_world import review_initial
            if base.get('generated'):
                report['warnings'].extend(review_initial(base['state'],base.get('source','')))
            notes=findings(base,report)
            if action=='fix' and not notes:raise ValueError('В текущем мире нет замечаний для исправления.')
            previous=db.execute("SELECT response_journal,status FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1",(wid,)).fetchone()
            if previous:
                pending=json.loads(previous[0] or '{}')
                old=pending.get('editor',{})
                if (previous['status'] in ('error','stopped') and old.get('action')==action
                        and old.get('base_revision')==revision and (pending.get('pending') or saved_reply(pending))):
                    raise ValueError('Продолжите сохранённое задание. Полученный ответ и расходы уже записаны.')
                if any(pending.get(key,{}).get('status')=='preview' for key in ('editor','field_proposal')):
                    raise ValueError('Сначала примите или отклоните открытое предложение.')
            extra=dict(action=action,findings=notes)
            if action=='recheck':
                extra['calendar_conflicts']=[i['path']+': '+i['message'] for i in report.get('semantic_warnings',[])]
        # A reservation consumes the revision even if the provider returns fast.
        db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
        return dict(editor=dict(status='running',base=base,base_version=head['id'],base_revision=revision+1,
            before_hash=candidate_hash(base['state']),instruction=config['_draft_input'],
            request_id=config['_editor_request_id'],slot='editor_proposal',**extra))

    def finish_world_edit(self,jid,epoch):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            journal=json.loads(job['response_journal'])
            if job['status']!='generating' or journal.get('recovery_epoch',0)!=epoch:return
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            phase='preview' if journal['editor']['status']=='preview' else 'saved'
            db.execute("UPDATE preparation_jobs SET status='saved',phase=? WHERE id=?",(phase,jid))

    def finish_review_action(self,jid,epoch,result):
        from backend.services.draft_review_tracking import observe
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            journal=json.loads(job['response_journal'])
            if job['status']!='generating' or journal.get('recovery_epoch',0)!=epoch:return
            wid=job['workspace_id']
            self._draft_workspace(db,wid,job['revision'],idle=False)
            edit=journal['editor']
            head=self._draft_head(db,wid)
            if not head or head['id']!=edit['base_version']:raise ValueError('Мир изменился после отправки запроса.')
            edit.update(result)
            if result['status']=='reviewed':
                record=json.loads(head['content'])
                review=dict(result['review'], checked_revision=job['revision']+1, outcomes=list(result['outcomes']))
                prior=record.get('review') or {}
                if prior.get('candidate_hash')==edit['before_hash']:
                    reassessed={row['message'] for row in [*review['outcomes'], *review['issues']]}
                    review['outcomes'] += [row for row in prior.get('outcomes',[]) if
                        row['outcome'] in ('fixed','disproved') and row['message'] not in reassessed]
                record['review']=review
                record['review_tracking']=observe(record.get('review_tracking'),record['state'],review)
                self._record_document(db,'world_draft',wid,json.dumps(record,ensure_ascii=False),True,'advisory_review',head['id'])
                edit['applied_version']=self._draft_head(db,wid)['id']
                db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
            db.execute("UPDATE preparation_jobs SET response_journal=?,status='saved',phase=? WHERE id=?",
                (json.dumps(journal,ensure_ascii=False),'preview' if result['status']=='preview' else 'saved',jid))

    def world_edits(self,wid,author=False):
        from backend.services.draft_review_actions import historical_assessment, superseded_year_preview
        with self.connect() as db:
            db.execute('BEGIN')
            w=self._draft_workspace(db,wid,idle=False);head=self._draft_head(db,wid)
            started=bool(db.execute("SELECT 1 FROM document_versions WHERE kind='draft_save' AND owner LIKE ?",(wid+':%',)).fetchone())
            # Same explicit author projection as draft(); never expose even old
            # rejected instructions, reviews or reference labels to player views.
            if not author:return dict(edits=[],started=started)
            result=[]
            for row in db.execute("SELECT * FROM preparation_jobs WHERE workspace_id=? AND kind='draft_editor' ORDER BY rowid DESC",(wid,)):
                edit=json.loads(row['response_journal']).get('editor',{})
                item={key:edit.get(key) for key in ('status','instruction','base_version','base_revision','proposal','diff','review','conflicts','applied_version','action','outcomes','failure','chronologies','warnings','diagnostics','removable','omitted','original_indices','family_impacts','related_records','amended_indices','original_proposal')}
                if edit.get('proposal'):
                    item['author_idea']=edit['base'].get('source','')
                if edit.get('status')=='unapplied' and edit.get('action')=='fix':
                    from backend.services.draft_review_actions import saved_reply
                    item['can_replay']=bool(saved_reply(json.loads(row['response_journal'])))
                if superseded_year_preview(edit):
                    from backend.services.draft_review_chronology import legacy_families
                    item['superseded_dates']=True
                    item['legacy_families']=legacy_families(edit)
                if historical_assessment(edit):
                    item.update(status='assessed', failure=None, diff=[])
                if edit.get('action') and not edit.get('outcomes') and row['status'] in ('error','stopped'):
                    item['outcomes']=[dict(note,outcome='unapplied',reason=row['error'] or 'Запрос остановлен.') for note in edit['findings']]
                item.update(id=row['id'],job_status=row['status'],error=row['error'],
                    stale=not head or head['id']!=edit.get('base_version') or w['revision']!=edit.get('base_revision'))
                if item['status']=='running' and row['status'] in ('error','stopped'):item['status']=row['status']
                if edit.get('candidate'):
                    from backend.services.draft_editor import references
                    item['references']=references(edit['base']['state'],edit['candidate'])
                item['requests']=[dict(r) for r in db.execute('SELECT id,stage,status,input_tokens,output_tokens,cost_usd FROM llm_requests WHERE job_id=? ORDER BY rowid',(row['id'],))]
                result.append(item)
            return dict(edits=result,started=started)

    def decide_world_edit(self,wid,jid,revision,decision,accept_conflicts=False,accept_warnings=False,family=(),values=None):
        from backend.repositories.drafts import candidate_hash
        from backend.services.draft_editor import accepted_state,manual_conflicts,differences
        from backend.services.draft_changes import validate_candidate
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute("SELECT * FROM preparation_jobs WHERE id=? AND workspace_id=? AND kind='draft_editor'",(jid,wid)).fetchone()
            if not job:raise ValueError('Предложение не принадлежит черновику.')
            journal=json.loads(job['response_journal']);edit=journal['editor']
            if decision=='recalculate_dates' and edit.get('calendar_recalculated'):
                return
            recoverable=decision=='replay' and edit.get('action')=='fix' and edit['status']=='unapplied'
            editable=decision in ('revise','omit_invalid') and bool(edit.get('proposal')) and edit['status']=='unapplied'
            if decision=='replay' and not recoverable:
                if edit.get('response_replayed'):return
                raise ValueError('Нет отклонённого ответа для повторного открытия.')
            dismiss=decision=='reject' and edit['status']=='unapplied'
            if edit.get('action') and not (recoverable or editable or dismiss) and edit['status'] not in ('preview','accepted','rejected'):
                raise ValueError('Нет пакета изменений для применения.')
            if edit['status'] in ('accepted','rejected'):
                if (edit['status'],decision) not in (('accepted','accept'),('rejected','reject')):raise ValueError('Решение уже принято.')
                return
            self._draft_workspace(db,wid,revision)
            if decision=='reject':
                edit['status']='rejected'
            else:
                head=self._draft_head(db,wid)
                if not head or head['id']!=edit['base_version'] or revision!=edit['base_revision']:
                    raise ValueError('Предпросмотр устарел: мир изменился. Создайте новое предложение.')
                if job['status']!='saved' or (edit['status']!='preview' and not (recoverable or editable)):raise ValueError('Предложение ещё не проверено.')
                current=json.loads(head['content'])
                if candidate_hash(current['state'])!=edit['before_hash']:raise ValueError('Кандидат изменился.')
                from backend.services.draft_review_actions import superseded_year_preview
                if decision in ('revise','replay','omit_invalid'):
                    from backend.services import draft_editor, draft_review_actions
                    if decision=='replay':
                        from backend.services.draft_response import join_fragments
                        saved=draft_review_actions.saved_reply(journal)
                        if not saved:raise ValueError('Сохранённый ответ отсутствует.')
                        raw=join_fragments(saved['parts'],saved.get('assembly'),terminal=True)
                        updated=draft_review_actions.proposal_result(edit,raw)
                        edit['response_replayed']=True
                    else:
                        from copy import deepcopy
                        proposal=deepcopy(edit['proposal'])
                        removed=set(edit.get('removable') or []) if decision=='omit_invalid' else set()
                        if not values and not removed:raise ValueError('Выберите значение для корректировки.')
                        original_indices=edit.get('original_indices',list(range(len(proposal['changes']))))
                        for i,value in (values or {}).items():
                            if i<0 or i>=len(proposal['changes']) or proposal['changes'][i]['op']=='remove':
                                raise ValueError('Некорректный номер операции для редактирования.')
                            proposal['changes'][i]['value']=value
                        retained=[i for i in range(len(proposal['changes'])) if i not in removed]
                        proposal['changes']=[proposal['changes'][i] for i in retained]
                        updated=draft_editor.preview(current['state'],draft_editor.EditorialProposal.model_validate(proposal))
                        if updated['status']=='unapplied':raise ValueError(updated['failure'])
                        edit.setdefault('original_proposal',edit['proposal'])
                        amended=set(edit.get('amended_indices',[]))|set(values or {})
                        edit['amended_indices']=[i for i,old in enumerate(retained) if old in amended]
                        edit['original_indices']=[original_indices[i] for i in retained]
                        edit['omitted']=sorted(set(edit.get('omitted',[]))|{original_indices[i] for i in removed})
                        if removed:
                            for finding in edit.get('outcomes',[]):
                                previous=finding.get('change_indices',[])
                                finding['change_indices']=[i for i,old in enumerate(retained) if old in previous]
                                if previous and not finding['change_indices']:
                                    finding.update(outcome='remaining',reason='Автор исключил предложенные операции.')
                        edit['chronologies']=[]
                        edit['calendar_decisions']={}
                        for finding in edit.get('outcomes',[]):
                            if finding['outcome']=='unapplied' and finding.get('change_indices'):
                                finding['outcome']='proposed'
                    for key in ('failure','candidate','diff','diagnostics','warnings','removable'):
                        edit.pop(key,None)
                    edit.update(updated,base_revision=revision+1)
                    db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
                    db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(json.dumps(journal,ensure_ascii=False),jid))
                    return
                if decision=='recalculate_dates':
                    if not superseded_year_preview(edit):
                        raise ValueError('В этом предложении нет прежнего расчёта по году рождения.')
                    from backend.services.draft_review_actions import saved_reply, proposal_result
                    from backend.services.draft_response import join_fragments
                    saved=saved_reply(journal)
                    if not saved:raise ValueError('Исходный ответ для локального пересчёта недоступен.')
                    raw=join_fragments(saved['parts'],saved.get('assembly'),terminal=True)
                    from backend.services.draft_review_chronology import confirmed_reply
                    evidence,packet=confirmed_reply(edit,raw,family)
                    updated=proposal_result(evidence,packet)
                    if updated['status']=='unapplied':
                        raise ValueError(updated['failure'])
                    edit['family_confirmation']=[row.model_dump() for row in family]
                    # The old preview on another device cannot approve the recalculated values.
                    for field in ('candidate','proposal','outcomes','diff','calendar_decisions','failure'):
                        edit.pop(field,None)
                    edit.update(updated,base_revision=revision+1,calendar_recalculated=True)
                    db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
                    db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(json.dumps(journal,ensure_ascii=False),jid))
                    return
                fix=edit.get('action')=='fix'
                trial=validate_candidate(current['state'],edit['candidate'],editing=True)
                if differences(current['state'],trial)!=edit['diff']:raise ValueError('Предпросмотр изменился.')
                review=edit.get('review') or {}
                conflicts=manual_conflicts(current['state'],trial)
                if (conflicts or any(d['operation']=='remove' for d in edit['diff'])) and not accept_conflicts:
                    raise ValueError('Подтвердите удаления и замену ручных авторских решений.')
                from backend.services.draft_review_actions import accept_calendar_updates, issue_from_finding
                before=current['state']
                trial=accepted_state(before,trial,edit['instruction'],jid)
                accept_calendar_updates(before,trial,edit.get('calendar_decisions'))
                for i in edit.get('amended_indices',[]):
                    path=edit['proposal']['changes'][i]['path']
                    from backend.services.draft_editor import rebased_path
                    path=rebased_path(before,trial,path)
                    if path and not path.endswith('/-') and path not in trial['authoring']['manual_paths']:
                        trial['authoring']['manual_paths'].append(path)
                previous=current.get('review') or {}
                issues=[issue_from_finding(n) for n in edit['findings']] if fix else previous.get('issues',[])
                issues=list(issues)
                messages={issue['message'] for issue in issues}
                advisory=[*review.get('issues',[]),*(edit.get('warnings') or [])]
                advisory.extend(dict(message=text) for text in edit['proposal'].get('conflicts',[]))
                for issue in advisory:
                    if issue['message'] not in messages:
                        issues.append(dict(issue,severity='warning'))
                        messages.add(issue['message'])
                current.update(state=trial,candidate=True,diagnostics=[],review=dict(previous,status='stale',advisory=True,
                    reason='Изменения сохранены. Можно повторно проверить эту версию.',issues=issues))
                self._record_document(db,'world_draft',wid,json.dumps(current,ensure_ascii=False),True,'ai_edit',head['id'])
                edit.update(status='accepted',applied_version=self._draft_head(db,wid)['id'])
                db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
            db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(json.dumps(journal,ensure_ascii=False),jid))
