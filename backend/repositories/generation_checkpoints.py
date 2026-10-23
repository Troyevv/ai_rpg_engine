"""SQLite checkpoint/lease extension of existing Preparation jobs and journal."""
import json
import time
import uuid
from backend.services.initial_world_stages import fingerprint


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class GenerationCheckpoints:
    def init_generation_checkpoints(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS preparation_submissions (
              workspace_id TEXT NOT NULL REFERENCES preparation_workspaces(id),
              request_key TEXT NOT NULL, digest TEXT NOT NULL,
              job_id TEXT NOT NULL REFERENCES preparation_jobs(id),
              PRIMARY KEY(workspace_id,request_key));
            CREATE TABLE IF NOT EXISTS preparation_runs (
              job_id TEXT PRIMARY KEY REFERENCES preparation_jobs(id),
              revision INTEGER NOT NULL DEFAULT 0,
              lease_token TEXT, lease_until REAL NOT NULL DEFAULT 0,
              progress_floor REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS preparation_units (
              job_id TEXT NOT NULL REFERENCES preparation_runs(job_id),
              unit_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              weight REAL NOT NULL CHECK(weight>0), required_inputs TEXT NOT NULL,
              output_paths TEXT NOT NULL, input_manifest TEXT NOT NULL DEFAULT '{}',
              artifact_id INTEGER REFERENCES document_versions(id), attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '', PRIMARY KEY(job_id,unit_id));
            CREATE TABLE IF NOT EXISTS preparation_resources (
              job_id TEXT NOT NULL REFERENCES preparation_runs(job_id), resource_key TEXT NOT NULL,
              digest TEXT NOT NULL, artifact_id INTEGER NOT NULL REFERENCES document_versions(id),
              pointer TEXT NOT NULL, unit_id TEXT,
              PRIMARY KEY(job_id,resource_key));
            CREATE TABLE IF NOT EXISTS preparation_field_locks (
              job_id TEXT NOT NULL, unit_id TEXT NOT NULL, pointer TEXT NOT NULL,
              value_json TEXT NOT NULL, revision INTEGER NOT NULL,
              PRIMARY KEY(job_id,unit_id,pointer),
              FOREIGN KEY(job_id,unit_id) REFERENCES preparation_units(job_id,unit_id));
            CREATE TABLE IF NOT EXISTS preparation_attempts (
              job_id TEXT NOT NULL, unit_id TEXT NOT NULL, attempt INTEGER NOT NULL,
              lease_token TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL, finished REAL,
              PRIMARY KEY(job_id,unit_id,attempt),
              FOREIGN KEY(job_id,unit_id) REFERENCES preparation_units(job_id,unit_id));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns={row['name'] for row in db.execute('PRAGMA table_info(preparation_units)')}
            if 'retry_attempts' not in columns:
                db.execute('ALTER TABLE preparation_units ADD COLUMN retry_attempts INTEGER NOT NULL DEFAULT 0')
                db.execute('UPDATE preparation_units SET retry_attempts=attempts')

    def _pipeline_guard(self, db, jid, token=None, now=None, statuses=('generating','pause_requested'), verify_revision=True):
        row=db.execute('SELECT r.*,j.status,j.workspace_id,j.revision workspace_revision FROM preparation_runs r JOIN preparation_jobs j ON j.id=r.job_id WHERE r.job_id=?',(jid,)).fetchone()
        if not row: raise ValueError('generation/job: checkpointed job not found')
        if row['status'] not in statuses: raise ValueError('generation/job: action unavailable in current state')
        self._draft_workspace(db,row['workspace_id'],row['workspace_revision'] if verify_revision else None,idle=False)
        if token is not None and (row['lease_token']!=token or row['lease_until'] <= (time.time() if now is None else now)):
            raise ValueError('generation/lease: expired or superseded worker')
        return row

    @staticmethod
    def _pointer(value, pointer):
        for part in pointer.split('/')[1:] if pointer else []:
            key=part.replace('~1','/').replace('~0','~')
            value=value[int(key)] if isinstance(value,list) else value[key]
        return value

    def _publish_resources(self,db,jid,vid,payload,outputs,unit=None):
        for key,pointer in outputs.items():
            old=db.execute('SELECT unit_id FROM preparation_resources WHERE job_id=? AND resource_key=?',(jid,key)).fetchone()
            if old and old['unit_id']!=unit:
                raise ValueError(f'generation/outputs/{key}: another unit owns this resource')
            digest=fingerprint(self._pointer(payload,pointer))
            db.execute('INSERT INTO preparation_resources VALUES(?,?,?,?,?,?) ON CONFLICT(job_id,resource_key) DO UPDATE SET digest=excluded.digest,artifact_id=excluded.artifact_id,pointer=excluded.pointer,unit_id=excluded.unit_id',
                       (jid,key,digest,vid,pointer,unit))

    def create_generation_run(self,jid,inputs):
        """Inputs contain no credentials; provider credentials stay process-local."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._create_generation_run(db,jid,inputs)

    def _create_generation_run(self,db,jid,inputs):
        job=db.execute('SELECT * FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
        if not job or job['status']!='generating': raise ValueError('generation/job: not active')
        self._draft_workspace(db,job['workspace_id'],job['revision'],idle=False)
        if db.execute('SELECT 1 FROM preparation_runs WHERE job_id=?',(jid,)).fetchone():
            prior=db.execute("SELECT v.content FROM document_heads h JOIN document_versions v ON v.id=h.version_id WHERE h.kind='generation_input' AND h.owner=?",(jid,)).fetchone()
            if not prior or fingerprint(json.loads(prior['content']))!=fingerprint(inputs):
                raise ValueError('generation/input: existing immutable input differs')
            return
        db.execute('INSERT INTO preparation_runs(job_id) VALUES(?)',(jid,))
        vid=self._record_document(db,'generation_input',jid,dump(inputs),True,'input')
        self._publish_resources(db,jid,vid,inputs,{key:'/'+key.replace('~','~0').replace('/','~1') for key in inputs})

    def _create_generation_review(self,db,jid,wid):
        """Fork the validated journal for review of an explicitly edited draft.

        No creative stages are rerun and no historical checkpoint is rewritten.
        The immutable author snapshot is the sole assembly input for this job.
        """
        from backend.services import generation_semantics as semantics
        from backend.services.initial_world_v2 import normalize
        from backend.services.generation_constraints import validate_snapshot_facts
        head=self._draft_head(db,wid)
        record=json.loads(head['content']) if head else {}
        origin=record.get('generation')
        if not origin:raise ValueError('generation/review: нужен мир поэтапного генератора')
        old=origin['job_id']
        self._generation_readiness(db,old,workspace_id=wid,revision=origin['revision'])
        resources=db.execute('SELECT * FROM preparation_resources WHERE job_id=?',(old,)).fetchall()
        def value(row):
            return self._pointer(json.loads(db.execute('SELECT content FROM document_versions WHERE id=?',(row['artifact_id'],)).fetchone()[0]),row['pointer'])
        values={r['resource_key']:value(r) for r in resources}
        if values['prompt']['version'] not in ('initial-world-stages-5','initial-world-stages-6'):
            raise ValueError('generation/review: этот мир использует прежний контракт генерации')
        snapshot=normalize(record['state']).snapshot
        validate_snapshot_facts(snapshot,values['interpretation'])
        self._create_generation_run(db,jid,{**{r['resource_key']:values[r['resource_key']] for r in resources if r['unit_id'] is None},
            'author_draft':snapshot,'review_origin':{'job_id':old,'version_id':head['id']}})
        groups={g['id']:g for g in semantics.groups(values['interpretation'])}
        digest=fingerprint(snapshot)
        for unit in db.execute("SELECT * FROM preparation_units WHERE job_id=? AND status!='retired' ORDER BY rowid",(old,)).fetchall():
            payload=json.loads(db.execute('SELECT content FROM document_versions WHERE id=?',(unit['artifact_id'],)).fetchone()[0])
            vid=self._record_document(db,'generation_checkpoint',jid+':'+unit['unit_id'],dump(payload),True,'review_reuse',unit['artifact_id'])
            inputs=json.loads(unit['required_inputs']);manifest=json.loads(unit['input_manifest'])
            status='completed'
            if unit['unit_id'] in groups or unit['unit_id']=='assembly':
                if 'author_draft' not in inputs:inputs.append('author_draft')
                manifest['author_draft']=digest
                if unit['unit_id']=='assembly' or payload.get('basis_hash')!=fingerprint(semantics.context(snapshot,groups[unit['unit_id']])):
                    status='stale'
            db.execute('INSERT INTO preparation_units(job_id,unit_id,stage,status,weight,required_inputs,output_paths,input_manifest,artifact_id) VALUES(?,?,?,?,?,?,?,?,?)',
                (jid,unit['unit_id'],unit['stage'],status,unit['weight'],dump(inputs),unit['output_paths'],dump(manifest),vid))
            self._publish_resources(db,jid,vid,payload,json.loads(unit['output_paths']),unit['unit_id'])

    def claim_generation(self,jid,seconds=90,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,statuses=('generating',))
            if run['lease_token'] and run['lease_until']>now: return None
            if db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='running'",(jid,)).fetchone():
                self._interrupt_units(db,jid,now)
                return None
            token=uuid.uuid4().hex
            db.execute('UPDATE preparation_runs SET lease_token=?,lease_until=? WHERE job_id=?',(token,now+seconds,jid))
            return token

    def renew_generation(self,jid,token,seconds=90,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token,now)
            db.execute('UPDATE preparation_runs SET lease_until=? WHERE job_id=?',(now+seconds,jid))

    def plan_generation_units(self,jid,token,units):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            for unit in units:
                if unit['stage'] not in ('interpret','setting','places','characters','life','lore','opening','assembly'):
                    raise ValueError('generation/stage: unknown stage')
                old=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit['id'])).fetchone()
                definition=(unit['stage'],float(unit.get('weight',1)),dump(sorted(unit['inputs'])),dump(unit['outputs']))
                if old:
                    comparable=dict(old)
                    if unit['stage']=='interpret':
                        comparable['output_paths']=dump({k:v for k,v in json.loads(old['output_paths']).items() if not k.startswith('scope:')})
                    if tuple(comparable[key] for key in ('stage','weight','required_inputs','output_paths')) != definition:
                        raise ValueError('generation/plan: existing unit definition changed')
                    continue
                if db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND stage=? AND status!='pending'",(jid,unit['stage'])).fetchone():
                    raise ValueError('generation/plan: cannot expand an already running stage')
                for existing in db.execute('SELECT output_paths FROM preparation_units WHERE job_id=?',(jid,)):
                    if set(json.loads(existing['output_paths'])) & set(unit['outputs']):
                        raise ValueError('generation/plan: duplicate resource producer')
                db.execute('INSERT INTO preparation_units(job_id,unit_id,stage,weight,required_inputs,output_paths) VALUES(?,?,?,?,?,?)',(jid,unit['id'],*definition))

    def generation_resources(self,jid,keys):
        with self.connect() as db:
            result={}
            for key in keys:
                row=db.execute('SELECT r.pointer,v.content,u.status FROM preparation_resources r JOIN document_versions v ON v.id=r.artifact_id LEFT JOIN preparation_units u ON u.job_id=r.job_id AND u.unit_id=r.unit_id WHERE r.job_id=? AND r.resource_key=?',(jid,key)).fetchone()
                if not row or row['status'] not in (None,'completed'):
                    raise ValueError(f'generation/inputs/{key}: missing or stale')
                result[key]=self._pointer(json.loads(row['content']),row['pointer'])
            return result

    def prepare_ties_subdivision(self, jid, token):
        """Allow one failed, unpublished monolithic unit to gain dependencies.

        Called only by the leased worker after normal resume/retry authorization.
        No accepted artifact, lock, attempt counter or uncertain outcome is reset.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); self._pipeline_guard(db,jid,token)
            row=db.execute("SELECT * FROM preparation_units WHERE job_id=? AND unit_id='life_ties'",(jid,)).fetchone()
            if not row or row['artifact_id'] is not None or row['status'] != 'failed':return
            if row['retry_attempts']>=3:raise ValueError('generation/budget: explicit retry required')
            if db.execute("SELECT 1 FROM preparation_field_locks WHERE job_id=? AND unit_id='life_ties'",(jid,)).fetchone():
                raise ValueError('generation/plan: locked ties cannot be subdivided')
            db.execute("UPDATE preparation_units SET status='pending' WHERE job_id=? AND unit_id='life_ties'",(jid,))
            self._record_document(db,'generation_plan',jid,dump({'unit':'life_ties','operation':'subdivide_unpublished','attempts':row['attempts']}),True,'subdivide')

    def reconcile_generation_plan(self,jid,token,units,batches):
        """Replan invalidated batches atomically, retaining artifacts and attempts.

        Only the leased worker may replace definitions, and only after upstream
        invalidation. Locks follow canonical characters across batch boundaries.
        Retired units remain in SQLite and the document journal for audit.
        """
        assigned={cid:batch['id'] for batch in batches for cid in batch['character_ids']}
        if len(assigned)!=sum(len(batch['character_ids']) for batch in batches):
            raise ValueError('generation/plan: duplicate character assignment')
        expected={u['id']:u for u in units}
        if len(expected)!=len(units):raise ValueError('generation/plan: duplicate unit')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            old={r['unit_id']:r for r in db.execute('SELECT * FROM preparation_units WHERE job_id=?',(jid,))}
            if any(uid in old and old[uid]['stage'] not in ('characters','life','lore','opening','assembly') for uid in expected):
                raise ValueError('generation/plan: source unit ownership cannot change')
            for uid,row in old.items():
                if row['stage'] not in ('characters','life','lore','opening','assembly'):continue
                definition=expected.get(uid)
                changed=definition is None or (row['stage'],row['weight'],row['required_inputs'],row['output_paths'])!=(definition['stage'],float(definition.get('weight',1)),dump(sorted(definition['inputs'])),dump(definition['outputs']))
                if row['stage']=='characters' and row['status']=='completed':
                    artifact=db.execute('SELECT content FROM document_versions WHERE id=?',(row['artifact_id'],)).fetchone()
                    prior_ids=set(json.loads(artifact['content'])['characters']) if artifact else set()
                    changed=changed or prior_ids!={cid for cid,target in assigned.items() if target==uid}
                if changed and row['status'] not in ('pending','stale','retired'):
                    raise ValueError('generation/plan/'+uid+': invalidate upstream inputs before changing the plan')
            moved={}
            for lock in db.execute("SELECT l.* FROM preparation_field_locks l JOIN preparation_units u ON u.job_id=l.job_id AND u.unit_id=l.unit_id WHERE l.job_id=? AND u.stage='characters'",(jid,)):
                parts=lock['pointer'].split('/')[1:]
                value=json.loads(lock['value_json'])
                if not parts or parts[0] not in ('characters','cards'):
                    raise ValueError('generation/plan/locks: unsupported character lock')
                targets=[(parts[1].replace('~1','/').replace('~0','~'),lock['pointer'],value)] if len(parts)>1 else [(cid,'/'+parts[0]+'/'+cid.replace('~','~0').replace('/','~1'),item) for cid,item in value.items()]
                for cid,pointer,item in targets:
                    if cid not in assigned:raise ValueError('generation/plan/locks/'+cid+': protected character is missing from the new roster')
                    key=(assigned[cid],pointer)
                    candidate=(dump(item),lock['revision'])
                    if key in moved and moved[key][0]!=candidate[0]:raise ValueError('generation/plan/locks: conflicting accepted edits')
                    moved[key]=candidate
            producers={}
            for uid,row in old.items():
                if row['stage'] in ('characters','life','lore','opening','assembly'):continue
                producers.update({key:uid for key in json.loads(row['output_paths'])})
            for unit in units:
                if unit['stage'] not in ('characters','life','lore','opening','assembly'):
                    raise ValueError('generation/plan: cannot replan source stages')
                for key in unit['outputs']:
                    if key in producers:raise ValueError('generation/plan: duplicate resource producer')
                    producers[key]=unit['id']
            for uid,row in old.items():
                if row['stage'] in ('characters','life','lore','opening','assembly') and uid not in expected:
                    db.execute("UPDATE preparation_units SET status='retired',error='Superseded by explicit roster revision.' WHERE job_id=? AND unit_id=?",(jid,uid))
            for unit in units:
                uid=unit['id'];definition=(unit['stage'],float(unit.get('weight',1)),dump(sorted(unit['inputs'])),dump(unit['outputs']))
                if uid in old:
                    db.execute("UPDATE preparation_units SET stage=?,weight=?,required_inputs=?,output_paths=?,status=CASE WHEN status='retired' THEN 'stale' ELSE status END WHERE job_id=? AND unit_id=?",(*definition,jid,uid))
                else:
                    db.execute('INSERT INTO preparation_units(job_id,unit_id,stage,weight,required_inputs,output_paths) VALUES(?,?,?,?,?,?)',(jid,uid,*definition))
            db.execute("DELETE FROM preparation_field_locks WHERE job_id=? AND unit_id IN (SELECT unit_id FROM preparation_units WHERE job_id=? AND stage='characters')",(jid,jid))
            for (uid,pointer),(value,revision) in moved.items():
                db.execute('INSERT INTO preparation_field_locks VALUES(?,?,?,?,?)',(jid,uid,pointer,value,revision))
            self._record_document(db,'generation_plan',jid,dump({'units':units,'batches':batches}),True,'reconcile')

    def begin_generation_unit(self,jid,token,unit,attempt_limit=3):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token,statuses=('generating',))
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row: raise ValueError('generation/unit: unknown unit')
            if row['status']=='completed': return False
            if row['status'] not in ('pending','failed','stale') or (row['status']!='stale' and row['retry_attempts']>=attempt_limit):
                raise ValueError('generation/unit: retry unavailable or budget exhausted')
            manifest={}
            for key in json.loads(row['required_inputs']):
                resource=db.execute('SELECT r.digest,u.status FROM preparation_resources r LEFT JOIN preparation_units u ON u.job_id=r.job_id AND u.unit_id=r.unit_id WHERE r.job_id=? AND resource_key=?',(jid,key)).fetchone()
                if not resource or resource['status'] not in (None,'completed'):
                    raise ValueError(f'generation/inputs/{key}: missing or stale')
                manifest[key]=resource['digest']
            attempt=row['attempts']+1
            db.execute("UPDATE preparation_units SET status='running',attempts=?,retry_attempts=?,input_manifest=?,error='' WHERE job_id=? AND unit_id=?",(attempt,1 if row['status']=='stale' else row['retry_attempts']+1,dump(manifest),jid,unit))
            db.execute("INSERT INTO preparation_attempts VALUES(?,?,?,?,'running',?,NULL)",(jid,unit,attempt,token,time.time()))
            db.execute('UPDATE preparation_jobs SET phase=? WHERE id=?',(unit,jid))
            return True

    def commit_generation_unit(self,jid,token,unit,payload):
        """Payload must already pass its stage DTO and semantic checks.

        The ownership/revision/input CAS guards run again inside the publication
        transaction, after provider I/O. A late response cannot publish twice.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row or row['status']!='running': raise ValueError('generation/unit: no matching running attempt')
            attempt=db.execute('SELECT * FROM preparation_attempts WHERE job_id=? AND unit_id=? AND attempt=?',(jid,unit,row['attempts'])).fetchone()
            if attempt['lease_token']!=token or attempt['status']!='running': raise ValueError('generation/attempt: stale provider response')
            for key,digest in json.loads(row['input_manifest']).items():
                resource=db.execute('SELECT r.digest,u.status FROM preparation_resources r LEFT JOIN preparation_units u ON u.job_id=r.job_id AND u.unit_id=r.unit_id WHERE r.job_id=? AND resource_key=?',(jid,key)).fetchone()
                if not resource or resource['digest']!=digest or resource['status'] not in (None,'completed'):
                    raise ValueError(f'generation/inputs/{key}: changed during request')
            for lock in db.execute('SELECT pointer,value_json FROM preparation_field_locks WHERE job_id=? AND unit_id=?',(jid,unit)):
                try: current=self._pointer(payload,lock['pointer'])
                except (KeyError,IndexError,TypeError,ValueError):
                    raise ValueError('generation/locks'+lock['pointer']+': accepted edit is missing') from None
                if dump(current)!=lock['value_json']:
                    raise ValueError('generation/locks'+lock['pointer']+': conflicts with accepted edit')
            vid=self._record_document(db,'generation_checkpoint',jid+':'+unit,dump(payload),True,'checkpoint',row['artifact_id'])
            outputs=json.loads(row['output_paths'])
            if row['stage']=='interpret' and 'scopes' in payload:
                outputs.update({'scope:'+key:'/scopes/'+key for key in payload['scopes']})
                db.execute('UPDATE preparation_units SET output_paths=? WHERE job_id=? AND unit_id=?',(dump(outputs),jid,unit))
            self._publish_resources(db,jid,vid,payload,outputs,unit)
            db.execute("UPDATE preparation_units SET status='completed',artifact_id=?,error='' WHERE job_id=? AND unit_id=?",(vid,jid,unit))
            db.execute("UPDATE preparation_attempts SET status='completed',finished=? WHERE job_id=? AND unit_id=? AND attempt=?",(time.time(),jid,unit,row['attempts']))
            self._update_generation_progress(db,jid)
            return vid

    def record_generation_diagnostic(self,jid,token,unit,payload):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            self._record_document(db,'generation_diagnostic',jid+':'+unit,dump(payload),True,'semantic_review')

    def fail_generation_unit(self,jid,token,unit,error):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row or row['status']!='running': raise ValueError('generation/unit: not running')
            db.execute("UPDATE preparation_units SET status='failed',error=? WHERE job_id=? AND unit_id=?",(error,jid,unit))
            db.execute("UPDATE preparation_attempts SET status='failed',finished=? WHERE job_id=? AND unit_id=? AND attempt=?",(time.time(),jid,unit,row['attempts']))

    @staticmethod
    def _update_generation_progress(db,jid):
        rows=db.execute("SELECT stage,sum(CASE WHEN status='completed' THEN weight ELSE 0 END) done,sum(weight) total FROM preparation_units WHERE job_id=? AND status!='retired' GROUP BY stage",(jid,)).fetchall()
        # Fixed logical stages; batches split a stage's weight, not the entire
        # denominator. Planning later batches cannot announce completion early.
        progress=sum((row['done'] or 0)/(row['total'] or 1) for row in rows)/8
        # Stale work is visible separately; completed-work progress never rewinds.
        db.execute('UPDATE preparation_runs SET progress_floor=max(progress_floor,?) WHERE job_id=?',(progress,jid))

    @staticmethod
    def _interrupt_units(db,jid,now):
        db.execute("UPDATE preparation_attempts SET status='uncertain',finished=? WHERE job_id=? AND status='running'",(now,jid))
        db.execute("UPDATE preparation_units SET status='uncertain',error='Interrupted provider request; outcome and billing are uncertain. Explicit retry required.' WHERE job_id=? AND status='running'",(jid,))
        db.execute("UPDATE preparation_jobs SET status='paused',error='Interrupted request: inspect the checkpoint and explicitly authorize retry.' WHERE id=?",(jid,))
        db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))

    def generation_status(self,jid):
        with self.connect() as db:
            run=db.execute('SELECT revision,progress_floor FROM preparation_runs WHERE job_id=?',(jid,)).fetchone()
            if not run: return None
            units=[dict(row) for row in db.execute("SELECT unit_id,stage,status,weight,attempts,retry_attempts,error FROM preparation_units WHERE job_id=? AND status!='retired' ORDER BY rowid",(jid,))]
            for unit in units:
                error=unit['error'].lower()
                unit['error_kind']=('json' if 'invalid json' in error else 'provider' if 'provider' in error else 'semantic' if 'generation/semantic' in error else 'budget' if 'budget' in error else 'schema' if error else None)
            review_only=db.execute("SELECT 1 FROM preparation_resources WHERE job_id=? AND resource_key='review_origin'",(jid,)).fetchone() is not None
            exhausted=[u['unit_id'] for u in units if u['status'] in ('pending','failed','uncertain') and u['retry_attempts']>=3]
            return dict(revision=run['revision'],overall_progress=run['progress_floor'],units=units,review_only=review_only,can_resume=not exhausted,exhausted_units=exhausted)

    def generation_control(self,jid,action,revision=None,allow_uncertain_retry=False):
        """Idempotent transitions. Resume never replays an uncertain call silently."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,statuses=('generating','pause_requested','paused','waiting_for_credentials','failed','cancelled','completed'), verify_revision=action!='cancel')
            if revision is not None and run['revision']!=revision:
                raise ValueError('generation/revision: refresh before changing the job')
            status=run['status']
            if action=='pause':
                if status in ('pause_requested','paused'): return status
                if status!='generating': raise ValueError('generation/pause: unavailable')
                status='pause_requested' if run['lease_token'] else 'paused'
            elif action=='cancel':
                if status in ('cancelled','completed'): return status
                status='cancelled'
                db.execute("UPDATE preparation_units SET status='cancelled' WHERE job_id=? AND status IN ('running','pending','failed','stale','uncertain')",(jid,))
                db.execute("UPDATE preparation_attempts SET status='cancelled',finished=? WHERE job_id=? AND status='running'",(time.time(),jid))
                db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
            elif action in ('resume','retry'):
                if status=='generating': return status
                if status not in ('paused','waiting_for_credentials','failed'): raise ValueError('generation/resume: wait for a stable checkpoint')
                if run['lease_token'] and run['lease_until']>time.time():
                    raise ValueError('generation/resume: previous worker has not released its lease')
                uncertain=db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='uncertain'",(jid,)).fetchone()
                if uncertain and not allow_uncertain_retry:
                    raise ValueError('generation/resume: interrupted request may have been billed; explicit retry required')
                exhausted=db.execute("SELECT unit_id FROM preparation_units WHERE job_id=? AND status IN ('pending','failed','uncertain') AND retry_attempts>=3",(jid,)).fetchall()
                if exhausted and action!='retry':raise ValueError('generation/budget: попытки исчерпаны; разреши новый ограниченный повтор')
                if action=='retry':
                    if not exhausted:raise ValueError('generation/budget: новый бюджет не требуется')
                    self._record_document(db,'generation_retry',jid,dump({'units':[r['unit_id'] for r in exhausted],'revision':run['revision'],'attempt_limit':3}),True,'author_retry')
                    db.execute("UPDATE preparation_units SET retry_attempts=0 WHERE job_id=? AND status IN ('pending','failed','uncertain') AND retry_attempts>=3",(jid,))
                if uncertain:
                    db.execute("UPDATE preparation_units SET status='pending' WHERE job_id=? AND status='uncertain'",(jid,))
                status='generating'
            else: raise ValueError('generation/action: unknown action')
            db.execute('UPDATE preparation_jobs SET status=? WHERE id=?',(status,jid))
            db.execute('UPDATE preparation_runs SET revision=revision+1 WHERE job_id=?',(jid,))
            return status

    def generation_boundary(self,jid,token):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,token)
            if run['status']=='pause_requested':
                db.execute("UPDATE preparation_jobs SET status='paused' WHERE id=?",(jid,))
                db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
                return False
            return True

    def recover_generations(self,now=None,owned_jobs=()):
        """No speculative provider retry. Return jobs needing secure resumption."""
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT r.job_id,r.lease_token FROM preparation_runs r JOIN preparation_jobs j ON j.id=r.job_id WHERE j.status IN ('generating','pause_requested') AND r.lease_until<=?",(now,)).fetchall()
            # A local dispatcher may not have reached claim_generation yet.
            # Never suppress recovery of an expired leased worker, however.
            rows=[r for r in rows if r['lease_token'] is not None or r['job_id'] not in owned_jobs]
            for row in rows:
                jid=row['job_id']
                if db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='running'",(jid,)).fetchone():
                    self._interrupt_units(db,jid,now)
                else:
                    db.execute("UPDATE preparation_jobs SET status='waiting_for_credentials',error='Resume from the last validated checkpoint with provider access.' WHERE id=?",(jid,))
                    db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
            return [row['job_id'] for row in rows]

    def release_generation(self,jid,token,status=None,error=''):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=db.execute('SELECT lease_token FROM preparation_runs WHERE job_id=?',(jid,)).fetchone()
            if not run or run['lease_token']!=token: return
            db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
            if status:
                db.execute("UPDATE preparation_jobs SET status=?,error=? WHERE id=? AND status IN ('generating','pause_requested')",(status,error,jid))

    def _generation_readiness(self,db,jid,*,workspace_id=None,revision=None):
        """One transactional currency gate for publication and Start Game.

        Canonical validation remains owned by draft_world/Runtime. This checks
        the authoring dependency journal without modifying historical saves.
        """
        run=db.execute('SELECT r.revision,j.workspace_id,j.status FROM preparation_runs r JOIN preparation_jobs j ON j.id=r.job_id WHERE r.job_id=?',(jid,)).fetchone()
        if not run or (workspace_id is not None and run['workspace_id']!=workspace_id):
            raise ValueError('generation/readiness/job: missing or foreign generation')
        if revision is not None and (run['revision']!=revision or run['status']!='saved'):
            raise ValueError('generation/readiness/revision: generation changed; rebuild the draft')
        units=db.execute("SELECT * FROM preparation_units WHERE job_id=? AND status!='retired'",(jid,)).fetchall()
        stages={row['stage'] for row in units}
        if not {'interpret','setting','places','life','lore','opening','assembly'}<=stages:
            raise ValueError('generation/readiness: missing required stages')
        resources={r['resource_key']:r for r in db.execute('SELECT * FROM preparation_resources WHERE job_id=?',(jid,))}
        for unit in units:
            prefix=f'generation/readiness/{unit["unit_id"]}'
            artifact=db.execute("SELECT content FROM document_versions WHERE id=? AND kind='generation_checkpoint' AND owner=?",(unit['artifact_id'],jid+':'+unit['unit_id'])).fetchone()
            if unit['status']!='completed' or not artifact:
                raise ValueError(prefix+': missing or unvalidated checkpoint')
            manifest=json.loads(unit['input_manifest'])
            if set(manifest)!=set(json.loads(unit['required_inputs'])):
                raise ValueError(prefix+': incomplete input manifest')
            for key,digest in manifest.items():
                current=resources.get(key)
                if not current or current['digest']!=digest:
                    raise ValueError(prefix+': stale input '+key)
            payload=json.loads(artifact['content'])
            for key,pointer in json.loads(unit['output_paths']).items():
                current=resources.get(key)
                if not current or current['unit_id']!=unit['unit_id'] or current['artifact_id']!=unit['artifact_id'] or current['pointer']!=pointer:
                    raise ValueError(prefix+': missing or superseded output '+key)
                if current['digest']!=fingerprint(self._pointer(payload,pointer)):
                    raise ValueError(prefix+': changed output '+key)
            if unit['stage']=='interpret' and payload.get('blocking_ids'):
                raise ValueError(prefix+': unresolved blocking ambiguities')

    def validate_generation_semantics(self,db,jid,snapshot):
        from backend.services import generation_semantics as semantics
        def resource(key):
            row=db.execute('SELECT v.content,r.pointer FROM preparation_resources r JOIN document_versions v ON v.id=r.artifact_id WHERE r.job_id=? AND r.resource_key=?',(jid,key)).fetchone()
            if not row:raise ValueError('generation/semantic: missing review resource '+key)
            return self._pointer(json.loads(row['content']),row['pointer'])
        if resource('prompt')['version']!='initial-world-stages-5':return
        for group in semantics.groups(resource('interpretation')):
            report=resource(group['id']);data=semantics.context(snapshot,group)
            if report['basis_hash']!=fingerprint(data):
                raise ValueError('generation/semantic/'+group['id']+': accepted world changed after semantic review; regenerate affected checkpoints before Start Game')
            semantics.validate({'findings':report['findings']},data)

    def publish_generation_draft(self,jid,token,state):
        from backend.services import draft_world
        state=draft_world.prepare(state)
        report=draft_world.validate(state)
        if report['errors']: raise ValueError('; '.join(report['errors']))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,token,statuses=('generating',))
            self._generation_readiness(db,jid)
            from backend.services.initial_world_v2 import normalize
            self.validate_generation_semantics(db,jid,normalize(state).snapshot)
            assembled=db.execute("SELECT v.content FROM preparation_resources r JOIN document_versions v ON v.id=r.artifact_id WHERE r.job_id=? AND r.resource_key='assembled'",(jid,)).fetchone()
            if not assembled or fingerprint(draft_world.prepare(json.loads(assembled['content'])))!=fingerprint(state):
                raise ValueError('generation/readiness/assembly: draft differs from validated checkpoint')
            config=json.loads(db.execute('SELECT config_json FROM preparation_jobs WHERE id=?',(jid,)).fetchone()[0])
            previous={}
            if config.get('_review_only'):
                previous=json.loads(self._draft_head(db,run['workspace_id'])['content'])
            self._write_draft(db,run['workspace_id'],state,'staged_review' if previous else 'staged_generation',
                previous.get('source',config.get('_draft_input','')),warnings=previous.get('warnings',[]),outline=previous.get('outline',''),generated=True,
                generation={'job_id':jid,'revision':run['revision']})
            db.execute("UPDATE preparation_jobs SET status='saved',phase='completed',error='' WHERE id=?",(jid,))
            db.execute('UPDATE preparation_runs SET progress_floor=1,lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))

    def interrupt_generation(self,jid):
        """Server shutdown revokes publication, without turning it into user cancel."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT j.status FROM preparation_jobs j JOIN preparation_runs r ON r.job_id=j.id WHERE j.id=?',(jid,)).fetchone()
            if not row or row['status'] not in ('generating','pause_requested'): return
            if db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='running'",(jid,)).fetchone():
                self._interrupt_units(db,jid,time.time())
            else:
                db.execute("UPDATE preparation_jobs SET status='waiting_for_credentials' WHERE id=?",(jid,))
                db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))

    def inspect_generation_checkpoint(self,jid,unit,author=False):
        with self.connect() as db:
            job=db.execute('SELECT workspace_id FROM preparation_jobs WHERE id=?',(jid,)).fetchone()
            if not job: raise ValueError('Generation job not found.')
            self._draft_workspace(db,job['workspace_id'],idle=False)
            row=db.execute('SELECT u.stage,u.status,u.artifact_id,v.content FROM preparation_units u LEFT JOIN document_versions v ON v.id=u.artifact_id WHERE u.job_id=? AND u.unit_id=?',(jid,unit)).fetchone()
            if not row: raise ValueError('Generation unit not found.')
            result=dict(stage=row['stage'],status=row['status'],artifact_version=row['artifact_id'],author=author,read_only=True)
            if author and row['status']=='failed':
                diagnostic=db.execute("SELECT content FROM document_versions WHERE kind='generation_diagnostic' AND owner=? ORDER BY id DESC LIMIT 1",(jid+':'+unit,)).fetchone()
                if diagnostic:result['diagnostic']=json.loads(diagnostic['content'])
            if author and row['content'] is not None:
                result['artifact']=json.loads(row['content'])
                from backend.services.initial_world_stages import STAGES
                if row['stage'] in STAGES:
                    from backend.services.initial_world_stages import TiesPart, BackgroundPart
                    schema=(TiesPart if unit.startswith('life_ties_') else {'life_ties':TiesPart,'lore_background':BackgroundPart}.get(unit,STAGES[row['stage']])).model_json_schema()
                    if row['stage']=='setting':schema={**schema,'properties':{'setting':{'type':'object','properties':schema['properties']}}}
                    result['editor_schema']=schema
                if row['stage']=='interpret' and unit=='interpret':
                    from backend.services.world_interpretation import Interpretation
                    schema=Interpretation.model_json_schema()
                    fields=schema['$defs']['InterpretedClaim']['properties']
                    if result['artifact'].get('version')==2:
                        for key in ('spans','rules','blocking','value'):fields.pop(key,None)
                        schema['$defs']['InterpretedClaim']['required']=[k for k in schema['$defs']['InterpretedClaim'].get('required',[]) if k in fields]
                    for source,target in (('subject_key','subject_id'),('holder_keys','holder_ids'),('related_keys','related_ids')):
                        fields[target]=fields.pop(source)
                    for key in ('section','field'):
                        fields[key]['readOnly']=True
                    result['editor_schema']=schema
                registry=db.execute("SELECT v.content,r.pointer FROM preparation_resources r JOIN document_versions v ON v.id=r.artifact_id WHERE r.job_id=? AND r.resource_key='registry'",(jid,)).fetchone()
                result['reference_options']=[{'id':r['id'],'name':r['name']} for r in self._pointer(json.loads(registry['content']),registry['pointer'])] if registry else []
                if row['stage']=='interpret' and unit=='interpret':
                    result['reference_options']=[{'id':r['id'],'name':r['name']} for r in result['artifact']['entities']]
                lore=db.execute("SELECT v.content,r.pointer FROM preparation_resources r JOIN document_versions v ON v.id=r.artifact_id WHERE r.job_id=? AND r.resource_key='lore'",(jid,)).fetchone()
                if lore:
                    facts=self._pointer(json.loads(lore['content']),lore['pointer']).get('facts',{})
                    result['reference_options'] += [{'id':fid,'name':fact['text']} for fid,fact in facts.items()]
                result['locked_paths']=[r['pointer'] for r in db.execute('SELECT pointer FROM preparation_field_locks WHERE job_id=? AND unit_id=?',(jid,unit))]
            return result

    def revise_generation_checkpoint(self,jid,unit,payload,revision,artifact_version,locked_paths,*,preview=True,regenerate=False,unlock_paths=()):
        """Persist a service-validated author edit, or return its dependency impact.

        Callers own stage/semantic validation and constraint reconciliation. This
        persistence boundary checks the stable pause, artifact CAS and resource
        ownership again under one write transaction. It never edits Runtime saves.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,statuses=('paused',))
            if run['lease_token'] or run['revision']!=revision:
                raise ValueError('generation/revision: wait for a stable pause and refresh')
            rows={row['unit_id']:row for row in db.execute("SELECT * FROM preparation_units WHERE job_id=? AND status!='retired'",(jid,))}
            row=rows.get(unit)
            if not row or row['status']!='completed' or row['artifact_id']!=artifact_version:
                raise ValueError('generation/artifact: checkpoint changed or is not validated')
            outputs=json.loads(row['output_paths'])
            proposed={key:fingerprint(self._pointer(payload,path)) for key,path in outputs.items()}
            digests={r['resource_key']:r['digest'] for r in db.execute('SELECT resource_key,digest FROM preparation_resources WHERE job_id=?',(jid,))}
            changed={key for key,value in proposed.items() if digests.get(key)!=value}
            unavailable=set(outputs) if regenerate else set(changed);affected={unit} if regenerate else set()
            while True:
                found={uid for uid,r in rows.items() if uid!=unit and uid not in affected and
                       set(json.loads(r['required_inputs'])) & unavailable}
                if not found: break
                affected.update(found)
                for uid in found: unavailable.update(json.loads(rows[uid]['output_paths']))
            prior_locks={r['pointer']:r['value_json'] for r in db.execute('SELECT pointer,value_json FROM preparation_field_locks WHERE job_id=? AND unit_id=?',(jid,unit))}
            locks={path:dump(self._pointer(payload,path)) for path in locked_paths}
            for path in prior_locks:
                if path not in unlock_paths and any(path.startswith(p+'/') or p.startswith(path+'/') or path==p for p in locked_paths):
                    try: locks[path]=dump(self._pointer(payload,path))
                    except (KeyError,IndexError,TypeError): raise ValueError('generation/locks: unlock the removed field explicitly') from None
            impact=dict(revision=revision,artifact_version=artifact_version,
                changed_resources=sorted(changed),stale_units=sorted(affected),locked_paths=sorted((set(prior_locks)|set(locks))-set(unlock_paths)))
            lock_change=any(prior_locks.get(k)!=v for k,v in locks.items()) or bool(set(unlock_paths)&set(prior_locks))
            if preview or not (changed or regenerate or lock_change): return impact
            vid=self._record_document(db,'generation_checkpoint',jid+':'+unit,dump(payload),True,'regenerate' if regenerate else 'author_edit',artifact_version)
            self._publish_resources(db,jid,vid,payload,outputs,unit)
            db.execute('UPDATE preparation_units SET artifact_id=? WHERE job_id=? AND unit_id=?',(vid,jid,unit))
            for uid in affected:
                db.execute("UPDATE preparation_units SET status='stale',error='Upstream author edit requires revalidation.' WHERE job_id=? AND unit_id=?",(jid,uid))
            for path in unlock_paths:
                db.execute('DELETE FROM preparation_field_locks WHERE job_id=? AND unit_id=? AND pointer=?',(jid,unit,path))
            for path,value in locks.items():
                db.execute('INSERT INTO preparation_field_locks VALUES(?,?,?,?,?) ON CONFLICT(job_id,unit_id,pointer) DO UPDATE SET value_json=excluded.value_json,revision=excluded.revision',
                           (jid,unit,path,value,revision+1))
            db.execute('UPDATE preparation_runs SET revision=revision+1 WHERE job_id=?',(jid,))
            return {**impact,'revision':revision+1,'artifact_version':vid}

    def unlock_generation_fields(self,jid,unit,revision,artifact_version,paths,preview=True):
        """Release accepted locks even when a source revision made data stale.

        Unlocking cannot validate or mutate the stale artifact. Its next provider
        execution still requires current inputs, schema and semantic validation.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run=self._pipeline_guard(db,jid,statuses=('paused',))
            if run['lease_token'] or run['revision']!=revision:
                raise ValueError('generation/revision: wait for a stable pause and refresh')
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row or row['status'] not in ('completed','stale','failed') or not artifact_version or row['artifact_id']!=artifact_version:
                raise ValueError('generation/artifact: checkpoint changed')
            locks={r['pointer'] for r in db.execute('SELECT pointer FROM preparation_field_locks WHERE job_id=? AND unit_id=?',(jid,unit))}
            if not paths or not set(paths)<=locks:raise ValueError('generation/locks: selected lock does not exist')
            result=dict(revision=revision,artifact_version=artifact_version,stale_units=[],locked_paths=sorted(locks-set(paths)))
            if preview:return result
            for path in paths:db.execute('DELETE FROM preparation_field_locks WHERE job_id=? AND unit_id=? AND pointer=?',(jid,unit,path))
            self._record_document(db,'generation_lock_revision',jid+':'+unit,dump({'unlocked_paths':paths,'artifact_version':artifact_version,'revision':revision+1}),True,'author_unlock')
            db.execute('UPDATE preparation_runs SET revision=revision+1 WHERE job_id=?',(jid,))
            return {**result,'revision':revision+1}

    def generation_field_locks(self,jid,unit):
        """Author-only input for the bounded regeneration request, never status."""
        with self.connect() as db:
            return {row['pointer']:json.loads(row['value_json']) for row in db.execute(
                'SELECT pointer,value_json FROM preparation_field_locks WHERE job_id=? AND unit_id=?',(jid,unit))}
