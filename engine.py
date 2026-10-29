"""Background turn processing. Workers are independent of HTTP requests and browser sessions."""
from backend.services.world_delta_errors import StructuralDeltaError

from dataclasses import dataclass, field
import json
import threading
import time

from context_builder import build_context, describe_context, estimate
from llm import chat_stream, find_loaded_model, deepseek_key, PROVIDERS
from backend.runtime_v3.resolver import StateResolver
from storage import Storage
from backend.services.usage import tracked_stream
from backend.services.memory import compact
from backend.services.memory_compactor import output_budget


from backend.services.coordinator import LOCAL_MODEL_LOCK, model_lease

MODEL_LOCK = LOCAL_MODEL_LOCK
REGISTRY_LOCK = threading.Lock()
WORKERS = {}


@dataclass
class Worker:
    epoch: int | None = None
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
    from engine_storage import ExistingJob
    try:
        job_id = storage.begin_job(save_id, user_text, kind, config)
    except ExistingJob as existing:
        return existing.job_id
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
    handle = Worker(api_key=api_key,epoch=Storage(path).get_job(job_id)['attempt_epoch'])
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
    storage.worker_epoch=handle.epoch
    narrative = ''
    job_started=time.perf_counter()
    timings={}
    try:
        initial = storage.get_job(job_id)
        if handle.epoch is not None and initial['attempt_epoch']!=handle.epoch: return
        provider = json.loads(initial['config_json']).get('provider', 'local')
        with model_lease(provider):
            if handle.cancelled.is_set():
                return
            job = storage.get_job(job_id)
            if job['status'] not in ('generating', 'extracting'):
                return
            config = json.loads(job['config_json'])
            if job['kind'] == 'communication':
                from backend.services.communication import execute
                execute(storage, job, handle, chat_stream)
                return
            if job['kind'] == 'long_term':
                from backend.services.long_term_advance import execute
                execute(storage, job, handle, chat_stream)
                return
            context = config['context_length']
            if config.get('provider', 'local') == 'local':
                model = find_loaded_model(config['model'])
                if model is None:
                    raise ValueError('Выбранная модель не загружена. Загрузи её в настройках игры.')
                actual_context = model.get('config', {}).get('context_length') or config['context_length']
                context = min(int(actual_context), config['context_length'])
            before = json.loads(job['memory_before_json'] or job['before_json'])
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            before['world_state']=assert_world_state_v3_invariants(before['world_state'])
            if job['kind']=='turn' and config.get('interaction_channel'):
                before['world_state']['meta']['interaction_focus']=config['interaction_channel']
            from backend.runtime_v3.protagonist import initialize
            initialize(before)
            if job['kind']=='pov' and not job['memory_before_json']:
                from backend.runtime_v3.camera import transition
                before=transition(before,config['actor_id'],config.get('source_node_id'))
            if job['kind']=='background' and not job['memory_before_json']:
                from backend.runtime_v3.camera import observe
                before=observe(before,config.get('camera_actor_id'),config.get('camera_scene_id'),config.get('camera_direct',False))
            from backend.runtime_v3.repository import read_history
            with storage.connect() as db:
                world_history,history_audit=read_history(db,before.get('history_head'))
            from backend.runtime_v3.milestones import reader as milestone_reader
            world_history['_milestone_query'] = milestone_reader(storage, before.get('history_head'))
            from backend.runtime_v3.personality import history_reader
            world_history['_development_query'] = history_reader(storage,before.get('history_head'))
            from backend.runtime_v3.repository import continuity_reader, relationship_reader
            world_history['_relationship_query'] = relationship_reader(storage, before.get('history_head'))
            world_history['_continuity_query'] = continuity_reader(storage, before.get('history_head'))
            history = storage.list_turns(job['save_id'])
            if job['replaces_id'] is not None:
                target = next(t for t in history if t['id'] == job['replaces_id'])
                history = [t for t in history if t['sequence'] < target['sequence']]
            sequence = history[-1]['sequence'] + 1 if history else 0
            before['_resolver_turn_id']=sequence+1
            from backend.runtime_v3.time_skip import TimeSkipRequest, parse_skip, plan_skip
            skip_request = None
            if job['kind'] == 'turn':
                now = before['world_state']['meta']['world_time']
                manual_skip = config.get('time_skip')
                skip_request = TimeSkipRequest(now, now+manual_skip['duration'], manual_skip.get('reason',''), 'manual') if manual_skip else parse_skip(job['user_text'], now, before['character_cards'])
            skip_result = plan_skip(before['world_state'], skip_request) if skip_request else None
            if skip_result: before['_time_skip'] = skip_result
            narrative = job['narrative']
            private_artifacts = json.loads(job.get('private_artifacts_json') or '[]')

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
                    if config.get('_context_selection'):
                        from backend.runtime_v3.context import ContextMessages
                        messages = ContextMessages(messages, config['_context_selection'])
                    if estimate(messages)>context-config['max_tokens']-256:
                        raise ValueError('Сохранённый контекст не помещается в выбранную модель. Увеличь контекст или уменьши лимит ответа.')
                else:
                    stage_started=time.perf_counter()
                    timings['memory_compaction']=0.0
                    if handle.cancelled.is_set():
                        return
                    if job['kind'] not in ('background', 'pov') and not skip_result:
                        from backend.runtime_v3.remote_initiative import stage as stage_remote
                        before['_interaction_input_channel'] = before['world_state']['meta']['interaction_focus']
                        before = stage_remote(before, generate, 'job-' + job_id)
                    messages = build_context(before, history, job['user_text'], job['kind'], context, config['max_tokens'], recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'),world_history=world_history)
                    storage.save_context(job_id,messages,before)
                last_write = 0.0
                stage_started=time.perf_counter()
                from backend.services.private_artifacts import enabled, author_context
                private_options = {}
                if enabled(before['world_state']):
                    def capture_private(value):
                        nonlocal private_artifacts
                        private_artifacts = value
                    private_options['on_private_result'] = capture_private
                    messages = [*messages, author_context(before['world_state'])]
                for chunk in generate('narrative',messages,config['max_tokens'],config.get('temperature',0.8), **private_options):
                    if handle.cancelled.is_set():
                        return
                    narrative += chunk
                    if time.monotonic() - last_write > 0.2:
                        storage.job_progress(job_id, 'generating', narrative=narrative)
                        last_write = time.monotonic()
                timings['narrative']=time.perf_counter()-stage_started
                if not narrative.strip():
                    raise ValueError('Модель вернула пустую сцену.')
                # Payload and completion must share a transaction; a retry never
                # sees a completed public scene without its private authoring result.
                with storage.connect() as db:
                    db.execute("UPDATE game_jobs SET private_artifacts_json=? WHERE id=? AND status='generating' AND attempt_epoch=?",
                        (json.dumps(private_artifacts, ensure_ascii=False), job_id, job['attempt_epoch']))
                    db.execute("UPDATE game_jobs SET status='extracting', narrative=?, narrative_complete=1 WHERE id=? AND status='generating' AND attempt_epoch=?",
                        (narrative, job_id, job['attempt_epoch']))
            if handle.cancelled.is_set() or storage.get_job(job_id)['status'] != 'extracting':
                return
            # Use exactly the policy supplied to this narrative, including retry /
            # regenerate's recorded context. Extraction cannot expand its budget.
            recorded_messages = json.loads(storage.get_job(job_id).get('context_json') or '[]')
            from backend.runtime_v3.pacing import recorded_policy
            narrative_policy = recorded_policy(recorded_messages, before['world_state'])
            from backend.runtime_v3.initiative import recorded_plan
            initiative_plan = recorded_plan(recorded_messages)
            from backend.runtime_v3.continuity import recorded as recorded_continuity
            continuity_plan = recorded_continuity(recorded_messages)
            feedback = None
            previous_extraction = None
            if job['attempt_epoch']:
                from backend.runtime_v3.raw import RawTurnResult, repair_feedback
                # Retry reuses the latest failed proposal as feedback, never as
                # canonical truth or a union of mutually inconsistent attempts.
                for request in storage.request_log(job_id=job_id):
                    if request['stage'] not in ('extraction', 'extraction_repair') or not request.get('response_text'):
                        continue
                    try:
                        previous_extraction = RawTurnResult.parse(request['response_text'])
                    except StructuralDeltaError:
                        pass  # Invalid raw text is still useful repair feedback.
                    diagnostics = json.loads(job.get('repair_diagnostics_json') or '[]')
                    if diagnostics:
                        feedback = repair_feedback(diagnostics[-1], request['response_text'], before['world_state'])
                    break
            for attempt in range(2):
                if handle.cancelled.is_set() or storage.get_job(job_id)['status'] not in ('extracting', 'validating'):
                    return
                storage.job_progress(job_id, 'extracting')
                messages = build_context(before, history, job['user_text'], job['kind'], context,
                                         config['update_tokens'], extraction_text=narrative,
                                         validation_feedback=feedback, pacing_decision=narrative_policy, initiative_decision=initiative_plan,continuity_decision=continuity_plan, recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'),world_history=world_history)
                from backend.services.private_artifacts import enabled, extraction_context
                if private_artifacts or enabled(before['world_state']):
                    messages.append(extraction_context(private_artifacts))
                stage_started=time.perf_counter()
                result = ''.join(generate('extraction' if attempt==0 else 'extraction_repair',messages,config['update_tokens'],0.1,
                                          response_format={'type':'json_object'}))
                timings['extraction' if attempt==0 else 'extraction_repair']=time.perf_counter()-stage_started
                if handle.cancelled.is_set():
                    return
                storage.job_progress(job_id, 'validating')
                stage_started=time.perf_counter()
                resolver = None
                try:
                    from copy import deepcopy
                    from dataclasses import asdict
                    from backend.runtime_v3.raw import RawTurnResult, repair_feedback, repair_revision_warnings
                    raw=RawTurnResult.parse(result)
                    raw.warnings.extend(repair_revision_warnings(previous_extraction, raw))
                    previous_extraction = raw
                    if skip_result: raw.final_scene['elapsed_minutes'] = skip_result['elapsed_minutes']
                    from backend.runtime_v3.remote_semantics import staged_sources
                    from backend.runtime_v3.call_continuity import sources as call_sources
                    resolver=StateResolver(before['world_state'],narrative,job['user_text'],pacing_decision=getattr(messages,'selection',{}).get('pacing'),initiative_decision=initiative_plan,continuity_decision=continuity_plan,runtime_time_skip=bool(skip_result),require_elapsed=job['kind']=='turn' and not skip_result,turn_id=sequence+1,milestone_query=world_history.get('_milestone_query'),development_query=world_history.get('_development_query'),relationship_query=world_history.get('_relationship_query'),actor_names={c['id']:c['name'] for c in before['character_cards']},private_artifacts=private_artifacts,remote_semantic_sources=staged_sources(before),call_sources=call_sources(before['world_state'],world_history,narrative,job['user_text'],sequence+1))
                    resolved=resolver.resolve(raw)
                    if before['world_state']['meta'].get('interaction_focus')=='call':
                        rejected=[w for w in resolved.warnings if w.get('section')=='scheduled_events']
                        if rejected:
                            from backend.runtime_v3.models import fatal
                            fatal('Голосовая договорённость не прошла проверку.', 'call_commitment_rejected',repairable=True,diagnostics=rejected)
                    if staged_sources(before):
                        semantic_sections=set()
                        if any(r.get('remote_source_ids') for r in raw.records['scheduled_event_changes'] if isinstance(r,dict)):
                            semantic_sections.add('scheduled_events')
                        if any(any(isinstance(c,dict) and c.get('source_event_id') in staged_sources(before) for c in r.get('intentions_updates',[])) for r in raw.records['character_changes'] if isinstance(r,dict)):
                            semantic_sections.add('characters')
                        rejected=[w for w in resolved.warnings if w.get('section') in semantic_sections]
                        if rejected:
                            raise ValueError('Семантическая проверка входящей связи: '+json.dumps(rejected,ensure_ascii=False))
                    state=deepcopy(before)
                    state.pop('_resolver_turn_id',None)
                    state.pop('_time_skip', None)
                    state.pop('last_time_skip', None)
                    state.pop('_interaction_input_channel', None)
                    state['world_state']=resolved.state
                    if skip_result:
                        changes_skip=deepcopy(skip_result)
                        state['last_time_skip']=changes_skip
                    state['character_cards'].extend(resolved.cards)
                    choices=resolved.choices if job['kind']!='background' else []
                    changes={'time_skip':skip_result, 'raw_turn_result':asdict(raw), 'state_patch':asdict(resolved.patch)}
                    audience=list(resolved.state['camera']['present_character_ids'])
                    warnings=resolved.warnings
                    history_batch=resolved.history
                    for section, records in state.pop('_remote_batch', {}).items():
                        history_batch.setdefault(section, [])[:0] = records
                    if warnings:
                        with storage.connect() as db:
                            previous=json.loads(db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job_id,)).fetchone()[0] or '[]')
                            db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?', (json.dumps(previous+warnings,ensure_ascii=False),job_id))
                    break
                except StructuralDeltaError as exc:
                    diagnostic=exc.diagnostic('extraction_repair' if attempt==0 and exc.repairable else 'validation_failed')
                    diagnostic.update(attempt=attempt,attempt_epoch=job['attempt_epoch'],revision=job['revision'])
                    storage.record_repair(job_id,diagnostic)
                    if attempt == 1 or not exc.repairable:raise
                    feedback = repair_feedback(diagnostic, result, before['world_state'])
                finally:
                    timings['validation_apply']=timings.get('validation_apply',0)+time.perf_counter()-stage_started
            from backend.runtime_v3.simulation import simulate
            stage_started=time.perf_counter()
            background_warnings=[]
            state,history_batch=simulate(before,state,history_batch,context,config,generate,handle.cancelled,
                warnings=background_warnings,on_repair=lambda detail: storage.record_repair(job_id,detail),
                world_history={'events':world_history.get('events',[]),'_relationship_query':world_history['_relationship_query'],'_milestone_query':world_history['_milestone_query'],'_development_query':world_history['_development_query']})
            if background_warnings:
                with storage.connect() as db:
                    previous=json.loads(db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job_id,)).fetchone()[0] or '[]')
                    db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?',(json.dumps(previous+background_warnings,ensure_ascii=False),job_id))
            if any(request['stage'].startswith('world_simulation') for request in storage.request_log(job_id=job_id)):
                timings['background_simulation']=time.perf_counter()-stage_started
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            assert_world_state_v3_invariants(state['world_state'],before['world_state'])
            from backend.runtime_v3.models import StatePatch
            final=state['world_state'];prior=before['world_state']
            combined={section:{key:value for key,value in final[section].items() if value!=prior[section].get(key)} for section in resolved.patch.upserts}
            if skip_result:
                skip_result.update(state.get('last_time_skip', {}))
                skip_result['living_world_llm_calls']=sum(r['stage'].startswith('world_simulation') for r in storage.request_log(job_id=job_id))
                state['last_time_skip']=skip_result
                changes['time_skip']=skip_result
            changes['state_patch']=asdict(StatePatch(resolved.patch.before_hash,final['meta'],final['camera'],combined))
            with storage.connect() as db:
                db.execute('UPDATE game_jobs SET audience_json=? WHERE id=?',(json.dumps(audience),job_id))
            if not handle.cancelled.is_set():
                timings['total']=time.perf_counter()-job_started
                storage.commit_job(job_id, state, choices, changes, timing=timings, history_batch=history_batch)
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
            if WORKERS.get(job_id) is handle: WORKERS.pop(job_id, None)
