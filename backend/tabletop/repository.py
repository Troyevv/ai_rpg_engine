"""Independent SQLite tables, CAS revisions, idempotency and snapshot replay.

Current state is never reconstructed from history during ordinary load/play.
No provider credentials or hidden snapshots are exposed by HTTP.
"""

from contextlib import contextmanager
import hashlib
import json
import sqlite3
from uuid import uuid4
from .models import GameState
from .migrations import migrate


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class TabletopRepository:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tabletop_settings(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tabletop_games(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                  revision INTEGER NOT NULL, state_json TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS tabletop_history(game_id TEXT NOT NULL REFERENCES tabletop_games(id),
                  revision INTEGER NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                  before_json TEXT NOT NULL, before_hash TEXT NOT NULL, after_json TEXT NOT NULL, after_hash TEXT NOT NULL,
                  events_json TEXT NOT NULL, user_text TEXT NOT NULL, narrative TEXT NOT NULL DEFAULT '',
                  PRIMARY KEY(game_id,revision), UNIQUE(game_id,request_id));
                CREATE TABLE IF NOT EXISTS tabletop_drafts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0,
                  definition_json TEXT NOT NULL, source TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tabletop_migrations(game_id TEXT PRIMARY KEY, original_json TEXT NOT NULL, target_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS tabletop_requests(id TEXT PRIMARY KEY, game_id TEXT NOT NULL,
                  stage TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, state):
        gid = uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO tabletop_settings VALUES(?,?) ON CONFLICT(id) DO NOTHING",
                (state.world.id, state.world.model_dump_json()),
            )
            db.execute(
                "INSERT INTO tabletop_games(id,name,revision,state_json) VALUES(?,?,0,?)",
                (gid, state.campaign.name, state.model_dump_json()),
            )
        return gid

    def list_games(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,name,revision,updated_at FROM tabletop_games ORDER BY updated_at DESC,rowid DESC"
                )
            ]

    def load(self, gid):
        with self.connect() as db:
            r = db.execute("SELECT * FROM tabletop_games WHERE id=?", (gid,)).fetchone()
        if not r:
            raise ValueError("Кампания не найдена")
        state = migrate(json.loads(r["state_json"]))
        if json.loads(r["state_json"]).get("schema_version") != state.schema_version:
            retry = False
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT state_json,revision FROM tabletop_games WHERE id=?", (gid,)
                ).fetchone()
                if (
                    current["revision"] != r["revision"]
                    or current["state_json"] != r["state_json"]
                ):
                    retry = True
                else:
                    db.execute(
                        "INSERT OR IGNORE INTO tabletop_migrations VALUES(?,?,?)",
                        (gid, r["state_json"], state.schema_version),
                    )
                    db.execute(
                        "UPDATE tabletop_games SET state_json=? WHERE id=?",
                        (state.model_dump_json(), gid),
                    )
            if retry:
                return self.load(gid)
        return r["revision"], state

    def duplicate(self, gid, request_id, fingerprint):
        with self.connect() as db:
            row = db.execute(
                "SELECT fingerprint FROM tabletop_history WHERE game_id=? AND request_id=?",
                (gid, request_id),
            ).fetchone()
        if row and row["fingerprint"] != fingerprint:
            raise ValueError("ID запроса уже использован для другого действия")
        return bool(row)

    def commit(self, gid, revision, request_id, fingerprint, state, events, user_text):
        payload = dump(state.model_dump())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute(
                "SELECT fingerprint FROM tabletop_history WHERE game_id=? AND request_id=?",
                (gid, request_id),
            ).fetchone()
            if duplicate:
                if duplicate[0] != fingerprint:
                    raise ValueError("ID запроса уже использован")
                return False
            old = db.execute(
                "SELECT state_json,revision FROM tabletop_games WHERE id=?", (gid,)
            ).fetchone()
            if not old or old["revision"] != revision:
                raise ValueError("Кампания изменилась. Обнови экран.")
            db.execute(
                "INSERT INTO tabletop_history(game_id,revision,request_id,fingerprint,before_json,before_hash,after_json,after_hash,events_json,user_text) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    gid,
                    revision + 1,
                    request_id,
                    fingerprint,
                    old["state_json"],
                    digest(old["state_json"]),
                    payload,
                    digest(payload),
                    dump(events),
                    user_text,
                ),
            )
            db.execute(
                "UPDATE tabletop_games SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (payload, gid),
            )
        return True

    def annotate(self, gid, revision, narrative):
        # Narrative can never change mechanical state. No stale text on newer rows.
        with self.connect() as db:
            db.execute(
                "UPDATE tabletop_history SET narrative=? WHERE game_id=? AND revision=?",
                (narrative, gid, revision),
            )

    def history(self, gid):
        with self.connect() as db:
            rows = db.execute(
                "SELECT revision,user_text,narrative,events_json FROM tabletop_history WHERE game_id=? ORDER BY revision DESC LIMIT 100",
                (gid,),
            ).fetchall()
        result = []
        for r in reversed(rows):
            try:
                events = json.loads(r["events_json"])
                if not isinstance(events, list):
                    raise ValueError()
            except (ValueError, TypeError):
                events = [
                    {"text": "Повреждена запись журнала. Текущее состояние сохранено."}
                ]
            result.append(
                {
                    "revision": r["revision"],
                    "user_text": r["user_text"],
                    "narrative": r["narrative"],
                    "events": events,
                }
            )
        return result

    def replay(self, gid, revision):
        with self.connect() as db:
            r = db.execute(
                "SELECT after_json,after_hash FROM tabletop_history WHERE game_id=? AND revision=?",
                (gid, revision),
            ).fetchone()
        if not r or digest(r["after_json"]) != r["after_hash"]:
            raise ValueError("Снимок истории недоступен или повреждён")
        return migrate(json.loads(r["after_json"]))

    def before_last(self, gid, revision):
        with self.connect() as db:
            r = db.execute(
                "SELECT before_json,before_hash FROM tabletop_history WHERE game_id=? AND revision=?",
                (gid, revision),
            ).fetchone()
        if not r or digest(r["before_json"]) != r["before_hash"]:
            raise ValueError("Снимок для отката недоступен или повреждён")
        return migrate(json.loads(r["before_json"]))

    def request_log(self, gid, stage, payload):
        with self.connect() as db:
            db.execute(
                "INSERT INTO tabletop_requests VALUES(?,?,?,?)",
                (uuid4().hex, gid, stage, dump(payload)),
            )

    def usage(self, gid):
        with self.connect() as db:
            return [
                dict(stage=r["stage"], **json.loads(r["payload"]))
                for r in db.execute(
                    "SELECT stage,payload FROM tabletop_requests WHERE game_id=? ORDER BY rowid DESC LIMIT 50",
                    (gid,),
                )
            ]

    def save_draft(self, definition, source="import", draft_id=None, revision=None):
        from .compiler import CampaignCompiler

        definition = CampaignCompiler().validate(definition)
        did = draft_id or uuid4().hex
        with self.connect() as db:
            if draft_id:
                result = db.execute(
                    "UPDATE tabletop_drafts SET definition_json=?,revision=revision+1 WHERE id=? AND revision=?",
                    (definition.model_dump_json(), did, revision),
                )
                if result.rowcount != 1:
                    raise ValueError("Черновик изменился. Обнови его.")
            else:
                db.execute(
                    "INSERT INTO tabletop_drafts(id,definition_json,source) VALUES(?,?,?)",
                    (did, definition.model_dump_json(), source),
                )
        return self.draft(did)

    def draft(self, did):
        with self.connect() as db:
            r = db.execute(
                "SELECT * FROM tabletop_drafts WHERE id=?", (did,)
            ).fetchone()
        if not r:
            raise ValueError("Черновик не найден")
        return {
            "id": did,
            "revision": r["revision"],
            "definition": json.loads(r["definition_json"]),
            "source": r["source"],
            "usage": self.usage(did),
        }

    def list_drafts(self):
        with self.connect() as db:
            return [
                {
                    "id": r["id"],
                    "revision": r["revision"],
                    "name": json.loads(r["definition_json"])["name"],
                }
                for r in db.execute("SELECT * FROM tabletop_drafts ORDER BY rowid DESC")
            ]
