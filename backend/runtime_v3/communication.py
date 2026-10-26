"""One source-bound communication cycle, using #70 proposals and canonical commands.

Four decisions TOTAL, including group recipients/endpoint identification. Silence
ends the cycle. No polling, repair requests, ordinary turns or forced NPC speech.
"""
import json
from copy import deepcopy
from pydantic import BaseModel, ConfigDict, Field
from backend.runtime_v3.models import WorldHistoryV3, assert_world_state_v3_invariants
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.remote import members
from backend.runtime_v3.remote_initiative import opportunities, planning_context, accept

MAX_DECISIONS = 4


class Continuation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: str
    owner_id: str
    request_id: str = Field(min_length=8, max_length=100)


def validate(snapshot, request):
    r = Continuation.model_validate(request)
    s = snapshot["world_state"]
    e = s["remote_events"].get(r.source_event_id)
    if snapshot.get("runtime") == "tabletop" or snapshot.get("mode") == "tabletop":
        raise ValueError("Связь доступна только в Narrative.")
    if s["camera"]["controlled_actor_id"] != r.owner_id or not capabilities(s, r.owner_id)["can_act"]:
        raise ValueError("Владелец телефона уже изменился или не может действовать.")
    if not e or e["sender_id"] != r.owner_id:
        raise ValueError("Исходное действие связи недоступно в этой ветке.")
    if e["channel"] == "VOICE_CALL" and e["status"] != "ringing":
        raise ValueError("Этот вызов уже обработан.")
    if e["conversation_id"] and r.owner_id not in members(s["conversations"][e["conversation_id"]]):
        raise ValueError("Нет доступа к переписке.")
    return r


def options_for(snapshot, source_id, replied):
    s = snapshot["world_state"]
    e = s["remote_events"][source_id]
    owner = e["sender_id"]
    # Endpoint identification is offered only for this actual attempt.
    if not e["recipient_ids"]:
        return [o for o in opportunities(dict(s, remote_events={source_id:e})) if o.get("event_id") == source_id][:1]
    result = []
    for actor in e["recipient_ids"]:
        caps = capabilities(s, actor)
        if actor == owner or not caps["can_act"] or not caps["can_perceive"]:
            continue
        if any((c["blocked"] or not c["available"]) and {c["owner_id"], c["character_id"]} == {actor, owner} for c in s["contacts"].values()):
            continue
        base = dict(actor_id=actor, basis_ids=[source_id])
        if e["channel"] == "VOICE_CALL":
            if e["status"] == "ringing":
                result.append(dict(base, event_id=source_id, actions=["answer", "decline"] if caps["can_speak"] else ["decline"]))
        elif s["meta"]["communication"]["text_message"]:
            conv = s["conversations"].get(e["conversation_id"])
            if not conv or not {owner, actor} <= members(conv):
                continue
            if actor in e["delivered_to"] and actor not in e["read_by"]:
                result.append(dict(base, event_id=source_id, actions=["read"]))
            elif actor in e["read_by"] and actor not in replied:
                result.insert(0, dict(base, paths=[dict(conversation_id=conv["id"])], actions=["send"]))
    return result[:4]


def run(snapshot, request, generate, cancelled):
    r = validate(snapshot, request)
    after = deepcopy(snapshot)
    batch = WorldHistoryV3().to_dict()
    report = dict(source_event_id=r.source_event_id, owner_id=r.owner_id, decisions=0, accepted=[], rejected=[], max_decisions=MAX_DECISIONS)
    if not options_for(after, r.source_event_id, set()):
        report['unavailable'] = True
    replied = set()
    start = after["world_state"]["meta"]["world_time"]
    for index in range(MAX_DECISIONS):
        if cancelled.is_set():
            return None
        options = options_for(after, r.source_event_id, replied)
        if not options:
            break
        messages = planning_context(after, options)
        raw = generate(index, messages)
        report["decisions"] += 1
        try:
            proposal = json.loads(raw)["action"]
            if proposal is None:
                report["no_action"] = True
                break
            updated, delta = accept(after, proposal, options, f"{r.request_id}:{index}")
        except (ValueError, KeyError, TypeError) as exc:
            report["rejected"].append(str(exc)[:300])
            break  # One rejected decision is diagnostic, never a retry-until-answer.
        after = updated
        for section, rows in delta.items():
            batch[section].extend(rows)
        report["accepted"].append(proposal["action"])
        if proposal["action"] == "send":
            replied.add(proposal["actor_id"])
        if proposal["action"] in ("answer", "decline", "send"):
            break
    event = after["world_state"]["remote_events"][r.source_event_id]
    # Successful/refused calls and text cycles cost one minute. An unanswered
    # call advances only to its configured canonical expiry, at most 60 minutes.
    end = start + 1
    if event["channel"] == "VOICE_CALL" and event["status"] == "ringing":
        end = max(start, event["world_time"] + after["world_state"]["meta"]["communication"]["ring_timeout_minutes"])
    from backend.runtime_v3.long_term import advance_clock
    advance_clock(after, end, batch)
    after["world_state"]["meta"]["turn_id"] += 1
    report.update(elapsed_minutes=end-start, outcome=event["status"])
    batch["state_changes"].append(dict(kind="communication_cycle", **report))
    after["world_state"] = assert_world_state_v3_invariants(after["world_state"])
    return after, batch, report
