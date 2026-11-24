"""Communication continuation inside the existing job/usage/variant pipeline."""
import json
from backend.runtime_v3.communication import run
from backend.runtime_v3.remote_decision import parse as parse_decision, VERSION, LEGACY_VERSION
from backend.services.usage import tracked_stream
from context_builder import describe_context, estimate


def execute(storage, job, handle, chat_stream, config):
    before = json.loads(job["memory_before_json"] or job["before_json"])
    journal = json.loads(job["context_json"] or "[]")
    # Pre-stage journals contain decision frames without a stage tag. Normalize
    # metadata only; replay still validates the original response and context.
    original_journal = journal
    captured = []
    # Mark the durable command boundary retryable even if the provider fails
    # before returning any text. No fabricated player utterance is inserted.
    storage.job_progress(job["id"], "generating", complete=True)
    storage.save_communication_context(job["id"], original_journal, before)

    # Keep untouched frames for later recipients/stages until their replacements
    # are durable. A second interruption during replay must not erase that work.
    remaining = list(original_journal)
    def persist(warnings=None):
        storage.save_communication_context(job["id"], captured + remaining, before, warnings)

    def consume(old):
        if old is not None:
            remaining[:] = [f for f in remaining if f is not old]

    def generate(index, messages):
        # Keep actual outgoing prompts inside the selected context window. Trim
        # optional background Knowledge before the source message/path itself.
        group_reaction = messages[0]['content'].startswith('Group communication reaction/')
        limit = min(2400 if group_reaction else 1200, config['update_tokens'])
        budget = min(config['context_length'] - limit, config.get('_budget_caps', {}).get('max_input') or config['context_length']) - 512
        data = json.loads(messages[1]['content'])
        while estimate(messages) > budget:
            if group_reaction:
                raise ValueError('Контекст групповой реакции не помещается в окно модели.')
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
        consume(old)
        reusable = False
        if old and "response" in old:
            try:
                parse_frame(old, group_reaction)
                # Replay eligibility is not inferred from the existence of raw text.
                # Runtime validation is repeated by run against staged state.
                reusable = old.get('accepted') is not False
            except ValueError:
                reusable = False
        from backend.runtime_v3.group_planning import same_reaction_context
        same_context = (same_reaction_context(old.get('messages', []), messages) if group_reaction
                        else old.get('messages', [None,None])[1:] == messages[1:]) if old else False
        if old and reusable and not same_context:
            from backend.runtime_v3.remote_authoring import pre_style_context
            previous = pre_style_context(messages, before, group=group_reaction)
            same_context = (same_reaction_context(old.get('messages', []), previous) if group_reaction
                            else old.get('messages', [None,None])[1:] == previous[1:])
        if old and not job["replaces_id"] and same_context and reusable:
            old.setdefault("stage", "communication")
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
        frame = dict(stage="communication", messages=messages, contract=VERSION, group_reaction=group_reaction, source_event_id=source_id)
        if old:
            frame["previous_attempt"] = old
        captured.append(frame)
        persist()
        response = "".join(tracked_stream(
            storage, chat_stream, job["id"], "remote_initiative", config,
            messages, describe_context(messages), temperature=0.2,
            max_tokens=limit, model=config["model"],
            require_complete=True, cancel_event=handle.cancelled, on_stream=on_stream,
            provider=config.get("provider", "local"), api_key=handle.api_key,
            response_format={"type": "json_object"},
        ))
        frame["response"] = response
        persist()
        return response

    def decision_scope(frame):
        # An index addresses the paths actually shown, even after trimming or
        # regeneration. accept() independently rechecks the canonical route.
        return dict(options=json.loads(frame['messages'][1]['content'])['options'],
                    contract=frame.get('contract', LEGACY_VERSION))

    def parse_frame(frame, group_reaction):
        response = frame['response']
        if group_reaction:
            from backend.runtime_v3.group_planning import GroupReaction
            from backend.runtime_v3.remote_decision import decode
            GroupReaction.model_validate(decode(response))
            return dict(contract='group-reaction/1')
        return parse_decision(response, **decision_scope(frame))[1]

    def checkpoint(index, accepted, error=None):
        frame = [f for f in captured[offset:] if f['stage'] == 'communication'][index]
        frame['accepted'] = accepted
        frame['validation_contract'] = frame.get('contract', LEGACY_VERSION)
        if accepted:
            frame['parser'] = parse_frame(frame, frame.get('group_reaction'))
        if error is not None:
            frame['error'] = str(error)
            frame['category'] = 'schema' if hasattr(error,'errors') else 'json' if isinstance(error,json.JSONDecodeError) else 'runtime'
            if hasattr(error,'errors'):
                frame['validation_errors'] = json.loads(error.json(include_url=False))
        persist()
    def extract(after, source_id, batch, stage='remote_semantics'):
        from backend.runtime_v3.remote_semantics import messages as semantic_messages, resolve as semantic_resolve, same_extraction_context
        prompts = semantic_messages(after, source_id, response_only=stage=='remote_response_semantics')
        from backend.runtime_v3.remote_semantics import relationship_sources, evidence_slice
        from backend.runtime_v3.repository import relationship_reader
        resolver_options = dict(relationship_query=relationship_reader(storage, before.get('history_head'),
            candidates=relationship_sources(after, {e['id'] for e in evidence_slice(after['world_state'], source_id)})), relationship_receipts=batch.get('relationship_changes', []))
        if not prompts:
            return after
        semantic = next((f for f in journal if f.get('stage') == stage), None)
        consume(semantic)
        semantic_limit = min(1200, config['update_tokens']) if stage=='remote_response_semantics' else config['update_tokens']
        current_policy = config.get('_extraction_contract',1) >= 10
        if estimate(prompts) > config['context_length'] - semantic_limit - 512:
            if current_policy:
                warning = dict(section=stage,code='extraction_context_limit',action='preserve_exchange')
                captured.append(dict(stage=stage,accepted=False,deferred=True,warnings=[warning]))
                persist([warning])
                return after
            raise ValueError('Контекст телефонных последствий не помещается в окно модели; сообщения сохранены.')
        frame = dict(stage=stage, messages=prompts, accepted=False, source_event_id=source_id)
        if semantic:
            frame['previous_attempt'] = semantic
        captured.append(frame)
        persist()
        storage.job_progress(job['id'], 'extracting', complete=True)
        from backend.runtime_v3.remote_semantics import SemanticValidationError
        from backend.services.world_delta_errors import StructuralDeltaError
        def generate_semantics(stage, outgoing):
            if estimate(outgoing) > config['context_length'] - semantic_limit - 512:
                raise ValueError('Контекст исправления договорённости не помещается в окно модели.')
            def on_semantic_stream(stream):
                handle.stream = stream
                if handle.cancelled.is_set(): stream.close()
            return ''.join(tracked_stream(storage, chat_stream, job['id'], stage, config,
                outgoing, describe_context(outgoing), temperature=0.1, max_tokens=semantic_limit,
                model=config['model'], require_complete=True, cancel_event=handle.cancelled,
                on_stream=on_semantic_stream, provider=config.get('provider','local'), api_key=handle.api_key,
                response_format={'type':'json_object'}))
        try:
            # A failed repair resumes from the accepted decision journal AND the
            # original semantic response, without another NPC or extraction call.
            if semantic and semantic.get('response') and (semantic.get('accepted') or semantic.get('validation_errors')) and same_extraction_context(semantic.get('messages'), prompts, response_only=stage=='remote_response_semantics') and not job['replaces_id']:
                response = semantic['response']
            else:
                response = generate_semantics(stage, prompts)
            frame['response'] = response
            persist()
            if handle.cancelled.is_set(): return
            if stage=='remote_response_semantics':
                from backend.runtime_v3.raw import RawTurnResult
                parsed=RawTurnResult.parse(response)
                if any(v for k,v in parsed.records.items() if k!='group_response_changes'):
                    raise ValueError('Извлечение ответа содержит последствия вне текущей фазы.')
            warnings=[]
            try:
                if current_policy:
                    from backend.runtime_v3.remote_semantics import resolve_optional
                    resolved, consequences = resolve_optional(after, source_id, response, warnings, **resolver_options)
                else:
                    resolved, consequences = semantic_resolve(after, source_id, response, warnings, **resolver_options)
            except SemanticValidationError as rejection:
                if current_policy:
                    raise
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
                persist()
                try:
                    repaired=generate_semantics('remote_semantics_repair',repair)
                except RuntimeError as repair_error:
                    if handle.cancelled.is_set(): return
                    # The accepted exchange is independent of this optional
                    # correction. Provider diagnostics remain in request logs.
                    frame['repair_failure_type'] = type(repair_error).__name__
                    repaired = None
                frame['repair_response']=repaired
                persist()
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
                    resolved,consequences=semantic_resolve(after,source_id,repaired,warnings, **resolver_options)
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
                    resolved, consequences = resolve_optional(after, source_id, candidate, warnings, **resolver_options)
                    frame['deferred'] = True
                    frame['response'] = candidate
            after=resolved
            for section, records in consequences.items(): batch[section].extend(records)
            frame['warnings']=warnings
            frame['accepted'] = True
        except Exception as exc:
            from llm import ProviderGenerationError
            from backend.services.provider_attempt import ResponseStreamError
            if current_policy and isinstance(exc,(ValueError, ProviderGenerationError, ResponseStreamError)):
                frame.update(deferred=True,warnings=[dict(section=stage,code='remote_extraction_deferred',
                    reason=type(exc).__name__,action='preserve_exchange')])
            else:
                frame['error'] = str(exc)
                raise
        finally:
            persist(frame.get('warnings'))
        return after

    def resolve_source(after, source_id, batch):
        return extract(after, source_id, batch, 'remote_response_semantics')

    from backend.runtime_v3.models import WorldHistoryV3
    requests = [config["communication"], *config.get("_additional_invitations", [])]
    first_source = requests[0]["source_event_id"]
    after = before
    batch = WorldHistoryV3().to_dict()
    reports = []
    # Invitations use ordinary independent direct exchanges. A retry addresses
    # each recipient's own journal, even when an earlier one chose silence.
    for request in requests:
        source_id = request["source_event_id"]
        journal = [f for f in original_journal if f.get("source_event_id",first_source)==source_id]
        frames = [f for f in journal if f.get("stage","communication")=="communication"]
        offset = len(captured)
        output = run(after, request, generate, handle.cancelled, checkpoint=checkpoint, resolve_source=resolve_source,
            decision_scope=lambda index: decision_scope(captured[offset+index]),
            legacy_group=bool(frames and not frames[0].get('group_reaction')))
        if output is None or handle.cancelled.is_set():
            return
        after, delta, report = output
        source = after['world_state']['remote_events'][source_id]
        if 'send' in report['accepted'] or source['operation_id']==request['request_id']:
            after = extract(after,source_id,delta)
            if after is None or handle.cancelled.is_set():
                return
        for section, rows in delta.items():
            batch[section].extend(rows)
        batch["state_changes"].append(dict(kind="communication_receipt",request_id=request["request_id"],job_id=job["id"]))
        reports.append(report)
    report = reports[0]
    if len(reports)>1:
        report = dict(report, additional_exchanges=reports[1:])
    # Consume the source and its accepted consequences together. Pacing is a
    # snapshot value, so retry/rollback/variants retain the same boundary.
    group = after['world_state']['conversations'].get(source['conversation_id'])
    if group and group['group'] and group.get('initiative_pacing'):
        from backend.runtime_v3.group_planning import stimulus, history_cues
        if not before['world_state']['conversations'][group['id']].get('initiative_pacing'):
            from backend.runtime_v3.repository import read_history
            with storage.connect() as db:
                prior_history, _ = read_history(db, before.get('history_head'))
            group['initiative_pacing']['event_ids'] = [e['id'] for e in history_cues(after['world_state'], group, prior_history['events'])]
        group['initiative_pacing']['stimulus'] = stimulus(after['world_state'], group)
        from copy import deepcopy
        for change in batch['state_changes']:
            if change.get('kind')=='group_initiative_attempt' and change.get('entity')==group['id']:
                change['after']=deepcopy(group)

    labels = {"answered": "Собеседник ответил. Разговор доступен в сцене.", "declined": "Собеседник отклонил вызов.", "missed": "Вызов завершён без ответа."}
    text = labels.get(report["outcome"], "Обработка сообщения завершена. Переписка доступна в телефоне.")
    if any(f.get('deferred') for f in captured):
        text += ' Часть последствий не подтверждена проверкой; переписка сохранена, диагностика доступна в журнале.'
    if report.get('unavailable'):
        text = 'Собеседник сейчас недоступен для связи. Обработка завершена.'
    if report["rejected"]:
        text += " Решение связи отклонено проверкой; ответ не применён."
    storage.job_progress(job["id"], "validating", narrative=text, complete=True)
    storage.commit_job(job["id"], after, [], {"communication": report}, history_batch=batch)
