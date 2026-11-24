"""Explicit smartphone commands and read models. All identities belong to one snapshot."""

from backend.runtime_v3.calendar import age_on, exact_age, current_time, profile_of
from backend.runtime_v3.kinship import visible_name
from backend.runtime_v3.reproduction import known_birth
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.models import Fact, Knowledge, identity
from backend.runtime_v3.portraits import projection as portrait
from backend.runtime_v3.smartphone_models import (
    CATALOG_COLLECTIONS,
    DatingShelf,
    Publication,
    Reaction,
    ScenePublication,
    SmartphoneState,
)


def access(snapshot, app, *, write=False):
    state = snapshot["world_state"]
    actor = state["camera"]["controlled_actor_id"]
    cfg = state["meta"]["communication"]
    enabled = {
        "calls": cfg["voice_call"],
        "messages": cfg["text_message"],
        "contacts": cfg["voice_call"] or cfg["text_message"],
        "social": cfg.get("social", cfg.get("preset") == "modern"),
        "dating": cfg.get("dating", cfg.get("preset") == "modern"),
    }
    from backend.runtime_v3.phone_listings import CATALOGS, available
    if app in CATALOGS or app == "questions":
        enabled[app] = available(state, app)
    if cfg["presentation"] != "phone" or not enabled.get(app) or actor not in state["characters"]:
        raise ValueError("Приложение недоступно в этом мире.")
    if write and not capabilities(state, actor)["can_act"]:
        raise ValueError("Персонаж сейчас не может действовать.")
    if app == "dating":
        person = state["characters"][actor]
        age = age_on(person.get("birth_date"), current_time(state)["date"], profile_of(state))
        stage = person.get("developmental_stage")
        if age is None and stage in ("unknown", None):
            card = next((c for c in snapshot["character_cards"] if c["id"] == actor), None)
            if card:
                age = exact_age(card)
        if (
            age is None
            and stage != "adult"
            or age is not None
            and age < 18
            or stage in ("infant", "child", "adolescent")
        ):
            raise ValueError("Знакомства доступны взрослым персонажам.")
    return actor


def domain(state):
    if "smartphone" not in state:
        state["smartphone"] = SmartphoneState().model_dump()
    data = state["smartphone"]
    # Raw historical snapshots precede these optional collections.
    for key in CATALOG_COLLECTIONS:
        data.setdefault(key, {})
    data.setdefault("activity_index", 0)
    return data


def shelf(state, actor):
    shelves = domain(state)["dating"]
    if actor not in shelves:
        shelves[actor] = DatingShelf().model_dump()
    return shelves[actor]


def candidate(state, actor, cid):
    item = shelf(state, actor)["candidates"].get(cid)
    if not item:
        raise ValueError("Анкета недоступна.")
    return item


def perceive(state, actor, record):
    fid = identity("public_statement", record["id"])
    if fid not in state["facts"]:
        state["facts"][fid] = Fact(
            id=fid,
            text=f"Публикация {record['author'] or domain(state)['articles'][record['id']]['source']}: «{record['text']}»",
            character_ids=[record["author"]] if record["author"] else [],
        ).model_dump()
    key = actor + ":" + fid
    if key not in state["knowledge"]:
        state["knowledge"][key] = Knowledge(
            actor_id=actor, fact_id=fid, revision=1, confirmed_once=True, source_turn=state["meta"]["turn_id"]
        ).model_dump()


def publication(state, rid):
    row = domain(state)["publications"].get(rid)
    if not row:
        raise ValueError("Публикация недоступна.")
    return row


def publish(state, actor, kind, rid, *, target=None, text=None, desired=True):
    data = domain(state)
    rows = data["publications"]
    minute = state["meta"]["world_time"]
    parent = publication(state, target) if kind != "post" else None
    if kind in ("post", "comment"):
        if rid in rows:
            return rid
        row = Publication(
            id=rid,
            author=actor,
            text=text,
            minute=minute,
            sequence=data["sequence"] + 1,
            post_id=(parent["post_id"] or target) if parent else None,
            reply_to=target if parent else None,
        ).model_dump()
        rows[rid] = row
        if actor:
            perceive(state, actor, row)
    else:
        if kind == "repost" and parent["post_id"]:
            raise ValueError("Репост доступен для исходной публикации.")
        key = identity(kind, actor, target)
        if (key in data["reactions"]) == desired:
            return target
        if desired:
            data["reactions"][key] = Reaction(
                kind=kind, target=target, author=actor, minute=minute, sequence=data["sequence"] + 1
            ).model_dump()
        else:
            del data["reactions"][key]
    if parent:
        perceive(state, actor, parent)
    data["sequence"] += 1
    return rid if kind in ("post", "comment") else target


def external_posts(data):
    return data["articles"].keys() | {q["publication_id"] for q in data["questions"].values() if q["publication_id"]}


