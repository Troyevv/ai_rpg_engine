"""Communication continuation inside the existing job/usage/variant pipeline."""
import json
from backend.runtime_v3.communication import run
from backend.services.usage import tracked_stream
from context_builder import describe_context, estimate


def execute(storage, job, handle, chat_stream):
    config = json.loads(job["config_json"])
    before = json.loads(job["memory_before_json"] or job["before_json"])
    frames = json.loads(job["context_json"] or "[]")
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
        if old and not job["replaces_id"] and old.get("messages") == messages and "response" in old:
            captured.append(old)
            return old["response"]  # Retry replays accepted work without another call.
        if index == 0 and old:
            messages = old["messages"]  # Original source-bound context for regenerate.
        if estimate(messages)>budget:
            raise ValueError('Для исходного контекста связи нужно прежнее или большее окно модели.')
        def on_stream(stream):
            handle.stream = stream
            if handle.cancelled.is_set():
                stream.close()
        frame = dict(stage="communication", messages=messages)
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

    output = run(before, config["communication"], generate, handle.cancelled)
    if output is None or handle.cancelled.is_set():
        return
    after, batch, report = output
    batch["state_changes"].append(dict(kind="communication_receipt", request_id=config["communication"]["request_id"], job_id=job["id"]))
    labels = {"answered": "Собеседник ответил. Разговор доступен в сцене.", "declined": "Собеседник отклонил вызов.", "missed": "Вызов завершён без ответа."}
    text = labels.get(report["outcome"], "Обработка сообщения завершена. Переписка доступна в телефоне.")
    if report.get('unavailable'):
        text = 'Собеседник сейчас недоступен для связи. Обработка завершена.'
    if report["rejected"]:
        text += " Решение связи отклонено проверкой; ответ не применён."
    storage.job_progress(job["id"], "validating", narrative=text, complete=True)
    storage.commit_job(job["id"], after, [], {"communication": report}, history_batch=batch)
