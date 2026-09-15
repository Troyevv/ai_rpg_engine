"""Background turn processing. Workers never touch Streamlit session state."""
from dataclasses import dataclass, field
import json
import threading
import time

from context_builder import build_context
from llm import chat_stream, find_loaded_model, deepseek_key
from state_updates import apply_updates
from storage import Storage

from backend.services.coordinator import LOCAL_MODEL_LOCK, model_lease

MODEL_LOCK = LOCAL_MODEL_LOCK
REGISTRY_LOCK = threading.Lock()
WORKERS = {}


@dataclass
class Worker:
    cancelled: threading.Event = field(default_factory=threading.Event)
    stream: object = None
    api_key: str | None = field(default=None, repr=False)


def busy():
    with REGISTRY_LOCK:
        return bool(WORKERS)


def live(job_id):
    with REGISTRY_LOCK:
        return job_id in WORKERS


def check_config(config):
    if config.get('provider', 'local') not in ('local', 'deepseek'):
        raise ValueError('Неизвестный провайдер модели.')
    if not isinstance(config.get('model'), str) or not config['model']:
        raise ValueError('Выбери модель ведущего в левой панели.')
    for key in ('context_length', 'max_tokens', 'update_tokens'):
        if type(config.get(key)) is not int or config[key] < 256:
            raise ValueError('Некорректные параметры модели.')


def submit(storage, save_id, user_text='', kind='turn', config=None, api_key=None):
    config = config or {}
    check_config(config)
    if config.get('provider') == 'deepseek':
        api_key = deepseek_key(api_key)
    job_id = storage.begin_job(save_id, user_text, kind, config)
    if config.get('provider') == 'deepseek':
        launch(storage.path, job_id, api_key=api_key)
    else:
        launch(storage.path, job_id)
    return job_id


def retry(storage, job_id, config, api_key=None):
    check_config(config)
    if live(job_id):
        raise ValueError('Предыдущий запрос ещё останавливается. Подожди немного.')
    if config.get('provider') == 'deepseek':
        api_key = deepseek_key(api_key)
    storage.retry_job(job_id, config)
    if config.get('provider') == 'deepseek':
        launch(storage.path, job_id, api_key=api_key)
    else:
        launch(storage.path, job_id)


def launch(path, job_id, api_key=None):
    handle = Worker(api_key=api_key)
    with REGISTRY_LOCK:
        WORKERS[job_id] = handle
    threading.Thread(target=run_job, args=(path, job_id, handle), daemon=True, name=f'rpg-{job_id[:8]}').start()


def stop(storage, job_id):
    # This persistent status also prevents a late response from committing.
    storage.job_progress(job_id, 'stopped')
    with REGISTRY_LOCK:
        handle = WORKERS.get(job_id)
    if handle:
        handle.cancelled.set()
        if handle.stream:
            def close():
                try:
                    handle.stream.close()
                except Exception:
                    pass
            threading.Thread(target=close, daemon=True).start()


def run_job(path, job_id, handle):
    storage = Storage(path)
    narrative = ''
    try:
        initial = storage.get_job(job_id)
        provider = json.loads(initial['config_json']).get('provider', 'local')
        with model_lease(provider):
            if handle.cancelled.is_set():
                return
            job = storage.get_job(job_id)
            if job['status'] not in ('generating', 'extracting'):
                return
            config = json.loads(job['config_json'])
            context = config['context_length']
            if config.get('provider', 'local') == 'local':
                model = find_loaded_model(config['model'])
                if model is None:
                    raise ValueError('Выбранная модель не загружена. Загрузи её в настройках игры.')
                actual_context = model.get('config', {}).get('context_length') or config['context_length']
                context = min(int(actual_context), config['context_length'])
            before = json.loads(job['before_json'])
            history = storage.list_turns(job['save_id'])
            if job['replaces_id'] is not None:
                history = [t for t in history if t['id'] != job['replaces_id']]
            sequence = history[-1]['sequence'] + 1 if history else 0
            narrative = job['narrative']

            def on_stream(stream):
                handle.stream = stream
                if handle.cancelled.is_set():
                    stream.close()

            common = {'model': config['model'], 'require_complete': True,
                      'cancel_event': handle.cancelled, 'on_stream': on_stream,
                      'provider': config.get('provider', 'local'), 'api_key': handle.api_key}
            if not job['narrative_complete']:
                messages = build_context(before, history, job['user_text'], job['kind'], context, config['max_tokens'])
                last_write = 0.0
                for chunk in chat_stream(messages=messages, temperature=config.get('temperature', 0.8),
                                         max_tokens=config['max_tokens'], **common):
                    if handle.cancelled.is_set():
                        return
                    narrative += chunk
                    if time.monotonic() - last_write > 0.2:
                        storage.job_progress(job_id, 'generating', narrative=narrative)
                        last_write = time.monotonic()
                if not narrative.strip():
                    raise ValueError('Модель вернула пустую сцену.')
                storage.job_progress(job_id, 'extracting', narrative=narrative, complete=True)
            if handle.cancelled.is_set() or storage.get_job(job_id)['status'] != 'extracting':
                return
            messages = build_context(before, history, job['user_text'], job['kind'], context,
                                     config['update_tokens'], extraction_text=narrative)
            result = ''.join(chat_stream(messages=messages, temperature=0.1, max_tokens=config['update_tokens'],
                                       response_format={'type': 'json_object'}, **common))
            if handle.cancelled.is_set():
                return
            storage.job_progress(job_id, 'validating')
            state, choices, changes = apply_updates(before, result, narrative, job['user_text'], sequence)
            if not handle.cancelled.is_set():
                storage.commit_job(job_id, state, choices, changes)
    except Exception as exc:
        storage.job_progress(job_id, 'stopped' if handle.cancelled.is_set() else 'error',
                             narrative=narrative or None, error=str(exc))
    finally:
        if handle.cancelled.is_set() and narrative:
            with storage.connect() as db:
                db.execute("UPDATE game_jobs SET narrative=? WHERE id=? AND status='stopped' AND narrative_complete=0", (narrative, job_id))
        with REGISTRY_LOCK:
            WORKERS.pop(job_id, None)
