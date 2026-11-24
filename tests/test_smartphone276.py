"""Real repository/HTTP/job boundaries; only the model transport is replaced."""

from copy import deepcopy
import json
import sqlite3
import threading
from unittest.mock import patch

import pytest

import engine
from backend.runtime_v3.models import identity
from backend.runtime_v3.smartphone import badges, publish, social_view
from backend.runtime_v3.smartphone_models import SearchFilters
from backend.services.smartphone import consider, social_prompt
from smartphone_provider import response
from test_phone122 import CONFIG, setup
from test_narrative_test_world import ordinary_job


@pytest.fixture()
def app(tmp_path):
    repo, client, sid = setup(tmp_path)
    snap = repo.get_snapshot(sid)
    snap["world_state"]["meta"]["communication"].update(dating=True, social=True)
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))
    return repo, client, sid


def request(
    app, action, operation, *, generate=False, revision=None, actor="qa_kirill", app_id=None, **fields
):
    repo, client, sid = app
    cmd = dict(
        app=app_id or ("dating" if action in ("search", "accept", "skip") else "social"),
        actor_id=actor,
        action=action,
        operation_id=operation,
        **fields,
    )
    value = dict(revision=repo.get_save(sid)["revision"] if revision is None else revision, command=cmd)
    with patch("engine.launch"):
        if generate:
            value["config"] = CONFIG
        return client.post(f"/api/saves/{sid}/apps/" + ("dispatch" if generate else "command"), json=value)


def run(app, job, produce=response, expect="saved"):
    repo, _, _ = app

    def stream(**kwargs):
        yield json.dumps(produce(kwargs["messages"]), ensure_ascii=False)

    with patch("engine.chat_stream", side_effect=stream) as calls:
        engine.run_job(repo.path, job, engine.Worker(epoch=repo.get_job(job)["attempt_epoch"]))
    actual = repo.get_job(job)
    assert actual["status"] == expect, actual["error"]
    return calls.call_count


def dispatch(app, action, op, **fields):
    result = request(app, action, op, generate=True, **fields)
    assert result.status_code == 200, result.text
    return result.json()["job"]["id"]


def test_two_generations_fence_duplicates_rollback_age_and_retry(app):
    repo, client, sid = app
    before = repo.get_snapshot(sid)
    jid = dispatch(app, "search", "one-search", filters=SearchFilters(location="Озёрск").model_dump())
    assert run(app, jid) == 1
    url = f"/api/saves/{sid}/apps/dating"
    rows = client.get(url).json()["results"]
    assert len(rows) == 5 and rows == client.get(url).json()["results"]
    assert request(app, "skip", "skip-first", target=rows[0]["id"]).is_success
    assert repo.get_snapshot(sid)["world_state"]["characters"] == before["world_state"]["characters"]
    target = rows[1]["id"]
    # Advance one calendar year on the source branch before choosing the card.
    snap = repo.get_snapshot(sid)
    snap["world_state"]["meta"]["world_time"] += 365 * 1440
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=?,revision=revision+1 WHERE id=?", (json.dumps(snap), sid))
    revision = repo.get_save(sid)["revision"]
    jid = dispatch(app, "accept", "one-like", target=target)
    assert dispatch(app, "accept", "double-click", target=target) == jid
    assert request(app, "search", "racing-search", generate=True, filters={}).status_code == 409
    assert run(app, jid, lambda ms: {**response(ms), "birth_date": "1900-01-01"}, "error") == 1
    assert not client.get(url).json()["liked"]
    assert repo.get_snapshot(sid)["world_state"]["characters"] == before["world_state"]["characters"]
    repo.retry_job(jid)

    def expand_chosen(messages):
        result = response(messages)
        result["fields"]["Роль"] = "Другая профессия"
        return result

    assert run(app, jid, expand_chosen) == 1
    assert dispatch(app, "accept", "one-like", target=target, revision=revision) == jid
    assert dispatch(app, "accept", "later", target=target) == jid
    assert request(app, "accept", "one-like", target=rows[2]["id"], generate=True).status_code == 409
    liked = client.get(url).json()["liked"]
    assert len(liked) == 1 and "fields" not in liked[0]
    cid = liked[0]["character_id"]
    after = repo.get_snapshot(sid)
    assert len(after["world_state"]["characters"]) == len(before["world_state"]["characters"]) + 1
    assert after["world_state"]["camera"] == before["world_state"]["camera"]
    assert cid not in after.get("pending_reviews", {})
    card = next(c for c in repo.get_save(sid)["state"]["characters"] if c["id"] == cid)
    assert int(card["fields"]["Возраст"]) == liked[0]["age"] == rows[1]["age"] + 1
    assert card["name"] == rows[1]["name"] and card["fields"]["Роль"] == rows[1]["occupation"]
    assert after["world_state"]["characters"][cid]["procedural_portrait"]
    assert len([r for r in repo.request_log(save_id=sid) if r["stage"].startswith("smartphone_")]) == 3
    repo.transition_protagonist(sid, repo.get_save(sid)["revision"], "actor-switch", "temporary", "qa_vera")
    assert (
        not client.get(url).json()["results"] and cid in repo.get_snapshot(sid)["world_state"]["characters"]
    )


