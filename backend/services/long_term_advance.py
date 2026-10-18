"""Existing job/variant transaction and provider accounting for Long-term Advance."""

import json
from backend.runtime_v3.long_term import run
from backend.runtime_v3.calendar import calendar_label
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.milestones import reader
from backend.runtime_v3.personality import history_reader
from backend.services.usage import tracked_stream
from context_builder import describe_context


def execute(storage, job, handle, chat_stream):
    config = json.loads(job["config_json"])
    before = json.loads(job["memory_before_json"] or job["before_json"])
    with storage.connect() as db:
        history, _ = read_history(db, before.get("history_head"))
    history["_milestone_query"] = reader(storage, before.get("history_head"))
    history["_development_query"] = history_reader(storage, before.get("history_head"))
    from backend.runtime_v3.repository import advance_receipt_reader

    history["_advance_receipts"] = advance_receipt_reader(
        storage, before.get("history_head")
    )
    frames = json.loads(job["context_json"]) if job["context_json"] else []
    captured = []

    def generate(stage, messages, limit, temperature, *, context_key, **extra):
        if frames and stage == "long_term_narrative":
            frame = next(
                (
                    f
                    for f in frames
                    if f["stage"] == stage and f.get("context_key") == context_key
                ),
                None,
            )
            if frame is None:
                raise ValueError(
                    "Сохранённый контекст длительного перехода не соответствует группе."
                )
            messages[:] = frame["messages"]
            messages.selection = frame["selection"]
        captured.append(
            dict(
                stage=stage,
                context_key=context_key,
                messages=list(messages),
                selection=getattr(messages, "selection", {}),
            )
        )

        def on_stream(stream):
            handle.stream = stream
            if handle.cancelled.is_set():
                stream.close()

        return tracked_stream(
            storage,
            chat_stream,
            job["id"],
            stage,
            config,
            messages,
            describe_context(messages),
            temperature=temperature,
            max_tokens=limit,
            model=config["model"],
            require_complete=True,
            cancel_event=handle.cancelled,
            on_stream=on_stream,
            provider=config.get("provider", "local"),
            api_key=handle.api_key,
            **extra,
        )

    output = run(
        before,
        config["long_term_advance"],
        generate=generate,
        config=config,
        history=history,
        cancelled=handle.cancelled,
    )
    if output is None:
        return
    after, batch, report = output
    # Zero-budget jobs still have a recorded request/before boundary for regenerate.
    storage.save_context(job["id"], captured, before)
    text = "Длительный переход: " + calendar_label(after["world_state"])
    if report["interruption"]:
        text += "\nПереход прерван: требуется решение игрока."
    text += f"\nРазрешено групп: {len(report['accepted'])}. Нерешённых причин: {len(report['unresolved'])}."
    storage.job_progress(job["id"], "validating", narrative=text, complete=True)
    if not handle.cancelled.is_set():
        storage.commit_job(
            job["id"], after, [], {"long_term_advance": report}, history_batch=batch
        )
