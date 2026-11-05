"""Draft lifecycle reuses preparation workspaces and append-only document versions."""
import hashlib
import json
from backend.services import draft_world as domain
from backend.services.draft_presentation import clock_view,editor_contract,calendar_notices,event_times,event_periods
from backend.services.draft_relations import plans as relation_plans


def dump(value):return json.dumps(value,ensure_ascii=False)

def candidate_hash(state):
    return hashlib.sha256(json.dumps(state,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def review_metadata(record):
    review=record.get('review')
    if review is not None:return review
    if any(e.get('category')=='review_incomplete' for e in record.get('diagnostics',[])):
        return {'status':'failed','reason':'Смысловая проверка не завершена. Повторите проверку.','issues':[]}
    return None

def review_block(record):
    review=review_metadata(record)
    if not review:return 'Смысловая проверка не выполнена.' if record.get('origin_job') or record.get('generated') else None  # Manual imports retain their technical contract.
    if review.get('status')!='completed':return 'Смысловая проверка не завершена: '+review.get('reason','повторите проверку.')
    if review.get('candidate_hash')!=candidate_hash(record['state']):return 'Смысловая проверка устарела. Повторите проверку.'
    if review.get('issues'):return 'Смысловая проверка обнаружила противоречия. Исправьте их и повторите проверку.'
    return None



def _invalid_json_constant(value):
    raise ValueError(f'Некорректное JSON-значение: {value}.')


from backend.repositories.draft_editor import DraftEditorStorage


class DraftStorage(DraftEditorStorage):
    def draft_phase(self,jid,phase,reset_progress=False):
        with self.connect() as db:
            db.execute("UPDATE preparation_jobs SET phase=?,narrative=CASE WHEN ? THEN '' ELSE narrative END WHERE id=? AND status='generating'",(phase,int(reset_progress),jid))

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
            latest=db.execute('SELECT * FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1',(wid,)).fetchone()
            if record and latest and latest['status']!='generating' and (record.get('review') or {}).get('status')=='running':
                record['review']=dict(record['review'],status='failed',reason='Проверка прервана; сохранённый результат доступен.')
            candidate=record.get('candidate',False) if record else False
            raw=record['state'] if record else None
            if candidate:
                from backend.services.draft_initial import inspect_candidate
                checked,report=inspect_candidate(raw,for_start=True)
                try:state=domain.prepare(checked)
                except (ValueError,TypeError,KeyError,AttributeError):state=None
                saved_errors=record.get('diagnostics',[])
                semantic=[e for e in saved_errors if e.get('category') in ('semantic_completeness',)]
                report['diagnostics'].extend(semantic)
                report['warnings'].extend(e['path']+': '+e['message'] for e in semantic)
                if report['errors']:state=None  # Never expose a partial world to Player View.
            else:
                state=domain.prepare(raw) if record else None
                if state and state.get('draft_contract')==4:
                    from backend.services.draft_initial import inspect_candidate
                    state,report=inspect_candidate(state,for_start=True)
                else:report=domain.validate(state) if state else {'errors':[],'warnings':[]}
            if state and record.get('generated'):report['warnings'].extend(domain.review_initial(state,record.get('source','')))
            technical_valid=not report['errors'] if not candidate else not any(e.get('category')!='semantic_completeness' for e in report.get('diagnostics',[]))
            block=(review_block(record) if record else None) or ('Возраст в карточке не совпадает с датой рождения.' if report.get('semantic_warnings') else None)
            if block and author:report['warnings'].append(block)
            history=[dict(r) for r in db.execute("SELECT id,reason,created_at FROM document_versions WHERE kind='world_draft' AND owner=? ORDER BY id DESC",(wid,))]
            latest=db.execute('SELECT * FROM preparation_jobs WHERE workspace_id=? ORDER BY rowid DESC LIMIT 1',(wid,)).fetchone()
            quality_status=json.loads(latest['response_journal'] or '{}').get('quality',{}).get('status') if latest and record and record.get('origin_job')==latest['id'] else None
            if quality_status not in ('running','accepted','partial','rejected','cancelled'):quality_status=None
            if author and quality_status in ('rejected','partial'):
                report['warnings'].append('Необязательное дополнение не принято или качество не завершено полностью. Проверенные данные сохранены; некоторые поля могут требовать содержательного дополнения.')
            creative_status=json.loads(latest['response_journal'] or '{}').get('creative',{}).get('status') if latest and record and record.get('origin_job')==latest['id'] else None
            if creative_status=='running' and latest['status']!='generating':creative_status='interrupted'
            public_job=self.public_job(dict(latest)) if latest else None
            if public_job and record and review_metadata(record) and review_metadata(record).get('status')=='stale' and latest['status'] in ('error','stopped'):
                journal=json.loads(latest['response_journal'] or '{}')
                if not journal.get('pending') and journal.get('candidate_text') and record['state']!=json.loads(journal['candidate_text']):public_job['resumable']=True
            if public_job and not author and public_job.get('error'):
                # Refresh must not replace a safe transport diagnostic from SSE
                # with a generic error. Semantic/provider prose stays private.
                diagnostic=public_job.get('response_diagnostic')
                public_job['error']=diagnostic['message'] if diagnostic else 'Проверка или генерация завершилась с замечанием. Подробности доступны автору.'
            if public_job and not author:
                # Keep progress/transport state, never the script, summary, model
                # config or authored input from a previous preparation screen.
                public_job.pop('pinned_config',None);public_job.pop('effective_config',None)
                public_job['narrative']=''
            games=[json.loads(r[0]) for r in db.execute("SELECT content FROM document_versions WHERE kind='draft_save' AND owner LIKE ? ORDER BY id DESC",(wid+':%',))]
            reader=domain.player_view(state) if state and (not author or technical_valid) else None
            visible=state if author else reader
            return {'games':[{k:g[k] for k in ('world','save','version_id')} for g in games],'id':wid,'name':w['name'],'revision':w['revision'],'version_id':head['id'] if head else None,
                # Safe lineage metadata: identifies the saved version, never its private content.
                'version_origin_job_id':record.get('origin_job') if record else None,
                'version_is_candidate':bool(candidate),
                'candidate':raw if candidate and author else None,
                'relation_merges':relation_plans(raw) if raw and author else [],
                'editor':editor_contract() if author else None,
                'presentation':{'clock':clock_view(visible['world_clock']), 'event_times':event_times(visible), 'event_periods':event_periods(visible), 'scene_times':event_times(visible,'scenes','start_minute'), 'thread_visibility':{tid:('known' if tid in reader['world']['threads'] else 'author') for tid in visible['world']['threads']} if reader else {}, 'notices':calendar_notices(state) if author else []} if visible else None,
                'creation_settings':(raw.get('creation_settings',{}) if raw else json.loads(latest['config_json']).get('_creation_settings',{}) if latest else {}) if author else {},
                'state':visible,
                'portraits':self._portrait_view(state,visible,author),
                'validation':report if author else {'errors':['Мир пока не готов к запуску. Откройте редактор автора.'] if report['errors'] else [],'warnings':['У автора есть замечания к черновику.'] if report['warnings'] and not (record and (record.get('origin_job') or review_metadata(record))) else []},
                'review':review_metadata(record) if record and author else ({'status':review_metadata(record).get('status')} if record and review_metadata(record) else None),
                'pending_editor':bool(latest and (json.loads(latest['response_journal'] or '{}').get('editor',{}).get('status')=='preview' or json.loads(latest['response_journal'] or '{}').get('field_proposal',{}).get('status')=='preview')),
                'creative_status':creative_status,
                'quality_status':quality_status,  # Safe summary; raw reasons stay author-only.
                'start_block_reason':None,
                'start_warning':('Согласованность сюжета не подтверждена.' if block else None),
                'technical_valid':technical_valid,
                'import_warnings':record.get('warnings',[]) if record and author else [],
                'source_text':record.get('source','') if record and author else '',
                'outline':record.get('outline','') if record and author else '',
                'history':history,'job':public_job,'author':author}

    def finish_field_preview(self,jid,value,warnings):
        """The existing scoped generator prepares a proposal without writing canon."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if not job or job['status']!='generating':return
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            config=json.loads(job['config_json']);head=self._draft_head(db,job['workspace_id'])
            if not config.get('_preview_only') or config['_draft_task'] not in ('field','character'):raise ValueError('Нет адресного предложения.')
            target=config['_draft_target'];state=json.loads(head['content'])['state'];item=domain.entity(state,target['kind'],target['id'])
            before={key:item.get(key,[] if key=='aliases' else '') for key in ('name','aliases','fields')} if config['_draft_task']=='character' else item.get('fields',{}).get(target['field'][7:]) if target['field'].startswith('fields.') else item.get(target['field'])
            journal=json.loads(job['response_journal'] or '{}')
            journal['field_proposal']={'status':'preview','base_version':head['id'],'target':target,'before':before,'value':value,'warnings':warnings}
            db.execute("UPDATE preparation_jobs SET response_journal=?,status='saved',phase='preview' WHERE id=?",(dump(journal),jid))

    def field_proposal(self,wid,jid,author=False):
        if not author:raise ValueError('Предложение доступно только автору.')
        with self.connect() as db:
            self._draft_workspace(db,wid,idle=False)
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=? AND workspace_id=?',(jid,wid)).fetchone()
            if not job:raise ValueError('Задание не принадлежит черновику.')
            proposal=json.loads(job['response_journal'] or '{}').get('field_proposal')
            if not proposal:raise ValueError('Предложение ещё не готово.')
            head=self._draft_head(db,wid)
            return dict(proposal,stale=not head or head['id']!=proposal['base_version'])

    def decide_field_proposal(self,wid,jid,revision,decision,accept_warnings=False):
        from backend.services.draft_generation import decode_result
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=? AND workspace_id=?',(jid,wid)).fetchone()
            if not job:raise ValueError('Задание не принадлежит черновику.')
            journal=json.loads(job['response_journal'] or '{}');proposal=journal.get('field_proposal')
            if not proposal or proposal['status']!='preview':raise ValueError('Предложение уже рассмотрено или отсутствует.')
            if decision=='accept':
                head=self._draft_head(db,wid)
                if not head or head['id']!=proposal['base_version']:raise ValueError('Предложение устарело. Мир изменился.')
                record=json.loads(head['content']);config=json.loads(job['config_json'])
                state=decode_result(dump({'value':proposal['value']}),record['state'],config)
                report=domain.validate(state)
                if report['errors']:raise ValueError('; '.join(report['errors']))
                if report['warnings'] and not accept_warnings:raise ValueError('Подтвердите предупреждения перед применением.')
                review=review_metadata(record)
                if review:review=dict(review,status='stale',reason='Поле изменено автором.')
                self._write_draft(db,wid,state,job['kind'],record.get('source',''),record.get('warnings',[]),outline=record.get('outline',''),generated=record.get('generated',False),review=review,origin_job=record.get('origin_job'))
                proposal['status']='accepted'
            elif decision=='reject':proposal['status']='rejected'
            else:raise ValueError('Неизвестное решение.')
            db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(dump(journal),jid))

    def draft_version(self,wid,version_id,author=False):
        if not author:raise ValueError('Просмотр версии доступен только в режиме автора.')
        with self.connect() as db:
            self._draft_workspace(db,wid,idle=False)
            row=db.execute("SELECT * FROM document_versions WHERE id=? AND kind='world_draft' AND owner=?",(version_id,wid)).fetchone()
            if not row:raise ValueError('Версия не принадлежит черновику.')
            record=json.loads(row['content']);state=record['state']
            return {'id':row['id'],'reason':row['reason'],'created_at':row['created_at'],
                    'state':state,'presentation':{'clock':clock_view(state.get('world_clock',{}) if isinstance(state,dict) else {})}}

    @staticmethod
    def _portrait_view(state,visible,author):
        if state is None:return {}
        from backend.services.draft_portraits import presentation_map
        return presentation_map(state,visible['characters'],author)

    def _write_draft(self,db,wid,state,reason,source='',warnings=None,source_id=None,outline='',generated=False,review=None,origin_job=None):
        state=domain.prepare(state)
        record={'state':state,'source':source,'warnings':warnings or [],'outline':outline,'generated':generated}
        if origin_job:record['origin_job']=origin_job
        if review is not None:
            record['review']=dict(review)
            if reason=='draft_world' and review.get('status')=='completed':
                record['review']['candidate_hash']=candidate_hash(state)
                record['review']['checked_revision']=self._draft_workspace(db,wid,idle=False)['revision']+1
        self._record_document(db,'world_draft',wid,dump(record),True,reason,source_id)
        db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def save_draft_candidate(self,jid,value,diagnostics,review=None,epoch=None):
        # Append author versions without replacing the previous valid version.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if job['status']!='generating':return
            if epoch is not None and json.loads(job['response_journal'] or '{}').get('recovery_epoch',0)!=epoch:raise ValueError('Устаревший результат генерации.')
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            config=json.loads(job['config_json']);head=self._draft_head(db,job['workspace_id'])
            previous=json.loads(head['content']) if head else {}
            if review is None:review=review_metadata(previous)
            if review is not None:review=dict(review,candidate_hash=candidate_hash(value))
            if review is not None and review.get('status')=='completed':
                old_review=previous.get('review') or {}
                same_review={k:v for k,v in old_review.items() if k!='checked_revision'}=={k:v for k,v in review.items() if k!='checked_revision'}
                review=dict(review,checked_revision=old_review.get('checked_revision',job['revision']+1) if same_review else job['revision']+1)
            if previous.get('origin_job')==jid and previous.get('candidate') and previous.get('state')==value and previous.get('diagnostics')==diagnostics and previous.get('review')==review:return
            record=dict(state=value,origin_job=jid,candidate=True,source=config.get('_draft_source',config.get('_draft_input','')),warnings=[],diagnostics=diagnostics,review=review)
            self._record_document(db,'world_draft',job['workspace_id'],dump(record),True,'generation_candidate',None)
            db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(job['workspace_id'],))
            db.execute('UPDATE preparation_jobs SET revision=revision+1 WHERE id=?',(jid,))

    def edit_candidate(self,wid,revision,path,value):
        from backend.services.draft_repair import apply
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Нет кандидата.')
            record=json.loads(head['content'])
            # Exact assignment retains all unknown fields and other errors.
            old_minute=record['state'].get('world_clock',{}).get('minute')
            record['state']=json.loads(apply(dump(record['state']),dump({'patches':[{'path':path,'value':value}]}),[path]))
            from backend.services.draft_calendar import manual_edit
            record['state']=manual_edit(record['state'],path,old_minute)
            record['candidate']=True
            if review_metadata(record):record['review']=dict(review_metadata(record),status='stale',reason='Кандидат изменён. Повторите проверку.')
            record['diagnostics']=[e for e in record.get('diagnostics',[]) if e.get('path')!=path and not e.get('path','').startswith(path+'/')]
            self._record_document(db,'world_draft',wid,dump(record),True,'candidate_patch',None)
            db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def merge_draft_relations(self,wid,revision,ids):
        from backend.services.draft_relations import plans,merge
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Нет кандидата.')
            record=json.loads(head['content'])
            if not any(p['safe'] and p['ids']==ids for p in plans(record['state'])):
                raise ValueError('Эти связи нельзя безопасно объединить. Повторите проверку для локального исправления.')
            record['state']=merge(record['state'],ids);record['candidate']=True
            if review_metadata(record):record['review']=dict(review_metadata(record),status='stale',reason='Связи объединены. Повторите проверку.')
            self._record_document(db,'world_draft',wid,dump(record),True,'merge_relations',None)
            db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def import_draft(self,wid,text,revision,format='text'):
        assets=None
        if format=='json':
            try:
                state=json.loads(text.lstrip('\ufeff'),parse_constant=_invalid_json_constant)
            except (ValueError,RecursionError) as exc:
                raise ValueError('Не удалось прочитать JSON: ошибка синтаксиса.') from exc
            if not isinstance(state,dict):raise ValueError('JSON не содержит корректный World State. Нужен объект.')
            assets=state.get('portrait_assets')
            if 'state' in state:state=state['state']
            # Only the existing canonical aggregate is accepted, never legacy
            # data that normalize() would migrate and seed from prose.
            if not isinstance(state,dict) or not isinstance(state.get('world'),dict) or state['world'].get('version')!=2:
                raise ValueError('JSON не содержит корректный World State.')
            report=None
            try:
                state=domain.prepare(state)
                report=domain.validate(state)
                json.dumps(state,allow_nan=False)
                # Drafts may contain validation errors for editing, but must
                # remain readable through the existing player/editor response.
                domain.player_view(state)
            except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
                details='; '.join(report['errors']) if report and report['errors'] else str(exc) if isinstance(exc,ValueError) else ''
                raise ValueError('JSON не содержит корректный World State.'+(' '+details if details else '')) from exc
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
                from backend.services.draft_portraits import import_assets
                import_assets(db,wid,state,assets)
                self._write_draft(db,wid,state,'import')
            return
        if format!='text':raise ValueError('Неизвестный формат импорта.')
        from world_parser import parse_summary
        import re
        bundle=re.search(r'<!-- AI_RPG_PORTRAITS_V1 ([A-Za-z0-9+/=]+) -->',text)
        if bundle:
            import base64
            try: assets=json.loads(base64.b64decode(bundle[1],validate=True))
            except (ValueError,UnicodeError) as exc: raise ValueError('Повреждён пакет портретов.') from exc
            text=text[:bundle.start()]+text[bundle.end():]
        state=domain.prepare(parse_summary(text.lstrip('\ufeff')))
        # Legacy unknown prose is retained; holders are never guessed.
        warnings=['Исходные разделы сохранены. Знания без явных маркеров владельцев и отношения с неразрешёнными именами требуют проверки автора.'] if 'AI_RPG_STATE_V2' not in text else []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');w=self._draft_workspace(db,wid,revision)
            if state['campaign']['title']=='Новый мир':state['campaign']['title']=w['name']
            from backend.services.draft_portraits import import_assets
            import_assets(db,wid,state,assets)
            self._write_draft(db,wid,state,'import',text,warnings)

    def edit_draft(self,wid,revision,operation,kind='',eid='',field='',value=None,source_id=None,ack=False,*,field_visibility=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Сначала создай или импортируй мир.')
            record=json.loads(head['content'])
            if field_visibility is not None and (operation!='patch' or kind!='character' or not field.startswith('fields.')):
                raise ValueError('Политика видимости задаётся только литературному полю.')
            if operation=='restore':
                old=db.execute("SELECT * FROM document_versions WHERE id=? AND kind='world_draft' AND owner=?",(source_id,wid)).fetchone()
                if not old:raise ValueError('Версия не принадлежит черновику.')
                self._record_document(db,'world_draft',wid,old['content'],True,'restore',source_id)
                db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))
                return eid
            state=domain.prepare(record['state']);before=domain.validate(state)
            if operation=='patch':
                state=domain.patch(state,kind,eid,field,value)
                if field_visibility is not None:
                    from backend.services.draft_player_view import set_binding
                    set_binding(state,eid,field[7:],field_visibility)
            elif operation=='patch_fields':
                if not isinstance(value,dict) or not value:raise ValueError('Нужны изменённые поля.')
                for key,new in value.items():state=domain.patch(state,kind,eid,key,new,synchronize=False)
            elif operation=='add':state,eid=domain.add(state,kind,value)
            elif operation=='remove':state=domain.remove(state,kind,eid)
            else:raise ValueError('Неизвестная операция.')
            state=domain.prepare(state);after=domain.validate(state)
            if operation in ('add','patch_fields'):
                new_errors=set(after['errors'])-set(before['errors'])
                if new_errors:raise ValueError('; '.join(sorted(new_errors)))
            new_warnings=set(after['warnings'])-set(before['warnings'])
            if new_warnings and not ack:raise ValueError('Возможные связанные противоречия: '+'; '.join(new_warnings)+'. Подтверди «Изменить всё равно».')
            review=review_metadata(record)
            if review:review=dict(review,status='stale',reason='Кандидат изменён. Повторите проверку.')
            self._write_draft(db,wid,state,operation,record.get('source',''),record.get('warnings',[]),source_id,record.get('outline',''),record.get('generated',False),review=review,origin_job=record.get('origin_job'))
        return eid

    def finish_draft_job(self,jid,state,outline='',epoch=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if not job or job['status']!='generating':return
            if epoch is not None and json.loads(job['response_journal'] or '{}').get('recovery_epoch',0)!=epoch:raise ValueError('Устаревший результат генерации.')
            self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
            config=json.loads(job['config_json']);old=self._draft_head(db,job['workspace_id'])
            record=json.loads(old['content']) if old else {}
            self._write_draft(db,job['workspace_id'],state,job['kind'],config.get('_draft_source',config.get('_draft_input','')) if config['_draft_task']=='world' else record.get('source',''),record.get('warnings',[]),outline=outline if config['_draft_task']=='world' else record.get('outline',''),generated=config['_draft_task']=='world' or record.get('generated',False),origin_job=jid if config['_draft_task']=='world' else record.get('origin_job'),review=review_metadata(record) if config['_draft_task']=='world' else (dict(review_metadata(record),status='stale',reason='Кандидат изменён.') if review_metadata(record) else None))
            db.execute("UPDATE preparation_jobs SET status='saved' WHERE id=?",(jid,))

    def apply_communication_profile(self,wid,revision,profile):
        from backend.services.communication_profile import edit_profile
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Сначала создайте мир.')
            record=json.loads(head['content'])
            record['state']=edit_profile(record['state'],profile)
            if review_metadata(record):record['review']=dict(review_metadata(record),status='stale',reason='Технологии связи изменены автором.')
            self._record_document(db,'world_draft',wid,dump(record),True,'communication_profile',None)
            db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def apply_calendar_presets(self,wid,revision,choice):
        from backend.services.calendar_presets import apply
        from backend.services.draft_initial import inspect_candidate
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._draft_workspace(db,wid,revision)
            head=self._draft_head(db,wid)
            if not head:raise ValueError('Сначала создайте мир.')
            record=json.loads(head['content'])
            changed=apply(record['state'],choice,explicit=True)
            _,report=inspect_candidate(changed,for_start=True)
            if report['errors']:raise ValueError('Набор не применён: '+'; '.join(report['errors']))
            record['state']=changed
            if review_metadata(record):record['review']=dict(review_metadata(record),status='stale',reason='Календарь изменён автором.')
            self._record_document(db,'world_draft',wid,dump(record),True,'calendar_presets',None)
            db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?',(wid,))

    def confirm_draft(self,wid,revision,version_id,accept_warnings=False,stop_review=False):
        from backend.repositories.living_world import project
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Idempotency lives in the existing immutable document journal.
            owner=f'{wid}:{version_id}'
            done=db.execute("SELECT v.content FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind='draft_save' AND h.owner=?",(owner,)).fetchone()
            if done:return json.loads(done[0])
            w=self._draft_workspace(db,wid,revision,idle=False);head=self._draft_head(db,wid)
            if not head or head['id']!=version_id:raise ValueError('Подтверждённая версия устарела.')
            record=json.loads(head['content'])
            warning=review_block(record)
            running=db.execute("SELECT * FROM preparation_jobs WHERE workspace_id=? AND status='generating'",(wid,)).fetchall()
            if running and not stop_review:raise ValueError('Остановите проверку перед запуском.')
            if record.get('candidate') or record['state'].get('draft_contract')==4:
                from backend.services.draft_initial import inspect_candidate
                state,report=inspect_candidate(record['state'],for_start=True)
            else:state=domain.prepare(record['state']);report=domain.validate(state)
            if report['errors']:raise ValueError('Нельзя начать игру: '+'; '.join(report['errors']))
            if (warning or report.get('semantic_warnings')) and not accept_warnings:raise ValueError('Выберите запуск с предупреждениями для этой версии.')
            # Cancel atomically with snapshot selection. Late workers retain accounting,
            # but status/epoch guards prohibit candidate writes and new model stages.
            stopped_jobs=[]
            for job in running:
                if record.get('origin_job')!=job['id'] or job['kind']!='draft_world':
                    raise ValueError('Первичная генерация ещё не дала выбранный полный снимок.')
                journal=json.loads(job['response_journal'] or '{}')
                stopped_jobs.append({'id':job['id'],'epoch':journal.get('recovery_epoch',0)})
                journal['recovery_epoch']=journal.get('recovery_epoch',0)+1
                self.terminal_quality(journal,'stopped')
                db.execute("UPDATE preparation_jobs SET status='stopped',response_journal=? WHERE id=?",(dump(journal),job['id']))
            from backend.services.draft_portraits import initialize, handoff_assets
            initialize(state)
            name=state['campaign']['title'].strip() or w['name'];source=domain.export_markdown(state)
            digest=hashlib.sha256(dump(state).encode()).hexdigest()
            existing=db.execute('SELECT id FROM worlds WHERE name_key=? AND digest=?',(name.casefold(),digest)).fetchone()
            if existing:world_id=existing[0]
            else:
                version=db.execute('SELECT COALESCE(MAX(version),0)+1 FROM worlds WHERE name_key=?',(name.casefold(),)).fetchone()[0]
                world_id=db.execute('INSERT INTO worlds(name,name_key,version,source_md,digest) VALUES(?,?,?,?,?)',(name,name.casefold(),version,source,digest)).lastrowid
                db.executemany('INSERT INTO world_parts VALUES(?,?,?)',[(world_id,k,dump(v)) for k,v in state.items()])
            handoff_assets(db,wid,world_id,state)
            from backend.runtime_v3.repository import migrate_snapshot
            authoring=state.get('authoring')
            state,_=migrate_snapshot(db,state)
            if authoring is not None:state['authoring']=json.loads(dump(authoring))
            # Validate the actual disposable game projection before committing any save.
            from backend.runtime_v3.selectors import ui_view
            from backend.runtime_v3.reproduction import known_birth
            from backend.runtime_v3.kinship import visible_name
            view=ui_view(state)
            runtime=state['world_state'];observer=runtime['camera']['controlled_actor_id']
            expected={c['id']:visible_name(runtime,c['id'],observer,c['name']) for c in state['character_cards'] if known_birth(runtime,c['id'],observer)}
            if {c['id']:c['name'] for c in view['characters']}!=expected or set(expected)!=set(view['world']['characters']):
                raise ValueError('Runtime handoff: карточки и игровые идентичности расходятся.')
            sid=db.execute('INSERT INTO saves(world_id,name,state_json) VALUES(?,?,?)',(world_id,'Новое прохождение',dump(state))).lastrowid
            project(db,sid,state)
            result={'world':world_id,'save':sid,'version_id':version_id,'start_decision':{'candidate_hash':candidate_hash(record['state']),'revision':revision,'accepted_warnings':accept_warnings,'stopped_review':bool(running),'review_status':(review_metadata(record) or {}).get('status','unreviewed')}}
            result['start_decision']['stopped_jobs']=stopped_jobs
            self._record_document(db,'draft_save',owner,dump(result),True,'confirmed')
            return result
