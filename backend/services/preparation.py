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
    epoch: int = 0


class Preparation:
    def __init__(self, repository):
        self.repo = repository
        self.handles = {}
        self.lock = threading.Lock()

    def submit(self, wid, kind, text, config, revision, api_key=None):
        if config['provider'] == 'deepseek':
            api_key = deepseek_key(api_key)
        with self.lock:
            jid, created = self.repo.begin_preparation(wid, kind, text, config, revision, receipt=True)
            # Only the worker that inserted the job may dispatch the paid request.
            if not created:
                return jid
            handle = Handle()
            self.handles[jid] = handle
        threading.Thread(target=self.run, args=(jid, config, api_key, handle), daemon=True).start()
        return jid

    def resume(self,jid,api_key=None,**options):
        with self.lock:
            if jid in self.handles: raise ValueError('Запрос ещё завершается.')
            job=self.repo.preparation_job(jid)
            config=json.loads(job['config_json'])
            from backend.services.draft_review_actions import saved_reply
            if config['provider']=='deepseek' and not saved_reply(json.loads(job.get('response_journal') or '{}')):
                api_key=deepseek_key(api_key)
            config=self.repo.resume_draft_response(jid,**options)
            handle=Handle(epoch=json.loads(job.get('response_journal') or '{}').get('recovery_epoch',0)+1);self.handles[jid]=handle
        threading.Thread(target=self.run,args=(jid,config,api_key,handle),daemon=True).start()
        return jid

    def live(self, jid):
        with self.lock:
            return jid in self.handles

    def stop(self, jid):
        with self.lock:
            handle = self.handles.get(jid)
        if handle:
            handle.cancel.set()
        job = self.repo.preparation_job(jid)
        self.repo.preparation_progress(jid, job['narrative'], 'stopped')
        if handle and handle.stream:
            def close():
                try:
                    handle.stream.close()
                except Exception:
                    pass
            threading.Thread(target=close, daemon=True).start()

    def signal_stopped(self, jid, epoch):
        """Signal the exact worker already cancelled by the confirmation transaction.

        Do not write job status here: a later job/resume may already be running.
        Repeated confirmation must never cancel a newer handle or preparation.
        """
        with self.lock:
            handle = self.handles.get(jid)
            if not handle or handle.epoch != epoch:
                return
            handle.cancel.set()
        if handle.stream:
            def close():
                try:
                    handle.stream.close()
                except Exception:
                    pass
            threading.Thread(target=close, daemon=True).start()

    def run(self, jid, config, api_key, handle):
        narrative = ''
        worker_epoch=handle.epoch if config.get('_draft_task') in ('world','editor','field','character') else None
        try:
            if config.get('_draft_task') in ('editor','field','character'):
                from backend.services.draft_review_actions import saved_reply, finish
                from backend.services.draft_response import join_fragments
                journal=json.loads(self.repo.preparation_job(jid)['response_journal'])
                cached=saved_reply(journal)
                if cached:
                    text=join_fragments(cached['parts'],cached.get('assembly'),terminal=True)
                    if config.get('_review_action'):
                        finish(self.repo,jid,journal['editor'],text,worker_epoch)
                    elif config['_draft_task']=='editor':
                        from backend.services.draft_editor import finish_proposal
                        finish_proposal(self.repo,jid,journal,text,worker_epoch)
                    else:
                        from backend.services.draft_generation import finish_scoped
                        job=self.repo.preparation_job(jid)
                        base=self.repo.draft(job['workspace_id'],True)['state']
                        finish_scoped(self.repo,jid,text,base,config)
                    return
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
                if worker_epoch is not None and json.loads(job.get('response_journal') or '{}').get('recovery_epoch',0)!=worker_epoch:return
                from backend.services.token_budget import prepare, snapshot
                journal = json.loads(job.get('response_journal') or '{}')
                config = prepare(dict(config, _budget_snapshot=journal.get('budget_snapshot')), job['kind'], loaded=loaded, api_key=api_key)
                if worker_epoch is not None and config.get('budget_mode') and 'budget_snapshot' not in journal:
                    journal['budget_snapshot'] = snapshot(config)
                    self.repo.save_response_journal(jid, journal)
                if job['kind']=='draft_editor':
                    from backend.services.draft_editor import run
                    return run(self,jid,config,api_key,handle,loaded,chat_stream)
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
                for chunk in stream_document(messages,context,config['max_tokens'],generate,handle.cancel,output_ceiling=config['max_tokens']):
                    if handle.cancel.is_set():return
                    narrative += chunk
                    if time.monotonic() - last > 0.1:
                        self.repo.preparation_progress(jid, narrative)
                        last = time.monotonic()
                if not narrative.strip():
                    raise ValueError('Модель вернула пустой текст.')
                if not handle.cancel.is_set():
                    self.repo.preparation_progress(jid, narrative, 'saved')
        except MemoryError:
            raise
        except Exception as exc:
            if worker_epoch is not None and json.loads(self.repo.preparation_job(jid).get('response_journal') or '{}').get('recovery_epoch',0)!=worker_epoch:return
            if config.get('_draft_task'):
                from llm import ProviderHTTPError
                if not isinstance(exc,(ValueError,ProviderHTTPError)):
                    journal=json.loads(self.repo.preparation_job(jid).get('response_journal') or '{}')
                    journal.setdefault('internal_errors',[]).append(dict(code='internal_error',type=type(exc).__name__,message=str(exc)))
                    self.repo.save_response_journal(jid,journal)
                    exc=RuntimeError('internal_error: внутренняя ошибка обработки; кандидат сохранён, диагностика доступна автору.')
                narrative=self.repo.preparation_job(jid)['narrative']
            self.repo.preparation_progress(jid, narrative, 'stopped' if handle.cancel.is_set() else 'error', str(exc))
        finally:
            if handle.cancel.is_set() and narrative and (worker_epoch is None or json.loads(self.repo.preparation_job(jid).get('response_journal') or '{}').get('recovery_epoch',0)==worker_epoch):
                self.repo.preparation_progress(jid,narrative,'stopped')
            with self.lock:
                self.handles.pop(jid, None)
