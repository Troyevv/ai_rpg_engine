"""Provider contracts for public news, listings and voluntary Q&A."""

import json
from pydantic import Field
from backend.runtime_v3.calendar import profile_of
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.models import identity
from backend.runtime_v3.phone_listings import (
    ask,
    answer,
    employer,
    employer_keys,
    linked_representative,
    live,
    tick,
)
from backend.runtime_v3.smartphone import domain, read_domain, publish
from backend.runtime_v3.smartphone_models import (
    Record,
    Article,
    EventListing,
    Vacancy,
    Short,
    Text,
    PostedVacancy,
    PostedEvent,
)


class Story(Article):
    body: Text


class EventUpdate(Record):
    id: Short
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    cancel: bool = False


class NewsBatch(Record):
    articles: list[Story] = Field(max_length=6)


class EventsBatch(Record):
    events: list[EventListing] = Field(max_length=6)
    updates: list[EventUpdate] = Field(default_factory=list, max_length=4)


class ChangedTerms(Record):
    id: Short
    pay: str | None = Field(default=None, max_length=600)
    schedule: str | None = Field(default=None, max_length=600)
    requirements: str | None = Field(default=None, max_length=2000)


class WorkBatch(Record):
    vacancies: list[Vacancy] = Field(max_length=6)
    updates: list[ChangedTerms] = Field(default_factory=list, max_length=4)
    close: list[Short] = Field(default_factory=list, max_length=4)


SCHEMAS = {"news": NewsBatch, "events": EventsBatch, "work": WorkBatch}


def public_facts(state, audience, *, require_known=False):
    from backend.runtime_v3.reproduction import private_fact_ids
    from backend.runtime_v3.possessions import private_fact_ids as possession_facts

    protected = (
        private_fact_ids(state)
        | possession_facts(state)
        | {c.get("fact_id") for c in state["conditions"].values()}
    )

    def public(fid):
        f = state["facts"].get(fid, {})
        return (
            fid not in protected
            and f.get("visibility") == "public"
            and not f.get("story_secret")
            and not f.get("origin_remote_event_id")
            and not fid.startswith("public_statement_")
            and not f.get("secret_biography_ids")
            and not f.get("secret_subject_ids")
        )

    return {
        fid: f["text"][:350]
        for fid, f in state["facts"].items()
        if public(fid)
        and (
            not require_known and not f.get("character_ids")
            or all(state["knowledge"].get(cid + ":" + fid, {}).get("status") == "known" for cid in audience)
        )
    }


