"""Narrative phone app contracts through FastAPI, SQLite and the recorded provider transport."""

import json
from copy import deepcopy
from unittest.mock import patch

from backend.runtime_v3.models import identity
from backend.runtime_v3.smartphone import badges
from smartphone_provider import response
from test_smartphone276 import dispatch, request, run

from test_smartphone276 import app as phone_app

app = phone_app
from test_narrative_test_world import ordinary_job


def get(app, name, **query):
    repo, client, sid = app
    r = client.get(f"/api/saves/{sid}/apps/{name}", params=query)
    assert r.is_success, r.text
    return r.json()


def fill(app, name, operation, produce=response):
    jid = dispatch(app, "generate", operation, app_id=name)
    assert run(app, jid, produce) == 1
    return get(app, name)["items"]


def test_legacy_worlds_payloads_articles_badges_and_rollback(app):
    repo, client, sid = app
    snap = repo.get_snapshot(sid)
    config = snap["campaign"].setdefault("campaign", {})
    config.update(era="Эпоха парусников", technology="Печать на ручном прессе")
    snap["world_state"]["smartphone"].pop("articles", None)
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))
    payloads = []

    def capture(ms):
        payloads.append(json.loads(ms[1]["content"]))
        return response(ms)

    rows = fill(app, "news", "news-first", capture)
    assert len(rows) == 5 and payloads[-1]["world"]["era"] == "Эпоха парусников"
    state = repo.get_snapshot(sid)["world_state"]
    assert badges(state, "qa_kirill")["news"] == 5
    assert request(app, "open", "open-news", app_id="news").is_success
    after = repo.get_snapshot(sid)["world_state"]
    assert badges(after, "qa_kirill")["news"] == 0 and after["knowledge"] == state["knowledge"]
    assert get(app, "news")["items"] == rows and not get(app, "social")["entries"]
    rid = rows[0]["id"]
    assert request(app, "read", "read-news", app_id="news", ids=[rid]).is_success
    after = repo.get_snapshot(sid)["world_state"]
    fid = identity("public_statement", rid)
    assert "Издание сообщает" in after["facts"][fid]["text"] and "qa_kirill:" + fid in after["knowledge"]
    assert "qa_vera:" + fid not in after["knowledge"]
    assert (
        after["meta"]["world_time"] == state["meta"]["world_time"]
        and after["meta"]["turn_id"] == state["meta"]["turn_id"]
    )
    assert (
        run(
            app, dispatch(app, "comment", "article-discussion", app_id="news", target=rid, text="Где искать?")
        )
        == 1
    )
    assert len(get(app, "social", post=rid)["comments"]) >= 2
    rows2 = fill(app, "news", "next-edition", capture)
    assert len(rows2) == 10 and rows2[0]["previous_id"] in {r["id"] for r in rows}
    assert len(payloads[-1]["news"]) == 5 and "qa_private_letter" not in json.dumps(payloads)
    ordinary_job(repo, sid)
    repo.rollback_last(sid)
    assert get(app, "news")["items"] == rows2


def test_anonymous_routes_and_prompt(app):
    repo, client, sid = app
    jid = dispatch(
        app,
        "ask",
        "my-anonymous-question",
        app_id="questions",
        target="qa_vera",
        text="Какой концерт посоветуешь?",
    )
    q = get(app, "questions", tab="sent")["items"][0]
    assert q["sender"] is None and not get(app, "questions")["items"]

    def reply(ms):
        payload = json.loads(ms[1]["content"])
        assert payload["question"] == dict(text=q["text"], sender=None) and not payload["people"]
        assert "эмодзи" in ms[0]["content"] and "публичного ответа" in ms[0]["content"]
        assert payload["actor"] == "qa_vera" and "voice" in payload["profile"]
        assert "my-anonymous-question" not in str(payload)
        return response(ms)

    assert run(app, jid, reply) == 1
    public = get(app, "questions")["items"][0]
    assert public["id"] == q["id"] and public["publication_id"] and public["sender"] is None
    canon = repo.get_snapshot(sid)["world_state"]["smartphone"]["questions"][q["id"]]
    assert canon["sender"] == "qa_kirill"
    repo.transition_protagonist(sid, repo.get_save(sid)["revision"], "switch-q", "temporary", "qa_vera")
    assert (
        get(app, "questions")["items"][0]["sender"] is None and not get(app, "questions", tab="sent")["items"]
    )
    for projection in (client.get(f"/api/jobs/{jid}").json(), client.get(f"/api/saves/{sid}").json()["job"]):
        assert projection["presentation"].get("actor_id") is None
        assert not projection.get("user_text") and not projection["presentation"].get("target")
    assert not request(
        app, "answer", "fake-answer", app_id="questions", target=q["id"], text="Второй ответ"
    ).is_success


