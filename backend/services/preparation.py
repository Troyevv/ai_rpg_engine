"""Durable scenario/summary generation, independent from any HTTP or UI session."""
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
        jid = self.repo.begin_preparation(wid, kind, text, config, revision)
        handle = Handle()
        with self.lock:
            self.handles[jid] = handle
        threading.Thread(target=self.run, args=(jid, config, api_key, handle), daemon=True).start()
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

    def run(self, jid, config, api_key, handle):
        narrative = ''
        try:
            with model_lease(config['provider']):
                if handle.cancel.is_set():
                    return
                job = self.repo.preparation_job(jid)
                if job['status'] != 'generating':
                    return
                if config['provider'] == 'local' and not find_loaded_model(config['model']):
                    raise ValueError('Сначала загрузи выбранную локальную модель.')
                w = self.repo.workspace(job['workspace_id'])
                messages = build_idea_messages(w) if job['kind'] == 'idea' else build_summary_messages(w)
                def on_stream(stream):
                    handle.stream = stream
                    if handle.cancel.is_set():
                        stream.close()
                last = 0.0
                for chunk in tracked_stream(self.repo,chat_stream,jid,job['kind'],config,messages,model=config['model'], provider=config['provider'], api_key=api_key,
                                         temperature=config['temperature'], max_tokens=config['max_tokens'],
                                         require_complete=True, cancel_event=handle.cancel, on_stream=on_stream):
                    if handle.cancel.is_set():
                        return
                    narrative += chunk
                    if time.monotonic() - last > 0.1:
                        self.repo.preparation_progress(jid, narrative)
                        last = time.monotonic()
                if not narrative.strip():
                    raise ValueError('Модель вернула пустой текст.')
                if not handle.cancel.is_set():
                    self.repo.preparation_progress(jid, narrative, 'saved')
        except Exception as exc:
            self.repo.preparation_progress(jid, narrative, 'stopped' if handle.cancel.is_set() else 'error', str(exc))
        finally:
            with self.lock:
                self.handles.pop(jid, None)
