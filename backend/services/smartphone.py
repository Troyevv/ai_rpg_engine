"""Provider-authored public activity, short discovery batches and selected-character expansion."""

import json
from copy import deepcopy

from pydantic import ValidationError

from backend.runtime_v3.calendar import age_on, current_time, date_parts, profile_of
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.models import assert_world_state_v3_invariants, identity
from backend.runtime_v3.remote_authoring import speaker_context
from backend.runtime_v3.smartphone import candidate, domain, publish, shelf
from backend.runtime_v3.smartphone_models import AppCommand, Batch, Candidate, PublicAction, SearchResult
from backend.services.world import CARD_FIELDS


def messages(instruction, payload):
    return [
        dict(role="system", content=instruction),
        dict(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]


def setting(snapshot):
    campaign = snapshot.get("campaign", {}).get("campaign", {})
    return dict(
        world={
            key: str(campaign[key])[:800]
            for key in ("title", "genre", "era", "setting", "public_description")
            if campaign.get(key)
        },
        calendar=current_time(snapshot["world_state"]),
    )


def social_names(snapshot):
    cards = {c["id"]: c["name"] for c in snapshot.get("character_cards", [])}
    return {
        cid: actor.get("display_name") or cards.get(cid) or cid
        for cid, actor in snapshot["world_state"]["characters"].items()
    }


def social_prompt(snapshot, source=None, *, refresh=False, events=()):
    state = snapshot["world_state"]
    data = domain(state)
    owner = state["camera"]["controlled_actor_id"]
    authors = [cid for cid in state["characters"] if cid != owner and capabilities(state, cid)["can_act"]]
    if not authors:
        return None, []
    offset = (data["sequence"] + state["meta"]["world_time"] // 120) % len(authors)
    authors = (authors[offset:] + authors[:offset])[:3]
    recent = sorted(data["publications"].values(), key=lambda r: r["sequence"], reverse=True)[:6]
    if source and source not in {r["id"] for r in recent}:
        recent.append(data["publications"][source])
    # Only facts shared by the selected authors enter a multi-speaker request.
    common = {
        fid: f["text"][:400]
        for fid, f in state["facts"].items()
        if f["visibility"] == "public"
        and not f.get("story_secret")
        and not f.get("origin_remote_event_id")
        and all(state["knowledge"].get(cid + ":" + fid, {}).get("status") == "known" for cid in authors)
    }
    # Only shared, witnessed physical events belong in this multi-author public context.
    witnessed = [
        dict(text=e["text"][:400], minute=e.get("minute"), turn=e.get("turn_id"))
        for e in events
        if isinstance(e, dict)
        and isinstance(e.get("text"), str)
        and e.get("medium") in ("action", "observation")
        and isinstance(e.get("witnesses"), list)
        and all(cid in e["witnesses"] for cid in authors)
        and isinstance(e.get("fact_ids", []), list)
        and all(isinstance(fid, str) and fid in common for fid in e.get("fact_ids", []))
    ][-6:]
    names = social_names(snapshot)
    schema = Batch[PublicAction].model_json_schema()
    schema["$defs"]["PublicAction"]["properties"]["author"]["enum"] = authors
    cast = []
    for cid in authors:
        voice = speaker_context(snapshot, cid, authors + [owner])
        cast.append(
            dict(
                id=cid,
                name=names[cid],
                public_bio=data["profiles"].get(cid, "")[:350],
                voice=voice["legacy_voice"] or str(voice["personality"])[:600],
                relationships=[
                    dict(target=r["target_id"], dimensions=r["dimensions"]) for r in voice["relationships"]
                ],
            )
        )
    return messages(
        "Public social activity/1. Ты ведёшь живую публичную соцсеть мира. Пиши по-русски. "
        "Выбери уместные публикации NPC и реакции друг на друга или на повод. "
        "Пост не подтверждает истинность текста. Не разглашай чужие сведения, не играй за героя. "
        "Для каждого действия скопируй в author точный id из authors. Имена, номера, адресаты отношений "
        "и авторы прежних постов не являются допустимыми идентификаторами, если их нет в этом списке. "
        "Для нового поста target=null. Для реакции укажи id публикации из public_posts или ссылку на "
        "более раннюю запись этого ответа. "
        'Для ответа на действие в этом же пакете target="@1" обозначает первую запись. '
        "Возвращай JSON по схеме. Для like/repost текст не нужен."
        + (
            " Игрок обновил ленту. Напиши 2–4 новых самостоятельных поста. Дай авторам разные голоса и темы: "
            "личные наблюдения, свои интересы, события и повседневные дела. Персонажи могут откликаться друг "
            "на друга. Учитывай предыдущие записи, не повторяй их. Герой не обязан быть темой. "
            "Время остаётся прежним."
            if refresh
            else ""
        ),
        dict(
            **setting(snapshot),
            authors=cast,
            shared_knowledge=list(common.values())[-6:],
            recent_events=witnessed,
            source=source,
            public_posts=[{**r, "text": r["text"][:700]} for r in recent],
            schema=schema,
        ),
    ), authors


def social_result(snapshot, raw, authors, seed, *, refresh=False):
    state = snapshot["world_state"]
    names = social_names(snapshot)
    by_name = {}
    for cid, name in names.items():
        by_name.setdefault(name.casefold(), []).append(cid)
    existing = domain(state)["publications"]
    # Use original wire positions. @2 must not slide onto @1 if an action is dropped.
    references = {}
    is_reply = {rid: bool(p["post_id"]) for rid, p in existing.items()}
    prior_posts = (
        {(p["author"], p["text"]) for p in existing.values() if not p["post_id"]} if refresh else set()
    )
    plan = []
    warnings = []
    new_posts = set()
    for i, record in enumerate(Batch[object].model_validate_json(raw).actions):
        try:
            action = PublicAction.model_validate(record)
            author = action.author
            if author not in names:
                matches = by_name.get(author.casefold(), [])
                if len(matches) == 1:
                    author = matches[0]
            if (
                author not in state["characters"]
                or author not in authors
                or author == state["camera"]["controlled_actor_id"]
                or not capabilities(state, author)["can_act"]
            ):
                raise ValueError("Автор не входит в список доступных NPC.")
            target = action.target
            if target and target.startswith("@"):
                if target not in references:
                    raise ValueError("Ссылка не указывает на сохранённую предыдущую запись.")
                target = references[target]
            if action.kind != "post" and target not in is_reply:
                raise ValueError("Исходная публикация отсутствует.")
            if action.kind == "repost" and is_reply[target]:
                raise ValueError("Репост доступен для исходной публикации.")
            if action.kind in ("post", "comment") and not action.text:
                raise ValueError("Провайдер не вернул текст публикации.")
            if action.kind == "post":
                if action.target:
                    raise ValueError("Новый пост не может ссылаться на другую запись.")
                key = (author, action.text)
                if refresh and (key in new_posts or key in prior_posts):
                    raise ValueError("Провайдер повторил публикацию.")
                new_posts.add(key)
        except ValueError as exc:
            reason = "Неверный формат действия." if isinstance(exc, ValidationError) else str(exc)
            warnings.append(dict(section="social_activity", index=i, action="drop_record", reason=reason))
            continue

        rid = identity("social", seed, i)
        if action.kind in ("post", "comment"):
            is_reply[rid] = action.kind == "comment"
            references[f"@{i + 1}"] = rid
        else:
            references[f"@{i + 1}"] = target
        plan.append((author, action, rid, target))

    if (refresh and not new_posts) or (warnings and not plan):
        reason = warnings[0]["reason"] if warnings else ""
        raise ValueError(("Провайдер не вернул новых публикаций. " + reason).strip())
    for author, action, rid, target in plan:
        publish(state, author, action.kind, rid, text=action.text, target=target)
    return warnings


def search_result(snapshot, cmd, raw):
    state = snapshot["world_state"]
    actor = cmd.actor_id
    book = shelf(state, actor)
    rows = SearchResult.model_validate_json(raw).candidates
    filters = cmd.filters
    names = set()
    results = []
    for i, brief in enumerate(rows):
        if not filters.min_age <= brief.age <= filters.max_age or filters.gender not in ("any", brief.gender):
            raise ValueError("Возраст или пол в выдаче расходится с фильтрами.")
        if filters.location.strip() and filters.location.strip().casefold() != brief.location.casefold():
            raise ValueError("Место в анкете расходится с фильтром.")
        if brief.name.casefold() in names:
            raise ValueError("Повтор имени внутри выдачи.")
        names.add(brief.name.casefold())
        cid = identity("candidate", actor, cmd.operation_id, i)
        book["candidates"][cid] = Candidate(
            **brief.model_dump(), id=cid, search_date=current_time(state)["date"]
        ).model_dump()
        results.append(cid)
    book.update(filters=filters.model_dump(), results=results, searched=True)
    book["candidates"] = {
        cid: c for cid, c in book["candidates"].items() if cid in results or c["character_id"]
    }


def expand(snapshot, cmd, raw, jid):
    from backend.services.npc_review import card_fields

    state = snapshot["world_state"]
    item = candidate(state, cmd.actor_id, cmd.target)
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("name") != item["name"]:
        raise ValueError("Имя карточки расходится с выбранной анкетой.")
    fields = card_fields(obj.get("fields"), complete=True)
    birth = obj.get("birth_date")
    date_parts(birth, profile_of(state))
    if item["search_date"] and age_on(birth, item["search_date"], profile_of(state)) != item["age"]:
        raise ValueError("Дата рождения не соответствует возрасту на дату поиска.")
    age = age_on(birth, current_time(state)["date"], profile_of(state))
    fields["Возраст"] = str(age if age is not None else item["age"])
    for key, brief in [("Роль", "occupation"), ("Внешность", "appearance"), ("Характер", "personality")]:
        if not fields[key].startswith(item[brief]):
            # Keep the public description if the expansion replaced its identity anchor.
            fields[key] = item[brief]
    cid = identity("dating_npc", cmd.actor_id, item["id"])
    add_character(snapshot, cid, item["name"], fields, dict(
        birth_date=birth, biological_sex=item["gender"], life_status="alive", developmental_stage="adult"))
    domain(state)["profiles"][cid] = item["bio"]
    item.update(character_id=cid, job_id=jid)


def add_character(snapshot, cid, name, fields, attributes):
    from backend.runtime_v3.npc_identity import initial_character
    from backend.runtime_v3.personality import initialize_profiles
    from backend.services.npc_review import assign_new_portrait
    state = snapshot["world_state"]
    if cid in state["characters"]:
        raise ValueError("Идентификатор NPC уже занят.")
    state["characters"][cid] = initial_character(cid, name, attributes)
    card = dict(id=cid, name=name, fields=fields, aliases=[], is_player=False)
    snapshot["character_cards"].append(card)
    initialize_profiles(dict(world_state=state, character_cards=[card]))
    assign_new_portrait(state, cid)


def execute(repo, job, handle, stream, config):
    from backend.repositories.smartphone import finish_job
    from backend.services.usage import tracked_stream
    from context_builder import describe_context

    cmd = AppCommand.model_validate(config["smartphone"])
    snap = json.loads(job["before_json"])
    state = snap["world_state"] = assert_world_state_v3_invariants(snap["world_state"])
    authors = []
    from backend.services import phone_catalog as catalog
    if cmd.action == "generate":
        from backend.runtime_v3.repository import read_history
        with repo.connect() as db:
            history, _ = read_history(db, snap.get("history_head"))
        prompt, ctx = catalog.catalog_prompt(snap, cmd.app, history["events"])
    elif cmd.action == "apply":
        prompt = catalog.employer_prompt(snap,cmd)
    elif cmd.action == "ask":
        qid = identity("question", cmd.operation_id)
        prompt = catalog.question_prompt(snap,cmd.target,domain(state)["questions"][qid])
    elif cmd.action == "search":
        prompt = messages(
            "Dating search/1. Напиши по-русски около пяти разных кратких анкет взрослых. "
            "Строго соблюдай возраст, пол и точное название места. Учитывай мягкие пожелания и сеттинг. "
            "Без скрытых биографий. JSON по схеме.",
            dict(**setting(snap), filters=cmd.filters.model_dump(), schema=SearchResult.model_json_schema()),
        )
    elif cmd.action == "accept":
        brief = candidate(state, cmd.actor_id, cmd.target)
        prompt = messages(
            "Dating character/1. Разверни выбранную анкету в полноценного NPC на русском языке. "
            "Сохрани все показанные сведения. Верни JSON {name,birth_date,fields}. Дата YYYY-MM-DD "
            "соответствует возрасту на дату поиска. Заполни все поля, начни роль, внешность и характер "
            "точными фразами анкеты, затем развивай их. Не начинай встречу или роман.",
            dict(
                **setting(snap), candidate=brief, card_fields=CARD_FIELDS, calendar_profile=profile_of(state)
            ),
        )
    elif cmd.action == "refresh":
        from backend.runtime_v3.repository import read_history

        with repo.connect() as db:
            history, _ = read_history(db, snap.get("history_head"))
        prompt, authors = social_prompt(snap, refresh=True, events=history["events"])
        if not authors:
            raise ValueError("В этом мире пока некому опубликовать запись.")
    else:
        prompt, authors = social_prompt(snap, identity("publication", cmd.actor_id, cmd.operation_id))

    def connected(connection):
        handle.stream = connection
        if handle.cancelled.is_set():
            connection.close()

    cached = config.get("_smartphone_result")
    if prompt and cached is None:
        from context_builder import estimate
        output = min(4200,config["update_tokens"])
        limit = min(config["context_length"]-output,config.get("_budget_caps",{}).get("max_input") or config["context_length"])
        if estimate(prompt)>limit:
            raise ValueError("Контекст приложения не помещается в выбранное окно модели.")
    raw = (
        cached
        if cached is not None
        else "".join(
            tracked_stream(
                repo,
                stream,
                job["id"],
                "smartphone_" + cmd.action,
                config,
                prompt,
                describe_context(prompt),
                max_tokens=min(4200, config["update_tokens"]),
                temperature=config.get("temperature", 0.8),
                model=config["model"],
                provider=config.get("provider", "local"),
                api_key=handle.api_key,
                cancel_event=handle.cancelled,
                on_stream=connected,
                require_complete=True,
                response_format={"type": "json_object"},
            )
        )
        if prompt
        else '{"actions":[]}'
    )
    if handle.cancelled.is_set():
        return

    def apply(after, history=None):
        if cmd.action == "generate":
            catalog.apply_catalog(after,cmd.app,raw,ctx,cmd.operation_id)
        elif cmd.action == "apply":
            batch = catalog.deliver_application(after,cmd,raw)
            if history is not None:
                history.update(batch)
        elif cmd.action == "ask":
            if prompt:
                catalog.apply_question(after,cmd.target,qid,raw,cmd.operation_id)
        elif cmd.action == "search":
            search_result(after, cmd, raw)
        elif cmd.action == "accept":
            expand(after, cmd, raw, job["id"])
        else:
            return social_result(after, raw, authors, cmd.operation_id, refresh=cmd.action == "refresh")

    # Journal a validated provider response before the canonical SQLite transaction.
    # A failed projection can then retry without buying or changing the same result.
    if cached is None:
        apply(deepcopy(snap))
        with repo.connect() as db:
            written = db.execute(
                """UPDATE game_jobs SET config_json=json_set(config_json,'$._smartphone_result',?)
                WHERE id=? AND attempt_epoch=? AND status IN ('generating','extracting')""",
                (raw, job["id"], job["attempt_epoch"]),
            ).rowcount
            if not written:
                return
    continuation = finish_job(repo, job, cmd, apply)
    if continuation and not handle.cancelled.is_set():
        from backend.services.communication import execute as communicate
        next_job = repo.get_job(job["id"])
        communicate(repo,next_job,handle,stream,dict(config,communication=continuation))


def consider(before, snapshot, history, config, generate, cancelled, warnings):
    """Use game time and the existing optional simulation budget, once per interval."""
    from backend.runtime_v3.simulation import optional_generate, BackgroundGenerationError

    state = snapshot["world_state"]
    if (
        state["meta"]["communication"].get("presentation") != "phone"
        or not state["meta"]["communication"].get("social")
        or cancelled.is_set()
    ):
        return
    data = domain(state)
    now = state["meta"]["world_time"]
    last = data["last_considered"]
    if last is None:
        last = before["world_state"]["meta"]["world_time"]
        data["last_considered"] = last
    if now - last < 180 and (now - last < 45 or not history.get("events")):
        return
    data["last_considered"] = now
    from backend.services.phone_catalog import background_activity
    from backend.runtime_v3.phone_listings import merge_history
    index = data["activity_index"]
    data["activity_index"] += 1
    prompt, apply = background_activity(snapshot,history,index,identity("background_social",now,state["meta"]["turn_id"]))
    if not prompt:
        return
    try:
        raw = "".join(
            optional_generate(generate)(
                "social_activity",
                prompt,
                min(1800, config["update_tokens"]),
                0.7,
                response_format={"type": "json_object"},
            )
        )
        staged = dict(snapshot,world_state=deepcopy(state))
        batch = {}
        skipped = apply(staged,raw,batch) or []
    except (ValueError, BackgroundGenerationError) as exc:
        warnings.append(dict(section="social_activity", reason=str(exc), action="discard_background"))
        return
    if not cancelled.is_set():
        warnings.extend(skipped)
        merge_history(history,batch)
        snapshot["world_state"] = staged["world_state"]
        history["state_changes"].append(
            dict(kind="social_activity", minute=now, sequence=domain(staged["world_state"])["sequence"])
        )