def test_event_plan_invites_and_vacancy_projection(app):
    repo, client, sid = app
    e = fill(app, "events", "event-first")[0]
    before = repo.get_snapshot(sid)["world_state"]
    assert not e["planned"]
    for op in ("first-plan", "second-plan"):
        assert request(app, "plan", op, app_id="events", target=e["id"]).is_success
    now = repo.get_snapshot(sid)["world_state"]
    assert len(now["scheduled_events"]) == len(before["scheduled_events"]) + 1
    assert now["camera"] == before["camera"] and now["meta"]["world_time"] == before["meta"]["world_time"]
    r = request(
        app,
        "invite",
        "invite-two",
        app_id="events",
        target=e["id"],
        ids=["qa_vera", "qa_oleg"],
        text="Идём на репетицию?",
    )
    assert r.is_success, r.text
    now = repo.get_snapshot(sid)["world_state"]
    assert len(now["smartphone"]["invitations"]) == 2
    assert all(
        now["remote_events"][eid]["content"] == "Идём на репетицию?"
        for eid in now["smartphone"]["invitations"]
    )
    assert request(app, "plan", "cancel-plan", app_id="events", target=e["id"], desired=False).is_success
    jobs = fill(app, "work", "work-first")
    assert len(jobs) == 2 and len(repo.get_snapshot(sid)["world_state"]["characters"]) == len(
        before["characters"]
    )
    v = jobs[0]
    assert request(app, "favorite", "star-vacancy", app_id="work", target=v["id"]).is_success
    assert get(app, "work", tab="favorites", kind=v["employment"])["items"][0]["id"] == v["id"]
    assert not get(app, "work", query="бессмысленный фильтр")["items"]


