"""Reusable versioned worlds; games keep immutable snapshots of their content."""

import json
from .content_registry import SettingValidator


class SettingRepository:
    def __init__(self, repository):
        self.repository = repository
        with repository.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tabletop_world_definitions(
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS tabletop_world_versions(
                    id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(id,revision));
            """)

    def list(self):
        with self.repository.connect() as db:
            return [
                dict(
                    id=r["id"],
                    revision=r["revision"],
                    status=r["status"],
                    name=json.loads(r["payload"])["name"],
                )
                for r in db.execute(
                    "SELECT * FROM tabletop_world_definitions ORDER BY updated_at DESC,rowid DESC"
                )
            ]

    def get(self, id, revision=None):
        with self.repository.connect() as db:
            if revision is None:
                r = db.execute(
                    "SELECT * FROM tabletop_world_definitions WHERE id=?", (id,)
                ).fetchone()
            else:
                r = db.execute(
                    "SELECT *,'SAVED' AS status FROM tabletop_world_versions WHERE id=? AND revision=?",
                    (id, revision),
                ).fetchone()
        if not r:
            raise ValueError("Мир не найден")
        return dict(
            id=r["id"],
            revision=r["revision"],
            status=r["status"],
            definition=json.loads(r["payload"]),
        )

    def save(self, value, expected_revision=None, confirm=False):
        setting = SettingValidator().validate(value)
        with self.repository.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT revision FROM tabletop_world_definitions WHERE id=?",
                (setting.id,),
            ).fetchone()
            if old and expected_revision != old["revision"]:
                raise ValueError("Мир изменился. Обнови редактор.")
            if not old and expected_revision is not None:
                raise ValueError("Мир не найден")
            setting.revision = old["revision"] + 1 if old else 0
            payload = setting.model_dump_json()
            db.execute(
                "INSERT INTO tabletop_world_definitions(id,revision,status,payload) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,status=excluded.status,payload=excluded.payload,updated_at=CURRENT_TIMESTAMP",
                (
                    setting.id,
                    setting.revision,
                    "CONFIRMED" if confirm else "DRAFT",
                    payload,
                ),
            )
            db.execute(
                "INSERT INTO tabletop_world_versions VALUES(?,?,?)",
                (setting.id, setting.revision, payload),
            )
        return self.get(setting.id)
