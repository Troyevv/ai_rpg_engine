"""Bounded interval planning over canonical Runtime v3 causes.

A plan is a disposable projection, not a second world/knowledge store. Only
accepted resolver results and deterministic process/age transitions are committed.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import (
    StrictModel,
    WorldHistoryV3,
    assert_world_state_v3_invariants,
    identity,
)
from backend.runtime_v3.commitments import commitment_ready
from backend.runtime_v3.calendar import (
    scheduled_boundary,
    current_time,
    age_on,
    profile_of,
)
from backend.runtime_v3.long_term_calendar import target_minute, annual_occurrences
from backend.runtime_v3.scope import RelevanceResolver


class AdvanceRequest(StrictModel):
    amount: int = Field(ge=1, le=200, strict=True)
    unit: Literal["weeks", "months", "years"]
    max_llm_calls: int = Field(default=4, ge=0, le=8, strict=True)
    reason: str = Field(default="", max_length=1000)


@dataclass(frozen=True)
class Candidate:
    id: str
    kind: str
    source_id: str
    actor_ids: tuple[str, ...]
    minute: int
    score: float
    signals: tuple[str, ...]
    context: str = ""
    requires_player: bool = False
    domains: tuple[str, ...] = ()


@dataclass
class AdvancePlan:
    start: int
    requested_target: int
    actual_target: int
    candidates: list[Candidate]
    relevance: dict[str, str]
    calendar: list[dict]
    interruption: dict | None = None
    policy: dict = field(default_factory=dict)


def relevance(snapshot, scope):
    """Reuse ContextScope; explicit ties/causes can reactivate stored identities.

    One linear projection per request, never a per-NPC simulation. Dormancy does
    not close relations, delete history or prohibit later name-based retrieval.
    """
    s = snapshot["world_state"]
    core = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
    tied = set(scope.referenced_actor_ids)
    for relation in s["objective_relations"].values():
        pair = {relation["source_id"], relation["target_id"]}
        if relation["status"] == "active" and pair & core:
            tied.update(pair)
    for relation in s["relationships"].values():
        pair = {relation["source_id"], relation["target_id"]}
        if pair & core and any(abs(v) >= 50 for v in relation["dimensions"].values()):
            tied.update(pair)
    for section in ("threads", "scheduled_events"):
        for row in s[section].values():
            if row["status"] in ("active", "developing", "pending"):
                tied.update(row["character_ids"])
    for process in s["pregnancies"].values():
        if process["status"] != "born":
            tied.update(process["parent_ids"])
    return {
        cid: (
            "active"
            if cid in core
            else "background"
            if cid in tied
            else "archived"
            if actor["life_status"] == "dead"
            else "dormant"
        )
        for cid, actor in sorted(s["characters"].items())
    }


def plan(snapshot, request, history=None):
    request = AdvanceRequest.model_validate(request)
    s = snapshot["world_state"]
    start = s["meta"]["world_time"]
    target = target_minute(s, request.amount, request.unit)
    # Disallow embedding retrieval here: candidate ordering is a pure projection.
    scope = RelevanceResolver().resolve(
        snapshot, request.reason, world_history=history, completed_narrative=""
    )
    levels = relevance(snapshot, scope)
    controlled = s["camera"]["controlled_actor_id"]
    pending = [e for e in s["scheduled_events"].values() if e["status"] == "pending"]

    due = [
        (max(start, minute), e)
        for e in pending
        if (minute := scheduled_boundary(s, e)) is not None
        and minute <= target
        and commitment_ready(s, e)
    ]
    interruptions = sorted(
        (
            (minute, e)
            for minute, e in due
            if controlled and controlled in e["character_ids"]
        ),
        key=lambda pair: (pair[0], pair[1]["id"]),
    )
    interruption = None
    if s["meta"].get("protagonist_required"):
        interruption = dict(kind="protagonist_required", minute=start)
    else:
        from backend.runtime_v3.remote import active_call

        call = active_call(s, controlled)
        if call and call["status"] == "answered":
            interruption = dict(kind="remote_call", minute=start, source_id=call["id"])
    if interruption is None and interruptions:
        minute, event = interruptions[0]
        interruption = dict(kind="commitment", minute=minute, source_id=event["id"])
    actual = interruption["minute"] if interruption else target
    candidates = {}

    def add(kind, source, actors, minute, base, context="", domains=()):
        actors = tuple(sorted(set(actors) & s["characters"].keys()))
        if not actors or minute > actual:
            return
        signals = [kind]
        score = base
        if controlled in actors:
            score += 100
            signals.append("controlled_actor")
        if any(levels[c] == "active" for c in actors):
            score += 30
            signals.append("current_scope")
        if any(levels[c] == "background" for c in actors):
            score += 15
            signals.append("canonical_ties")
        if all(levels[c] in ("dormant", "archived") for c in actors):
            score -= 30
            signals.append("dormant")
        cid = identity("advance", kind, source)
        candidates[cid] = Candidate(
            cid,
            kind,
            source,
            actors,
            max(start, minute),
            score,
            tuple(signals),
            context[:600],
            controlled in actors,
            tuple(domains),
        )

    for minute, event in due:
        add(
            "scheduled",
            event["id"],
            event["character_ids"],
            minute,
            80,
            event["description"],
        )
    for p in s["pregnancies"].values():
        if p["status"] != "born" and p["due_minute"] <= actual:
            # One process candidate, not a duplicate of its scheduled cause.
            candidates.pop(identity("advance", "scheduled", p["id"]), None)
            add("birth", p["id"], p["parent_ids"], p["due_minute"], 90)
    for t in s["threads"].values():
        if t["status"] in ("active", "developing"):
            add(
                "thread",
                t["id"],
                t["character_ids"],
                actual,
                40 * t["relevance"],
                t["description"],
            )
    # A proven read/answered communication can motivate a later response. Merely
    # delivered or private messages do not become common knowledge or daily chat.
    for message in sorted(
        s.get("remote_events", {}).values(), key=lambda m: (-m["world_time"], m["id"])
    ):
        recipients = (
            message["read_by"]
            if message["channel"] != "VOICE_CALL"
            else message["recipient_ids"]
            if message["status"] in ("answered", "ended")
            else []
        )
        recipients = [
            cid
            for cid in recipients
            if levels.get(cid) in ("active", "background") and cid != controlled
        ]
        if message["fact_ids"] and recipients:
            add(
                "communication",
                message["id"],
                recipients,
                actual,
                30,
                "Значимое прочитанное сообщение; использовать только сведения получателя.",
            )
    # Pacing remains the single owner of contextual emergence eligibility.
    from backend.runtime_v3.pacing import evaluate, development_sources

    eligible = sorted(
        (cid for cid, level in levels.items() if level in ("active", "background")),
        key=lambda cid: (levels[cid] != "active", -scope.actor_scores.get(cid, 0), cid),
    )[:16]
    scope.active_actor_ids.update(set(eligible) - scope.present_actor_ids)
    scope.relevant_actor_ids.update(eligible)
    scope.role_ids = sorted(
        rid
        for rid, r in s["roles"].items()
        if r["actor_id"] in eligible and r["status"] == "active"
    )[:16]
    scope.residence_ids = sorted(
        rid
        for rid, r in s["residences"].items()
        if r["actor_id"] in eligible and r["status"] == "active"
    )[:16]
    milestone_query = (history or {}).get("_milestone_query")
    scope.development_sources = development_sources(s, scope, milestone_query, history)
    future = deepcopy(s)
    future["meta"]["world_time"] = actual
    policy = evaluate(future, scope, long_term=True)
    for c in policy["candidates"]:
        if c["selected"] and c["family"] == "life_opportunity":
            source = s.get(c["source_kind"], {}).get(c["source_id"], {})
            domains = (
                ("social_contact", "training", "employment")
                if c["source_kind"] == "roles"
                else ("social_contact", "relocation")
                if c["source_kind"] == "residences"
                else ("relationship", "relocation")
                if c["source_kind"] == "objective_relations"
                else ("training", "employment", "social_contact")
            )
            add(
                "opportunity",
                c["id"],
                c["actor_ids"],
                actual,
                35 * c["relevance"],
                source.get("title") or c["context"],
                domains,
            )
    # Existing #67 evidence, never time alone, makes formation/evolution eligible.
    if milestone_query and eligible:
        # One bounded History-index query, not an archive scan for every actor.
        experiences = milestone_query(actor_ids=eligible, end_minute=start, limit=16)
        for row in sorted(experiences, key=lambda r: (r.get("minute", 0), r["id"])):
            actors = [
                cid
                for cid in row["actor_ids"]
                if cid in eligible
                and identity("development", cid, row["id"])
                not in (s["characters"][cid].get("personality") or {}).get(
                    "seen_sources", []
                )
            ]
            add("personality", row["id"], actors, actual, 35, row.get("summary", ""))
    for cid in sorted(scope.relevant_actor_ids)[:16]:
        profile = s["characters"][cid].get("personality") or {}
        evidence = profile.get("evidence", {})
        if evidence:
            add(
                "personality",
                identity("experience", cid, sorted(evidence)),
                [cid],
                actual,
                25,
            )
    dates = annual_occurrences(s, start, actual, scope.relevant_actor_ids)
    for row in dates[:12]:
        add(
            "calendar",
            row["id"],
            row.get("character_ids") or sorted(scope.present_actor_ids),
            row["minute"],
            5,
            row.get("name") or row["kind"],
        )
    opportunity_ids = [
        c.id for c in candidates.values() if c.kind in ("opportunity", "communication")
    ]
    receipt_query = (history or {}).get("_advance_receipts")
    handled = (
        receipt_query(opportunity_ids)
        if receipt_query
        else {
            cid
            for change in (history or {}).get("state_changes", [])
            if change.get("kind") == "long_term_advance"
            for accepted in change.get("report", {}).get("accepted", [])
            for cid in accepted.get("candidate_ids", [])
        }
    )
    for cid in opportunity_ids:
        if cid in handled:
            candidates.pop(cid, None)
    ordered = sorted(candidates.values(), key=lambda c: (-c.score, c.minute, c.id))
    return AdvancePlan(
        start, target, actual, ordered, levels, dates[:24], interruption, policy
    )


def advance_clock(snapshot, minute, batch):
    """Certain transitions run even with zero remaining semantic budget."""
    s = snapshot["world_state"]
    previous = s["meta"]["world_time"]
    if minute < previous:
        raise ValueError("Длительный переход не может вернуть время назад.")
    s["meta"]["world_time"] = minute
    from backend.runtime_v3.reproduction import advance_due

    for p in advance_due(s):
        batch["state_changes"].append(
            dict(
                kind="process_due",
                entity=p["id"],
                before="active",
                after="due",
                minute=p["due_minute"],
                turn_id=s["meta"]["turn_id"],
                source_ids=[p["event_id"]],
            )
        )
    today = current_time(s)["date"]
    # Age is a date projection; this never creates traits, schooling or employment.
    for cid, actor in sorted(s["characters"].items()):
        if actor["life_status"] == "dead":
            continue
        age = age_on(actor.get("birth_date"), today, profile_of(s))
        if age is None:
            continue
        stage = (
            "infant"
            if age < 1
            else "child"
            if age < 12
            else "adolescent"
            if age < 18
            else "adult"
        )
        old = actor["developmental_stage"]
        if stage != old:
            actor["developmental_stage"] = stage
            batch["state_changes"].append(
                dict(
                    kind="developmental_stage",
                    entity=cid,
                    before=old,
                    after=stage,
                    minute=minute,
                    turn_id=s["meta"]["turn_id"],
                    source_ids=[actor.get("life_fact_id")]
                    if actor.get("life_fact_id")
                    else [],
                    basis=dict(birth_date=actor["birth_date"], date=today),
                )
            )
    from backend.runtime_v3.remote import advance as advance_remote

    history = WorldHistoryV3()
    advance_remote(s, history)
    for section, rows in history.to_dict().items():
        batch[section].extend(rows)
    from backend.runtime_v3.protagonist import reconcile

    reconcile(s)
    return snapshot


def run(snapshot, request, *, generate=None, config=None, history=None, cancelled=None):
    """Two provider attempts per group (narrative + normal extraction), no repairs.

    Failed/unselected groups remain unresolved. Deterministic transitions are
    independent of the budget. The enclosing job owns atomic publication.
    """
    import json
    from dataclasses import asdict
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.camera import observe
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.raw import RawTurnResult
    from backend.services.world_delta_errors import StructuralDeltaError

    request = AdvanceRequest.model_validate(request)
    config = config or {}
    result = deepcopy(snapshot)
    result["world_state"] = assert_world_state_v3_invariants(result["world_state"])
    original = deepcopy(result["world_state"])
    projection = plan(result, request, history)
    batch = WorldHistoryV3().to_dict()
    turn = original["meta"]["turn_id"] + 1
    result["world_state"]["meta"]["turn_id"] = turn
    protected = original["camera"]["controlled_actor_id"]
    report = dict(
        start=projection.start,
        requested_target=projection.requested_target,
        actual_target=projection.actual_target,
        interruption=projection.interruption,
        max_llm_calls=request.max_llm_calls,
        llm_calls=0,
        accepted=[],
        unresolved=[],
        decisions=[asdict(c) for c in projection.candidates if c.requires_player],
        calendar=projection.calendar,
        relevance=projection.relevance,
        diagnostics=[],
    )
    # Rank first, select under a hard constant cap, then execute in causal order.
    groups = {}
    for candidate in projection.candidates:
        if candidate.requires_player:
            report["unresolved"].append(dict(id=candidate.id, reason="player_decision"))
            continue
        # Selected groups never grow beyond three causes, even with huge registries.
        key = (candidate.minute, candidate.actor_ids)
        if key not in groups:
            groups[key] = []
        if len(groups[key]) < 3:
            groups[key].append(candidate)
        else:
            report["unresolved"].append(dict(id=candidate.id, reason="group_limit"))
    chosen = list(groups.values())[: request.max_llm_calls // 2] if generate else []
    chosen_ids = {c.id for group in chosen for c in group}
    report["unresolved"].extend(
        dict(id=c.id, reason="budget")
        for group in groups.values()
        for c in group
        if c.id not in chosen_ids
    )
    chosen.sort(key=lambda group: (group[0].minute, group[0].id))
    for group_index, group in enumerate(chosen):
        if cancelled is not None and cancelled.is_set():
            return None
        minute = group[0].minute
        if minute > report["actual_target"]:
            report["unresolved"].extend(
                dict(id=c.id, reason="interrupted") for c in group
            )
            continue
        advance_clock(result, minute, batch)
        actor = next(
            (
                cid
                for cid in group[0].actor_ids
                if result["world_state"]["characters"][cid]["life_status"] != "dead"
            ),
            None,
        )
        if actor is None:
            report["unresolved"].extend(
                dict(id=c.id, reason="actor_unavailable") for c in group
            )
            continue
        camera = observe(result, actor, allow_protagonist=True)
        # Canonical locations remain true, but an off-camera resolution cannot
        # invent physical presence/communication by the protected actor.
        camera["world_state"]["camera"]["present_character_ids"] = [actor]
        camera["world_state"]["camera"]["remote_interactions"] = []
        camera["_background_actor_ids"] = sorted(
            {cid for c in group for cid in c.actor_ids}
        )
        instruction = (
            "Длительный переход. Разреши только перечисленные причины на заданный момент. "
            "Возможность и наступление срока не доказывают событие. Допустимо оставить исход неизвестным. "
            "Не придумывай действия, решения, речь или обязательства EXTERNAL actor: "
            + str(protected)
            + ". "
            "Не переноси знания между персонажами без наблюдения или подтверждённого канала. "
            "Не создавай случайных людей; используй существующую личность, если она подходит. "
            "Для действительно нового человека достаточно минимальных известных сведений. "
            "Не придумывай биографию. Не воспроизводи каждый день. elapsed_minutes=0. "
            "Изменения должны опираться на принятые события. У каждого события events укажи advance_candidate_ids: "
            "ID только тех выбранных причин, исход которых это событие действительно устанавливает. "
            "Если исход остался неизвестен, не указывай его ID. "
            # Source prose is world truth and may contain a private facet. The
            # ordinary Context Builder, not this instruction, discloses its slice.
            + json.dumps(
                [{k: v for k, v in asdict(c).items() if k != "context"} for c in group],
                ensure_ascii=False,
            )
        )
        group_policy = deepcopy(projection.policy)
        sources = {c.source_id for c in group}
        group_policy["candidates"] = [
            c
            for c in group_policy["candidates"]
            if c["id"] in sources or c["source_id"] in sources
        ]
        group_policy["selected_ids"] = [
            c["id"] for c in group_policy["candidates"] if c["selected"]
        ]
        narrative = ""
        try:
            messages = build_context(
                camera,
                [],
                instruction,
                "background",
                config.get("context_length", 32768),
                config.get("max_tokens", 2000),
                prompts=config.get("_prompts"),
                world_history=history,
                pacing_decision=group_policy,
            )
            report["llm_calls"] += 1
            from backend.services.letter_sources import generate_result, extraction_context, enabled
            narrative, artifacts = generate_result(generate, "long_term_narrative", messages,
                config.get("max_tokens", 2000), config.get("temperature", 0.8), camera['world_state'],
                context_key=[c.id for c in group])
            if cancelled is not None and cancelled.is_set():
                return None
            if not narrative.strip():
                raise ValueError("Пустой результат длительного перехода.")
            messages = build_context(
                camera,
                [],
                instruction,
                "background",
                config.get("context_length", 32768),
                config.get("update_tokens", 4096),
                extraction_text=narrative,
                pacing_decision=messages.selection["pacing"],
                initiative_decision=messages.selection["initiative"],
                prompts=config.get("_prompts"),
                world_history=history,
            )
            report["llm_calls"] += 1
            if enabled(camera['world_state']): messages.append(extraction_context(artifacts))
            payload = "".join(
                generate(
                    "long_term_extraction",
                    messages,
                    config.get("update_tokens", 4096),
                    0.1,
                    context_key=[c.id for c in group],
                    response_format={"type": "json_object"},
                )
            )
            raw = RawTurnResult.parse(payload)
            if raw.final_scene.get("elapsed_minutes", 0) != 0:
                raise ValueError("Время группы задаётся Runtime, а не Extraction.")
            from backend.runtime_v3.long_term_promotions import prepare

            promotions = prepare(raw, result, [c.id for c in group])
            allowed = {cid for c in group for cid in c.actor_ids}
            # Prevent arbitrary remote facets and unscheduled player choices from
            # hitchhiking on an accepted NPC group. Knowledge still needs #76 proof.
            if len(raw.records["events"]) > 8:
                raise ValueError("Лимит событий группы превышен.")
            for event in raw.records["events"]:
                if not isinstance(event, dict):
                    continue
                if any(
                    not isinstance(event.get(key, []), list)
                    or any(not isinstance(cid, str) for cid in event.get(key, []))
                    for key in ("participants", "witnesses")
                ):
                    raise ValueError("Повреждены участники события.")
                if (
                    len(set(event.get("participants", []) + event.get("witnesses", [])))
                    > 16
                ):
                    raise ValueError("Лимит участников события превышен.")
                if protected and protected in event.get("participants", []) + event.get(
                    "witnesses", []
                ):
                    raise ValueError(
                        "Фоновое событие использует управляемого персонажа."
                    )
                if not set(event.get("participants", [])) & allowed:
                    raise ValueError("Событие не связано с выбранной причиной.")
                if event.get("minute", minute) != minute:
                    raise ValueError("Событие выходит за выбранную временную границу.")
                links = event.get("advance_candidate_ids", [])
                if (
                    not isinstance(links, list)
                    or not links
                    or any(not isinstance(link, str) for link in links)
                    or set(links) - {c.id for c in group}
                ):
                    raise ValueError("Событие не указывает выбранную причину исхода.")
                event["minute"] = minute
            resolved = StateResolver(
                camera["world_state"],
                narrative,
                "",
                letter_sources=artifacts,
                turn_id=turn,
                observed=False,
                mode="background",
                protected_actor_id=protected,
                protected_knowledge_actor_ids=[protected] if protected else [],
                pacing_decision=messages.selection["pacing"],
                initiative_decision=messages.selection["initiative"],
                milestone_query=(history or {}).get("_milestone_query"),
                development_query=(history or {}).get("_development_query"),
                relationship_query=(history or {}).get("_relationship_query"),
                relationship_receipts=batch["relationship_changes"],
                actor_names={c["id"]: c["name"] for c in result["character_cards"]},
                minimal_promotion_ids=promotions,
                event_namespace=identity("advance-group", sorted(c.id for c in group)),
            ).resolve(raw)
            if resolved.state["meta"]["world_time"] != minute:
                raise ValueError("Исход изменяет установленную временную границу.")
            if (
                protected
                and resolved.state["characters"][protected]
                != result["world_state"]["characters"][protected]
            ):
                raise ValueError("Фоновый исход изменяет управляемого персонажа.")
            for cid in promotions:
                continued = any(
                    r.get("actor_id") == cid
                    for section in ("roles", "residences")
                    for r in resolved.state[section].values()
                ) or any(
                    cid in (r["source_id"], r["target_id"])
                    for r in resolved.state["objective_relations"].values()
                )
                if cid not in resolved.state["characters"] or not continued:
                    raise ValueError(
                        "Создание персонажа не подтверждено принятой ролью или связью."
                    )
            if not resolved.history["events"]:
                raise ValueError("Нет принятого события, подтверждающего исход.")
            # Restore camera only; off-camera location changes remain canonical.
            resolved.state["camera"] = deepcopy(result["world_state"]["camera"])
            resolved.state["camera"]["present_character_ids"] = [
                cid
                for cid in resolved.state["camera"]["present_character_ids"]
                if resolved.state["characters"][cid]["life_status"] != "dead"
            ]
            from backend.runtime_v3.protagonist import reconcile

            reconcile(resolved.state)
            assert_world_state_v3_invariants(resolved.state)
            claims = {e["id"]: e for e in raw.records["events"] if isinstance(e, dict)}
            accepted_ids = set()
            for event in resolved.history["events"]:
                # Remote delivery/read receipts are canonical audit events, not
                # additional literary claims with local Extraction IDs.
                if event.get('remote_interaction_id'):
                    continue
                links = claims[event["local_id"]]["advance_candidate_ids"]
                event["advance_source_ids"] = [
                    c.source_id for c in group if c.id in links
                ]
                event["advance_candidate_ids"] = links
                accepted_ids.update(links)
            report["unresolved"].extend(
                dict(id=c.id, reason="no_outcome")
                for c in group
                if c.id not in accepted_ids
            )
            result["world_state"] = resolved.state
            result["character_cards"].extend(resolved.cards)
            for section, rows in resolved.history.items():
                batch[section].extend(rows)
            report["accepted"].append(
                dict(
                    candidate_ids=sorted(accepted_ids),
                    minute=minute,
                    event_ids=[e["id"] for e in resolved.history["events"]],
                    summaries=[e["text"] for e in resolved.history["events"] if not e.get("remote_interaction_id")],
                )
            )
            report["diagnostics"].extend(resolved.warnings)
            if protected:
                for event in resolved.state["scheduled_events"].values():
                    due = scheduled_boundary(resolved.state, event)
                    ready = commitment_ready(resolved.state, event)
                    if (
                        event["status"] == "pending"
                        and protected in event["character_ids"]
                        and ready
                        and due is not None
                        and due <= report["actual_target"]
                    ):
                        stop = max(minute, due)
                        if (
                            report["interruption"] is None
                            or stop < report["actual_target"]
                        ):
                            report["actual_target"] = stop
                            report["interruption"] = dict(
                                kind="commitment", minute=stop, source_id=event["id"]
                            )
            if resolved.state["meta"].get("protagonist_required"):
                report["actual_target"] = minute
                report["interruption"] = dict(
                    kind="protagonist_required", minute=minute
                )
                report["unresolved"].extend(
                    dict(id=c.id, reason="interrupted")
                    for later in chosen[group_index + 1 :]
                    for c in later
                )
                break
        except (ValueError, StructuralDeltaError) as exc:
            report["diagnostics"].append(
                dict(
                    kind="unresolved_group",
                    message=str(exc),
                    code=getattr(exc, "code", "invalid_outcome"),
                )
            )
            report["unresolved"].extend(
                dict(id=c.id, reason="unresolved") for c in group
            )
    if cancelled is not None and cancelled.is_set():
        return None
    advance_clock(result, report["actual_target"], batch)
    if report["actual_target"] < projection.actual_target:
        report["calendar"] = annual_occurrences(
            original,
            projection.start,
            report["actual_target"],
            {
                cid
                for cid, level in projection.relevance.items()
                if level in ("active", "background")
            },
        )[:24]
        report["decisions"] = [
            c for c in report["decisions"] if c["minute"] <= report["actual_target"]
        ]
    batch["state_changes"].append(
        dict(
            kind="long_term_advance",
            turn_id=turn,
            minute=report["actual_target"],
            before=projection.start,
            after=report["actual_target"],
            report=deepcopy(report),
        )
    )
    result["last_long_term_advance"] = report
    result.pop("last_time_skip", None)
    result["world_state"] = assert_world_state_v3_invariants(
        result["world_state"], original
    )
    return result, batch, report