def test_application_handoff_failure_retry_explicit_hire(app):
    from test_communication_cycle import decision
    from test_narrative_test_world import CONFIG

    repo, client, sid = app
    vacancy = fill(app, "work", "jobs-apply")[0]
    target = vacancy["id"]
    count = len(repo.get_snapshot(sid)["character_cards"])
    jid = dispatch(
        app, "apply", "application-first", app_id="work", target=target, text="Хочу узнать об условиях."
    )
    assert (
        dispatch(
            app, "apply", "application-double", app_id="work", target=target, text="Хочу узнать об условиях."
        )
        == jid
    )
    assert run(app, jid, lambda _: (_ for _ in ()).throw(ValueError("Тестовый сбой")), expect="error") == 1
    pending = get(app, "work", tab="mine")["items"][0]
    assert (
        pending["applied"]
        and not pending["conversation_id"]
        and len(repo.get_snapshot(sid)["character_cards"]) == count
    )
    repo.retry_job(jid)
    offer = "Предлагаю начать сегодня, оплата сдельная. Согласны?"

    def offer_reply(ms):
        instruction = ms[0]["content"]
        if instruction.startswith("Phone employer/1"):
            return response(ms)
        data = json.loads(ms[1]["content"])
        if "options" in data and data["options"][0]["actions"] == ["send"]:
            assert data["actors"][0]["vacancies"][0]["id"] == target
            assert "qa_private_letter" not in str(data)
        return json.loads(decision(ms).replace("Да, увидимся завтра.", offer))

    run(app, jid, offer_reply)
    now = repo.get_snapshot(sid)["world_state"]
    assert len(now["characters"]) == count + 1
    a = next(iter(now["smartphone"]["applications"].values()))
    thread = now["remote_events"][a["event_id"]]["conversation_id"]
    assert [e["content"] for e in now["remote_events"].values() if e["conversation_id"] == thread] == [
        "Хочу узнать об условиях.",
        offer,
    ]
    assert not get(app, "work", tab="roles")["roles"]
    assert (
        dispatch(
            app,
            "apply",
            "duplicate-after-delivery",
            app_id="work",
            target=target,
            text="Хочу узнать об условиях.",
        )
        == jid
    )
    assert request(app, "open", "open-work-now", app_id="work").is_success
    assert badges(repo.get_snapshot(sid)["world_state"], "qa_kirill")["work"] == 0
    assert client.post(
        f"/api/saves/{sid}/phone",
        json=dict(
            revision=repo.get_save(sid)["revision"],
            command=dict(action="read", conversation_id=thread, operation_id="read-the-offer"),
        ),
    ).is_success
    text = "Я принимаю эти условия и начинаю сегодня."
    with patch("engine.launch"):
        r = client.post(
            f"/api/saves/{sid}/phone/dispatch",
            json=dict(
                revision=repo.get_save(sid)["revision"],
                config=CONFIG,
                command=dict(
                    action="send", operation_id="accept_employment", conversation_id=thread, content=text
                ),
            ),
        )
    assert r.is_success, r.text

    def accept_reply(ms):
        data = json.loads(ms[1]["content"])
        if "accepted_messages" in data:
            assert data["vacancies"][0]["id"] == target
            source = data["source_event_id"]
            offer_id = next(e["id"] for e in data["accepted_messages"] if e["content"] == offer)
            return dict(
                final_scene=data["final_scene"],
                role_changes=[
                    dict(
                        id="accepted_hire",
                        actor_id="qa_kirill",
                        title=vacancy["title"],
                        assertion="established",
                        effective="now",
                        vacancy_id=target,
                        offer_event_id=offer_id,
                        player_source_id=source,
                        player_assertion="explicit_choice",
                        player_evidence=text,
                        evidence=text,
                    )
                ],
            )
        return json.loads(decision(ms))

    run(app, r.json()["job"]["id"], accept_reply)
    roles = get(app, "work", tab="roles")["roles"]
    assert any(r["label"] == vacancy["title"] and r["status"] == "active" for r in roles)


def test_contrasting_public_world_payloads_custom_calendar_and_history(app):
    from backend.runtime_v3.models import Fact
    from backend.runtime_v3.repository import append_history

    repo, _, sid = app
    first = repo.get_snapshot(sid)
    examples = []
    for era, place, org in [
        ("Парусный век", "Гавань Соли", "Портовая гильдия"),
        ("Орбитальная эпоха", "Станция Лира", "Орбитальная верфь"),
    ]:
        s = deepcopy(first)
        w = s["world_state"]
        cal = w["meta"]["calendar"]
        cal.update(
            start_date="1042-02-03",
            profile=dict(
                system="custom",
                month_lengths=[32] * 12,
                weekday_names=["А", "Б", "В", "Г"],
                seasons_enabled=True,
                seasons=[dict(name="Оттепель", month=2, day=1)],
            ),
        )
        s["campaign"]["campaign"].update(
            era=era,
            tone="Приключения",
            setting=place,
            technology="Паруса" if not examples else "Космические буксиры",
        )
        lid = next(iter(w["locations"]))
        w["locations"][lid]["name"] = place
        from backend.runtime_v3.models import Organization

        w["organizations"]["org_one"] = Organization(
            id="org_one", name=org, location_ids=[lid], status="active"
        ).model_dump()
        w["facts"]["opening"] = Fact(id="opening", text="Возобновилась работа верфи").model_dump()
        w["facts"]["secret_fixture"] = Fact(
            id="secret_fixture",
            text="Скрытый банковский пароль",
            story_secret=True,
            secret_subject_ids=["qa_vera"],
            visibility="secret",
        ).model_dump()
        with repo.connect() as db:
            s["history_head"] = append_history(
                db,
                s.get("history_head"),
                dict(
                    events=[
                        dict(
                            id="public_opening",
                            text="Публичное открытие и личная записка",
                            fact_ids=["opening"],
                            minute=530,
                            turn_id=1,
                            medium="action",
                            witnesses=["qa_vera"],
                        )
                    ]
                ),
            )
            db.execute("UPDATE saves SET revision=revision+1,state_json=? WHERE id=?", (json.dumps(s), sid))

        def sample(ms):
            payload = json.loads(ms[1]["content"])
            examples.append(payload)
            assert payload["calendar"]["season"] == "Оттепель"
            assert "public_opening" in {e["id"] for e in payload["recent_events"]}
            assert "Скрытый банковский пароль" not in str(payload) and "личная записка" not in str(payload)
            assert "qa_private_letter" not in str(payload)
            assert str(payload["places"]).find(place) >= 0 and payload["world"]["era"] == era
            assert any(o["name"] == org for o in payload["organizations"])
            return response(ms)

        vacancies = fill(app, "work", "work-world-" + era, sample)
        assert all(v["employer"] == org and v["organization_id"] == "org_one" for v in vacancies)
        assert vacancies[0]["title"].startswith(
            "Парусный мастер" if era == "Парусный век" else "Техник орбитальной верфи"
        )
        articles = fill(app, "news", "news-world-" + era, sample)
        assert {r["event_id"] for r in articles} == {None, "public_opening"}
    assert examples[0]["world"]["technology"] != examples[-1]["world"]["technology"]


