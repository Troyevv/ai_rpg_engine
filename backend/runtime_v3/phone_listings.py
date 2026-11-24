"""Branch-owned public listings and personal actions on the Narrative phone."""

from itertools import chain

from backend.runtime_v3.calendar import calendar_label, current_time
from backend.runtime_v3.models import ScheduledEvent, identity
from backend.runtime_v3.remote import apply as remote_action, visible_commitments
from backend.runtime_v3.reproduction import known_birth
from backend.runtime_v3.residence import visible_social_state
from backend.runtime_v3.smartphone_models import Application, Question

CATALOGS = {"news": "articles", "events": "listings", "work": "vacancies"}


def available(state, app):
    cfg = state["meta"]["communication"]
    return bool(
        cfg.get("social", cfg.get("preset") == "modern")
        and (app not in ("events", "work") or cfg["text_message"])
    )


def tick(data):
    data["sequence"] += 1
    return data["sequence"]


def employer(row):
    return row["organization_id"] or "label:" + " ".join(row["employer"].casefold().split())


def employer_keys(state, row):
    key = employer(row)
    keys = [key, "label:" + " ".join(row["employer"].casefold().split())]
    org = state["organizations"].get(row["organization_id"])
    if org:
        keys.extend("label:" + " ".join(n.casefold().split()) for n in [org["name"], *org["aliases"]])
    return list(dict.fromkeys(keys))


def linked_representative(state, row):
    reps = state.get("smartphone", {}).get("representatives", {})
    return next((reps[k] for k in employer_keys(state, row) if k in reps), None)


def live(row, now):
    if "start" in row:
        return not row["cancelled"] and (row["end"] if row["end"] is not None else row["start"]) >= now
    return not row["closed"] and (row["expires"] is None or row["expires"] >= now)


def require(rows, rid):
    if rid not in rows:
        raise ValueError("Запись недоступна.")
    return rows[rid]


def ask(state, sender, recipient, text, anonymous, rid):
    from backend.runtime_v3.smartphone import domain

    if (
        recipient == sender
        or recipient not in state["characters"]
        or not known_birth(state, recipient, sender)
    ):
        raise ValueError("Выбери доступного адресата.")
    data = domain(state)
    data["questions"][rid] = Question(
        id=rid,
        sender=sender,
        recipient=recipient,
        anonymous=anonymous,
        text=text,
        sequence=tick(data),
        minute=state["meta"]["world_time"],
    ).model_dump()


def answer(state, actor, q, text):
    from backend.runtime_v3.smartphone import publish

    if q["recipient"] != actor or q["publication_id"] or q["hidden"]:
        raise ValueError("Этот вопрос уже обработан или адресован другому персонажу.")
    perceive_question(state, actor, q)
    q["publication_id"] = publish(state, actor, "post", identity("answer", q["id"]), text=text)


def question_view(snapshot, q):
    from backend.runtime_v3.smartphone import subject

    return dict(
        id=q["id"],
        text=q["text"],
        recipient=subject(snapshot, q["recipient"]),
        sender=None if q["anonymous"] else subject(snapshot, q["sender"]),
        publication_id=q["publication_id"],
        minute=q["minute"],
        sequence=q["sequence"],
    )


def plan_key(actor, listing):
    return identity("attendance", actor, listing)


def personal_plan(state, actor, listing):
    plans = state["scheduled_events"]
    return next(
        (
            plans[pid]
            for pid, lid in state["smartphone"]["attendance_plans"].items()
            if lid == listing and plans[pid]["character_ids"] == [actor] and plans[pid]["status"] == "pending"
        ),
        None,
    )


def attendance(state, actor, row, desired):
    old = personal_plan(state, actor, row["id"])
    key = plan_key(actor, row["id"])
    if desired:
        now = state["meta"]["world_time"]
        if not live(row, now) or row["start"] < now:
            raise ValueError("Мероприятие уже недоступно для планирования.")
        if old and old["status"] == "pending":
            return
        if key in state["scheduled_events"]:
            key = identity("attendance", actor, row["id"], tick(state["smartphone"]))
        state["smartphone"]["attendance_plans"][key] = row["id"]
        state["scheduled_events"][key] = ScheduledEvent(
            id=key,
            description=row["title"],
            character_ids=[actor],
            due_minute=row["start"],
            location_id=row["location_id"],
            commitment=True,
            time_semantics="explicit",
            time_reference_minute=now,
            evidence="Личный план посещения: " + row["title"],
            source_turn=state["meta"]["turn_id"],
        ).model_dump()
    elif old and old["status"] == "pending":
        old.update(status="cancelled", outcome="cancelled")


