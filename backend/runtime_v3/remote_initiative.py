"""Bounded #69 remote opportunity selection and event-first acceptance.

One optional planning request for a grounded opportunity set, never per-contact
polling. Accepted events are staged with the job's immutable original context.
"""

import json
from backend.runtime_v3.remote_decision import RemoteDecision, parse as parse_decision, VERSION
from copy import deepcopy
from backend.runtime_v3.models import identity, Character, WorldHistoryV3
from backend.runtime_v3.remote_models import RemoteCommand, RemoteProposal
from backend.runtime_v3.remote import apply, active_call, members, participants
from backend.runtime_v3.life import capabilities


def opportunities(state):
    cfg = state["meta"]["communication"]
    external = state["camera"]["controlled_actor_id"]
    if not external or not (cfg["text_message"] or cfg["voice_call"]):
        return []
    result = []
    now = state["meta"]["world_time"]
    latest = {}
    for event in state["remote_events"].values():
        cid = event["sender_id"]
        previous = latest.get(cid)
        if previous is None or (
            event["world_time"],
            event["turn_id"],
            event["ordinal"],
        ) > (previous["world_time"], previous["turn_id"], previous["ordinal"]):
            latest[cid] = event
    for e in reversed(list(state["remote_events"].values())):
        if (
            e["sender_id"] == external
            and not e["recipient_ids"]
            and e["status"] in ("sent", "ringing")
        ):
            # No bulk contact generation. An actual player-originated attempt
            # is the only opportunity to establish a previously unknown speaker.
            contact = state["contacts"].get(e["contact_id"], {})
            matches = (
                sorted(
                    {
                        c["character_id"]
                        for c in state["contacts"].values()
                        if c["kind"] == "person"
                        and c["address"] == e["destination"]
                        and c["character_id"]
                    }
                )
                if contact.get("kind") == "person"
                else []
            )
            result.append(
                dict(
                    actor_id="endpoint",
                    basis_ids=[e["id"]],
                    event_id=e["id"],
                    actions=["identify"],
                    destination=e["destination"],
                    label=contact.get("label", ""),
                    existing_ids=matches,
                )
            )
            break
    # Only an actual pending call offers an answer/decline decision.
    for e in reversed(list(state["remote_events"].values())):
        if (
            e["channel"] == "VOICE_CALL"
            and e["status"] == "ringing"
            and e["sender_id"] == external
        ):
            for actor in e["recipient_ids"]:
                if capabilities(state, actor)["can_act"]:
                    result.append(
                        dict(
                            actor_id=actor,
                            basis_ids=[e["id"]],
                            event_id=e["id"],
                            actions=["answer", "decline"],
                        )
                    )
    for e in reversed(list(state["remote_events"].values())):
        if e["channel"] != "TEXT_MESSAGE":
            continue
        for actor in e["delivered_to"]:
            if actor == external or not capabilities(state, actor)["can_act"]:
                continue
            if actor not in e["read_by"]:
                result.append(
                    dict(
                        actor_id=actor,
                        basis_ids=[e["id"]],
                        event_id=e["id"],
                        actions=["read"],
                    )
                )
                if len(result) >= 4:
                    return result[:4]
    # Select from established intentions/threads, then test explicit paths. A
    # contact is eligibility, not a reason to invent a social interaction.
    basis = {}
    for cid, c in state["characters"].items():
        if cid == external or not capabilities(state, cid)["can_act"]:
            continue
        ids = [
            r["id"]
            for r in c["intentions"]
            if r["status"] == "active"
            and (r["due_minute"] is None or r["due_minute"] <= now)
        ]
        if ids:
            basis[cid] = ids[:3]
    for t in state["threads"].values():
        if (
            t["status"] not in ("active", "developing")
            or external not in t["character_ids"]
        ):
            continue
        for cid in t["character_ids"]:
            if cid != external and capabilities(state, cid)["can_act"]:
                basis.setdefault(cid, []).append(t["id"])
    for e in reversed(list(state["remote_events"].values())):
        if e["channel"] == "TEXT_MESSAGE" and e["sender_id"] == external:
            for cid in e["read_by"]:
                if cid not in latest or latest[cid]["ordinal"] < e["ordinal"]:
                    basis.setdefault(cid, []).append(e["id"])
    for cid, ids in sorted(basis.items()):
        if not capabilities(state,cid)["can_act"] or any(c["blocked"] and {c["owner_id"],c["character_id"]} == {cid,external} for c in state["contacts"].values()):
            continue
        recent = latest.get(cid)
        if recent and (
            recent["turn_id"] >= state["meta"]["turn_id"] - 2
            or now - recent["world_time"] < 5
        ):
            continue
        paths = [
            dict(contact_id=c["id"])
            for c in state["contacts"].values()
            if c["owner_id"] == cid
            and c["character_id"] == external
            and c["available"]
            and not c["blocked"]
        ]
        paths += [
            dict(conversation_id=c["id"])
            for c in state["conversations"].values()
            if {cid, external} <= members(c)
        ]
        if paths:
            result.append(
                dict(
                    actor_id=cid,
                    basis_ids=ids[:4],
                    paths=paths[:2],
                    actions=(["send"] if cfg["text_message"] else [])
                    + (["call"] if cfg["voice_call"] else []),
                )
            )
        if len(result) >= 4:
            break
    return result[:4]