def test_cancelled_and_closed_history_survives_refresh_and_rollback(app):
    repo, client, sid = app
    event = fill(app, "events", "first-event")[0]
    assert request(app, "plan", "attend-event", app_id="events", target=event["id"]).is_success

    def update(change):
        return lambda ms: dict(events=[], updates=[dict(id=event["id"], **change)])

    start = event["start"] + 1440
    newer = fill(app, "events", "move-it", update(dict(start=start)))[0]
    assert not newer["planned"] and newer["previous_time"] == event["time"] and newer["start"] == start
    assert request(app, "plan", "confirm-changed", app_id="events", target=event["id"]).is_success
    cancelled = fill(app, "events", "cancel-it", update(dict(cancel=True)))[0]
    assert cancelled["cancelled"] and not cancelled["active"] and not cancelled["planned"]

    def duplicate(ms):
        p = json.loads(ms[1]["content"])
        prior = p["events"][0]
        assert prior["cancelled"]
        return dict(
            events=[
                dict(
                    listing_key=prior["listing_key"],
                    title="Название изменилось",
                    category="Музыка",
                    description="Та же репетиция",
                    start=start + 1440,
                )
            ]
        )

    jid = dispatch(app, "generate", "repeat-event", app_id="events")
    run(app, jid, duplicate, expect="error")
    assert len(get(app, "events")["items"]) == 1
    v = fill(app, "work", "work-to-close")[0]
    fill(
        app,
        "work",
        "new-terms",
        lambda _: dict(vacancies=[], updates=[dict(id=v["id"], pay="Оплата за страницу")]),
    )
    changed = get(app, "work", item=v["id"])["items"][0]
    assert changed["previous_terms"][0]["pay"] == v["pay"]
    fill(app, "work", "close-job", lambda _: dict(vacancies=[], close=[v["id"]]))
    assert not request(
        app, "apply", "too-late", app_id="work", target=v["id"], text="Хочу узнать.", generate=True
    ).is_success
    assert not get(app, "work", item=v["id"])["items"][0]["active"]


