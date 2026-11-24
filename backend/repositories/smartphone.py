"""Smartphone commands use the same transaction, branch receipts and undo boundary as phone controls."""

from copy import deepcopy
import json

from backend.repositories.living_world import project
from backend.runtime_v3.milestones import stable_id
from backend.runtime_v3.models import assert_world_state_v3_invariants, identity
from backend.runtime_v3.repository import append_history
from backend.runtime_v3.smartphone import access, candidate, domain, markers, perceive, publication, publish
from backend.runtime_v3.smartphone_models import AppCommand


def receipt(db, head, operation):
    row = db.execute(
        """WITH RECURSIVE lineage(id,parent_id,payload_json) AS (
        SELECT id,parent_id,payload_json FROM world_history_v3 WHERE id=?
        UNION ALL SELECT h.id,h.parent_id,h.payload_json FROM world_history_v3 h JOIN lineage l ON h.id=l.parent_id)
        SELECT j.value FROM lineage,json_each(lineage.payload_json,'$.state_changes') j
        WHERE json_extract(j.value,'$.operation_id')=? AND json_extract(j.value,'$.kind')='smartphone' LIMIT 1""",
        (head, operation),
    ).fetchone()
    return json.loads(row[0]) if row else None


def check(snapshot, command):
    actor = access(snapshot, command.app, write=command.action not in ("open", "read"))
    if actor != command.actor_id:
        raise ValueError("Владелец телефона изменился.")
    return actor


def save_snapshot(db, row, before, after, command, *, job_id=None):
    after["world_state"] = assert_world_state_v3_invariants(after["world_state"])
    change = dict(
        kind="smartphone",
        operation_id=command.operation_id,
        action=command.action,
        actor_id=command.actor_id,
        digest=stable_id("app", command.model_dump()),
        job_id=job_id,
    )
    after["history_head"] = append_history(
        db,
        before.get("history_head"),
        {"state_changes": [change]},
        before=before["world_state"],
        after=after["world_state"],
    )
    sid = row["id"]
    encoded = json.dumps(after, ensure_ascii=False)
    parent = db.execute(
        "SELECT active_variant_id FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1", (sid,)
    ).fetchone()
    checkpoint = db.execute(
        "INSERT INTO actor_switches(save_id,revision,before_json,after_json,parent_variant_id) VALUES(?,?,?,?,?)",
        (sid, row["revision"], row["state_json"], encoded, parent[0] if parent else None),
    )
    if parent and parent[0]:
        db.execute(
            "UPDATE response_variants SET payload=json_set(payload,'$.smartphone_checkpoint',?) WHERE id=?",
            (checkpoint.lastrowid, parent[0]),
        )
    project(db, sid, after)
    db.execute(
        "UPDATE saves SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (encoded, sid),
    )


def check_receipt(db, snap, cmd):
    previous = receipt(db, snap.get("history_head"), cmd.operation_id)
    if previous and previous["digest"] != stable_id("app", cmd.model_dump()):
        raise ValueError("ID операции уже использован с другими данными.")
    return previous


