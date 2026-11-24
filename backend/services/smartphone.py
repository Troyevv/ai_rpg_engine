"""Provider-authored public activity, short discovery batches and selected-character expansion."""

import json
from copy import deepcopy

from backend.runtime_v3.calendar import age_on, current_time, date_parts, profile_of
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.models import identity
from backend.runtime_v3.remote_authoring import speaker_context
from backend.runtime_v3.smartphone import candidate, domain, publish, shelf
from backend.runtime_v3.smartphone_models import AppCommand, Batch, Candidate, SearchResult
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


def social_prompt(snapshot, source=None):
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
    common = [
        f["text"][:400]
        for fid, f in state["facts"].items()
        if f["visibility"] == "public"
        and all(state["knowledge"].get(cid + ":" + fid, {}).get("status") == "known" for cid in authors)
    ][-6:]
    cast = []
    for cid in authors:
        voice = speaker_context(snapshot, cid, authors + [owner])
        cast.append(
            dict(
                id=cid,
                name=state["characters"][cid].get("display_name"),
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
        'Для ответа на действие в этом же пакете target="@1" обозначает первую запись. '
        "Возвращай JSON по схеме. Для like/repost текст не нужен.",
        dict(
            **setting(snapshot),
            authors=cast,
            shared_knowledge=common,
            source=source,
            public_posts=[{**r, "text": r["text"][:700]} for r in recent],
            schema=Batch.model_json_schema(),
        ),
    ), authors


def social_result(state, raw, authors, seed):
    references = []
    for i, action in enumerate(Batch.model_validate_json(raw).actions):
        if action.author not in authors or not capabilities(state, action.author)["can_act"]:
            raise ValueError("Неизвестный или недоступный автор публикации.")
        target = action.target
        if target and target.startswith("@"):
            index = target[1:]
            if not index.isdecimal() or not 1 <= int(index) <= len(references):
                raise ValueError("Неизвестная ссылка в обсуждении.")
            target = references[int(index) - 1]
        references.append(
            publish(
                state,
                action.author,
                action.kind,
                identity("social", seed, i),
                text=action.text,
                target=target,
            )
        )


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
    from backend.runtime_v3.npc_identity import initial_character
    from backend.services.npc_review import card_fields, assign_new_portrait
    from backend.runtime_v3.personality import initialize_profiles

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
            fields[key] = item[brief] + ". " + fields[key]
    cid = identity("dating_npc", cmd.actor_id, item["id"])
    if cid in state["characters"]:
        raise ValueError("Идентификатор NPC уже занят.")
    state["characters"][cid] = initial_character(
        cid,
        item["name"],
        dict(
            birth_date=birth, biological_sex=item["gender"], life_status="alive", developmental_stage="adult"
        ),
    )
    card = dict(id=cid, name=item["name"], fields=fields, aliases=[], is_player=False)
    snapshot["character_cards"].append(card)
    partial = dict(world_state=state, character_cards=[card])
    initialize_profiles(partial)
    assign_new_portrait(state, cid)
    domain(state)["profiles"][cid] = item["bio"]
    item.update(character_id=cid, job_id=jid)


def execute(repo, job, handle, stream, config):
    from backend.repositories.smartphone import finish_job
    from backend.services.usage import tracked_stream
    from context_builder import describe_context

    cmd = AppCommand.model_validate(config["smartphone"])
    snap = json.loads(job["before_json"])
    state = snap["world_state"]
    authors = []
    if cmd.action == "search":
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
    else:
        prompt, authors = social_prompt(snap, identity("publication", cmd.actor_id, cmd.operation_id))

    def connected(connection):
        handle.stream = connection
        if handle.cancelled.is_set():
            connection.close()

    cached = config.get("_smartphone_result")
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

    def apply(after):
        if cmd.action == "search":
            search_result(after, cmd, raw)
        elif cmd.action == "accept":
            expand(after, cmd, raw, job["id"])
        else:
            social_result(after["world_state"], raw, authors, cmd.operation_id)

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
    finish_job(repo, job, cmd, apply)


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
    prompt, authors = social_prompt(snapshot)
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
        staged = deepcopy(state)
        social_result(staged, raw, authors, identity("background_social", now, state["meta"]["turn_id"]))
    except (ValueError, BackgroundGenerationError) as exc:
        warnings.append(dict(section="social_activity", reason=str(exc), action="discard_background"))
        return
    if not cancelled.is_set():
        snapshot["world_state"] = staged
        history["state_changes"].append(
            dict(kind="social_activity", minute=now, sequence=domain(staged)["sequence"])
        )