def test_private_background_questions_and_invitations_share_one_clock(app):
    import threading
    from backend.services.smartphone import consider
    from test_narrative_test_world import CONFIG

    repo, _, sid = app
    fill(app, "events", "bg-seed")
    snap = repo.get_snapshot(sid)
    owner = snap["world_state"]["camera"]["controlled_actor_id"]
    prompts = []

    def generate(stage, ms, *args, **kwargs):
        data = json.loads(ms[1]["content"])
        prompts.append(data)
        if ms[0]["content"].startswith("Phone invitation/1"):
            raw = dict(invitation=dict(event=data["events"][0]["id"], recipient=owner, text="Идём вместе?"))
        elif ms[0]["content"].startswith("Phone questions/1"):
            raw = dict(question=dict(recipient=owner, text="Ты уже слышал квартет?", anonymous=True))
        else:
            raw = response(ms)
        yield json.dumps(raw)

    for index in (2, 5):
        before = deepcopy(snap)
        w = snap["world_state"]
        w["smartphone"]["activity_index"] = index
        w["meta"]["world_time"] += 240
        t = w["meta"]["world_time"]
        turn = w["meta"]["turn_id"]
        batch = dict(state_changes=[])
        warnings = []
        consider(before, snap, batch, CONFIG, generate, threading.Event(), warnings)
        consider(before, snap, batch, CONFIG, generate, threading.Event(), warnings)
        assert (
            not warnings
            and snap["world_state"]["meta"]["world_time"] == t
            and snap["world_state"]["meta"]["turn_id"] == turn
        )
    assert len(prompts) == 2
    w = snap["world_state"]
    q = next(iter(w["smartphone"]["questions"].values()))
    assert q["recipient"] == owner and q["sender"] != owner and not q["publication_id"]
    eid = next(iter(w["smartphone"]["invitations"]))
    assert w["remote_events"][eid]["recipient_ids"] == [owner] and not w["scheduled_events"]
    with repo.connect() as db:
        db.execute("UPDATE saves SET revision=revision+1,state_json=? WHERE id=?", (json.dumps(snap), sid))
    mine = get(app, "questions", tab="inbox")["items"][0]
    assert mine["id"] == q["id"] and mine["sender"] is None
    assert request(app, "read", "read-question", app_id="questions", ids=[q["id"]]).is_success
    fid = identity("question_statement", q["id"])
    fact = repo.get_snapshot(sid)["world_state"]["facts"][fid]
    assert q["sender"] not in json.dumps(fact) and fact["character_ids"] == [owner]
    assert request(
        app, "answer", "voluntary-answer", app_id="questions", target=q["id"], text="Ещё нет."
    ).is_success
    assert get(app, "questions")["items"][0]["sender"] is None


def test_independent_invitation_answers_only_read_confirmation_reaches_calendar(app):
    from phone277_provider import reply
    from backend.runtime_v3.player_calendar import visible_calendar_state

    repo, client, sid = app
    listing = fill(app, "events", "two-invites-seed")[0]
    before = repo.get_snapshot(sid)["world_state"]
    args = dict(
        app_id="events", target=listing["id"], text="Идём вместе на репетицию?", ids=["qa_vera", "qa_oleg"]
    )
    jid = dispatch(app, "invite", "both-invited", **args)
    assert run(app, jid, reply) == 6
    assert dispatch(app, "invite", "both-invited", **args) == jid
    s = repo.get_snapshot(sid)["world_state"]
    assert s["camera"] == before["camera"]
    assert len(s["scheduled_events"]) == len(before["scheduled_events"]) + 1
    plan = next(p for p in s["scheduled_events"].values() if p["description"] == listing["title"])
    assert set(plan["character_ids"]) == {"qa_vera", "qa_kirill"}
    assert plan["id"] not in visible_calendar_state(s)["scheduled_events"]
    detail = get(app, "events", item=listing["id"])["items"][0]
    assert not any(i["plans"] or i["reply"] for i in detail["invitations"])
    for i in detail["invitations"]:
        resp = client.post(
            f"/api/saves/{sid}/phone",
            json=dict(
                revision=repo.get_save(sid)["revision"],
                command=dict(
                    action="read",
                    conversation_id=i["conversation_id"],
                    operation_id="read-" + i["conversation_id"],
                ),
            ),
        )
        assert resp.is_success, resp.text
    detail = get(app, "events", item=listing["id"])["items"][0]
    assert [i["plans"] for i in detail["invitations"]] == [[listing["title"]], []]
    assert plan["id"] in visible_calendar_state(repo.get_snapshot(sid)["world_state"])["scheduled_events"]