def test_post_reactions_and_read_marker_have_separate_knowledge(app):
    repo, client, sid = app
    initial = repo.get_snapshot(sid)
    before = repo.get_save(sid)["revision"]
    jid = dispatch(app, "post", "player-post", text="Я выиграл миллион.")
    url = f"/api/saves/{sid}/apps/social"
    post = client.get(url).json()["entries"][0]["post"]
    assert post["text"] == "Я выиграл миллион."
    assert run(app, jid) == 1
    assert dispatch(app, "post", "player-post", text=post["text"], revision=before) == jid
    discussion = client.get(url, params={"post": post["id"]}).json()
    assert len(discussion["comments"]) == 2
    assert request(app, "like", "like", target=post["id"]).is_success
    assert request(app, "like", "like-again", target=post["id"]).is_success
    assert request(app, "repost", "share", target=post["id"]).is_success
    assert len(client.get(url).json()["entries"]) == 2
    for action in ("like", "repost"):
        assert request(app, action, "undo-" + action, target=post["id"], desired=False).is_success
    only = client.get(url).json()["entries"]
    assert len(only) == 1 and only[0]["post"]["likes"] == 0 and only[0]["post"]["reposts"] == 0
    state = repo.get_snapshot(sid)["world_state"]
    assert state["possessions"] == initial["world_state"]["possessions"]
    assert state["relationships"] == initial["world_state"]["relationships"]
    assert state["camera"] == initial["world_state"]["camera"]
    assert badges(state, "qa_kirill")["social"] == 1
    assert request(app, "open", "open-chats", app_id="messages").is_success
    assert request(app, "open", "open-social").is_success
    now = repo.get_snapshot(sid)["world_state"]
    assert not badges(now, "qa_kirill")["social"] and now["knowledge"] == state["knowledge"]
    ids = [r["id"] for r in discussion["comments"]]
    assert request(app, "read", "read-visible", ids=ids).is_success
    after = repo.get_snapshot(sid)["world_state"]
    assert all("qa_kirill:" + identity("public_statement", rid) in after["knowledge"] for rid in ids)
    assert request(app, "profile", "spoof", actor="qa_vera", text="spoof").status_code == 409
    ordinary_job(repo, sid)
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)["world_state"] == after
    # Rewind the preceding turn to a branch without this phone activity.
    repo.rollback_last(sid)
    assert not repo.get_snapshot(sid)["world_state"]["smartphone"]["publications"]


def test_durable_failure_fences_stale_and_stopped_jobs(app):
    repo, client, sid = app
    jid = dispatch(app, "search", "failing-search", filters={})
    with patch("backend.repositories.smartphone.project", side_effect=sqlite3.OperationalError("disk full")):
        assert run(app, jid, expect="error") == 1
    assert not client.get(f"/api/saves/{sid}/apps/dating").json()["results"]
    repo.retry_job(jid)
    from backend.repositories.smartphone import finish_job
    from backend.runtime_v3.smartphone_models import AppCommand

    stale = dict(repo.get_job(jid), attempt_epoch=0)
    cmd = AppCommand.model_validate(json.loads(stale["config_json"])["smartphone"])
    finish_job(repo, stale, cmd, lambda _: pytest.fail("Late attempt wrote a result"))
    engine.stop(repo, jid)
    finish_job(repo, repo.get_job(jid), cmd, lambda _: pytest.fail("Cancelled job wrote a result"))
    assert not client.get(f"/api/saves/{sid}/apps/dating").json()["results"]
    repo.retry_job(jid)
    assert run(app, jid) == 0
    assert len(client.get(f"/api/saves/{sid}/apps/dating").json()["results"]) == 5