def send(snapshot, sender, recipient, text, operation, *, autonomous=False):
    after, history = remote_action(
        snapshot,
        dict(action="send", operation_id=operation, character_id=recipient, content=text),
        actor_id=sender,
        autonomous=autonomous,
    )
    snapshot.update(after)
    return identity("remote", sender, operation), history


def merge_history(target, batch):
    for section, rows in batch.items():
        target.setdefault(section, []).extend(rows)


def command(snapshot, cmd, job_id, history):
    from backend.runtime_v3.smartphone import domain

    state = snapshot["world_state"]
    data = domain(state)
    actor, target = cmd.actor_id, cmd.target
    if cmd.action == "ask":
        ask(state, actor, target, cmd.text.strip(), cmd.desired, identity("question", cmd.operation_id))
    elif cmd.action in ("answer", "hide"):
        q = require(data["questions"], target)
        if q["recipient"] != actor or q["publication_id"]:
            raise ValueError("Нет доступного входящего вопроса.")
        if cmd.action == "answer":
            answer(state, actor, q, cmd.text.strip())
        else:
            q["hidden"] = True
    elif cmd.action in ("plan", "invite"):
        row = require(data["listings"], target)
        if cmd.action == "plan":
            attendance(state, actor, row, cmd.desired)
        else:
            if not live(row, state["meta"]["world_time"]) or not 1 <= len(set(cmd.ids)) <= 16:
                raise ValueError("Выбери получателей и актуальное мероприятие.")
            for cid in dict.fromkeys(cmd.ids):
                eid, batch = send(snapshot, actor, cid, cmd.text, identity("invite", cmd.operation_id, cid))
                domain(snapshot["world_state"])["invitations"][eid] = target
                merge_history(history, batch)
    elif cmd.action in ("favorite", "apply"):
        row = require(data["vacancies"], target)
        if cmd.action == "favorite":
            ids = data["favorites"].setdefault(actor, [])
            if cmd.desired and target not in ids:
                ids.append(target)
            elif not cmd.desired and target in ids:
                ids.remove(target)
        else:
            if not job_id or not live(row, state["meta"]["world_time"]):
                raise ValueError("Отклик недоступен.")
            aid = identity("application", actor, target)
            if aid in data["applications"] and not data["applications"][aid]["event_id"]:
                data["applications"][aid]["job_id"] = job_id
            elif aid not in data["applications"]:
                data["applications"][aid] = Application(
                    actor=actor, vacancy=target, pending_text=cmd.text.strip(), job_id=job_id
                ).model_dump()
    else:
        raise ValueError("Неизвестное действие приложения.")


def invitation_view(snapshot, listing, actor):
    from backend.runtime_v3.smartphone import subject

    state = snapshot["world_state"]
    data = state["smartphone"]
    result = []
    for eid, reference in data["invitations"].items():
        if reference != listing:
            continue
        source = state["remote_events"][eid]
        if source["sender_id"] != actor and actor not in source["read_by"]:
            continue
        thread = source["conversation_id"]
        other = source["recipient_ids"][0] if source["sender_id"] == actor else source["sender_id"]
        later = [
            e
            for e in state["remote_events"].values()
            if e["conversation_id"] == thread
            and e["ordinal"] > source["ordinal"]
            and e["sender_id"] == other
            and actor in e["read_by"]
        ]
        plans = [
            p["description"]
            for p in visible_commitments(state, actor).values()
            if eid in p["remote_source_ids"] and p["status"] == "pending"
        ]
        result.append(
            dict(
                conversation_id=thread,
                person=subject(snapshot, other),
                outgoing=source["sender_id"] == actor,
                reply=later[-1]["content"] if later else None,
                plans=plans,
            )
        )
    return result


def work_threads(state, actor):
    data = state["smartphone"]
    result = {}
    for a in data.get("applications", {}).values():
        if a["actor"] != actor or not a["event_id"]:
            continue
        ev = state["remote_events"][a["event_id"]]
        result.setdefault(ev["conversation_id"], ev)
    return result


def question_activity(data, actor):
    threads = {}
    for q in data["questions"].values():
        if q["recipient"] == actor:
            yield q["sequence"], q["id"], "Новый входящий вопрос"
        pid = q["publication_id"]
        if pid:
            threads[pid] = q
            if q["sender"] == actor:
                yield data["publications"][pid]["sequence"], q["id"], "Опубликован ответ на ваш вопрос"
    for item in chain(data["publications"].values(), data["reactions"].values()):
        if item["author"] == actor:
            continue
        target = data["publications"].get(item.get("reply_to") or item.get("target"))
        if not target:
            continue
        q = threads.get(target["post_id"] or target["id"])
        if q and (target["author"] == actor or actor in (q["recipient"], q["sender"])):
            yield item["sequence"], q["id"], "Обсуждение ответа"


