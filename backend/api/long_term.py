"""Explicit long interval API; ordinary <=7-day turns are unchanged."""

from dataclasses import asdict
from backend.api.schemas import Credential, ModelConfig
from backend.runtime_v3.long_term import AdvanceRequest, plan
from backend.runtime_v3.calendar import calendar_label
from pydantic import Field
import engine


class Advance(Credential):
    revision: int = Field(ge=0)
    request: AdvanceRequest
    config: ModelConfig


def install(app, repo, credentials, public_job):
    @app.post("/api/saves/{sid}/long-term/preview")
    def preview(sid: int, body: AdvanceRequest):
        saved = repo.get_save(sid)
        snapshot = repo.get_snapshot(sid)
        if snapshot.get("mode") == "tabletop" or snapshot.get("runtime") == "tabletop":
            raise ValueError("Длительный переход доступен только в Narrative.")
        from backend.runtime_v3.repository import advance_receipt_reader
        from backend.runtime_v3.milestones import reader

        p = plan(
            snapshot,
            body,
            {
                "_advance_receipts": advance_receipt_reader(
                    repo, snapshot.get("history_head")
                ),
                "_milestone_query": reader(repo, snapshot.get("history_head")),
            },
        )
        return dict(
            revision=saved["revision"],
            requested_target=p.requested_target,
            actual_target=p.actual_target,
            label=calendar_label(snapshot["world_state"], p.actual_target),
            interruption=p.interruption,
            candidate_count=len(p.candidates),
            decisions=[asdict(c) for c in p.candidates if c.requires_player],
        )

    @app.post("/api/saves/{sid}/long-term")
    def start(sid: int, body: Advance):
        settings = dict(
            body.config.model_dump(),
            expected_revision=body.revision,
            long_term_advance=body.request.model_dump(),
        )
        jid = engine.submit(
            repo,
            sid,
            "",
            "long_term",
            settings,
            api_key=credentials.resolve(body.config.provider, body.key()),
        )
        return public_job(jid)