def public_context(snapshot, history):
    from backend.services.smartphone import setting
    from backend.runtime_v3.birth_identity import is_game_birth

    state = snapshot["world_state"]
    data = read_domain(state)
    world = setting(snapshot)
    campaign = snapshot.get("campaign", {})
    campaign = campaign.get("campaign", campaign)
    for key in ("title", "setting", "era", "genre", "tone", "technology", "culture", "public_description"):
        if isinstance(campaign.get(key), str):
            world["world"][key] = campaign[key][:900]
    # Surface labels only. Never include location descriptions, sheets, private correspondence or intentions.
    people = {
        cid: c.get("display_name") or cid
        for cid, c in state["characters"].items()
        if not is_game_birth(state, cid)
    }
    facts = public_facts(state, people)
    recent = []
    for e in history:
        if e.get("medium") not in ("action", "observation") or e.get("interaction_channel") in (
            "phone",
            "call",
        ):
            continue
        ids = e.get("fact_ids", [])
        # Use public propositions verbatim, never the private literary scene around them.
        texts = [facts[k] for k in ids if k in facts]
        if texts and e.get("id"):
            recent.append(dict(id=e["id"], minute=e.get("minute"), text=" ".join(texts)[:500]))
    cfg = state["meta"]["communication"]
    orgs = {
        k: o
        for k, o in state["organizations"].items()
        if o["status"] != "closed" and (not o.get("fact_id") or o["fact_id"] in facts)
    }

    def recent_rows(rows):
        return sorted(rows, key=lambda r: r["sequence"], reverse=True)[:10]

    def listing_history(key):
        rows = list(data[key].values())
        selected = recent_rows(rows)
        # Retain negative context even if a burst of newer active listings pushed it off the first page.
        closed = [
            r for r in reversed(rows) if not live(r, state["meta"]["world_time"]) and r not in selected
        ][:3]
        return [
            {
                k: (r[k][:180] if isinstance(r[k], str) else r[k])
                for k in (
                    "id",
                    "listing_key",
                    "title",
                    "location_id",
                    "start",
                    "end",
                    "cancelled",
                    "expires",
                    "closed",
                    "employer",
                    "organization_id",
                    "employment",
                    "category",
                )
                if k in r
            }
            | (dict(representative_id=linked_representative(state, r)) if key == "vacancies" else {})
            for r in selected + closed
        ]

    from backend.runtime_v3.calendar import nearby_calendar

    calendar_events = nearby_calendar(state, [])
    profile = profile_of(state)
    current_place = state["camera"].get("location_id")
    nearby = set()
    while current_place and current_place not in nearby:
        nearby.add(current_place)
        current_place = state["locations"].get(current_place, {}).get("parent_id")
    places = sorted(state["locations"].values(), key=lambda place: place["id"] not in nearby)
    return dict(
        **world,
        technology={k: cfg[k] for k in ("preset", "presentation", "text_message", "voice_call")},
        calendar_profile={
            k: profile[k] for k in ("system", "month_lengths", "weekday_names") if k in profile
        },
        upcoming_observances=[
            {k: row[k] for k in ("id", "name", "date", "kind") if k in row}
            for row in calendar_events
            if not row.get("character_ids")
        ],
        observances=[
            {k: r[k] for k in ("name", "month", "day", "date") if k in r}
            for r in profile.get("observances", [])
            if not r.get("character_ids")
        ][:12],
        places=[dict(id=place["id"], name=place["name"][:180], kind=place["kind"]) for place in places[:24]],
        organizations=[
            dict(id=k, name=o["name"][:180], locations=o["location_ids"][:6])
            for k, o in list(orgs.items())[:16]
        ],
        public_roles=[
            dict(
                actor_id=role["actor_id"], title=role["title"][:180], organization_id=role["organization_id"]
            )
            for role in state["roles"].values()
            if role["status"] == "active"
            and role["actor_id"] in people
            and role.get("fact_id") in facts
            and (not role["organization_id"] or role["organization_id"] in orgs)
        ][:12],
        people=[
            dict(id=k, name=name[:180], public_bio=data["profiles"].get(k, "")[:220])
            for k, name in list(people.items())[:12]
        ],
        public_facts=list(facts.values())[-8:],
        recent_events=recent[-8:],
        news=[
            dict(
                id=r["id"],
                topic=data["articles"][r["id"]]["topic"],
                title=data["articles"][r["id"]]["title"],
                previous_id=data["articles"][r["id"]]["previous_id"],
                summary=data["articles"][r["id"]]["summary"][:240],
            )
            for r in recent_rows(data["publications"][k] for k in data["articles"])
        ],
        events=listing_history("listings"),
        vacancies=listing_history("vacancies"),
    )


def catalog_prompt(snapshot, app, history):
    from backend.services.smartphone import messages

    ctx = public_context(snapshot, history)
    task = {
        "news": "Опубликуй фоновые и, когда есть основания, событийные статьи. Ссылку event_id бери из recent_events. "
        "Для продолжения темы укажи previous_id. Старые выпуски неизменны. Дай изданию подпись.",
        "events": "Предложи будущие местные мероприятия, учитывай открытые праздники. Используй абсолютные игровые "
        "минуты start/end, известное место либо null. Переносы/отмены оформляй updates по ID.",
        "work": "Предложи разную постоянную работу и подработку с реальными для эпохи условиями. Неизвестные "
        "условия оставь открытыми. Сохраняй название работодателя и канонические ID. Закрытие по ID в close.",
    }[app]
    return messages(
        "Phone catalog/1 "
        + app
        + ". Пиши по-русски. "
        + task
        + " Учитывай культурную среду, географию, технологии, даты и историю. Не дублируй существующие записи, "
        "включая закрытые. Для той же темы сохраняй topic, для мероприятия/вакансии сохраняй listing_key даже при новом заголовке. "
        "Новые условия вакансии оформляй updates, прежнюю запись не открывай повторно. Не утверждай тайны, намерения, действия героя или посещение. Верни JSON по schema.",
        dict(**ctx, schema=SCHEMAS[app].model_json_schema()),
    ), ctx


