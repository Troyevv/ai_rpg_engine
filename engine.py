"""Background turn processing. Workers are independent of HTTP requests and browser sessions."""
from backend.runtime_v3.remote_semantics import relationship_sources as remote_relationship_sources
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
    if config.get('provider') == 'deepseek' and kind != 'regenerate':
        api_key = deepseek_key(api_key)
    from engine_storage import ExistingJob
    try:
        job_id = storage.begin_job(save_id, user_text, kind, config)
    except ExistingJob as existing:
        return existing.job_id
    effective = json.loads(storage.get_job(job_id)['config_json'])
    provider = effective.get('provider','local')
    if provider != config.get('provider','local'):
        from backend.services.credentials import Credentials
        api_key = Credentials(storage).resolve(provider)
    if provider != 'local' and api_key:
        launch(storage.path, job_id, api_key=api_key)
    else:
        launch(storage.path, job_id)
    return job_id


def retry(storage, job_id, config, api_key=None, *, correct_chronology=False, revision=None, attempt_epoch=None):
    if correct_chronology:
        config = json.loads(storage.get_job(job_id)['config_json'])
    check_config(config)
    if live(job_id):
        raise ValueError('Предыдущий запрос ещё останавливается. Подожди немного.')
    if config.get('provider') == 'deepseek':
        api_key = deepseek_key(api_key)
    if correct_chronology:
        # Correction inherits the original effective model/config; a UI settings
        # change cannot silently turn it into a different experiment.
        job_id = storage.correct_chronology_job(job_id, revision, attempt_epoch)
    else:
        storage.retry_job(job_id, config, revision=revision, attempt_epoch=attempt_epoch)
    if config.get('provider') != 'local' and api_key:
        launch(storage.path, job_id, api_key=api_key)
    else:
        launch(storage.path, job_id)

    return job_id


def launch(path, job_id, api_key=None):
    handle = Worker(api_key=api_key,epoch=Storage(path).get_job(job_id)['attempt_epoch'])
    with REGISTRY_LOCK:
        WORKERS[job_id] = handle
    threading.Thread(target=run_job, args=(path, job_id, handle), daemon=True, name=f'rpg-{job_id[:8]}').start()