def test_role_authority_does_not_cross_messages_or_begin_future_employment(app):
    import pytest
    from phone277_provider import reply, OFFER
    from backend.runtime_v3.remote_semantics import messages, resolve
    from backend.runtime_v3.remote import apply

    repo, _, sid = app
    v = fill(app, "work", "roles-prereq")[0]
    jid = dispatch(
        app, "apply", "explicit-application", app_id="work", target=v["id"], text="Расскажите о вакансии."
    )
    run(app, jid, reply)
    snap = repo.get_snapshot(sid)
    a = next(iter(snap["world_state"]["smartphone"]["applications"].values()))
    events = snap["world_state"]["remote_events"]
    proposal = next(e for e in events.values() if e["content"] == OFFER)
    actor = a["actor"]
    snap, _ = apply(snap, dict(action="read", event_id=proposal["id"], operation_id="read-proposal"))
    snap, _ = apply(
        snap,
        dict(
            action="send",
            conversation_id=proposal["conversation_id"],
            operation_id="another-question",
            content="А когда начинается смена?",
        ),
    )
    source = identity("remote", actor, "another-question")
    payload = json.loads(messages(snap, source)[1]["content"])
    base = dict(
        id="hire",
        title=v["title"],
        actor_id=actor,
        assertion="established",
        effective="now",
        vacancy_id=v["id"],
        player_assertion="explicit_choice",
        player_evidence="Расскажите о вакансии.",
        player_source_id=a["event_id"],
        offer_event_id=proposal["id"],
    )
    for fields in (
        {},
        dict(player_source_id=proposal["id"]),
        dict(effective="future", player_source_id=source),
        dict(player_source_id=source, offer_event_id=a["event_id"]),
    ):
        with pytest.raises(ValueError):
            resolve(
                snap, source, dict(final_scene=payload["final_scene"], role_changes=[dict(base, **fields)])
            )
    assert not snap["world_state"]["roles"]


def test_archived_save_defaults_story_integrity_and_stale_catalog(app):
    import sqlite3
    from test_playability251 import seed
    from backend.repositories.smartphone import finish_job
    from backend.runtime_v3.smartphone_models import AppCommand

    repo, client, _ = app
    original = seed(repo, "006")
    sid = original["save"]
    with repo.connect() as db:
        db.execute(
            """UPDATE saves SET state_json=json_remove(json_set(state_json,'$.world_state.meta.communication.social',
                   json('true')),'$.world_state.smartphone') WHERE id=?""",
            (sid,),
        )
    old = (repo, client, sid)
    before = repo.get_snapshot(sid)
    actor = before["world_state"]["camera"]["controlled_actor_id"]
    count = len(before["character_cards"])
    assert get(old, "news")["items"] == []
    jid = dispatch(old, "generate", "archive-news", app_id="news", actor=actor)
    with patch("backend.repositories.smartphone.project", side_effect=sqlite3.OperationalError("disk full")):
        run(old, jid, expect="error")
    assert not get(old, "news")["items"]
    repo.retry_job(jid)
    assert run(old, jid) == 0
    assert len(get(old, "news")["items"]) == 5
    assert len(repo.get_snapshot(sid)["character_cards"]) == count
    assert repo.get_snapshot(sid)["world_state"]["camera"] == before["world_state"]["camera"]
    stale = repo.get_job(jid)
    cmd = AppCommand.model_validate(json.loads(stale["config_json"])["smartphone"])
    repo.rollback_last(sid)
    finish_job(repo, stale, cmd, lambda s: (_ for _ in ()).throw(AssertionError("Stale job committed")))
    restored = repo.get_snapshot(sid)["world_state"]
    assert not restored.get("smartphone", {}).get("articles")
    assert client.get(f"/api/saves/{sid}/apps/news").status_code == 409


def test_employer_reuse_second_owner_and_private_application_context(app, monkeypatch):
    from phone277_provider import reply

    repo, _, sid = app
    # The seed was authored on v5. New phone jobs use the current v11 wire policy.
    monkeypatch.setattr("backend.runtime_v3.player_actions.EXTRACTION_VERSION", 11)
    first, second = fill(app, "work", "shared-employer")
    count = len(repo.get_snapshot(sid)["character_cards"])
    private = "Хочу обсудить особое условие первого кандидата."
    run(
        app, dispatch(app, "apply", "first-candidate", app_id="work", target=first["id"], text=private), reply
    )
    repo.transition_protagonist(
        sid, repo.get_save(sid)["revision"], "switch-applicant", "temporary", "qa_vera"
    )
    jid = dispatch(
        app,
        "apply",
        "second-candidate",
        app_id="work",
        actor="qa_vera",
        target=second["id"],
        text="Какой график работы?",
    )

    def verify(messages):
        assert private not in str(messages)
        assert not messages[0]["content"].startswith("Phone employer/1")
        return reply(messages)

    run(app, jid, verify)
    state = repo.get_snapshot(sid)["world_state"]
    assert len(repo.get_snapshot(sid)["character_cards"]) == count + 1
    apps = list(state["smartphone"]["applications"].values())
    assert len(apps) == 2 and len({a["actor"] for a in apps}) == 2
    events = [state["remote_events"][a["event_id"]] for a in apps]
    assert events[0]["recipient_ids"] == events[1]["recipient_ids"]
    assert events[0]["conversation_id"] != events[1]["conversation_id"]
    assert [a["id"] for a in get(app, "work", tab="mine")["items"]] == [second["id"]]