def apply_command(repo, db, sid, revision, cmd, *, job_id=None):
    row = db.execute("SELECT * FROM saves WHERE id=?", (sid,)).fetchone()
    if not row:
        raise ValueError("Прохождение не найдено.")
    before = json.loads(row["state_json"])
    after = deepcopy(before)
    state = after["world_state"]
    actor = check(after, cmd)
    if check_receipt(db, before, cmd):
        return
    repo._assert_idle(db, sid)
    if row["revision"] != revision:
        raise ValueError("Сейв изменился. Обнови телефон.")
    data = domain(state)
    if cmd.action == "open":
        latest = markers(state, actor).get(cmd.app, 0)
        mark = min(latest, cmd.marker if cmd.marker is not None else latest)
        seen = data["opened"].setdefault(actor, {})
        if seen.get(cmd.app, 0) >= mark:
            return
        seen[cmd.app] = mark
    elif cmd.action == "profile":
        data["profiles"][actor] = cmd.text.strip()
    elif cmd.action == "skip":
        item = candidate(state, actor, cmd.target)
        if item["character_id"]:
            raise ValueError("Анкета уже понравилась.")
        item["skipped"] = True
    elif cmd.action == "read":
        for rid in cmd.ids:
            perceive(state, actor, publication(state, rid))
        if state["knowledge"] == before["world_state"]["knowledge"]:
            return
    elif cmd.action in ("post", "comment", "like", "repost"):
        publish(
            state,
            actor,
            cmd.action,
            identity("publication", actor, cmd.operation_id),
            target=cmd.target,
            text=cmd.text,
            desired=cmd.desired,
        )
    else:
        raise ValueError("Это действие требует генерации.")
    save_snapshot(db, row, before, after, cmd, job_id=job_id)
    if cmd.action in ("open", "read"):
        # These controls change only the owner's reading state. The original
        # prompt, target and provider checkpoint of a failed app job stay valid.
        db.execute(
            """UPDATE game_jobs SET revision=revision+1
            WHERE save_id=? AND revision=? AND kind='smartphone' AND status IN ('error','stopped')""",
            (sid, revision),
        )


def register_job(repo, db, save, config, jid):
    from engine_storage import ACTIVE, ExistingJob

    cmd = AppCommand.model_validate(config["smartphone"])
    snap = json.loads(save["state_json"])
    state = snap["world_state"]
    actor = check(snap, cmd)
    previous = check_receipt(db, snap, cmd)
    if previous and previous.get("job_id"):
        raise ExistingJob(previous["job_id"])
    if cmd.action == "accept":
        item = candidate(state, actor, cmd.target)
        if item["character_id"]:
            raise ExistingJob(item["job_id"])
        if item["skipped"]:
            raise ValueError("Анкета пропущена.")
    for row in db.execute(
        "SELECT id,status,config_json FROM game_jobs WHERE save_id=? AND revision=? AND kind='smartphone' ORDER BY rowid DESC",
        (save["id"], save["revision"]),
    ):
        old = json.loads(row["config_json"])["smartphone"]
        if old["operation_id"] == cmd.operation_id:
            if old != cmd.model_dump():
                raise ValueError("ID операции уже использован с другими данными.")
            raise ExistingJob(row["id"])
        if (
            cmd.action == old["action"] == "refresh"
            and row["status"] in ACTIVE
            and config["expected_revision"] == save["revision"]
        ):
            raise ExistingJob(row["id"])
        if (
            cmd.action == "accept"
            and old["action"] == "accept"
            and old["actor_id"] == actor
            and old["target"] == cmd.target
        ):
            raise ExistingJob(row["id"])
    if cmd.action in ("post", "comment"):
        apply_command(repo, db, save["id"], config["expected_revision"], cmd, job_id=jid)
        save = db.execute("SELECT * FROM saves WHERE id=?", (save["id"],)).fetchone()
        config["expected_revision"] = save["revision"]
    elif cmd.action not in ("search", "accept", "refresh"):
        raise ValueError("Для этого действия генерация не требуется.")
    return save


def finish_job(repo, job, command, apply):
    with repo.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT status,attempt_epoch FROM game_jobs WHERE id=?", (job["id"],)).fetchone()
        row = db.execute("SELECT * FROM saves WHERE id=?", (job["save_id"],)).fetchone()
        if (
            current["status"] not in ("generating", "extracting")
            or current["attempt_epoch"] != job["attempt_epoch"]
        ):
            return
        if row["revision"] != job["revision"]:
            raise ValueError("Сейв изменился во время генерации.")
        before = json.loads(row["state_json"])
        after = deepcopy(before)
        check(after, command)
        warnings = apply(after) or []
        save_snapshot(db, row, before, after, command, job_id=job["id"])
        db.execute(
            "UPDATE game_jobs SET status='saved',error='',warnings_json=? WHERE id=?",
            (json.dumps(warnings, ensure_ascii=False), job["id"]),
        )