def apply_catalog(snapshot, app, raw, ctx, seed):
    state = snapshot["world_state"]
    data = domain(state)
    now = state["meta"]["world_time"]
    batch = SCHEMAS[app].model_validate_json(raw)
    section, items = (
        ("articles", batch.articles)
        if app == "news"
        else ("listings", batch.events)
        if app == "events"
        else ("vacancies", batch.vacancies)
    )
    existing = data[section]
    count = 0
    for i, item in enumerate(items):
        rid = identity(app, seed, i)
        if any(
            r["title"].casefold() == item.title.casefold()
            and (app != "work" or employer(r) == employer(item.model_dump()))
            for r in existing.values()
        ):
            continue
        if app != "news" and any(
            r["listing_key"].casefold() == item.listing_key.casefold() for r in existing.values()
        ):
            continue
        if app == "news":
            if not item.previous_id and any(
                r["topic"].casefold() == item.topic.casefold() for r in existing.values()
            ):
                continue
            if (
                item.previous_id
                and item.previous_id not in existing
                or item.event_id
                and item.event_id not in {e["id"] for e in ctx["recent_events"]}
            ):
                continue
            existing[rid] = item.model_dump(exclude={"body"})
            publish(state, None, "post", rid, text=item.body)
        else:
            if item.location_id and item.location_id not in {place["id"] for place in ctx["places"]}:
                continue
            if app == "events" and (
                item.start < now or item.end is not None and item.end < item.start or item.cancelled
            ):
                continue
            if app == "work" and (
                not live(item.model_dump(), now)
                or item.organization_id
                and item.organization_id not in {o["id"] for o in ctx["organizations"]}
            ):
                continue
            model = PostedEvent if app == "events" else PostedVacancy
            fields = item.model_dump()
            if app == "work" and item.organization_id:
                fields["employer"] = state["organizations"][item.organization_id]["name"]
            existing[rid] = model(**fields, id=rid, sequence=tick(data), minute=now).model_dump()
        count += 1
    if app == "events":
        for change in batch.updates:
            row = existing.get(change.id)
            if (
                not row
                or not live(row, now)
                or not change.cancel
                and (
                    change.start is None
                    or change.start <= now
                    or change.end is not None
                    and change.end < change.start
                )
            ):
                continue
            if change.cancel:
                row["cancelled"] = True
            else:
                row.update(previous_start=row["start"], start=change.start, end=change.end)
            row["version"] += 1
            row["sequence"] = tick(data)
            # Existing agreements keep their original date. A changed public slot needs fresh consent.
            personal = {pid for pid, lid in data["attendance_plans"].items() if lid == change.id}
            for plan in state["scheduled_events"].values():
                linked = any(data["invitations"].get(eid) == change.id for eid in plan["remote_source_ids"])
                if (plan["id"] in personal or linked) and plan["status"] == "pending":
                    plan.update(status="cancelled", outcome="cancelled")
            count += 1
    if app == "work":
        for change in batch.updates:
            row = existing.get(change.id)
            if not row or not live(row, now):
                continue
            terms = {
                k: v for k, v in change.model_dump(exclude={"id"}, exclude_none=True).items() if row[k] != v
            }
            if terms:
                row["previous_terms"].append(
                    dict(changed_at=now, **{k: row[k] for k in ("pay", "schedule", "requirements")})
                )
                row.update(terms, sequence=tick(data))
                count += 1
        for rid in batch.close:
            if rid in existing and not existing[rid]["closed"]:
                existing[rid].update(closed=True, sequence=tick(data))
                count += 1
    if not count:
        raise ValueError("Провайдер не вернул новых подходящих публикаций или изменений.")


class Reply(Record):
    answer: Text | None