def planning_context(snapshot, options):
    state = snapshot["world_state"]
    actors = {r["actor_id"] for r in options if r["actor_id"] in state["characters"]}
    cards = {c["id"]: c for c in snapshot["character_cards"]}
    data = []
    source_ids = {eid for option in options for eid in option.get('basis_ids', [])}
    for cid in sorted(actors):
        c = state["characters"][cid]
        knowledge = [
            dict(
                id=k,
                text=state["facts"][v["fact_id"]]["text"][:500],
                status=v["status"],
            )
            for k, v in state["knowledge"].items()
            if v["actor_id"] == cid and v["status"] in ("known", "suspected")
        ][:8]
        data.append(
            dict(
                id=cid,
                name=c["display_name"] or cards.get(cid, {}).get("name", cid),
                situation=c["situation"][:400],
                intentions=[
                    r["text"][:300] for r in c["intentions"] if r["status"] == "active"
                ][:3],
                personality=[
                    dict(field=i["field"], text=i["text"][:200])
                    for i in list(
                        (c.get("personality") or {}).get("items", {}).values()
                    )[:6]
                ],
                knowledge=knowledge,
                pending=[
                    dict(
                        id=e["id"],
                        channel=e["channel"],
                        status=e["status"],
                        content=e["content"][:1000] if cid in e["read_by"] else None,
                    )
                    for e in state["remote_events"].values()
                    if cid in e["recipient_ids"] and (not source_ids or e['id'] in source_ids)
                ][-4:],
            )
        )
    return [
        dict(
            role="system",
            content="Select at most ONE optional grounded autonomous remote action. "
            'Return a JSON object with required outer action: an operation object or null. No prose. '
            'Example (substitute only listed IDs): {"action":{"actor_id":"npc_1","action":"answer","event_id":"call_1","basis_ids":["call_1"]}}. '
            'No action example: {"action":null}. Outer action is the decision; inner action is the operation. '
            "Do not control the external actor. Do not invent knowledge. Use listed basis IDs and paths only. "
            "Message content is authored testimony in the active game language. "
            "Answer or decline only a listed actual pending incoming call; no forced answer. "
            "An endpoint may remain unavailable (action:null). Only a meaningful reached individual "
            "may identify: speaker_name, existing_character_id only from the exact-address existing_ids list. "
            "Do not invent a biography or turn an organization into a person; identify an individual operator. "
            "Schema: "
            + json.dumps(RemoteDecision.model_json_schema(), ensure_ascii=False),
        ),
        dict(
            role="user",
            content=json.dumps(
                dict(
                    options=options,
                    actors=data,
                    world_time=state["meta"]["world_time"],
                    language=snapshot.get("campaign", {}).get("language", "ru"),
                ),
                ensure_ascii=False,
            ),
        ),
    ]


def accept(snapshot, proposal, options, operation_id):
    p = RemoteProposal.model_validate(proposal)
    permitted = next(
        (
            r
            for r in options
            if r["actor_id"] == p.actor_id
            and p.action in r["actions"]
            and set(p.basis_ids) <= set(r["basis_ids"])
            and p.basis_ids
        ),
        None,
    )
    if not permitted:
        raise ValueError("remote_ineligible")
    if p.action == "identify":
        if p.event_id != permitted["event_id"] or not p.speaker_name.strip():
            raise ValueError("remote_identity_evidence")
        if p.existing_character_id and (
            p.existing_character_id not in permitted["existing_ids"]
            or p.existing_character_id
            == snapshot["world_state"]["camera"]["controlled_actor_id"]
        ):
            raise ValueError("remote_identity_not_address_grounded")
        return _identify_endpoint(snapshot, p, operation_id)
    if p.action in ("send", "call"):
        if not any(
            path.get("contact_id") == p.contact_id
            and path.get("conversation_id") == p.conversation_id
            for path in permitted.get("paths", [])
        ):
            raise ValueError("remote_unreachable")
    elif p.event_id != permitted.get("event_id"):
        raise ValueError("remote_event_mismatch")
    state = snapshot["world_state"]
    for key in p.knowledge_ids:
        row = state["knowledge"].get(key)
        if not row or row["actor_id"] != p.actor_id or row["status"] != "known":
            raise ValueError("remote_knowledge")
    cmd = RemoteCommand(
        operation_id=operation_id,
        action=p.action,
        contact_id=p.contact_id,
        conversation_id=p.conversation_id,
        event_id=p.event_id,
        content=p.content,
    )
    return apply(snapshot, cmd, actor_id=p.actor_id, autonomous=True)