def badge_events(state, actor):
    from backend.runtime_v3.smartphone import domain

    data = domain(state)
    return dict(
        news=[data["publications"][k]["sequence"] for k in data["articles"]],
        questions=[n for n, _, _ in question_activity(data, actor)],
    )


def work_notifications(state, actor):
    threads = work_threads(state, actor)
    return sum(
        e["conversation_id"] in threads
        and e["ordinal"] > threads[e["conversation_id"]]["ordinal"]
        and actor in e["delivered_to"]
        for e in state["remote_events"].values()
    )


def view(
    snapshot,
    app,
    *,
    item=None,
    tab="",
    profile=None,
    query="",
    category="",
    place="",
    kind="",
    date="",
    cursor=None,
    limit=20,
):
    from backend.runtime_v3.smartphone import access, domain

    actor = access(snapshot, app)
    state = snapshot["world_state"]
    data = domain(state)
    now = state["meta"]["world_time"]
    records = []
    roles = []
    if app == "questions":
        for q in data["questions"].values():
            public = bool(q["publication_id"])
            visible = (q["recipient"] == actor and not q["hidden"]) or q["sender"] == actor or public
            if not visible:
                continue
            if not item and not (
                q["recipient"] == actor and not public and not q["hidden"]
                if tab == "inbox"
                else q["sender"] == actor
                if tab == "sent"
                else public and (not profile or profile == q["recipient"])
            ):
                continue
            if item and item != q["id"]:
                continue
            records.append(question_view(snapshot, q))
    else:
        favorites = data["favorites"].get(actor, [])
        for key, row in data[CATALOGS[app]].items():
            if item and item != key:
                continue
            if category and category != row["category"] or place and place != row.get("location_id"):
                continue
            result = dict(row, id=key)
            if app == "news":
                p = data["publications"][key]
                result.update(minute=p["minute"], sequence=p["sequence"], publication_id=key)
            else:
                result.update(
                    active=live(row, now), location=state["locations"].get(row["location_id"], {}).get("name")
                )
            if app == "events":
                result["time"] = calendar_label(state, row["start"])
                result["end_time"] = calendar_label(state, row["end"]) if row["end"] is not None else None
                when = current_time(state, row["start"])
                if date and date not in (when["date"], str(when["day"])):
                    continue
                plan = personal_plan(state, actor, key)
                result["planned"] = bool(plan and plan["status"] == "pending")
                result["can_plan"] = result["active"] and row["start"] >= now
                if item:
                    result["invitations"] = invitation_view(snapshot, key, actor)
                result["previous_time"] = (
                    calendar_label(state, row["previous_start"])
                    if row.get("previous_start") is not None
                    else None
                )
            if app == "work":
                a = data["applications"].get(identity("application", actor, key))
                if (
                    kind
                    and kind != row["employment"]
                    or tab == "favorites"
                    and key not in favorites
                    or tab == "mine"
                    and not a
                ):
                    continue
                result.update(
                    favorite=key in favorites,
                    applied=bool(a),
                    conversation_id=None,
                    expires_at=calendar_label(state, row["expires"]) if row["expires"] is not None else None,
                )
                if item and a and not a["event_id"]:
                    result["pending_text"] = a["pending_text"]
                if a and a["event_id"]:
                    result["conversation_id"] = state["remote_events"][a["event_id"]]["conversation_id"]
                    latest = next(
                        (
                            e
                            for e in reversed(list(state["remote_events"].values()))
                            if e["conversation_id"] == result["conversation_id"]
                            and e["sender_id"] != actor
                            and actor in e["read_by"]
                            and e["ordinal"] > state["remote_events"][a["event_id"]]["ordinal"]
                        ),
                        None,
                    )
                    result["reply"] = latest["content"] if latest else None
                    if item:
                        result["plans"] = [
                            dict(id=p["id"], description=p["description"], location_id=p["location_id"])
                            for p in visible_commitments(state, actor).values()
                            if p["status"] == "pending"
                            and actor in p["character_ids"]
                            and any(
                                state["remote_events"].get(e, {}).get("conversation_id")
                                == result["conversation_id"]
                                for e in p["remote_source_ids"]
                            )
                        ]
            if (
                query
                and query.casefold()
                not in " ".join(
                    str(result.get(k) or "")
                    for k in ("title", "description", "category", "location", "employer", "requirements")
                ).casefold()
            ):
                continue
            records.append(result)
        if app == "work" and tab == "roles":
            roles = [
                r for r in visible_social_state(state, actor, {actor})["roles"] if r["kind"] == "employment"
            ]
            for role in roles:
                saved = state["roles"][role["id"]]
                org = state["organizations"].get(saved["organization_id"], {})
                locations = org.get("location_ids", [])
                row = next(
                    (
                        v
                        for v in data["vacancies"].values()
                        if identity("employment", actor, v["id"]) == role["id"]
                    ),
                    None,
                )
                location = row["location_id"] if row and row["location_id"] else next(iter(locations), None)
                if role["status"] == "active" and location:
                    role["workplace"] = state["locations"][location]["name"]
            records = []
    if item and not records:
        raise ValueError("Запись недоступна.")
    records.sort(key=lambda r: (r["minute"], r["sequence"], r["id"]), reverse=True)
    if cursor:
        records = [r for r in records if (r["minute"], r["sequence"]) < cursor]
    page = records[:limit]
    for r in page:
        r["published"] = calendar_label(state, r["minute"])
    options = data.get(CATALOGS.get(app), {}).values()
    dates = {}
    if app == "events":
        for row in options:
            when = current_time(state, row["start"])
            dates[when["date"] or str(when["day"])] = when["date"] or f"День {when['day']}"
    return dict(
        items=page,
        dates=dates,
        next=f"{page[-1]['minute']},{page[-1]['sequence']}" if len(records) > limit else None,
        categories=sorted({r["category"] for r in options}),
        roles=roles,
        places={
            r["location_id"]: state["locations"][r["location_id"]]["name"]
            for r in options
            if r.get("location_id")
        },
    )