def test_bounded_actual_catalog_request_and_reload_without_provider(app):
    from backend.runtime_v3.models import Fact

    repo, _, sid = app
    snap = repo.get_snapshot(sid)
    for n in range(600):
        fid = f"public_{n}"
        snap["world_state"]["facts"][fid] = Fact(
            id=fid, text=(str(n) + " Продолжается ярмарка в порту. ") * 40
        ).model_dump()
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))

    def verify(messages):
        payload = json.loads(messages[1]["content"])
        assert len(payload["public_facts"]) == 8
        assert len(messages[1]["content"]) < 24000
        return response(messages)

    entries = fill(app, "news", "bounded-news", verify)
    with patch("engine.chat_stream", side_effect=AssertionError("No provider call on reload")):
        assert entries == get(app, "news")["items"] == get(app, "news")["items"]


def test_unanswered_question_pov_history_and_narrative(app):
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.repository import read_history

    repo, client, sid = app
    phrase = "Какая мелодия звучала во время затмения?"
    assert request(app, "ask", "private-ask", app_id="questions", target="qa_vera", text=phrase).is_success
    qid = get(app, "questions", tab="sent")["items"][0]["id"]
    with repo.connect() as db:
        history, _ = read_history(db, repo.get_snapshot(sid)["history_head"])
    receipt = next(r for r in history["state_changes"] if r.get("operation_id") == "private-ask")
    assert "actor_id" not in receipt and phrase not in str(receipt)

    def switch(actor):
        repo.transition_protagonist(sid, repo.get_save(sid)["revision"], "to-" + actor, "temporary", actor)

    def narrative():
        return json.dumps(
            build_context(
                repo.get_snapshot(sid), [], "Вспоминаю разговор.", "turn", 32768, 2000, extraction_contract=11
            ),
            ensure_ascii=False,
        )

    switch("qa_vera")
    assert phrase not in narrative()
    assert request(
        app, "read", "read-inbox-question", app_id="questions", actor="qa_vera", ids=[qid]
    ).is_success
    context = narrative()
    assert phrase in context and "Вопрос от Аноним" in context
    switch("qa_oleg")
    assert phrase not in narrative()
    assert phrase not in client.get(f"/api/saves/{sid}").text
    assert not get(app, "questions", tab="inbox")["items"]
    assert not client.get(f"/api/saves/{sid}/apps/questions", params={"item": qid}).is_success


def test_retry_second_invitation_reuses_first_recipient_decision(app):
    from phone277_provider import reply

    repo, _, sid = app
    listing = fill(app, "events", "retry-two-invites")[0]
    jid = dispatch(
        app,
        "invite",
        "invite-two",
        app_id="events",
        target=listing["id"],
        text="Пойдём на концерт вместе?",
        ids=["qa_vera", "qa_oleg"],
    )

    def interrupt_second(messages):
        data = json.loads(messages[1]["content"])
        if any(c["id"] == "qa_oleg" for c in data.get("actors", [])):
            raise ValueError("Ответ второго адресата временно недоступен.")
        return reply(messages)

    run(app, jid, interrupt_second, expect="error")
    state = repo.get_snapshot(sid)["world_state"]
    assert len(state["smartphone"]["invitations"]) == 2
    repo.retry_job(jid)

    def resume(messages):
        data = json.loads(messages[1]["content"])
        assert not any(c["id"] == "qa_vera" for c in data.get("actors", []))
        return reply(messages)

    assert run(app, jid, resume) == 3
    state = repo.get_snapshot(sid)["world_state"]
    assert len(state["smartphone"]["invitations"]) == 2
    assert sum(p["description"] == listing["title"] for p in state["scheduled_events"].values()) == 1


