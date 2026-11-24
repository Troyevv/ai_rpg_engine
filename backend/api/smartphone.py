from fastapi import Query
from backend.api.schemas import Credential, ModelConfig, Revision
from backend.repositories.smartphone import apply_command
from backend.runtime_v3.smartphone import access, activity, dating_view, social_view, subject
from backend.runtime_v3.smartphone_models import AppCommand
import engine


class Control(Revision):
    command: AppCommand


class Dispatch(Credential):
    revision: int
    command: AppCommand
    config: ModelConfig


def install(app, repo, credentials, job):
    base = "/api/saves/{sid}/apps"

    @app.get(base + "/social")
    def social(
        sid: int,
        profile: str | None = None,
        post: str | None = None,
        cursor: str | None = None,
        limit: int = Query(20, ge=1, le=50),
    ):
        before = tuple(map(int, cursor.split(","))) if cursor else None
        if before and len(before) != 2:
            raise ValueError("Некорректная страница.")
        return social_view(repo.get_snapshot(sid), profile=profile, post=post, before=before, limit=limit)

    @app.get(base + "/social/notifications")
    def notifications(sid: int):
        snap = repo.get_snapshot(sid)
        state = snap["world_state"]
        actor = access(snap, "social")
        return [
            dict(
                subject=subject(snap, r["author"]),
                kind=r.get("kind", "comment"),
                post_id=r.get("post_id") or r.get("target") or r["id"],
                sequence=r["sequence"],
            )
            for r in sorted(activity(state, actor), key=lambda r: -r["sequence"])
            if r.get("post_id") or r.get("kind")
        ][:30]

    @app.get(base + "/dating")
    def dating(sid: int):
        return dating_view(repo.get_snapshot(sid))

    from backend.runtime_v3.phone_listings import view
    from typing import Literal

    @app.get(base + "/{app_id}")
    def listing(sid: int, app_id: Literal["news", "questions", "events", "work"],
                item: str | None = None, tab: str = "", profile: str | None = None,
                query: str = "", category: str = "", place: str = "", kind: str = "", date: str = "",
                cursor: str | None = None, limit: int = Query(20, ge=1, le=50)):
        before = tuple(map(int, cursor.split(","))) if cursor else None
        if before and len(before) != 2:
            raise ValueError("Некорректная страница.")
        return view(repo.get_snapshot(sid), app_id, item=item, tab=tab, profile=profile, query=query,
                    category=category, place=place, kind=kind, date=date, cursor=before, limit=limit)

    @app.post(base + "/command")
    def control(sid: int, body: Control):
        with repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            apply_command(repo, db, sid, body.revision, body.command)
        return repo.get_save(sid)

    @app.post(base + "/dispatch")
    def dispatch(sid: int, body: Dispatch):
        settings = dict(
            body.config.model_dump(), smartphone=body.command.model_dump(), expected_revision=body.revision
        )
        jid = engine.submit(
            repo,
            sid,
            "",
            "smartphone",
            settings,
            api_key=credentials.resolve(body.config.provider, body.key()),
        )
        return dict(job=job(jid), save=repo.get_save(sid))