def thread_listings(state, conversation):
    """Only references owned by this direct conversation, never another applicant's history."""
    data = state.get("smartphone", {})
    events = state["remote_events"]
    return [
        (a, data["vacancies"][a["vacancy"]])
        for a in data.get("applications", {}).values()
        if a["event_id"] and events[a["event_id"]]["conversation_id"] == conversation
    ]


class InvalidEmploymentChange(ValueError):
    def __init__(self, section, index, message):
        super().__init__(message)
        self.section = section
        self.index = index


def bind_job_changes(state, source, rows, raw):
    """Extraction identifies an effective hire; Runtime binds fresh assent and a read offer."""
    applications = {v["id"]: (a, v) for a, v in thread_listings(state, source["conversation_id"])}
    by_id = {e["id"]: e for e in rows}
    orgs = {}
    roles = []
    for index, change in enumerate(raw.records["role_changes"]):
        if not isinstance(change, dict) or not all(
            isinstance(change.get(key), str) and change[key].strip()
            for key in ("vacancy_id", "offer_event_id", "title")
        ):
            raise InvalidEmploymentChange(
                "role_changes", index, "Нужны идентификаторы вакансии и предложения, а также название роли."
            )
        a, vacancy = applications.get(change.get("vacancy_id"), (None, None))
        offer = by_id.get(change.get("offer_event_id"))
        actor = state["camera"]["controlled_actor_id"]
        if (
            not a
            or a["actor"] != actor
            or source["sender_id"] != actor
            or not offer
            or source["id"] != change.get("player_source_id")
            or source["id"] == a["event_id"]
            or offer["sender_id"] not in source["recipient_ids"]
            or actor not in offer["read_by"]
            or offer["sender_id"] not in source["read_by"]
            or not state["remote_events"][a["event_id"]]["ordinal"] < offer["ordinal"] < source["ordinal"]
            or change.get("player_assertion") != "explicit_choice"
            or change.get("player_evidence") != source["content"]
            or change.get("effective") != "now"
            or change.get("actor_id") != actor
            or change.get("status", "active") != "active"
            or change.get("assertion", "established") != "established"
            or change.get("replaces")
        ):
            raise InvalidEmploymentChange(
                "role_changes",
                index,
                "Для трудоустройства нужны прочитанное предложение и текущее явное согласие на действующую работу.",
            )
        org = vacancy["organization_id"]
        if not org:
            org = next(
                (
                    o["id"]
                    for o in state["organizations"].values()
                    if vacancy["employer"].casefold() in {n.casefold() for n in [o["name"], *o["aliases"]]}
                ),
                identity("employer_org", employer(vacancy)),
            )
            if org not in state["organizations"]:
                orgs[org] = dict(
                    id=org,
                    name=vacancy["employer"],
                    status="active",
                    evidence=offer["content"],
                    location_ids=[vacancy["location_id"]] if vacancy["location_id"] else [],
                )
        rid = identity("employment", actor, vacancy["id"])
        roles.append(
            dict(
                id=rid,
                actor_id=actor,
                title=change["title"],
                kind="employment",
                organization_id=org,
                fact_id=identity("communicated_text", offer["id"]),
                assertion="established",
                transition="voluntary",
                player_assertion="explicit_choice",
                player_evidence=source["content"],
                evidence=source["content"],
            )
        )
    associated_names = {r["name"] for r in orgs.values()}
    for role in roles:
        org = state["organizations"].get(role["organization_id"])
        if org:
            associated_names.update([org["name"], *org["aliases"]])
    for index, o in enumerate(raw.records["organization_changes"]):
        if (
            not isinstance(o, dict)
            or not isinstance(o.get("name"), str)
            or o["name"] not in associated_names
            or o.get("status", "active") != "active"
        ):
            raise InvalidEmploymentChange(
                "organization_changes", index, "Организация не связана с подтверждённой работой."
            )
    raw.records["organization_changes"] = list(orgs.values())
    raw.records["role_changes"] = roles