def activity(state, actor):
    data = domain(state)
    rows = data["publications"]
    external = external_posts(data)
    for item in rows.values():
        if (item["post_id"] or item["id"]) in external:
            continue
        if item["author"] != actor and (not item["post_id"] or rows[item["reply_to"]]["author"] == actor):
            yield item
    for item in data["reactions"].values():
        if (rows[item["target"]]["post_id"] or item["target"]) not in external and item["author"] != actor and rows[item["target"]]["author"] == actor:
            yield item


def remote_count(state, actor, channel):
    return sum(
        e["channel"] == channel
        and actor in e["recipient_ids"]
        and e["sender_id"] != actor
        and (channel == "VOICE_CALL" or actor in e["delivered_to"])
        for e in state["remote_events"].values()
    )


def markers(state, actor):
    data = domain(state)
    from backend.runtime_v3.phone_listings import badge_events, work_notifications
    counts = {k: max(v, default=0) for k,v in badge_events(state, actor).items()}
    counts["events"] = sum(e.get("version",1) for e in data["listings"].values())
    counts["work"] = len(data["vacancies"]) + work_notifications(state, actor)
    return dict(
        **counts, social=data["sequence"],
        calls=remote_count(state, actor, "VOICE_CALL"),
        messages=remote_count(state, actor, "TEXT_MESSAGE"),
    )


def badges(state, actor):
    seen = domain(state)["opened"].get(actor, {})
    counts = markers(state, actor)
    counts["social"] = sum(i["sequence"] > seen.get("social", 0) for i in activity(state, actor))
    from backend.runtime_v3.phone_listings import badge_events
    for app, seq in badge_events(state, actor).items():
        if app not in ("work","events"):
            counts[app] = sum(n > seen.get(app, 0) for n in seq)
    for app in ("messages", "calls", "work", "events"):
        counts[app] = max(0, counts[app] - seen.get(app, 0))
    return counts


def subject(snapshot, cid):
    state = snapshot["world_state"]
    actor = state["characters"].get(cid)
    observer = state["camera"]["controlled_actor_id"]
    if not actor:
        raise ValueError("Профиль недоступен.")
    if not known_birth(state, cid, observer):
        return dict(id="", name="Неизвестный участник", portrait=None, silhouette="neutral")
    name = actor.get("display_name") or next(
        (c["name"] for c in snapshot["character_cards"] if c["id"] == cid), cid
    )
    return dict(id=cid, name=visible_name(state, cid, observer, name), **portrait(state, cid))


def social_view(snapshot, *, profile=None, post=None, before=None, limit=20):
    state = snapshot["world_state"]
    actor = access(snapshot, "social")
    if profile and (profile not in state["characters"] or not known_birth(state, profile, actor)):
        raise ValueError("Профиль недоступен.")
    data = domain(state)
    rows, reactions = data["publications"], data["reactions"]
    counts, mine, comments = {}, set(), {}
    for reaction in reactions.values():
        key = (reaction["kind"], reaction["target"])
        counts[key] = counts.get(key, 0) + 1
        if reaction["author"] == actor:
            mine.add(key)
    for row in rows.values():
        if row["post_id"]:
            comments.setdefault(row["post_id"], []).append(row)

    external = external_posts(data)

    def card(row):
        key = row["id"]
        return dict(
            **row,
            subject=subject(snapshot, row["author"]) if row["author"] else dict(id="", name=data["articles"][key]["source"], portrait=None, silhouette="neutral"),
            likes=counts.get(("like", key), 0),
            liked=("like", key) in mine,
            reposts=counts.get(("repost", key), 0),
            reposted=("repost", key) in mine,
            comments=len(comments.get(key, [])),
        )

    if post:
        original = publication(state, post)
        original = publication(state, original["post_id"]) if original["post_id"] else original
        return dict(post=card(original), comments=[card(c) for c in comments.get(original["id"], [])])
    entries = [
        (r["minute"], r["sequence"], r["id"], None)
        for r in rows.values()
        if not r["post_id"] and r["id"] not in external and (not profile or r["author"] == profile)
    ]
    entries.extend(
        (r["minute"], r["sequence"], r["target"], r["author"])
        for r in reactions.values()
        if r["kind"] == "repost" and (not profile or r["author"] == profile)
    )
    entries.sort(reverse=True)
    if before:
        entries = [e for e in entries if e[:2] < before]
    page = entries[:limit]
    return dict(
        profile=dict(subject=subject(snapshot, profile), bio=data["profiles"].get(profile, ""))
        if profile
        else None,
        entries=[
            dict(post=card(rows[rid]), sequence=seq, by=subject(snapshot, by) if by else None)
            for _, seq, rid, by in page
        ],
        next=f"{page[-1][0]},{page[-1][1]}" if len(entries) > limit else None,
    )


