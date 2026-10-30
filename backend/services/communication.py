"""Communication continuation inside the existing job/usage/variant pipeline."""
import json
from backend.runtime_v3.communication import run
from backend.runtime_v3.remote_decision import parse as parse_decision, VERSION
from backend.services.usage import tracked_stream
from context_builder import describe_context, estimate


def execute(storage, job, handle, chat_stream):
    config = json.loads(job["config_json"])
    before = json.loads(job["memory_before_json"] or job["before_json"])
    journal = json.loads(job["context_json"] or "[]")
    semantic = next((f for f in journal if f.get("stage") == "remote_semantics"), None)
    frames = [f for f in journal if f.get("stage") != "remote_semantics"]
    captured = []
    # Mark the durable command boundary retryable even if the provider fails
    # before returning any text. No fabricated player utterance is inserted.
    storage.job_progress(job["id"], "generating", complete=True)
    storage.save_communication_context(job["id"], frames, before)

    def generate(index, messages):
        # Keep actual outgoing prompts inside the selected context window. Trim
        # optional background Knowledge before the source message/path itself.
        budget = config['context_length'] - min(1200, config['update_tokens']) - 512
        data = json.loads(messages[1]['content'])
        while estimate(messages) > budget:
            actor = max(data['actors'], key=lambda a: len(a['knowledge']), default=None)
            if actor and actor['knowledge']:
                actor['knowledge'].pop()
            elif len(data['options'])>1:
                data['options'].pop()
                allowed={o['actor_id'] for o in data['options']}
                data['actors']=[a for a in data['actors'] if a['id'] in allowed]
            else:
                raise ValueError('Контекст связи не помещается в выбранное окно модели.')
            messages[1]['content'] = json.dumps(data,ensure_ascii=False)
        old = frames[index] if index < len(frames) else None
        reusable = False
        if old and "response" in old:
            try:
                proposal, diagnostic = parse_decision(old['response'])
                # Replay eligibility is not inferred from the existence of raw text.
                # Runtime validation is repeated by run against staged state.
                reusable = old.get('accepted') is not False
            except ValueError:
                reusable = False
        if old and not job["replaces_id"] and old.get("messages", [None,None])[1:] == messages[1:] and reusable:
            captured.append(old)
            return old["response"]  # Retry replays accepted work without another call.
        if index == 0 and old:
            messages = [messages[0], old["messages"][1]]  # Original source-bound context for regenerate.
        if estimate(messages)>budget:
            raise ValueError('Для исходного контекста связи нужно прежнее или большее окно модели.')
        def on_stream(stream):
            handle.stream = stream
            if handle.cancelled.is_set():
                stream.close()
        frame = dict(stage="communication", messages=messages, contract=VERSION)
        if old:
            frame["previous_attempt"] = old
        captured.append(frame)
        storage.save_communication_context(job["id"], captured, before)
        response = "".join(tracked_stream(
            storage, chat_stream, job["id"], "remote_initiative", config,
            messages, describe_context(messages), temperature=0.2,
            max_tokens=min(1200, config["update_tokens"]), model=config["model"],
            require_complete=True, cancel_event=handle.cancelled, on_stream=on_stream,
            provider=config.get("provider", "local"), api_key=handle.api_key,
            response_format={"type": "json_object"},
        ))
        frame["response"] = response
        storage.save_communication_context(job["id"], captured, before)
        return response

    def checkpoint(index, accepted, error=None):
        captured[index]['accepted'] = accepted
        captured[index]['validation_contract'] = VERSION
        if accepted:
            _, captured[index]['parser'] = parse_decision(captured[index]['response'])
        if error is not None:
            captured[index]['error'] = str(error)
            captured[index]['category'] = 'schema' if hasattr(error,'errors') else 'json' if isinstance(error,json.JSONDecodeError) else 'runtime'
            if hasattr(error,'errors'):
                captured[index]['validation_errors'] = json.loads(error.json(include_url=False))
        storage.save_communication_context(job['id'], captured, before)
    output = run(before, config["communication"], generate, handle.cancelled, checkpoint=checkpoint)
    if output is None or handle.cancelled.is_set():
        return
    after, batch, report = output
    from backend.runtime_v3.remote_semantics import messages as semantic_messages, resolve as semantic_resolve
    source=after['world_state']['remote_events'][report['source_event_id']]
    substantive = 'send' in report['accepted'] or source['operation_id']==config['communication']['request_id']
    prompts = semantic_messages(after, report['source_event_id']) if substantive else None
    if prompts:
        if estimate(prompts) > config['context_length'] - config['update_tokens'] - 512:
            raise ValueError('Контекст телефонных последствий не помещается в окно модели; сообщения сохранены.')
        frame = dict(stage='remote_semantics', messages=prompts, accepted=False)
        if semantic:
            frame['previous_attempt'] = semantic
        captured.append(frame)
        storage.save_communication_context(job['id'], captured, before)
        storage.job_progress(job['id'], 'extracting', complete=True)
        from backend.runtime_v3.remote_semantics import SemanticValidationError
        from backend.services.world_delta_errors import StructuralDeltaError
        def generate_semantics(stage, outgoing):
            if estimate(outgoing) > config['context_length'] - config['update_tokens'] - 512:
                raise ValueError('Контекст исправления договорённости не помещается в окно модели.')
            def on_semantic_stream(stream):
                handle.stream = stream
                if handle.cancelled.is_set(): stream.close()
            return ''.join(tracked_stream(storage, chat_stream, job['id'], stage, config,
                outgoing, describe_context(outgoing), temperature=0.1, max_tokens=config['update_tokens'],
                model=config['model'], require_complete=True, cancel_event=handle.cancelled,
                on_stream=on_semantic_stream, provider=config.get('provider','local'), api_key=handle.api_key,
                response_format={'type':'json_object'}))
        try:
            # A failed repair resumes from the accepted decision journal AND the
            # original semantic response, without another NPC or extraction call.
            if semantic and semantic.get('response') and (semantic.get('accepted') or semantic.get('validation_errors')) and semantic.get('messages') == prompts and not job['replaces_id']:
                response = semantic['response']
            else:
                response = generate_semantics('remote_semantics', prompts)
            frame['response'] = response
            storage.save_communication_context(job['id'], captured, before)
            if handle.cancelled.is_set(): return
            warnings=[]
            try:
                resolved, consequences = semantic_resolve(after, report['source_event_id'], response, warnings)
            except SemanticValidationError as rejection:
                # Exactly one source-bound correction per attempt, never an HTTP
                # retry and never a fresh communication decision or time advance.
                repair_data=json.loads(prompts[1]['content'])
                repair_data['repair']=dict(rejected_response=response, diagnostics=rejection.warnings,
                    required_candidate_ids=rejection.candidate_ids,
                    instruction='Return corrected JSON using ONLY the supplied accepted messages. Preserve every candidate ID and valid record; do not erase a rejected meeting to hide an error. Correct evidence identity/quotation, never invent consent. If evidence is insufficient leave the candidate invalid for explicit recovery.')
                repair=[prompts[0],dict(role='user',content=json.dumps(repair_data,ensure_ascii=False))]
                frame['repair_messages']=repair
                frame['validation_errors']=rejection.warnings
                storage.record_repair(job['id'],dict(stage='remote_semantics_repair',repair_error_code='remote_semantic_validation',
                    repair_error_type=type(rejection).__name__,repair_reason=str(rejection)))
                storage.save_communication_context(job['id'],captured,before)
                try:
                    repaired=generate_semantics('remote_semantics_repair',repair)
                except RuntimeError as repair_error:
                    if handle.cancelled.is_set(): return
                    # The accepted exchange is independent of this optional
                    # correction. Provider diagnostics remain in request logs.
                    frame['repair_failure_type'] = type(repair_error).__name__
                    repaired = None
                frame['repair_response']=repaired
                storage.save_communication_context(job['id'],captured,before)
                if handle.cancelled.is_set():return
                try:
                    if repaired is None:
                        raise SemanticValidationError([dict(section='scheduled_events', code='remote_semantic_repair_unavailable')], rejection.candidate_ids)
                    from backend.runtime_v3.raw import RawTurnResult
                    records=RawTurnResult.parse(repaired).records['scheduled_event_changes']
                    ids={r.get('id') for r in records if isinstance(r,dict) and isinstance(r.get('id'),str)}
                    original_records=RawTurnResult.parse(response).records['scheduled_event_changes']
                    if len(records)<len(original_records) or not set(rejection.candidate_ids)<=ids:
                        raise SemanticValidationError([dict(code='commitment_repair_omission',section='scheduled_events',action='reject_repair')],rejection.candidate_ids)
                    warnings=[]
                    resolved,consequences=semantic_resolve(after,report['source_event_id'],repaired,warnings)
                    frame['initial_response']=response
                    frame['response']=repaired
                except (SemanticValidationError, StructuralDeltaError) as unresolved:
                    if isinstance(unresolved, StructuralDeltaError) and not unresolved.code.startswith('raw_'):
                        raise
                    from backend.runtime_v3.remote_semantics import resolve_optional
                    frame['repair_validation_errors'] = unresolved.warnings if isinstance(unresolved, SemanticValidationError) else [unresolved.diagnostic('remote_semantics_repair')]
                    # An invalid repair has no accepted changes. Isolate the
                    # original candidates, preserving original valid records.
                    candidate = response
                    warnings = []
                    resolved, consequences = resolve_optional(after, report['source_event_id'], candidate, warnings)
                    frame['deferred'] = True
                    frame['response'] = candidate
            after=resolved
            for section, records in consequences.items(): batch[section].extend(records)
            frame['warnings']=warnings
            frame['accepted'] = True
        except Exception as exc:
            frame['error'] = str(exc)
            raise
        finally:
            storage.save_communication_context(job['id'], captured, before, frame.get('warnings'))

    batch["state_changes"].append(dict(kind="communication_receipt", request_id=config["communication"]["request_id"], job_id=job["id"]))
    labels = {"answered": "Собеседник ответил. Разговор доступен в сцене.", "declined": "Собеседник отклонил вызов.", "missed": "Вызов завершён без ответа."}
    text = labels.get(report["outcome"], "Обработка сообщения завершена. Переписка доступна в телефоне.")
    if prompts and frame.get('deferred'):
        text += ' Часть последствий не подтверждена проверкой; переписка сохранена, диагностика доступна в журнале.'
    if report.get('unavailable'):
        text = 'Собеседник сейчас недоступен для связи. Обработка завершена.'
    if report["rejected"]:
        text += " Решение связи отклонено проверкой; ответ не применён."
    storage.job_progress(job["id"], "validating", narrative=text, complete=True)
    storage.commit_job(job["id"], after, [], {"communication": report}, history_batch=batch)
