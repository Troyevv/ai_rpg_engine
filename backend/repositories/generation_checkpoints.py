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
            CREATE TABLE IF NOT EXISTS preparation_attempts (
              job_id TEXT NOT NULL, unit_id TEXT NOT NULL, attempt INTEGER NOT NULL,
              lease_token TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL, finished REAL,
              PRIMARY KEY(job_id,unit_id,attempt),
              FOREIGN KEY(job_id,unit_id) REFERENCES preparation_units(job_id,unit_id));
            ''')

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
                    if tuple(old[key] for key in ('stage','weight','required_inputs','output_paths')) != definition:
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

    def begin_generation_unit(self,jid,token,unit,attempt_limit=3):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token,statuses=('generating',))
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row: raise ValueError('generation/unit: unknown unit')
            if row['status']=='completed': return False
            if row['status'] not in ('pending','failed','stale') or row['attempts']>=attempt_limit:
                raise ValueError('generation/unit: retry unavailable or budget exhausted')
            manifest={}
            for key in json.loads(row['required_inputs']):
                resource=db.execute('SELECT r.digest,u.status FROM preparation_resources r LEFT JOIN preparation_units u ON u.job_id=r.job_id AND u.unit_id=r.unit_id WHERE r.job_id=? AND resource_key=?',(jid,key)).fetchone()
                if not resource or resource['status'] not in (None,'completed'):
                    raise ValueError(f'generation/inputs/{key}: missing or stale')
                manifest[key]=resource['digest']
            attempt=row['attempts']+1
            db.execute("UPDATE preparation_units SET status='running',attempts=?,input_manifest=?,error='' WHERE job_id=? AND unit_id=?",(attempt,dump(manifest),jid,unit))
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
            vid=self._record_document(db,'generation_checkpoint',jid+':'+unit,dump(payload),True,'checkpoint',row['artifact_id'])
            self._publish_resources(db,jid,vid,payload,json.loads(row['output_paths']),unit)
            db.execute("UPDATE preparation_units SET status='completed',artifact_id=?,error='' WHERE job_id=? AND unit_id=?",(vid,jid,unit))
            db.execute("UPDATE preparation_attempts SET status='completed',finished=? WHERE job_id=? AND unit_id=? AND attempt=?",(time.time(),jid,unit,row['attempts']))
            self._update_generation_progress(db,jid)
            return vid

    def fail_generation_unit(self,jid,token,unit,error):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._pipeline_guard(db,jid,token)
            row=db.execute('SELECT * FROM preparation_units WHERE job_id=? AND unit_id=?',(jid,unit)).fetchone()
            if not row or row['status']!='running': raise ValueError('generation/unit: not running')
            db.execute("UPDATE preparation_units SET status='failed',error=? WHERE job_id=? AND unit_id=?",(error,jid,unit))
            db.execute("UPDATE preparation_attempts SET status='failed',finished=? WHERE job_id=? AND unit_id=? AND attempt=?",(time.time(),jid,unit,row['attempts']))

    @staticmethod
    def _update_generation_progress(db,jid):
        rows=db.execute("SELECT stage,sum(CASE WHEN status='completed' THEN weight ELSE 0 END) done,sum(weight) total FROM preparation_units WHERE job_id=? GROUP BY stage",(jid,)).fetchall()
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
            units=[dict(row) for row in db.execute('SELECT unit_id,stage,status,weight,attempts,error FROM preparation_units WHERE job_id=? ORDER BY rowid',(jid,))]
            return dict(revision=run['revision'],overall_progress=run['progress_floor'],units=units)

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
            elif action=='resume':
                if status=='generating': return status
                if status not in ('paused','waiting_for_credentials','failed'): raise ValueError('generation/resume: wait for a stable checkpoint')
                if run['lease_token'] and run['lease_until']>time.time():
                    raise ValueError('generation/resume: previous worker has not released its lease')
                uncertain=db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='uncertain'",(jid,)).fetchone()
                if uncertain and not allow_uncertain_retry:
                    raise ValueError('generation/resume: interrupted request may have been billed; explicit retry required')
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

    def recover_generations(self,now=None):
        """No speculative provider retry. Return jobs needing secure resumption."""
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT r.job_id FROM preparation_runs r JOIN preparation_jobs j ON j.id=r.job_id WHERE j.status IN ('generating','pause_requested') AND r.lease_until<=?",(now,)).fetchall()
            for row in rows:
                jid=row['job_id']
                if db.execute("SELECT 1 FROM preparation_units WHERE job_id=? AND status='running'",(jid,)).fetchone():
                    self._interrupt_units(db,jid,now)
                else:
                    db.execute("UPDATE preparation_jobs SET status='waiting_for_credentials',error='Resume from the last validated checkpoint with provider access.' WHERE id=?",(jid,))
                    db.execute('UPDATE preparation_runs SET lease_token=NULL,lease_until=0 WHERE job_id=?',(jid,))
            return [row['job_id'] for row in rows]