class Initiative(Record):
    recipient: Short
    text: Text
    anonymous: bool = True


class InitiativeResult(Record):
    question: Initiative | None


def question_prompt(snapshot, recipient, question=None):
    from backend.services.smartphone import NETWORK_VOICE, messages, network_profile, setting
    from backend.runtime_v3.remote_authoring import speaker_context
    from backend.runtime_v3.reproduction import known_birth

    state = snapshot["world_state"]
    if recipient == state["camera"]["controlled_actor_id"] or not capabilities(state, recipient)["can_act"]:
        return None
    if question:
        # One responder only. No job owner, operation ID, hidden sender or surrounding inbox in the payload.
        visible = dict(text=question["text"], sender=None if question["anonymous"] else question["sender"])
        audience = [] if question["anonymous"] else [question["sender"]]
    else:
        visible = None
        audience = [
            cid for cid in state["characters"] if cid != recipient and known_birth(state, cid, recipient)
        ][:16]
    voice = speaker_context(snapshot, recipient, audience)
    return messages(
        "Phone questions/1. Пиши по-русски за одного адресата. " + NETWORK_VOICE
        + " Вопрос или ответ — это реплика в сети. Можно попросить совет, позвать куда-то, подколоть знакомого "
        "или поспорить о любимой музыке. Уважай границы адресата и приватность публичного ответа. "
        + (
            "Можно публично ответить, отказаться или промолчать (answer=null). Не угадывай анонима."
            if question
            else "Задай уместный живой вопрос одному из собеседников либо верни null в question."
        ),
        dict(
            actor=recipient,
            voice=voice,
            profile=network_profile(snapshot, recipient, [recipient]),
            **setting(snapshot),
            question=visible,
            people=audience,
            knowledge=[
                state["facts"][k["fact_id"]]["text"][:320]
                for k in state["knowledge"].values()
                if k["actor_id"] == recipient and k["status"] == "known"
            ][-6:],
            schema=Reply.model_json_schema() if question else InitiativeResult.model_json_schema(),
        ),
    )


def apply_question(snapshot, recipient, question_id, raw, seed):
    state = snapshot["world_state"]
    if state["camera"]["controlled_actor_id"] == recipient or not capabilities(state, recipient)["can_act"]:
        raise ValueError("Персонаж недоступен.")
    if question_id:
        q = domain(state)["questions"][question_id]
        value = Reply.model_validate_json(raw).answer
        if value is not None:
            answer(state, recipient, q, value)
        else:
            q["hidden"] = True
    else:
        q = InitiativeResult.model_validate_json(raw).question
        if q is not None:
            ask(state, recipient, q.recipient, q.text, q.anonymous, identity("question", seed))


def representative(state, row, applicant):
    cid = linked_representative(state, row)
    if cid:
        if cid == applicant or not capabilities(state, cid)["can_act"]:
            raise ValueError("Представитель недоступен для этого отклика.")
        return cid
    # A canonical affiliation is required before reusing an existing person.
    for role in state["roles"].values():
        cid = role["actor_id"]
        if (
            row["organization_id"]
            and role["organization_id"] == row["organization_id"]
            and role["status"] == "active"
            and role["kind"] == "employment"
            and cid != applicant
            and capabilities(state, cid)["can_act"]
        ):
            return cid
    return None


def employer_prompt(snapshot, cmd):
    from backend.services.smartphone import messages
    from backend.services.world import CARD_FIELDS

    state = snapshot["world_state"]
    row = domain(state)["vacancies"][cmd.target]
    if representative(state, row, cmd.actor_id):
        return None
    ctx = public_context(snapshot, [])
    return messages(
        "Phone employer/1. Создай одного канонического представителя указанного работодателя, "
        "который общается с соискателями. Дай полное имя и полностью заполни поля карточки на русском. "
        "Не решай исход отклика. Верни JSON {name,fields}.",
        dict(world=ctx["world"], calendar=ctx["calendar"], vacancy=row, card_fields=CARD_FIELDS),
    )