def stop(storage, job_id):
    # This persistent status also prevents a late response from committing.
    if not storage.finish_interpretation(job_id, 'interpretation_stopped'):
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
            from backend.services.token_budget import prepare, snapshot, extraction_output, extraction_reserve, preflight_downstream
            before = json.loads(job['memory_before_json'] or job['before_json'])
            detail = before['world_state']['meta'].get('narrative_detail','balanced')
            def prepare_job(loaded=None):
                resolved = prepare(config, job['kind'], loaded=loaded, detail=detail, api_key=handle.api_key)
                if config.get('budget_mode') and not config.get('_budget_snapshot'):
                    with storage.connect() as db:
                        db.execute("UPDATE game_jobs SET config_json=json_set(config_json,'$._budget_snapshot',json(?)) WHERE id=? AND attempt_epoch=?",
                                   (json.dumps(snapshot(resolved)), job_id, job['attempt_epoch']))
                return resolved
            if job['kind'] in ('communication','long_term'):
                if job['kind'] == 'communication':
                    from backend.services.communication import execute
                else:
                    from backend.services.long_term_advance import execute
                if job['kind']=='communication' or config['long_term_advance'].get('max_llm_calls') != 0:
                    config = prepare_job()
                execute(storage, job, handle, chat_stream, config)
                return
            model = None
            if config.get('provider', 'local') == 'local':
                model = find_loaded_model(config['model'])
                if model is None:
                    raise ValueError('Выбранная модель не загружена. Загрузи её в настройках игры.')
            config = prepare_job(model)
            context = config['context_length']
            max_input = config['_budget_caps'].get('max_input')
            recorded = config.get('_recorded_budget')
            if recorded:
                original_endpoint = recorded.get('capabilities',{}).get('endpoint_id')
                if original_endpoint and original_endpoint != config['_budget_caps'].get('endpoint_id'):
                    raise ValueError('Адрес провайдера изменился. Восстановите подключение исходной модели.')
                if context < recorded['context_window'] or config['_budget_caps'].get('max_output') and config['_budget_caps']['max_output'] < recorded['output_allowance']:
                    raise ValueError('Возможности модели изменились. Сохранённый план запроса несовместим.')
                context = config['context_length'] = recorded['context_window']
                config['max_tokens'] = recorded['output_allowance']
            from backend.runtime_v3.repository import restore_biographical_secrets
            with storage.connect() as db:
                restore_biographical_secrets(db, before)
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
            version = config.get('_extraction_contract', 1)
            if version >= 9:
                camera = before['world_state']['camera']
                history, sequence = storage.context_history(job['save_id'], config.get('_published_scene',{}).get('turn_id',job['replaces_id']),
                    max(int(version >= 10),config.get('recent_turns',6)), camera.get('pov_actor_id') or camera.get('controlled_actor_id'),
                    before.get('campaign',{}).get('protagonist_id'))
                def literary_sources(sequences):
                    return storage.list_turns(job['save_id'], context=True,
                                              sequences={n for n in sequences if 0 <= n < sequence})
                world_history['_literary_sources'] = literary_sources
            else:
                history = storage.list_turns(job['save_id'], context=True)
                if job['replaces_id'] is not None:
                    target = next(t for t in history if t['id'] == job['replaces_id'])
                    history = [t for t in history if t['sequence'] < target['sequence']]
                sequence = history[-1]['sequence'] + 1 if history else 0
            before['_resolver_turn_id']=sequence+1
            from backend.runtime_v3.time_skip import TimeSkipRequest, parse_skip, plan_skip, interpreted_skip
            skip_request = None
            if job['kind'] == 'turn':
                now = before['world_state']['meta']['world_time']
                manual_skip = config.get('time_skip')
                if manual_skip:
                    skip_request = TimeSkipRequest(now, now+manual_skip['duration'], manual_skip.get('reason',''), 'manual')
                else:
                    try:
                        skip_request = parse_skip(job['user_text'], now, before['character_cards'])
                    except ValueError:
                        if version < 11:
                            raise
                        # An unrepresentable free-text hint is still ordinary player input.
                        skip_request = None
            skip_result = plan_skip(before['world_state'], skip_request, version=version) if skip_request else None
            if skip_result: before['_time_skip'] = skip_result
            narrative = job['narrative']
            suggestions = config.get('_narrative_suggestions', []) if version >= 9 else []
            from backend.runtime_v3.suggestions import split_suggestions
            from backend.runtime_v3 import narrative_frame
            frame = config.get('_authored_frame')
            legacy_letter_sources = json.loads(job.get('private_artifacts_json') or '[]')
            letter_sources = legacy_letter_sources

            def on_stream(stream):
                handle.stream = stream
                if handle.cancelled.is_set():
                    stream.close()

            common = {'model': config['model'], 'require_complete': True,
                      'cancel_event': handle.cancelled, 'on_stream': on_stream,
                      'provider': config.get('provider', 'local'), 'api_key': handle.api_key}
            def generate(stage, messages, limit, temperature, **extra):
                if stage == 'world_simulation' and config.get('_narrative_recovery'):
                    # Preserve the source branch's authored background too. The
                    # new Extraction still receives corrected before/context.
                    source = config['_narrative_recovery']['source_job_id']
                    originals = [r for r in storage.request_log(job_id=source)
                                 if r['stage']==stage and r['status']=='complete' and r.get('response_text')]
                    def subject(rows):
                        for row in rows:
                            if row.get('content','').startswith('Текущее состояние / GM-only\n'):
                                return json.loads(row['content'].split('\n',1)[1])['camera'].get('subject_id')
                    current_subject = subject(messages)
                    matches = [r for r in originals if current_subject is not None and subject(r['messages'])==current_subject]
                    if len(matches)!=1:
                        raise RuntimeError('Не найден однозначный исходный background Narrative для recovery.')
                    return iter([matches[0]['response_text']])
                if stage in ('remote_initiative', 'remote_group_semantics') or (version >= 10 and stage == 'extraction' and job['attempt_epoch']):
                    # Reuse a completed source-identical request after a later
                    # provider failure; the existing usage journal owns the text.
                    for attempt in storage.request_log(job_id=job_id):
                        if (attempt['stage'] == stage and attempt['status'] == 'complete'
                                and attempt['messages'] == messages and attempt.get('response_text')):
                            return iter([attempt['response_text']])
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
                        from llm import ProviderGenerationError
                        before = stage_remote(before, generate, 'job-' + job_id, context_limit=context, cancelled=handle.cancelled, provider_errors=(ProviderGenerationError,), history_events=world_history.get('events', []))
                    messages = build_context(before, history, job['user_text'], job['kind'], context, config['max_tokens'], max_input=max_input, extraction_contract=version, public_observation=job['kind']=='background', recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'),world_history=world_history)
                from backend.runtime_v3.player_actions import NARRATIVE_CONTRACT as action_contract, required as agency_required
                if agency_required(before['world_state'], job['user_text'], job['kind']) and not any('PLAYER ACTION AGENCY:' in m.get('content', '') for m in messages):
                    from copy import copy
                    messages = copy(messages)
                    # Old recorded contexts keep their original world/input. Only
                    # the current agency safety contract is added, as for letters.
                    messages.append({'role': 'system', 'content': action_contract})
                    if estimate(messages) > context-config['max_tokens']-256:
                        raise ValueError('Сохранённый контекст с проверкой agency не помещается в выбранную модель.')
                last_write = 0.0
                stage_started=time.perf_counter()
                from backend.services.letter_sources import enabled, CONTRACT
                if enabled(before['world_state']) and not any('LETTER AUTHORING CONTRACT:' in str(m.get('content','')) for m in messages):
                    from copy import copy
                    messages = copy(messages)
                    # Compatibility for recorded pre-change contexts only.
                    messages.append({'role':'system','content':CONTRACT})
                    if estimate(messages)>context-config['max_tokens']-256:
                        raise ValueError('Сохранённый контекст с контрактом письма не помещается в выбранную модель.')
                if config.get('budget_mode') and not config.get('_narrative_correction'):
                    # Project Extraction with the same scope and pinned policies before buying prose.
                    from backend.runtime_v3.pacing import recorded_policy
                    from backend.runtime_v3.initiative import recorded_plan
                    from backend.runtime_v3.continuity import recorded as recorded_continuity
                    preflight_downstream(config, lambda reserve: build_context(
                        before, history, job['user_text'], job['kind'], context, reserve, max_input=max_input, extraction_text='',
                        extraction_contract=version, recent_turns=config.get('recent_turns',6), prompts=config.get('_prompts'),
                        world_history=world_history, pacing_decision=recorded_policy(messages,before['world_state']),
                        initiative_decision=recorded_plan(messages), continuity_decision=recorded_continuity(messages)))
                storage.save_context(job_id,messages,before)
                correction = config.get('_narrative_correction')
                if correction:
                    chronology_only = all(g.get('kind') not in ('agency','birth','birth_boundary') for g in correction['grounds'])
                    instruction = ('Исправь только хронологические утверждения отклонённого кандидата по каноническим основаниям. '
                                   if chronology_only else 'Исправь только указанные фрагменты отклонённой сцены по исходному выбору игрока и канону. ')
                    correction_messages = list(messages) + [{'role':'system', 'content':
                        instruction +
                        'Сохрани события, стиль и смысл остальных фрагментов. Верни JSON {"edits":[{"original":"точный evidence",'
                        '"replacement":"исправленный фрагмент"}]}. Не создавай новую сцену.\n' +
                        json.dumps(correction, ensure_ascii=False)}]
                    if estimate(correction_messages) > context-config['max_tokens']-256:
                        raise ValueError('Контекст адресной коррекции не помещается; увеличь окно явно.')
                    from backend.runtime_v3.continuity import corrected_candidate
                    correction_payload = ''.join(generate('narrative_correction', correction_messages,
                        config['max_tokens'], config.get('temperature', 0.8), response_format={'type':'json_object'}))
                    if handle.cancelled.is_set(): return
                    narrative = corrected_candidate(correction['original'], correction_payload, correction['grounds'])
                    chunks = []
                else:
                    structured_menu = version >= 10 and narrative_frame.requested(messages)
                    # Ask for the frame in the prompt. DeepSeek JSON Output can
                    # replace unrecognized output with spaces before we see it.
                    chunks = generate('narrative',messages,config['max_tokens'],config.get('temperature',0.8))
                authored = narrative
                for chunk in chunks:
                    if handle.cancelled.is_set():
                        return
                    authored += chunk
                    decoded = narrative_frame.read(authored, complete=False) if structured_menu else None
                    narrative = decoded[0] if decoded else split_suggestions(authored, verbatim=version>=10)[0] if version >= 9 else authored
                    if time.monotonic() - last_write > 0.2:
                        storage.job_progress(job_id, 'generating', narrative=narrative)
                        last_write = time.monotonic()
                if version >= 9 and not correction:
                    decoded = narrative_frame.recorded_reply(authored, messages) if structured_menu else None
                    if decoded:
                        narrative, frame = decoded
                        suggestions = []
                    else:
                        narrative, suggestions = split_suggestions(authored, complete=True, verbatim=version>=10)
                timings['narrative']=time.perf_counter()-stage_started
                if not narrative.strip():
                    raise ValueError('Модель вернула пустую сцену.')
                # New letters are recovered directly from the recorded Narrative.
                # Keep the old column only for pre-change completed job recovery.
                with storage.connect() as db:
                    db.execute("UPDATE game_jobs SET status='extracting', narrative=?, narrative_complete=1, config_json=json_patch(config_json,?) WHERE id=? AND status='generating' AND attempt_epoch=?",
                        (narrative, json.dumps({'_narrative_suggestions': suggestions, '_authored_frame':frame} if version >= 9 else {}, ensure_ascii=False), job_id, job['attempt_epoch']))
            if version >= 10 and not config.get('_published_scene'):
                if handle.cancelled.is_set():
                    return
                storage.publish_scene(job_id, before, sequence, narrative, job['user_text'], timings)
            messages = json.loads(storage.get_job(job_id)['context_json'] or '[]')
            if not letter_sources:
                from backend.services.letter_sources import parse, enabled
                letter_sources = parse(narrative) if enabled(before['world_state']) else []
            if handle.cancelled.is_set() or storage.get_job(job_id)['status'] != 'extracting':
                return
            if config.get('_narrative_recovery') and not job['context_json']:
                # A new, explicitly linked candidate uses corrected current canon.
                # No Narrative request; old context/hash belongs to the old branch.
                messages = build_context(before, history, job['user_text'], job['kind'], context,
                    config['max_tokens'], max_input=max_input, extraction_contract=version, recent_turns=config.get('recent_turns',6),
                    prompts=config.get('_prompts'), world_history=world_history)
                storage.save_context(job_id, messages, before)
            # Use exactly the policy supplied to this narrative, including retry /
            # regenerate's recorded context. Extraction cannot expand its budget.
            recorded_messages = json.loads(storage.get_job(job_id).get('context_json') or '[]')
            from backend.runtime_v3.pacing import recorded_policy
            narrative_policy = recorded_policy(recorded_messages, before['world_state'])
            from backend.runtime_v3.initiative import recorded_plan
            initiative_plan = recorded_plan(recorded_messages)
            from backend.runtime_v3.continuity import recorded as recorded_continuity, due_birth_repair_required
            continuity_plan = recorded_continuity(recorded_messages)
            corrected_boundary = any(g.get('kind') == 'birth_boundary'
                                     for g in config.get('_narrative_correction', {}).get('grounds', []))
            require_due_birth_assessment = corrected_boundary or due_birth_repair_required(json.loads(job.get('repair_diagnostics_json') or '[]'), before['world_state'])
            feedback = None
            previous_extraction = None
            if job['attempt_epoch'] and config.get('_extraction_contract', 1) < 6:
                from backend.runtime_v3.raw import RawTurnResult, repair_feedback
                # Retry reuses the latest failed proposal as feedback, never as
                # canonical truth or a union of mutually inconsistent attempts.
                latest_payload = None
                complete_payload = None
                for request in storage.request_log(job_id=job_id):
                    if request['stage'] not in ('extraction', 'extraction_repair') or not request.get('response_text'):
                        continue
                    if latest_payload is None:
                        latest_payload = request['response_text']
                    try:
                        previous_extraction = RawTurnResult.parse(request['response_text'])
                        complete_payload = request['response_text']
                    except StructuralDeltaError:
                        continue  # Keep the latest failure and find its complete predecessor.
                    break
                diagnostics = json.loads(job.get('repair_diagnostics_json') or '[]')
                if diagnostics and latest_payload is not None:
                    latest = diagnostics[-1]
                    feedback = repair_feedback([d for d in diagnostics if (d.get('attempt_epoch'), d.get('attempt')) == (latest.get('attempt_epoch'), latest.get('attempt'))], latest_payload, before['world_state'], previous_complete=complete_payload)
            from backend.runtime_v3.scene_repair import SceneCandidate
            semantic_candidate = SceneCandidate(before['world_state'], narrative, job['user_text'], sequence+1,
                version=version, suggestions=suggestions, on_record=lambda audit: storage.record_extraction_candidate(getattr(messages,'request_id',None),audit)) if 6 <= version < 10 else None
            config['update_tokens'] = extraction_output(config, estimate([{'content':narrative}]))
            for attempt in range(1 if version >= 10 else 2):
                if handle.cancelled.is_set() or storage.get_job(job_id)['status'] not in ('extracting', 'validating'):
                    return
                storage.job_progress(job_id, 'extracting')
                from llm import ProviderGenerationError
                from backend.services.provider_attempt import ResponseStreamError
                import requests
                provider_warning = None
                correction_grounds = []
                calendar_grounds = []
                stage_started=time.perf_counter()
                try:
                    messages = build_context(before, history, job['user_text'], job['kind'], context,
                                             extraction_reserve(config, config['update_tokens']), max_input=max_input, extraction_text=narrative, extraction_contract=config.get('_extraction_contract', 1),
                                             suggestions=suggestions, validation_feedback=feedback, pacing_decision=narrative_policy, initiative_decision=initiative_plan,continuity_decision=continuity_plan, recent_turns=config.get('recent_turns',6),prompts=config.get('_prompts'),world_history=world_history)
                    correction_grounds = config.get('_narrative_correction', {}).get('grounds', [])
                    calendar_grounds = [g for g in correction_grounds if g.get('kind') not in ('agency','birth','birth_boundary')]
                    if calendar_grounds:
                        ids = [dict(kind=g.get('kind', 'event_elapsed'), event_id=g.get('event_id'),
                                    reference_minute=g.get('current_minute')) for g in calendar_grounds]
                        messages.append({'role':'system', 'content':'Corrected candidate: recheck objective assertions for '
                            + json.dumps(ids) + ' in chronology_claims against the NEW prose; never omit or downgrade them.'})
                        if estimate(messages)>context-extraction_reserve(config, config['update_tokens'])-256:
                            raise ValueError('Контекст повторной проверки хронологии не помещается в выбранную модель.')
                    if legacy_letter_sources:
                        from backend.services.letter_sources import extraction_context
                        messages.append(extraction_context(legacy_letter_sources))
                        if estimate(messages)>context-extraction_reserve(config, config['update_tokens'])-256:
                            raise ValueError('Контекст восстановления старого письма не помещается в выбранную модель.')
                    stage_started=time.perf_counter()
                    result = ''.join(generate('extraction' if attempt==0 else 'extraction_repair',messages,config['update_tokens'],0.1,
                                              response_format={'type':'json_object'}))
                except (ProviderGenerationError, ResponseStreamError, requests.RequestException, ValueError) as failure:
                    if version < 10:
                        raise
                    result = '{}'
                    provider_warning = dict(section='extraction', code='extraction_unavailable',
                                            reason=type(failure).__name__, action='preserve_scene')
                timings['extraction' if attempt==0 else 'extraction_repair']=time.perf_counter()-stage_started
                if handle.cancelled.is_set():
                    return
                storage.job_progress(job_id, 'validating')
                stage_started=time.perf_counter()
                try:
                    from copy import deepcopy
                    from dataclasses import asdict
                    from backend.runtime_v3.raw import RawTurnResult, repair_feedback, repair_revision_warnings
                    from backend.runtime_v3.remote_semantics import staged_sources
                    from backend.runtime_v3.call_continuity import sources as call_sources
                    from backend.runtime_v3.player_actions import resolver_options
                    def resolve(raw):
                        if skip_result and version >= 11 and 'elapsed_minutes' not in raw.final_scene:
                            raw.warnings.append(dict(section='scene', code='skip_endpoint_unknown',
                                                     action='retain_clock', requested_target=skip_result['requested_target']))
                        elif skip_result:
                            skip = skip_result
                            if version >= 11:
                                skip = interpreted_skip(before['world_state'], skip_request, skip_result,
                                                        raw.final_scene.get('elapsed_minutes'))
                                if raw.final_scene.get('elapsed_minutes', skip['elapsed_minutes']) != skip['elapsed_minutes']:
                                    raw.warnings.append(dict(section='scene', code='end_time_after_skip_target', action='use_target'))
                            raw.final_scene['elapsed_minutes'] = skip['elapsed_minutes']
                        return StateResolver(
                            before['world_state'], narrative, job['user_text'], turn_id=sequence+1,
                            chronology_events=world_history.get('events', []),
                            require_due_birth_assessment=require_due_birth_assessment,
                            **resolver_options(before['world_state'], job['user_text'], job['kind'], version,
                                               time_skip=bool(skip_result)),
                            pacing_decision=getattr(messages,'selection',{}).get('pacing'),
                            initiative_decision=initiative_plan, continuity_decision=continuity_plan,
                            runtime_time_skip=bool(skip_result), milestone_query=world_history.get('_milestone_query'),
                            development_query=world_history.get('_development_query'),
                            relationship_query=relationship_reader(storage, before.get('history_head'),
                                candidates=remote_relationship_sources(before, staged_sources(before))),
                            actor_names={c['id']:c['name'] for c in before['character_cards']},
                            letter_sources=letter_sources, remote_semantic_sources=staged_sources(before),
                            call_sources=call_sources(before['world_state'],world_history,narrative,job['user_text'],sequence+1)
                        ).resolve(raw)
                    if version >= 10:
                        from backend.runtime_v3.consequences import resolve_consequences
                        raw, resolved = resolve_consequences(result,before['world_state'],narrative,sequence+1,suggestions,resolve, version=version, authored_scene=narrative_frame.scene_fields(frame or {}))
                        if provider_warning:
                            resolved.warnings.append(provider_warning)
                    else:
                        raw=semantic_candidate.parse(result, defer_errors=True) if semantic_candidate else RawTurnResult.parse(result)
                        for ground in correction_grounds:
                            if ground.get('kind') == 'birth' and not any(
                                isinstance(b,dict) and b.get('pregnancy_id') == ground['pregnancy_id'] for b in raw.records['births']
                            ):
                                raise StructuralDeltaError('Повторно проверьте рождение по исправленному тексту.',
                                                           'birth_recheck_missing', section='births')
                        if calendar_grounds:
                            from backend.runtime_v3.continuity import require_chronology_recheck
                            require_chronology_recheck(raw, calendar_grounds)
                        raw.warnings.extend(repair_revision_warnings(previous_extraction, raw))
                        previous_extraction = raw
                        resolved = resolve(raw)
                    if version < 10 and before['world_state']['meta'].get('interaction_focus')=='call':
                        rejected=[w for w in resolved.warnings if w.get('section')=='scheduled_events']
                        if rejected:
                            from backend.runtime_v3.models import fatal
                            fatal('Голосовая договорённость не прошла проверку.', 'call_commitment_rejected',repairable=True,diagnostics=rejected)
                    if version < 10 and staged_sources(before):
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
                    if version >= 11 and 'elapsed_minutes' not in raw.final_scene:
                        skip_result = None
                    if skip_result:
                        changes_skip=deepcopy(skip_result)
                        if version >= 11:
                            changes_skip = interpreted_skip(before['world_state'], skip_request, skip_result,
                                                           resolved.state['meta']['world_time'] - now)
                        state['last_time_skip']=changes_skip
                    from backend.services.npc_review import publish_cards
                    publish_cards(state, resolved)
                    choices=resolved.choices if job['kind']!='background' else []
                    if frame is not None:
                        choices, menu_warnings = narrative_frame.menu(frame, state['world_state'])
                    elif version >= 10 and narrative_frame.requested(recorded_messages):
                        menu_warnings = narrative_frame.menu_diagnostics(len(suggestions), len(choices))
                    else:
                        menu_warnings = []
                    changes={'time_skip':skip_result, 'raw_turn_result':asdict(raw), 'state_patch':asdict(resolved.patch)}
                    audience=list(resolved.state['camera']['present_character_ids'])
                    warnings=resolved.warnings
                    if version >= 10:
                        changes.update(interpretation='partial' if warnings else 'applied',
                                       interpretation_warnings=warnings)
                        if menu_warnings:
                            changes['menu_available'] = len(choices)
                            changes['interpretation_warnings'] = [*warnings,*menu_warnings]
                    history_batch=resolved.history
                    for section, records in state.pop('_remote_batch', {}).items():
                        history_batch.setdefault(section, [])[:0] = records
                    if warnings and version < 10:
                        with storage.connect() as db:
                            previous=json.loads(db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job_id,)).fetchone()[0] or '[]')
                            db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?', (json.dumps(previous+warnings,ensure_ascii=False),job_id))
                    break
                except StructuralDeltaError as exc:
                    if version >= 10:
                        storage.finish_interpretation(job_id, exc.code)
                        return
                    diagnostics=exc.diagnostics('extraction_repair' if attempt==0 and exc.repairable else 'validation_failed')
                    for diagnostic in diagnostics:
                        diagnostic.update(attempt=attempt,attempt_epoch=job['attempt_epoch'],revision=job['revision'])
                    storage.record_repair(job_id,diagnostics)
                    require_due_birth_assessment = require_due_birth_assessment or due_birth_repair_required(diagnostics, before['world_state'])
                    if attempt == 1 or not exc.repairable:raise
                    feedback = semantic_candidate.feedback(diagnostics, result) if semantic_candidate else repair_feedback(diagnostics, result, before['world_state'])
                finally:
                    timings['validation_apply']=timings.get('validation_apply',0)+time.perf_counter()-stage_started
            from backend.runtime_v3.simulation import simulate
            stage_started=time.perf_counter()
            background_warnings=[]
            state,history_batch=simulate(before,state,history_batch,context,config,generate,handle.cancelled,
                warnings=background_warnings,on_repair=lambda detail: storage.record_repair(job_id,detail),
                on_candidate=lambda messages,audit: storage.record_extraction_candidate(getattr(messages,'request_id',None),audit),
                world_history={'events':world_history.get('events',[]),'_relationship_query':world_history['_relationship_query'],'_milestone_query':world_history['_milestone_query'],'_development_query':world_history['_development_query']})
            if version >= 10 and background_warnings:
                changes['interpretation'] = 'partial'
                changes['interpretation_warnings'].extend(background_warnings)
            elif background_warnings:
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

            if not handle.cancelled.is_set():
                timings['total']=time.perf_counter()-job_started
                storage.commit_job(job_id, state, choices, changes, timing=timings, history_batch=history_batch, audience=audience)
                # Include the commit and variant snapshot in independently measured
                # wall-clock time; the provisional value covers an interrupted final write.
                storage.finalize_job_timing(job_id,time.perf_counter()-job_started)
    except Exception as exc:
        storage.job_progress(job_id, 'stopped' if handle.cancelled.is_set() else 'error',
                             narrative=narrative or None, complete=bool(timings.get('narrative') and narrative.strip()), error=str(exc))
    finally:
        if handle.cancelled.is_set() and narrative:
            with storage.connect() as db:
                db.execute("UPDATE game_jobs SET narrative=? WHERE id=? AND status='stopped' AND narrative_complete=0", (narrative, job_id))
        with REGISTRY_LOCK:
            if WORKERS.get(job_id) is handle: WORKERS.pop(job_id, None)
