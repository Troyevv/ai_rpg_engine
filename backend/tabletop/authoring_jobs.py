"""Persistent authoring checkpoints; credentials never enter a job record."""

import json
import threading
from contextlib import contextmanager
from uuid import uuid4

_LOCKS = {}
_GUARD = threading.Lock()


class AuthoringJobs:
    def __init__(self, repo):
        self.repo = repo
        with repo.connect() as db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS tabletop_authoring_jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,request TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL DEFAULT "",outputs TEXT NOT NULL DEFAULT "{}",issues TEXT NOT NULL DEFAULT "[]",result TEXT)'
            )

    def get(self, id):
        with self.repo.connect() as db:
            r = db.execute(
                "SELECT * FROM tabletop_authoring_jobs WHERE id=?", (id,)
            ).fetchone()
        if not r:
            raise ValueError("Задача генерации не найдена")
        return {
            **dict(r),
            "request": json.loads(r["request"]),
            "outputs": json.loads(r["outputs"]),
            "issues": json.loads(r["issues"]),
            "result": json.loads(r["result"]) if r["result"] else None,
        }

    def public(self, id):
        data = self.get(id)
        data["completed_stages"] = [
            k for k in data.pop("outputs") if not k.startswith("_")
        ]
        return data

    @contextmanager
    def run(self, id, kind, request):
        id = id or uuid4().hex
        with _GUARD:
            lock = _LOCKS.setdefault((str(self.repo.path), id), threading.Lock())
        if not lock.acquire(False):
            raise ValueError("Генерация уже выполняется")
        try:
            with self.repo.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO tabletop_authoring_jobs(id,kind,request,status) VALUES(?,?,?,?)",
                    (id, kind, json.dumps(request, ensure_ascii=False), "READY"),
                )
            job = self.get(id)
            if job["kind"] != kind or job["request"] != request:
                raise ValueError("Для изменённого запроса начни новую генерацию")
            checkpoint = Checkpoint(self, id)
            if job["status"] != "COMPLETE":
                checkpoint.update(status="RUNNING", issues=[])
            try:
                yield checkpoint
            except Exception as exc:
                checkpoint.update(
                    status="FAILED",
                    issues=[i.model_dump() for i in getattr(exc, "issues", [])],
                )
                raise
        finally:
            lock.release()


class Checkpoint:
    def __init__(self, jobs, id):
        self.jobs = jobs
        self.id = id

    def update(self, **values):
        allowed = {"status", "stage", "outputs", "issues", "result"}
        if not set(values) <= allowed:
            raise ValueError("Неизвестное поле checkpoint")
        with self.jobs.repo.connect() as db:
            db.execute(
                "UPDATE tabletop_authoring_jobs SET "
                + ",".join(key + "=?" for key in values)
                + " WHERE id=?",
                tuple(
                    (
                        json.dumps(v, ensure_ascii=False)
                        if key in {"outputs", "issues", "result"}
                        else v
                    )
                    for key, v in values.items()
                )
                + (self.id,),
            )

    def cached(self, stage):
        return self.jobs.get(self.id)["outputs"].get(stage)

    def progress(self, stage):
        self.update(stage=stage)

    def save(self, stage, value):
        outputs = self.jobs.get(self.id)["outputs"]
        outputs[stage] = value
        self.update(outputs=outputs, issues=[])

    def complete(self, result):
        self.update(status="COMPLETE", result=result)

    @property
    def result(self):
        return self.jobs.get(self.id)["result"]
