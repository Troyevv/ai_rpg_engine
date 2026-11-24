"""Scripted interpersonal dialogue at the model boundary; all effects run through Runtime."""

import json
from test_communication_cycle import decision

OFFER = "Предлагаю начать сегодня. Оплата сдельная. Подходят такие условия?"
ACCEPT = "Условия подходят. Принимаю работу и начинаю сегодня."


def reply(messages):
    instruction = messages[0]["content"]
    data = json.loads(messages[1]["content"])
    if instruction.startswith("Select at most ONE"):
        value = json.loads(decision(messages))
        action = value.get("action") or {}
        if action.get("action") == "send":
            actor = data["actors"][0]
            if actor.get("vacancies"):
                action["content"] = OFFER if ACCEPT not in actor["recent_dialogue"] else "Договорились."
            else:
                action["content"] = (
                    "Согласна, буду на репетиции."
                    if actor["id"] == "qa_vera"
                    else "Спасибо, я не смогу прийти."
                )
        return value
    if instruction.startswith("Remote semantic extraction/"):
        result = dict(final_scene=data["final_scene"])
        events = data["accepted_messages"]
        source = next(e for e in events if e["id"] == data["source_event_id"])
        if data.get("event_invitations"):
            invitation = data["event_invitations"][-1]
            event = invitation["event"]
            request = next(e for e in events if e["id"] == invitation["message_id"])
            response = next(
                (
                    e
                    for e in events
                    if e["ordinal"] > request["ordinal"]
                    and e["sender_id"] != request["sender_id"]
                    and e["content"].startswith("Согласна")
                ),
                None,
            )
            if response:
                result["scheduled_event_changes"] = [
                    dict(
                        id="plan-" + request["id"],
                        description=event["title"],
                        location_id=event["location_id"],
                        character_ids=[request["sender_id"], response["sender_id"]],
                        assertion="agreed",
                        temporal=dict(minute_offset=event["start"] - request["world_time"]),
                        remote_source_ids=[request["id"], response["id"]],
                        remote_time_source_id=request["id"],
                        evidence=response["content"],
                        player_assertion="explicit_choice",
                        player_source_id=request["id"],
                        player_evidence=request["content"],
                    )
                ]
        elif data.get("vacancies") and source["content"] == ACCEPT:
            vacancy = data["vacancies"][0]
            offer = next(e for e in events if e["content"] == OFFER)
            result["role_changes"] = [
                dict(
                    id="job_role",
                    assertion="established",
                    effective="now",
                    actor_id=source["sender_id"],
                    title=vacancy["title"],
                    vacancy_id=vacancy["id"],
                    offer_event_id=offer["id"],
                    player_source_id=source["id"],
                    player_assertion="explicit_choice",
                    player_evidence=source["content"],
                    evidence=source["content"],
                )
            ]
        return result
    from smartphone_provider import response

    return response(messages)