def test_recorded_phone_patch_accepts_archived_shapes_but_rejects_changed_content(app):
    from hashlib import sha256
    import pytest
    from backend.runtime_v3.models import StatePatch, StructuralDeltaError, assert_world_state_v3_invariants
    from backend.runtime_v3.smartphone import domain
    from backend.runtime_v3.smartphone_models import CATALOG_FIELDS

    repo, _, sid = app
    sparse = repo.get_snapshot(sid)["world_state"]
    for key in CATALOG_FIELDS:
        sparse["smartphone"].pop(key, None)
    sparse = assert_world_state_v3_invariants(sparse)
    expanded = deepcopy(sparse)
    domain(expanded)
    for recorded in (sparse, expanded):
        assert assert_world_state_v3_invariants(recorded) == recorded
        digest = sha256(json.dumps(recorded, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        patch = StatePatch(digest, recorded["meta"], recorded["camera"], {"smartphone": {"activity_index": 1}})
        for before in (sparse, expanded):
            assert patch.apply(before)["smartphone"]["activity_index"] == 1
        changed = deepcopy(recorded)
        changed["smartphone"]["activity_index"] = 2
        with pytest.raises(StructuralDeltaError, match="другого состояния"):
            patch.apply(changed)


def test_public_network_offstage_voice_and_topics_reach_both_generation_paths(app):
    import threading
    from backend.runtime_v3.models import PersonalityItem, PersonalityProfile
    from backend.runtime_v3.smartphone import domain, publish
    from backend.services.smartphone import consider
    from test_phone122 import CONFIG

    repo, _, sid = app
    fill(app, "events", "music-listing")
    snap = repo.get_snapshot(sid)
    state = snap["world_state"]
    owner = state["camera"]["controlled_actor_id"]
    state["camera"]["present_character_ids"] = [owner]
    snap["campaign"]["campaign"]["culture"] = "Портовый город со своими группами"
    for cid, actor in state["characters"].items():
        if cid == owner:
            continue
        actor["personality"] = PersonalityProfile(items={
            "hobby": PersonalityItem(field="preferences", text="Пластинки " + cid),
            "style": PersonalityItem(field="communication", text="Манера " + cid),
            "private": PersonalityItem(field="fears", text="Закрытый дневник"),
        }).model_dump()
    publish(state, owner, "post", "record-shop", text="Куда переехал магазин пластинок?")
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(snap), sid))

    def inspect(messages):
        instruction, content = (m["content"] for m in messages)
        payload = json.loads(content)
        assert "эмодзи" in instruction and "мем" in instruction
        assert payload["world"]["culture"] == "Портовый город со своими группами"
        assert payload["community"]["places"] and payload["community"]["events"][0]["category"] == "Музыка"
        assert any(p["id"] == "record-shop" for p in payload["public_posts"])
        assert "Закрытый дневник" not in content and "Тайное действие в сцене" not in content
        assert all(a["id"] not in state["camera"]["present_character_ids"] for a in payload["authors"])
        for actor in payload["authors"]:
            assert actor["voice"]["preferences"] == "Пластинки " + actor["id"]
            assert actor["voice"]["communication"] == "Манера " + actor["id"]
        batch = response(messages)
        batch["actions"][0]["text"] = "кто на винил? 🎧"
        return batch

    assert run(app, dispatch(app, "refresh", "offstage-refresh"), inspect) == 1
    assert any(p["post"]["text"] == "кто на винил? 🎧" for p in get(app, "social")["entries"])

    before = deepcopy(snap)
    state["meta"]["world_time"] += 360
    domain(state)["activity_index"] = 0
    calls = []

    def generate(stage, messages, *args, **kwargs):
        calls.append(stage)
        yield json.dumps(inspect(messages), ensure_ascii=False)

    history = dict(state_changes=[], events=[dict(text="Тайное действие в сцене", medium="action",
                                                  witnesses=list(state["characters"]), fact_ids=[])])
    warnings = []
    consider(before, snap, history, CONFIG, generate, threading.Event(), warnings)
    assert calls == ["social_activity"] and not warnings
    assert any(p["text"] == "кто на винил? 🎧" for p in domain(snap["world_state"])["publications"].values())