def perceive_question(state, actor, q):
    from backend.runtime_v3.models import Fact, Knowledge

    if not q["publication_id"] and actor not in (q["sender"], q["recipient"]):
        raise ValueError("Вопрос недоступен.")
    fid = identity("question_statement", q["id"])
    # The receipt records the text the recipient saw, including only disclosed authorship.
    sender = (
        "Аноним" if q["anonymous"] else state["characters"][q["sender"]].get("display_name") or q["sender"]
    )
    state["facts"].setdefault(
        fid,
        Fact(
            id=fid,
            text=f"Вопрос от {sender}: «{q['text']}»",
            visibility="secret",
            character_ids=[q["recipient"]],
        ).model_dump(),
    )
    key = actor + ":" + fid
    state["knowledge"].setdefault(
        key,
        Knowledge(
            actor_id=actor, fact_id=fid, revision=1, confirmed_once=True, source_turn=state["meta"]["turn_id"]
        ).model_dump(),
    )


def validate_links(state):
    data = state["smartphone"]
    actors = state["characters"]
    pubs = data["publications"]
    for rid, article in data["articles"].items():
        post = pubs.get(rid)
        previous = article["previous_id"]
        if (
            not post
            or post["author"] is not None
            or post["post_id"]
            or previous
            and (previous not in data["articles"] or pubs[previous]["sequence"] >= post["sequence"])
        ):
            raise ValueError("Некорректная связь новостной статьи.")
    for qid, q in data["questions"].items():
        pid = q["publication_id"]
        if (
            q["id"] != qid
            or q["sender"] not in actors
            or q["recipient"] not in actors
            or (pid and (pid not in pubs or pubs[pid]["author"] != q["recipient"] or pubs[pid]["post_id"]))
        ):
            raise ValueError("Некорректная связь вопроса.")
    for section in ("listings", "vacancies"):
        for rid, row in data[section].items():
            if (
                rid != row["id"]
                or (row["location_id"] and row["location_id"] not in state["locations"])
                or (row.get("organization_id") and row["organization_id"] not in state["organizations"])
            ):
                raise ValueError("Некорректная ссылка объявления.")
    for cid, ids in data["favorites"].items():
        if cid not in actors or set(ids) - data["vacancies"].keys():
            raise ValueError("Неизвестная избранная вакансия.")
    if set(data["representatives"].values()) - actors.keys():
        raise ValueError("Неизвестный представитель работодателя.")
    for aid, a in data["applications"].items():
        event = state["remote_events"].get(a["event_id"])
        if (
            aid != identity("application", a["actor"], a["vacancy"])
            or a["actor"] not in actors
            or a["vacancy"] not in data["vacancies"]
            or a["event_id"]
            and (not event or event["sender_id"] != a["actor"] or event["operation_id"] != aid)
        ):
            raise ValueError("Некорректная ссылка отклика.")
    for refs, targets in (
        (data["invitations"], state["remote_events"]),
        (data["attendance_plans"], state["scheduled_events"]),
    ):
        if refs.keys() - targets.keys() or set(refs.values()) - data["listings"].keys():
            raise ValueError("Некорректная ссылка мероприятия.")