def dating_view(snapshot):
    state = snapshot["world_state"]
    actor = access(snapshot, "dating")
    book = shelf(state, actor)

    def public(c):
        entry = {k: v for k, v in c.items() if k != "job_id"}
        if c["character_id"]:
            person = state["characters"][c["character_id"]]
            age = age_on(person.get("birth_date"), current_time(state)["date"], profile_of(state))
            if age is not None:
                entry["age"] = age
        return entry

    return dict(
        searched=book.get("searched", bool(book["results"])),
        filters=book["filters"],
        results=[public(book["candidates"][cid]) for cid in book["results"]],
        liked=[public(c) for c in book["candidates"].values() if c["character_id"]],
    )


def narrative_publications(resolver, rows):
    state = resolver.state
    if not rows:
        return
    if resolver.scene_version < 11 or not state["meta"]["communication"].get("social"):
        raise ValueError("Публикации недоступны в этом мире.")
    for proposal in rows:
        row = ScenePublication.model_validate(proposal).model_dump()
        actor = row["author"]
        if actor not in state["characters"] or not capabilities(state, actor)["can_act"]:
            raise ValueError("Недоступный автор публикации.")
        if actor == resolver.protected_actor_id:
            quote = row.get("player_evidence", "").strip()
            if resolver.mode == "background" or not quote or quote not in resolver.player_input:
                raise ValueError("Нет явного действия управляемого персонажа.")
        rid = identity("scene_post", resolver.turn_id, actor, row.get("target"), row["text"])
        publish(
            state,
            actor,
            "comment" if row.get("target") else "post",
            rid,
            text=row["text"],
            target=row.get("target"),
        )


def publication_patch(before, after):
    """Narrative can add posts/reactions and move the scheduling cursor."""
    patch = {}
    for key in ("sequence", "last_considered", "activity_index"):
        if after.get(key) != before.get(key):
            patch[key] = after[key]
    for key in ("publications", "reactions", "articles", "questions", "listings", "vacancies", "invitations", "attendance_plans"):
        added = {k: v for k, v in after.get(key, {}).items() if before.get(key, {}).get(k) != v}
        if added:
            patch[key] = added
    return patch


def validate_links(state):
    data = state["smartphone"]
    actors, rows = state["characters"], data["publications"]
    from backend.runtime_v3.phone_listings import validate_links as validate_listings
    validate_listings(state)
    for key, row in rows.items():
        if (row["author"] not in actors and not (row["author"] is None and key in data.get("articles", {}))) or row["id"] != key or row["sequence"] > data["sequence"]:
            raise ValueError("Некорректная ссылка на публикацию.")
        if row["post_id"]:
            post, parent = rows.get(row["post_id"]), rows.get(row["reply_to"])
            if (
                not post
                or post["post_id"]
                or not parent
                or (parent["post_id"] or parent["id"]) != row["post_id"]
            ):
                raise ValueError("Некорректная ссылка на обсуждение.")
    for key, r in data["reactions"].items():
        if (
            r["target"] not in rows
            or r["author"] not in actors
            or key != identity(r["kind"], r["author"], r["target"])
        ):
            raise ValueError("Некорректная ссылка на реакцию.")
    if (data["profiles"].keys() | data["opened"].keys() | data["dating"].keys()) - actors.keys():
        raise ValueError("Неизвестный владелец приложения.")
    for book in data["dating"].values():
        if set(book["results"]) - book["candidates"].keys():
            raise ValueError("Некорректная ссылка на анкету.")
        for key, c in book["candidates"].items():
            if key != c["id"] or (c["character_id"] and c["character_id"] not in actors):
                raise ValueError("Неизвестный персонаж анкеты.")


def launcher_notices(snapshot, actor, events):
    state = snapshot["world_state"]
    notices = []
    incoming = next((e for e in reversed(events) if e["unread"] and e["conversation_id"]), None)
    if incoming:
        notices.append(
            dict(
                app="messages",
                screen="conversation",
                id=incoming["conversation_id"],
                label="Сообщение · " + incoming["label"],
            )
        )
    if state["meta"]["communication"].get("social"):
        seen = domain(state)["opened"].get(actor, {}).get("social", 0)
        recent = max(
            (
                r
                for r in activity(state, actor)
                if r["sequence"] > seen and (r.get("post_id") or r.get("kind"))
            ),
            key=lambda r: r["sequence"],
            default=None,
        )
        if recent:
            notices.append(
                dict(
                    app="social",
                    screen="post",
                    id=recent.get("post_id") or recent["target"],
                    label="Реакция · " + subject(snapshot, recent["author"])["name"],
                )
            )
    if state["meta"]["communication"].get("social"):
        data = domain(state)
        mark = data["opened"].get(actor,{}).get("questions",0)
        from backend.runtime_v3.phone_listings import question_activity
        latest = max((r for r in question_activity(data,actor) if r[0]>mark), default=None)
        if latest:
            _,qid,label = latest
            notices.append(dict(app="questions",screen="detail",id=qid,label=label))
    return notices
