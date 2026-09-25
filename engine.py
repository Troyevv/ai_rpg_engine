"""Background turn processing. Workers are independent of HTTP requests and browser sessions."""
from backend.services.world_delta_errors import StructuralDeltaError

from dataclasses import dataclass, field
import json
import threading
import time

from context_builder import build_context, describe_context, estimate
from llm import chat_stream, find_loaded_model, deepseek_key, PROVIDERS
from state_updates import apply_world_updates
from storage import Storage
from backend.services.usage import tracked_stream
from backend.services.memory import compact
from backend.services.memory_compactor import output_budget
from backend.services.pov import apply_scene_policy

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
    if config.get('provider', 'local') not in PROVIDERS:
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
    job_started=time.perf_counter()
    timings={}
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
            from backend.services.world import normalize, record_narrative, compatibility_view
            before = normalize(json.loads(job['memory_before_json'] or job['before_json']))
            if job['kind']=='pov' and not job['memory_before_json']:
                from backend.services.pov import transition
                before=transition(before,config['actor_id'],config.get('source_node_id'))
            if job['kind']=='background' and not job['memory_before_json']:
                from backend.services.director import observe
                before=observe(before,config.get('camera_actor_id'),config.get('camera_scene_id'),config.get('camera_direct',False))
            history = storage.list_turns(job['save_id'])
            if job['replaces_id'] is not None:
                target = next(t for t in history if t['id'] == job['replaces_id'])
                history = [t for t in history if t['sequence'] < target['sequence']]
            sequence = history[-1]['sequence'] + 1 if history else 0
            narrative = job['narrative']

            def on_stream(stream):
                handle.stream = stream
                if handle.cancelled.is_set():
                    stream.close()

            common = {'model': config['model'], 'require_complete': True,
                      'cancel_event': handle.cancelled, 'on_stream': on_stream,
                      'provider': config.get('provider', 'local'), 'api_key': handle.api_key}
            def generate(stage, messages, limit, temperature, **extra):
                return tracked_stream(storage, chat_stream, job_id, stage, config, messages,
                                      describe_context(messages), temperature=temperature,
                                      max_tokens=limit, **extra, **common)

            if not job['narrative_complete']:
                if job['context_json']:
                    messages = json.loads(job['context_json'])
                    if estimate(messages)>context-config['max_tokens']-256:
                        raise ValueError('Сохранённый контекст не помещается в выбранную модель. Увеличь контекст или уменьши лимит ответа.')
                else:
                    stage_started=time.perf_counter()
                    before = compact(storage, job, before, history, dict(config,context_length=context),
                                     lambda messages: generate('memory',messages,output_budget(dict(config,context_length=context)),0.1), handle.cancelled)
                    if any(request['stage']=='memory' for request in storage.request_log(job_id=job_id)):
                        timings['memory_compaction']=time.perf_counter()-stage_started
                    if handle.cancelled.is_set():
                        return
                    messages = build_context(before, history, job['user_text'], job['kind'], context, config['max_tokens'], recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'))
                    storage.save_context(job_id,messages,before)
                last_write = 0.0
                stage_started=time.perf_counter()
                for chunk in generate('narrative',messages,config['max_tokens'],config.get('temperature',0.8)):
                    if handle.cancelled.is_set():
                        return
                    narrative += chunk
                    if time.monotonic() - last_write > 0.2:
                        storage.job_progress(job_id, 'generating', narrative=narrative)
                        last_write = time.monotonic()
                timings['narrative']=time.perf_counter()-stage_started
                if not narrative.strip():
                    raise ValueError('Модель вернула пустую сцену.')
                storage.job_progress(job_id, 'extracting', narrative=narrative, complete=True)
            if handle.cancelled.is_set() or storage.get_job(job_id)['status'] != 'extracting':
                return
            feedback = None
            for attempt in range(2):
                if handle.cancelled.is_set() or storage.get_job(job_id)['status'] not in ('extracting', 'validating'):
                    return
                storage.job_progress(job_id, 'extracting')
                messages = build_context(before, history, job['user_text'], job['kind'], context,
                                         config['update_tokens'], extraction_text=narrative,
                                         validation_feedback=feedback, recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'))
                stage_started=time.perf_counter()
                result = ''.join(generate('extraction' if attempt==0 else 'extraction_repair',messages,config['update_tokens'],0.1,
                                          response_format={'type':'json_object'}))
                timings['extraction' if attempt==0 else 'extraction_repair']=time.perf_counter()-stage_started
                if handle.cancelled.is_set():
                    return
                storage.job_progress(job_id, 'validating')
                stage_started=time.perf_counter()
                try:
                    state, choices, changes, audience, warnings = apply_world_updates(
                        before,result,narrative,job['user_text'],sequence,job['kind'],discard_unsupported=True)
                    if warnings:
                        with storage.connect() as db:
                            previous=json.loads(db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job_id,)).fetchone()[0] or '[]')
                            db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?', (json.dumps(previous+warnings,ensure_ascii=False),job_id))
                    break
                except StructuralDeltaError as exc:
                    if attempt == 1 or not exc.repairable:raise
                    diagnostic=exc.diagnostic('extraction_repair')
                    storage.record_repair(job_id,diagnostic)
                    feedback = json.dumps(diagnostic,ensure_ascii=False)
                finally:
                    timings['validation_apply']=timings.get('validation_apply',0)+time.perf_counter()-stage_started
            record_narrative(state,narrative,sequence,True,set(before['world']['events']))
            from backend.services.simulation import simulate
            stage_started=time.perf_counter()
            background_warnings=[]
            state=simulate(before,state,sequence,context,config,generate,handle.cancelled,warnings=background_warnings,on_repair=lambda detail: storage.record_repair(job_id,detail))
            if background_warnings:
                with storage.connect() as db:
                    previous=json.loads(db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job_id,)).fetchone()[0] or '[]')
                    db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?',(json.dumps(previous+background_warnings,ensure_ascii=False),job_id))
            if any(request['stage'].startswith('world_simulation') for request in storage.request_log(job_id=job_id)):
                timings['background_simulation']=time.perf_counter()-stage_started
            state=compatibility_view(state)
            with storage.connect() as db:
                db.execute('UPDATE game_jobs SET audience_json=? WHERE id=?',(json.dumps(audience),job_id))
            if not handle.cancelled.is_set():
                timings['total']=time.perf_counter()-job_started
                storage.commit_job(job_id, state, choices, changes, timing=timings)
                # Include the commit and variant snapshot in independently measured
                # wall-clock time; the provisional value covers an interrupted final write.
                storage.finalize_job_timing(job_id,time.perf_counter()-job_started)
    except Exception as exc:
        storage.job_progress(job_id, 'stopped' if handle.cancelled.is_set() else 'error',
                             narrative=narrative or None, error=str(exc))
    finally:
        if handle.cancelled.is_set() and narrative:
            with storage.connect() as db:
                db.execute("UPDATE game_jobs SET narrative=? WHERE id=? AND status='stopped' AND narrative_complete=0", (narrative, job_id))
        with REGISTRY_LOCK:
            WORKERS.pop(job_id, None)