def test_large_public_archive_bounded_context_and_autonomous_batch(app):
    repo, client, sid = app
    snap = repo.get_snapshot(sid)
    state = snap["world_state"]
    for i in range(150):
        publish(state, "qa_vera", "post", f"item-{i}", text="Публичный текст " + str(i) + "я" * 500)
    page = social_view(snap, limit=12)
    next_page = social_view(snap, limit=12, before=tuple(map(int, page["next"].split(","))))
    assert len(page["entries"]) == 12 and {e["sequence"] for e in page["entries"]}.isdisjoint(
        e["sequence"] for e in next_page["entries"]
    )
    prompt, _ = social_prompt(snap)
    assert len(json.dumps(prompt, ensure_ascii=False)) < 16000
    assert 'item-0"' not in str(prompt) and "qa_private_letter" not in str(prompt)
    assert client.get(f"/api/saves/{sid}/apps/social", params={"profile": "unknown"}).status_code == 409
    before = deepcopy(snap)
    state["meta"]["world_time"] += 360
    calls = []

    def generate(stage, ms, *args, **kwargs):
        calls.append(stage)
        yield json.dumps(response(ms))

    batch = dict(state_changes=[])
    consider(before, snap, batch, CONFIG, generate, threading.Event(), [])
    consider(before, snap, batch, CONFIG, generate, threading.Event(), [])
    assert calls == ["social_activity"]
    pubs = snap["world_state"]["smartphone"]["publications"]
    last = list(pubs.values())[-2:]
    assert last[0]["author"] != last[1]["author"] and last[1]["reply_to"] == last[0]["id"]
    old = deepcopy(snap)
    old["world_state"]["meta"]["communication"].update(social=False, dating=False)
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(old), sid))
    for app_id in ("social", "dating"):
        assert client.get(f"/api/saves/{sid}/apps/{app_id}").status_code == 409
        assert request(app, "open", "denied", app_id=app_id).status_code == 409


def test_extraction_uses_actual_publication_preserves_foreground_and_sibling(app):
    from backend.runtime_v3.consequences import resolve_consequences
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.player_actions import contract_options
    from backend.runtime_v3.context import build_context

    repo, _, sid = app
    snap = repo.get_snapshot(sid)
    state = snap["world_state"]
    narrative = "Вера публикует в соцсети: «Вечером жду вас в галерее»."
    turn = state["meta"]["turn_id"] + 1

    def resolve(raw):
        return StateResolver(
            state, narrative, "Смотрю в окно.", turn_id=turn, **contract_options(11)
        ).resolve(raw)

    proposals = [
        dict(author="qa_vera", text="Вечером жду вас в галерее"),
        dict(author="qa_kirill", text="Я приду"),
        dict(text="Нет автора"),
    ]
    _, resolved = resolve_consequences(
        json.dumps(dict(publications=proposals)), state, narrative, turn, [], resolve, version=11
    )
    rows = resolved.state["smartphone"]["publications"]
    assert len(rows) == 1 and resolved.warnings, resolved.warnings
    assert resolved.patch.apply(state)["smartphone"]["publications"] == rows
    _, again = resolve_consequences(
        json.dumps(dict(publications=proposals[:1])), state, narrative, turn, [], resolve, version=11
    )
    assert again.state["smartphone"]["publications"] == rows
    assert not state["smartphone"]["publications"]
    from backend.runtime_v3.smartphone import perceive

    snap["world_state"] = again.state
    text = proposals[0]["text"]
    unknown = build_context(snap, [], "Вспоминаю галерею.", "turn", 32768, 2000, extraction_contract=11)
    assert text not in json.dumps(unknown, ensure_ascii=False)
    perceive(again.state, "qa_kirill", next(iter(rows.values())))
    known = build_context(snap, [], "Вспоминаю галерею.", "turn", 32768, 2000, extraction_contract=11)
    assert text in json.dumps(known, ensure_ascii=False)


def test_five_publications_badge_is_per_actor_per_app_and_persists(app):
    repo, client, sid = app
    snap = repo.get_snapshot(sid)
    for i in range(5):
        publish(snap["world_state"], "qa_vera", "post", f"p{i}", text=f"Вечер {i}")
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))

    def badge():
        return client.get(f"/api/saves/{sid}").json()["state"]["phone"]["badges"]["social"]

    assert badge() == 5
    assert request(app, "open", "other", app_id="dating").is_success and badge() == 5
    assert request(app, "open", "seen").is_success and badge() == 0
    assert repo.get_snapshot(sid)["world_state"]["knowledge"] == snap["world_state"]["knowledge"]
    repo.transition_protagonist(sid, repo.get_save(sid)["revision"], "other-owner", "temporary", "qa_timur")
    assert badge() == 5
    request(app, "post", "other-post", actor="qa_timur", text="Новая запись")
    repo.transition_protagonist(sid, repo.get_save(sid)["revision"], "return", "temporary", "qa_kirill")
    assert badge() == 1