def _identify_endpoint(snapshot, proposal, operation_id):
    """Accepted endpoint response establishes a minimal person, never a business."""
    from backend.runtime_v3.remote import resolve_identity, _event_history, _read
    from backend.runtime_v3.models import assert_world_state_v3_invariants

    result = deepcopy(snapshot)
    s = result["world_state"]
    e = s["remote_events"][proposal.event_id]
    previous = deepcopy(e)
    contact = s["contacts"].get(e["contact_id"])
    batch = WorldHistoryV3()
    cid = proposal.existing_character_id or identity("endpoint_speaker", e["id"])
    if cid not in s["characters"]:
        s["characters"][cid] = Character(
            id=cid, display_name=proposal.speaker_name, life_status="alive"
        ).model_dump()
        result["character_cards"].append(
            dict(
                id=cid,
                name=proposal.speaker_name,
                aliases=[],
                fields={},
                is_player=False,
            )
        )
        batch.state_changes.append(
            dict(kind="remote_person_established", entity=cid, source_event_id=e["id"])
        )
    caps = capabilities(s, cid)
    if (
        not caps["can_act"]
        or not caps["can_perceive"]
        or (e["channel"] == "VOICE_CALL" and not caps["can_speak"])
    ):
        raise ValueError("remote_endpoint_unavailable")
    if contact and (contact["blocked"] or not contact["available"]):
        raise ValueError("remote_endpoint_unavailable")
    if any(
        c["owner_id"] == cid and c["character_id"] == e["sender_id"] and c["blocked"]
        for c in s["contacts"].values()
    ):
        raise ValueError("remote_endpoint_blocked")
    if contact and contact["kind"] == "person":
        result = resolve_identity(
            result,
            contact["id"],
            address=contact["address"],
            evidence="endpoint_response:" + e["id"],
            character_id=cid,
        )
        s = result["world_state"]
        e = s["remote_events"][proposal.event_id]
        batch.state_changes.append(
            dict(
                kind="contact_identity",
                entity=contact["id"],
                source_event_id=e["id"],
                after=deepcopy(s["contacts"][contact["id"]]),
            )
        )
    # A service/shared endpoint keeps no persistent Character link. This call's
    # individual speaker can differ from the next call's grounded operator.
    e["recipient_ids"] = [cid]
    e["updated_at"] = s["meta"]["world_time"]
    if e["channel"] == "VOICE_CALL":
        e["status"] = "answered"
        s["meta"]["interaction_focus"] = "call"
    else:
        e.update(status="delivered", delivered_to=[cid])
        conv = s["conversations"][e["conversation_id"]]
        if cid not in members(conv):
            conv["members"].append(
                dict(
                    actor_id=cid,
                    joined_at=s["meta"]["world_time"],
                    left_at=None,
                    provenance="endpoint_response:" + e["id"],
                )
            )
    _event_history(batch, s, e, previous)
    if e["channel"] == "TEXT_MESSAGE":
        _read(s, e, cid, batch)
    # The return path is proven by the actual incoming communication, not by a
    # friendship or an organization relationship.
    from backend.runtime_v3.remote_models import Contact

    contact_id = identity("return_path", cid, e["sender_id"], e["id"])
    s["contacts"][contact_id] = Contact(
        id=contact_id,
        owner_id=cid,
        character_id=e["sender_id"],
        label=e["sender_id"],
        address="return:" + e["id"],
        identity_visible=False,
        provenance="established_remote_channel:" + e["id"],
        created_at=s["meta"]["world_time"],
    ).model_dump()
    result["world_state"] = assert_world_state_v3_invariants(s)
    return result, batch.to_dict()


def stage(snapshot, generate, operation_id):
    if "_remote_batch" in snapshot:
        return snapshot
    from backend.runtime_v3.initiative import scene_plan
    from backend.runtime_v3.scope import ContextScope

    state = snapshot["world_state"]
    scope = ContextScope(
        state["camera"]["controlled_actor_id"],
        present_actor_ids=set(state["camera"]["present_character_ids"]),
    )
    options = scene_plan(state, scope).get("remote_opportunities", [])
    if not options:
        return snapshot
    answer = "".join(
        generate(
            "remote_initiative",
            planning_context(snapshot, options),
            1200,
            0.2,
            response_format={"type": "json_object"},
        )
    )
    result = deepcopy(snapshot)
    try:
        proposed, diagnostic = parse_decision(answer)
    except ValueError as exc:
        result['_remote_batch'] = {'state_changes': [dict(kind='remote_rejected', code="decision_schema", contract=VERSION, error_type=type(exc).__name__)]}
        return result
    if proposed is not None:
        try:
            result, batch = accept(snapshot, proposed, options, operation_id)
            batch.setdefault("state_changes", []).append(dict(kind="remote_decision_parser", **diagnostic))
            result["_remote_batch"] = batch
        except ValueError as exc:
            # Rejection is recorded, but never enters Narrative as an actual cue.
            result["_remote_batch"] = {
                "state_changes": [dict(kind="remote_rejected", code="decision_runtime", error_type=type(exc).__name__)]
            }
    else:
        result["_remote_batch"] = {"state_changes": [dict(kind="remote_no_action")]}
    return result