def deliver_application(snapshot, cmd, raw):
    from backend.services.smartphone import add_character
    from backend.services.npc_review import card_fields
    from backend.runtime_v3.phone_listings import send

    state = snapshot["world_state"]
    data = domain(state)
    row = data["vacancies"][cmd.target]
    key = employer(row)
    cid = representative(state, row, cmd.actor_id)
    if not cid:
        obj = json.loads(raw)
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 240:
            raise ValueError("Не указано имя представителя.")
        cid = identity("employer_npc", key)
        add_character(
            snapshot,
            cid,
            name.strip(),
            card_fields(obj.get("fields"), complete=True),
            dict(life_status="alive", developmental_stage="adult"),
        )
    for alias in employer_keys(state, row):
        data["representatives"][alias] = cid
    aid = identity("application", cmd.actor_id, cmd.target)
    a = data["applications"][aid]
    eid, history = send(snapshot, cmd.actor_id, cid, a["pending_text"], aid)
    domain(snapshot["world_state"])["applications"][aid].update(event_id=eid, pending_text="")
    return history


class Invitation(Record):
    event: Short
    recipient: Short
    text: Text


class InviteResult(Record):
    invitation: Invitation | None


def background_activity(snapshot, history, index, seed):
    """Choose one prompt within #276's existing clock/budget. Private speakers never share a request."""
    from backend.runtime_v3.phone_listings import available, send, merge_history
    from backend.runtime_v3.remote import recipient_eligible
    from backend.services.smartphone import messages, social_prompt, social_result
    from backend.runtime_v3.remote_authoring import speaker_context

    state = snapshot["world_state"]
    data = domain(state)
    owner = state["camera"]["controlled_actor_id"]
    authors = [cid for cid in state["characters"] if cid != owner and capabilities(state, cid)["can_act"]]
    activities = ["social", "news", "questions", "events", "work", "invitation"]
    activity = activities[index % len(activities)]
    if activity in ("work", "events", "invitation") and not available(state, "events"):
        activity = "news"
    if activity in SCHEMAS:
        prompt, ctx = catalog_prompt(snapshot, activity, history.get("events", []))

        def apply(after, raw, batch):
            apply_catalog(after, activity, raw, ctx, seed)

        return prompt, apply
    if not authors:
        return None, None
    cid = authors[(index // len(activities)) % len(authors)]
    if activity == "questions":
        pending = next(
            (
                q
                for q in data["questions"].values()
                if q["recipient"] in authors and not q["hidden"] and not q["publication_id"]
            ),
            None,
        )
        if pending:
            cid = pending["recipient"]
        prompt = question_prompt(snapshot, cid, pending)

        def apply(after, raw, batch):
            apply_question(after, cid, pending["id"] if pending else None, raw, seed)

        return prompt, apply
    if activity == "invitation":
        events = [r for r in data["listings"].values() if live(r, state["meta"]["world_time"])][-5:]
        people = [
            p for p in state["characters"] if p != cid and recipient_eligible(state, cid, p, "TEXT_MESSAGE")
        ][:12]
        if events and people:
            prompt = messages(
                "Phone invitation/1. Можешь пригласить одного знакомого на конкретное мероприятие "
                "в обычном чате или вернуть invitation=null. Не утверждай согласие адресата. Напиши по-русски.",
                dict(
                    actor=cid,
                    voice=speaker_context(snapshot, cid, people),
                    people=people,
                    events=events,
                    calendar=public_context(snapshot, [])["calendar"],
                    schema=InviteResult.model_json_schema(),
                ),
            )

            def apply(after, raw, batch):
                invitation = InviteResult.model_validate_json(raw).invitation
                if invitation:
                    if (
                        invitation.event not in {r["id"] for r in events}
                        or invitation.recipient not in people
                    ):
                        raise ValueError("Приглашение не связано с доступным мероприятием или адресатом.")
                    eid, delta = send(
                        after, cid, invitation.recipient, invitation.text, seed, autonomous=True
                    )
                    domain(after["world_state"])["invitations"][eid] = invitation.event
                    merge_history(batch, delta)

            return prompt, apply
    prompt, _ = social_prompt(snapshot, events=history.get("events", []))
    return prompt, lambda after, raw, batch: social_result(after, raw, prompt, seed)