def test_reselect_variant_recovers_its_person_and_original_job_receipts(app):
    repo, client, sid = app
    ordinary_job(repo, sid)
    turn = repo.list_turns(sid)[-1]
    original = turn["active_variant_id"]
    search = dispatch(app, "search", "branch-search", filters={})
    run(app, search)
    url = f"/api/saves/{sid}/apps/dating"
    first = client.get(url).json()["results"][0]
    accept = dispatch(app, "accept", "branch-accept", target=first["id"])
    run(app, accept)
    cid = client.get(url).json()["liked"][0]["character_id"]
    assert request(app, "post", "branch-post", text="Запись исходной ветки").is_success
    ordinary_job(repo, sid, "regenerate")
    sibling = repo.list_turns(sid)[-1]["active_variant_id"]
    assert sibling != original
    assert not client.get(url).json()["results"]
    assert cid not in repo.get_snapshot(sid)["world_state"]["characters"]

    def select(vid):
        repo.select_variant(sid, turn["id"], vid, repo.get_save(sid)["revision"])

    select(original)
    assert client.get(url).json()["liked"][0]["character_id"] == cid
    assert dispatch(app, "accept", "different-operation", target=first["id"]) == accept
    assert (
        client.get(f"/api/saves/{sid}/apps/social").json()["entries"][0]["post"]["text"]
        == "Запись исходной ветки"
    )
    select(sibling)
    assert not client.get(f"/api/saves/{sid}/apps/social").json()["entries"]


def test_closed_phone_background_publishes_through_normal_turn_job(app, monkeypatch):
    monkeypatch.setattr("backend.runtime_v3.player_actions.EXTRACTION_VERSION", 11)
    from test_narrative_test_world import NARRATIVE

    repo, client, sid = app
    snap = repo.get_snapshot(sid)
    state = snap["world_state"]
    state["smartphone"]["last_considered"] = state["meta"]["world_time"] - 180
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))

    def stream(**args):
        if args["messages"][0]["content"].startswith("Public social activity/1"):
            yield json.dumps(response(args["messages"]))
        else:
            yield (
                json.dumps(dict(scene=dict(elapsed_minutes=1), scene_steps=[]))
                if args.get("response_format")
                else NARRATIVE
            )

    jid = repo.begin_job(sid, "Рассматриваю фотографии.", "turn", CONFIG)
    with (
        patch("engine.find_loaded_model", return_value={"config": {"context_length": 32768}}),
        patch("engine.chat_stream", side_effect=stream),
    ):
        engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]
    assert sum(r["stage"] == "social_activity" for r in repo.request_log(job_id=jid)) == 1
    url = f"/api/saves/{sid}/apps/social"
    post = client.get(url).json()["entries"][0]["post"]
    reply = client.get(url, params={"post": post["id"]}).json()["comments"][0]
    assert reply["author"] != post["author"] and reply["reply_to"] == post["id"]
    assert post["author"] != "qa_kirill" and reply["author"] != "qa_kirill"
    assert repo.get_snapshot(sid)["world_state"]["meta"]["world_time"] == state["meta"]["world_time"] + 1


def test_opening_badge_after_failed_reply_keeps_retry_and_polling_idempotent(app):
    repo, client, sid = app
    initial = repo.get_snapshot(sid)
    publish(initial["world_state"], "qa_vera", "post", "prior-post", text="Утренний свет")
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(initial), sid))
    jid = dispatch(app, "post", "with-prior-badge", text="Вечером в галерее")
    assert (
        run(
            app,
            jid,
            lambda _: dict(actions=[dict(kind="like", author="unknown", target="prior-post")]),
            "error",
        )
        == 1
    )
    assert request(app, "open", "seen-on-error").is_success
    latest = repo.get_save(sid)["revision"]
    assert repo.get_job(jid)["revision"] == latest
    assert repo.get_save(sid)["state"]["phone"]["badges"]["social"] == 0
    repo.retry_job(jid, revision=latest)
    assert run(app, jid) == 1
    feed = client.get(f"/api/saves/{sid}/apps/social").json()["entries"]
    assert len(feed) == 2 and feed[0]["post"]["comments"] == 2
