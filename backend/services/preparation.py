"""Durable scenario/summary generation, independent from any HTTP or UI session."""
import json
import threading
import time
from dataclasses import dataclass, field
from llm import chat_stream, find_loaded_model, deepseek_key
from backend.services.coordinator import model_lease
from backend.services.usage import tracked_stream
from backend.services.generation_prompts import build_idea_messages, build_summary_messages


@dataclass
class Handle:
    cancel: threading.Event = field(default_factory=threading.Event)
    stream: object = None


class Preparation:
    def __init__(self, repository):
        self.repo = repository
        self.handles = {}
        self.lock = threading.Lock()

    def submit(self, wid, kind, text, config, revision, api_key=None):
        if config['provider'] == 'deepseek':
            api_key = deepseek_key(api_key)
        handle = Handle()
        with self.lock:
            # Publish the queued job and register its local dispatcher together
            # with respect to periodic recovery, before the worker claims a lease.
            jid = self.repo.begin_preparation(wid, kind, text, config, revision)
            if jid in self.handles or self.repo.preparation_job(jid)['status']!='generating': return jid
            self.handles[jid] = handle
        threading.Thread(target=self.run, args=(jid, config, api_key, handle), daemon=True).start()
        return jid

    def resume_generation(self,jid,api_key=None,revision=None,allow_uncertain_retry=False,new_budget=False):
        job=self.repo.preparation_job(jid)
        if job['kind']!='draft_world_staged': raise ValueError('This job has no staged checkpoints.')
        config=json.loads(job['config_json'])
        if config['provider']=='deepseek': api_key=deepseek_key(api_key)
        with self.lock:
            if jid in self.handles:
                if job['status']=='generating': return
                raise ValueError('The current worker is finishing its checkpoint. Retry resume after it stops.')
            self.repo.generation_control(jid,'retry' if new_budget else 'resume',revision,allow_uncertain_retry)
            handle=Handle();self.handles[jid]=handle
            threading.Thread(target=self.run,args=(jid,config,api_key,handle),daemon=True).start()

    def recover_generations(self,credentials):
        with self.lock:
            recovered=self.repo.recover_generations(owned_jobs=tuple(self.handles))
        with self.repo.connect() as db:
            waiting=[row['id'] for row in db.execute("SELECT j.id FROM preparation_jobs j JOIN preparation_runs r ON r.job_id=j.id WHERE j.status='waiting_for_credentials'")]
        for jid in set(recovered+waiting):
            job=self.repo.preparation_job(jid)
            if job['status']!='waiting_for_credentials': continue
            config=json.loads(job['config_json'])
            try:
                key=credentials.resolve(config['provider'])
                if config['provider']=='local' and not find_loaded_model(config['model']): continue
                self.resume_generation(jid,key)
            except ValueError:
                # Retain an actionable state. Missing/decryption-failed credentials
                # cannot erase checkpoints or trigger an implicit new account.
                continue

    def suspend_generation(self,jid):
        self.repo.interrupt_generation(jid)
        with self.lock: handle=self.handles.get(jid)
        if handle:
            handle.cancel.set()
            if handle.stream:
                def close():
                    try: handle.stream.close()
                    except Exception: pass
                threading.Thread(target=close,daemon=True).start()

    def live(self, jid):
        with self.lock:
            return jid in self.handles

    def stop(self, jid):
        with self.lock:
            handle = self.handles.get(jid)
        if handle:
            handle.cancel.set()
        job = self.repo.preparation_job(jid)
        if self.repo.generation_status(jid) is not None:
            self.repo.generation_control(jid,'cancel')
        else:
            self.repo.preparation_progress(jid, job['narrative'], 'stopped')
        if handle and handle.stream:
            def close():
                try:
                    handle.stream.close()
                except Exception:
                    pass
            threading.Thread(target=close, daemon=True).start()

    def run(self, jid, config, api_key, handle):
        narrative = ''
        try:
            job=self.repo.preparation_job(jid)
            if job['kind']=='draft_world_staged':
                if handle.cancel.is_set() or job['status']!='generating': return
                from backend.services.world_generation import run
                return run(self,jid,json.loads(job['config_json']),api_key,handle,None,chat_stream)
            with model_lease(config['provider']):
                if handle.cancel.is_set():
                    return
                job = self.repo.preparation_job(jid)
                if job['status'] != 'generating':
                    return
                loaded=None
                if config['provider'] == 'local':
                    loaded=find_loaded_model(config['model'])
                    if not loaded:raise ValueError('Сначала загрузи выбранную локальную модель.')
                config = json.loads(job['config_json'])
                if job['kind'].startswith('draft_'):
                    from backend.services.draft_generation import run
                    return run(self,jid,config,api_key,handle,loaded,chat_stream)
                prompts = config.get('_prompts')
                w = self.repo.workspace(job['workspace_id'])
                messages = build_idea_messages(w,prompts) if job['kind'] == 'idea' else build_summary_messages(w,prompts)
                def on_stream(stream):
                    handle.stream = stream
                    if handle.cancel.is_set():
                        stream.close()
                from backend.services.continuation import stream_document
                context=config['context_length']
                if loaded:
                    context=min(context,int(loaded.get('config',{}).get('context_length') or context))
                def generate(request_messages,limit):
                    return tracked_stream(self.repo,chat_stream,jid,job['kind'],config,request_messages,
                        model=config['model'],provider=config['provider'],api_key=api_key,
                        temperature=config['temperature'],max_tokens=limit,require_complete=True,
                        cancel_event=handle.cancel,on_stream=on_stream)
                last = 0.0
                for chunk in stream_document(messages,context,config['max_tokens'],generate,handle.cancel):
                    if handle.cancel.is_set():return
                    narrative += chunk
                    if time.monotonic() - last > 0.1:
                        self.repo.preparation_progress(jid, narrative)
                        last = time.monotonic()
                if not narrative.strip():
                    raise ValueError('Модель вернула пустой текст.')
                if not handle.cancel.is_set():
                    self.repo.preparation_progress(jid, narrative, 'saved')
        except Exception as exc:
            if config.get('_draft_task'):
                narrative=self.repo.preparation_job(jid)['narrative']
            self.repo.preparation_progress(jid, narrative, 'stopped' if handle.cancel.is_set() else 'error', str(exc))
        finally:
            if handle.cancel.is_set() and narrative:
                self.repo.preparation_progress(jid,narrative,'stopped')
            with self.lock:
                self.handles.pop(jid, None)
