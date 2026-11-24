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


def save_snapshot(db, row, before, after, command, *, job_id=None, history=None):
    after["world_state"] = assert_world_state_v3_invariants(after["world_state"])
    change = dict(
        kind="smartphone",
        operation_id=command.operation_id,
        action=command.action,
        actor_id=command.actor_id,
        digest=stable_id("app", command.model_dump()),
        job_id=job_id,
    )
    if command.action == "ask" and command.desired:
        change.pop("actor_id")
    history = history or {}
    history.setdefault("state_changes", []).append(change)
    after["history_head"] = append_history(
        db,
        before.get("history_head"),
        history,
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
    state = after["world_state"] = assert_world_state_v3_invariants(after["world_state"])
    actor = check(after, cmd)
    if check_receipt(db, before, cmd):
        return
    repo._assert_idle(db, sid)
    if row["revision"] != revision:
        raise ValueError("Сейв изменился. Обнови телефон.")
    data = domain(state)
    history = {}
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
            if cmd.app=="questions" and rid in data["questions"]:
                from backend.runtime_v3.phone_listings import perceive_question
                perceive_question(state,actor,data["questions"][rid])
            else:
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
    elif cmd.action in ("ask", "answer", "hide", "plan", "invite", "favorite", "apply"):
        from backend.runtime_v3.phone_listings import command
        command(after, cmd, job_id, history)
    else:
        raise ValueError("Это действие требует генерации.")
    save_snapshot(db, row, before, after, cmd, job_id=job_id, history=history)
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
    state = snap["world_state"] = assert_world_state_v3_invariants(snap["world_state"])
    actor = check(snap, cmd)
    previous = check_receipt(db, snap, cmd)
    if cmd.action == "apply":
        a = domain(state)["applications"].get(identity("application", actor, cmd.target))
        if a:
            prior_job = db.execute(
                "SELECT revision,status FROM game_jobs WHERE id=? AND save_id=?", (a["job_id"], save["id"])
            ).fetchone()
            if a["event_id"] and not prior_job:
                raise ValueError("Отклик уже отправлен. Переписка доступна в этой вакансии.")
            if prior_job and (a["event_id"] or prior_job["revision"] == save["revision"]
                              or prior_job["status"] not in ("error", "stopped")):
                raise ExistingJob(a["job_id"])
    if previous and previous.get("job_id"):
        if db.execute("SELECT 1 FROM game_jobs WHERE id=? AND save_id=?",
                      (previous["job_id"], save["id"])).fetchone():
            raise ExistingJob(previous["job_id"])
        raise ValueError("Эта операция уже сохранена в истории прохождения.")
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
            cmd.action in ("refresh", "generate") and cmd.action == old["action"] and cmd.app == old["app"]
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
    if cmd.action in ("post", "comment", "ask", "apply", "invite"):
        apply_command(repo, db, save["id"], config["expected_revision"], cmd, job_id=jid)
        save = db.execute("SELECT * FROM saves WHERE id=?", (save["id"],)).fetchone()
        config["expected_revision"] = save["revision"]
        if cmd.action=="invite":
            sources = []
            for recipient in dict.fromkeys(cmd.ids):
                operation = identity("invite",cmd.operation_id,recipient)
                sources.append(dict(source_event_id=identity("remote",actor,operation),owner_id=actor,request_id=operation))
            config["communication"], config["_additional_invitations"] = sources[0],sources[1:]
    elif cmd.action not in ("search", "accept", "refresh", "generate"):
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
        after["world_state"] = assert_world_state_v3_invariants(after["world_state"])
        check(after, command)
        history = {}
        warnings = (apply(after, history) if command.action=="apply" else apply(after)) or []
        save_snapshot(db, row, before, after, command, job_id=job["id"], history=history)
        if command.action=="apply":
            aid = identity("application",command.actor_id,command.target)
            event = domain(after["world_state"])["applications"][aid]["event_id"]
            continuation = dict(source_event_id=event,owner_id=command.actor_id,request_id=aid)
            # Durable handoff: retry after delivery resumes the ordinary communication worker.
            db.execute("""UPDATE game_jobs SET kind='communication', revision=?, before_json=?, memory_before_json=NULL,
                    context_json=NULL, config_json=json_set(config_json,'$.communication',json(?)) WHERE id=?""",
                (row["revision"]+1,json.dumps(after,ensure_ascii=False),json.dumps(continuation),job["id"]))
            return continuation
        db.execute(
            "UPDATE game_jobs SET status='saved',error='',warnings_json=? WHERE id=?",
            (json.dumps(warnings, ensure_ascii=False), job["id"]),
        )
