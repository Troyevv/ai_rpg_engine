"""#70 deterministic canonical actions and information boundaries."""

import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_protagonist import snapshot
from backend.runtime_v3.models import Contact, Character, WorldHistoryV3, Location
from backend.runtime_v3.remote_models import CommunicationCapabilities
from backend.runtime_v3.remote import (
    apply,
    projection,
    context_projection,
    resolve_identity,
    advance,
)
from backend.runtime_v3.remote_initiative import accept, opportunities
from backend.runtime_v3.protagonist import transition


def phone():
    snap = snapshot()
    s = snap["world_state"]
    s["meta"]["communication"] = CommunicationCapabilities(
        text_message=True, voice_call=True, presentation="phone"
    ).model_dump()
    for owner, target in [("a", "b"), ("b", "a"), ("a", "child")]:
        cid = owner + "-" + target
        s["contacts"][cid] = Contact(
            id=cid,
            owner_id=owner,
            character_id=target,
            label="Saved " + target,
            address="address-" + target,
            identity_visible=True,
            provenance="explicit fixture",
            created_at=0,
        ).model_dump()
    s["characters"]["b"]["location_id"] = "away"
    s["locations"]["away"] = Location(id="away", name="Другое место").model_dump()
    s["camera"]["present_character_ids"].remove("b")
    return snap


def command(s, action, **kw):
    return apply(
        s,
        dict(
            action=action,
            operation_id=kw.pop(
                "operation_id",
                "operation-"
                + str(len(s["world_state"]["remote_events"]))
                + "-"
                + action,
            ),
            **kw,
        ),
    )[0]


def incoming(s, action="send", content="Давай завтра встретимся."):
    return apply(
        s,
        dict(
            action=action,
            operation_id="incoming-" + action,
            contact_id="b-a",
            content=content,
        ),
        actor_id="b",
        autonomous=True,
    )[0]


def test_contacts_switch_and_no_automatic_graph():
    s = phone()
    p = projection(s)
    assert [c["label"] for c in p["contacts"]] == ["Saved b", "Saved child"]
    assert s["world_state"]["characters"]["b"]["display_name"] == "b"
    other, _ = transition(s, "temporary", "b", "switch")
    assert [c["label"] for c in projection(other)["contacts"]] == ["Saved a"]
    assert not projection(snapshot())


def test_delivery_read_and_quote_provenance():
    s = incoming(phone())
    e = next(iter(s["world_state"]["remote_events"].values()))
    assert e["status"] == "delivered" and e["read_by"] == []
    assert projection(s)["events"][0]["content"] is None
    assert "Давай завтра" not in json.dumps(
        context_projection(s["world_state"]), ensure_ascii=False
    )
    assert len(s["world_state"]["knowledge"]) == 1
    after, batch = apply(
        s, dict(action="read", operation_id="read-message", event_id=e["id"])
    )
    assert projection(after)["events"][0]["content"] == e["content"]
    assert len(after["world_state"]["knowledge"]) == 2
    assert batch["knowledge_acquisitions"][0]["source_event_id"] in {
        r["id"] for r in batch["events"]
    }
    assert not any(
        k["actor_id"] == "child" for k in after["world_state"]["knowledge"].values()
    )
    again = command(after, "read", event_id=e["id"])
    assert again["world_state"] == after["world_state"]


def test_group_membership_delivery_snapshot_and_late_join():
    s = command(phone(), "create_group", label="Группа", member_ids=["b"])
    gid = next(iter(s["world_state"]["conversations"]))
    s = command(
        s,
        "send",
        conversation_id=gid,
        content="До вступления",
        operation_id="first-text",
    )
    s = command(s, "join", conversation_id=gid, member_ids=["child"])
    old = next(iter(s["world_state"]["remote_events"].values()))
    assert old["delivered_to"] == ["b"]
    s = command(
        s,
        "send",
        conversation_id=gid,
        content="После вступления",
        operation_id="second-text",
    )
    assert list(s["world_state"]["remote_events"].values())[-1]["delivered_to"] == [
        "b",
        "child",
    ]
    s = command(s, "remove", conversation_id=gid, member_ids=["child"])
    s = command(
        s,
        "send",
        conversation_id=gid,
        content="После выхода",
        operation_id="third-text",
    )
    assert list(s["world_state"]["remote_events"].values())[-1]["delivered_to"] == ["b"]


@pytest.mark.parametrize(
    "action,outcome",
    [("answer", "answered"), ("decline", "declined"), ("ignore", "missed")],
)
def test_call_controls_preserve_physical_scene(action, outcome):
    s = phone()
    before = deepcopy(s["world_state"]["camera"])
    s = incoming(s, "call", "")
    e = next(iter(s["world_state"]["remote_events"].values()))
    assert e["status"] == "ringing"
    s = command(s, action, event_id=e["id"])
    assert s["world_state"]["remote_events"][e["id"]]["status"] == outcome
    assert s["world_state"]["camera"] == before
    assert s["world_state"]["characters"]["b"]["location_id"] == "away"
    if action == "answer":
        assert s["world_state"]["meta"]["interaction_focus"] == "call"
        s = command(s, "focus", focus="physical")
        assert s["world_state"]["remote_events"][e["id"]]["status"] == "answered"
        s = command(s, "end", event_id=e["id"])
        assert s["world_state"]["meta"]["interaction_focus"] == "physical"


def test_outgoing_does_not_assume_answer_and_canonical_timeout():
    s = command(phone(), "call", contact_id="a-b")
    e = next(iter(s["world_state"]["remote_events"].values()))
    assert e["status"] == "ringing"
    with pytest.raises(ValueError):
        command(s, "answer", event_id=e["id"])
    before = s["world_state"]["characters"]["b"]["location_id"]
    s["world_state"]["meta"]["world_time"] = 2
    batch = WorldHistoryV3()
    advance(s["world_state"], batch)
    assert (
        e["status"] == "missed"
        and s["world_state"]["characters"]["b"]["location_id"] == before
    )
    assert not s["world_state"]["knowledge"].get("b:secret")


def test_unresolved_and_shared_identity_no_eager_character():
    s = command(
        phone(), "add_contact", label="Мастерская", address="workshop", kind="shared"
    )
    cid = list(s["world_state"]["contacts"])[-1]
    s = command(s, "call", contact_id=cid)
    assert len(s["world_state"]["characters"]) == 4
    with pytest.raises(ValueError):
        resolve_identity(s, cid, address="workshop", evidence="Name", name="Иван")
    s = command(phone(), "add_contact", label="Неизвестный", address="number")
    cid = list(s["world_state"]["contacts"])[-1]
    s = command(s, "send", contact_id=cid, content="Привет")
    assert list(s["world_state"]["remote_events"].values())[-1]["status"] == "sent"
    linked = resolve_identity(
        s,
        cid,
        address="number",
        evidence="Подтверждён владелец номера",
        character_id="b",
    )
    assert len(linked["world_state"]["characters"]) == 4
    fresh = resolve_identity(
        s, cid, address="number", evidence="Представился", name="Иван"
    )
    assert len(fresh["world_state"]["characters"]) == 5
    assert (
        resolve_identity(
            fresh, cid, address="number", evidence="Представился", name="Иван"
        )
        == fresh
    )


def test_emergency_is_setting_destination_and_no_real_person():
    s = phone()
    with pytest.raises(ValueError):
        command(s, "call", service="medical")
    s["world_state"]["meta"]["communication"].update(
        region="fiction", emergency_numbers={"medical": "fiction-med"}
    )
    after = command(s, "call", service="medical")
    event = next(iter(after["world_state"]["remote_events"].values()))
    assert event["destination"] == "fiction-med" and event["recipient_ids"] == []
    assert after["world_state"]["characters"] == s["world_state"]["characters"]


def test_event_first_eligibility_and_external_control():
    s = phone()
    s["world_state"]["characters"]["b"]["intentions"] = [
        dict(
            id="reason",
            text="Связаться",
            status="active",
            source_sequence=None,
            evidence="",
            due_minute=None,
            revision=0,
            source_event_id=None,
            dependencies={},
            review_required=[],
            reviewed_signature="",
        )
    ]
    options = opportunities(s["world_state"])
    assert options
    p = dict(actor_id="b", action="call", contact_id="b-a", basis_ids=["reason"])
    after, batch = accept(s, p, options, "npc-operation")
    assert (
        next(iter(after["world_state"]["remote_events"].values()))["status"]
        == "ringing"
    )
    assert batch["events"] and not s["world_state"]["remote_events"]
    with pytest.raises(ValueError):
        accept(s, dict(p, actor_id="a"), options, "invalid-actor")
    with pytest.raises(ValueError):
        accept(s, dict(p, contact_id="a-b"), options, "invalid-path")
    with pytest.raises(ValueError):
        accept(s, dict(p, knowledge_ids=["a:secret"]), options, "invalid-knowledge")


def test_context_bounded_and_portrait_authorization():
    s = phone()
    for i in range(40):
        s = command(
            s, "send", contact_id="a-b", content="x" * 2000, operation_id=f"text-{i:08}"
        )
    ctx = context_projection(s["world_state"])
    assert len(ctx["recent"]) == 6
    assert len(json.dumps(ctx)) < 9000
    s["world_state"]["contacts"]["a-b"]["identity_visible"] = False
    c = projection(s)["contacts"][0]
    assert c["subject"]["id"] == "" and not c["subject"]["portrait"]


def test_qa_import_and_persisted_idempotency(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture

    repo = Repository(tmp_path / "phone.sqlite")
    sid = load_fixture(repo, "phone")["save"]
    initial = repo.get_save(sid)
    p = initial["state"]["phone"]
    assert p
    cmd = dict(
        action="send",
        operation_id="persistent-send",
        contact_id=p["contacts"][0]["id"],
        content="Авторский текст без изменений",
    )
    after = repo.remote_action(sid, initial["revision"], cmd)
    duplicate = repo.remote_action(sid, initial["revision"], cmd)
    assert duplicate == after
    with pytest.raises(ValueError):
        repo.remote_action(sid, initial["revision"], dict(cmd, content="Подмена"))
    assert (
        len(Repository(repo.path).get_snapshot(sid)["world_state"]["remote_events"])
        == 1
    )


@pytest.mark.parametrize("fail_first", [False, True])
def test_atomic_event_first_retry_regenerate_variants_and_rollback(
    tmp_path, fail_first
):
    import engine
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG, ordinary_job
    from backend.runtime_v3.models import Motivation

    repo = Repository(tmp_path / "lineage.sqlite")
    sid = load_fixture(repo, "phone")["save"]
    ordinary_job(repo, sid, "start")
    s = repo.get_snapshot(sid)
    s["world_state"]["characters"]["qa_vera"]["intentions"] = [
        Motivation(id="call-reason", text="Обсудить встречу").model_dump()
    ]
    with repo.connect() as db:
        db.execute("UPDATE saves SET state_json=? WHERE id=?", (json.dumps(s), sid))
    before = repo.get_snapshot(sid)
    camera = before["world_state"]["camera"]
    seen = []
    proposal = dict(
        actor_id="qa_vera",
        action="call",
        contact_id="phone-qa_vera-qa-kirill",
        basis_ids=["call-reason"],
    )

    def stream(**kw):
        if kw["messages"][0]["content"].startswith("Select at most ONE"):
            seen.append("plan")
            yield json.dumps({"action": proposal})
            return
        if not kw.get("response_format"):
            seen.append("narrative")
            current = json.loads(
                next(
                    m["content"].split("\n", 1)[1]
                    for m in kw["messages"]
                    if m["content"].startswith("Текущее состояние / GM-only\n")
                )
            )
            assert current["communication"]["recent"][0]["status"] == "ringing"
            assert (
                repo.get_save(sid)["state"]["phone"]["events"] == []
            )  # atomic publication
            yield "Телефон звонит. В комнате тихо."
        else:
            if fail_first:
                raise RuntimeError("Deterministic extraction outage")
            yield json.dumps(
                dict(
                    final_scene=dict(
                        location_id=camera["location_id"],
                        present_character_ids=camera["present_character_ids"],
                        elapsed_minutes=0,
                    ),
                    choices=[],
                )
            )

    jid = repo.begin_job(sid, "Смотрю в окно.", "turn", CONFIG)
    with (
        patch(
            "engine.find_loaded_model",
            return_value={"config": {"context_length": 32768}},
        ),
        patch("engine.chat_stream", side_effect=stream),
    ):
        engine.run_job(repo.path, jid, engine.Worker())
    if fail_first:
        assert repo.get_job(jid)["status"] == "error"
        assert repo.get_save(sid)["state"]["phone"]["events"] == []
        assert repo.public_job(repo.get_job(jid))["narrative"] == ""
        assert repo.get_snapshot(sid) == before
        fail_first = False
        repo.retry_job(jid, CONFIG)
        with (
            patch(
                "engine.find_loaded_model",
                return_value={"config": {"context_length": 32768}},
            ),
            patch("engine.chat_stream", side_effect=stream),
        ):
            engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]
    after = repo.get_snapshot(sid)
    events = after["world_state"]["remote_events"]
    assert len(events) == 1
    original = repo.list_turns(sid)[-1]
    assert seen == ["plan", "narrative"]

    def regenerated(**kw):
        assert not kw["messages"][0]["content"].startswith("Select at most ONE")
        yield (
            json.dumps(
                dict(
                    final_scene=dict(
                        location_id=camera["location_id"],
                        present_character_ids=camera["present_character_ids"],
                        elapsed_minutes=0,
                    ),
                    choices=[],
                )
            )
            if kw.get("response_format")
            else "Телефон продолжает звонить."
        )

    jid2 = repo.begin_job(sid, "", "regenerate", CONFIG)
    with (
        patch(
            "engine.find_loaded_model",
            return_value={"config": {"context_length": 32768}},
        ),
        patch("engine.chat_stream", side_effect=regenerated),
    ):
        engine.run_job(repo.path, jid2, engine.Worker())
    assert repo.get_job(jid2)["status"] == "saved", repo.get_job(jid2)["error"]
    assert repo.get_snapshot(sid)["world_state"]["remote_events"] == events
    repo.select_variant(
        sid,
        original["id"],
        original["active_variant_id"],
        repo.get_save(sid)["revision"],
    )
    assert repo.get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    assert not repo.get_save(sid)["state"]["phone"]["events"]


def test_phone_ordinary_cycle_and_legacy_disabled(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job

    repo = Repository(tmp_path / "cycle.sqlite")
    sid = load_fixture(repo, "phone")["save"]
    ordinary_job(repo, sid, "start")
    ordinary_job(repo, sid)
    saved = repo.get_snapshot(sid)
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == saved
    ordinary_job(repo, sid)
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == saved
    legacy = load_fixture(repo, "base")["save"]
    ordinary_job(repo, legacy, "start")
    assert repo.get_save(legacy)["state"]["phone"] is None


def test_message_agreement_uses_existing_commitment_pipeline_and_read_proof():
    from backend.runtime_v3.resolver import StateResolver

    s = command(
        phone(),
        "send",
        contact_id="a-b",
        content="Давай завтра в 19:00 встретимся.",
        operation_id="propose-meeting",
    )
    first = list(s["world_state"]["remote_events"].values())[-1]
    s, _ = apply(
        s,
        dict(action="read", event_id=first["id"], operation_id="npc-read-proposal"),
        actor_id="b",
        autonomous=True,
    )
    s = incoming(s, "send", "Да, договорились.")
    second = list(s["world_state"]["remote_events"].values())[-1]
    record = dict(
        id="remote-plan",
        description="Встреча",
        character_ids=["a", "b"],
        assertion="agreed",
        temporal=dict(day_offset=1, time="19:00"),
        remote_source_ids=[first["id"], second["id"]],
        remote_time_source_id=first["id"],
        evidence="Да, договорились.",
        player_assertion="explicit_choice",
        player_evidence=first["content"],
    )

    def resolve(snap, item):
        c = snap["world_state"]["camera"]
        return StateResolver(
            snap["world_state"], "В комнате тихо.", "Смотрю в окно."
        ).resolve(
            dict(
                final_scene=dict(
                    location_id=c["location_id"],
                    present_character_ids=c["present_character_ids"],
                ),
                scheduled_event_changes=[item],
            )
        )

    from backend.services.world_delta_errors import StructuralDeltaError
    before=deepcopy(s)
    with pytest.raises(StructuralDeltaError) as exc: resolve(s, record)
    assert exc.value.code=='commitment_remote_unperceived' and s==before
    s = command(s, "read", event_id=second["id"])
    accepted = resolve(s, record)
    assert (
        accepted.state["scheduled_events"]["remote-plan"]["remote_source_ids"]
        == record["remote_source_ids"]
    )
    assert (
        accepted.state["scheduled_events"]["remote-plan"]["time_reference_minute"]
        == first["world_time"]
    )
    assert accepted.history["state_changes"]
    with pytest.raises(StructuralDeltaError) as exc:
        resolve(s, dict(record, player_evidence="Я обещаю другое."))
    assert exc.value.code=='controlled_actor_unsupported'


def test_endpoint_identity_establishment_is_lazy_address_bound_and_service_specific():
    s = command(phone(), "add_contact", label="Неизвестный", address="address-b")
    cid = list(s["world_state"]["contacts"])[-1]
    s = command(s, "call", contact_id=cid)
    eid = list(s["world_state"]["remote_events"])[-1]
    opts = opportunities(s["world_state"])
    p = dict(
        actor_id="endpoint",
        action="identify",
        event_id=eid,
        basis_ids=[eid],
        speaker_name="Борис",
        existing_character_id="b",
    )
    linked, batch = accept(s, p, opts, "endpoint-operation")
    assert len(linked["world_state"]["characters"]) == 4
    assert linked["world_state"]["contacts"][cid]["character_id"] == "b"
    assert linked["world_state"]["remote_events"][eid]["status"] == "answered"
    with pytest.raises(ValueError):
        accept(s, dict(p, existing_character_id="child"), opts, "wrong-identity")
    s = command(
        phone(), "add_contact", label="Мастерская", address="workshop", kind="shared"
    )
    cid = list(s["world_state"]["contacts"])[-1]
    s = command(s, "call", contact_id=cid)
    eid = list(s["world_state"]["remote_events"])[-1]
    reached, _ = accept(
        s,
        dict(
            actor_id="endpoint",
            action="identify",
            event_id=eid,
            basis_ids=[eid],
            speaker_name="Иван",
        ),
        opportunities(s["world_state"]),
        "service-endpoint",
    )
    assert reached["world_state"]["contacts"][cid]["character_id"] is None
    assert len(reached["world_state"]["characters"]) == 5


def test_former_group_member_can_read_delivery_but_not_future_membership():
    s = command(phone(), "create_group", label="Группа", member_ids=["b"])
    gid = next(iter(s["world_state"]["conversations"]))
    s, _ = apply(
        s,
        dict(
            action="send",
            conversation_id=gid,
            content="Старое сообщение",
            operation_id="group-inbound",
        ),
        actor_id="b",
        autonomous=True,
    )
    s = command(s, "leave", conversation_id=gid)
    s, _ = apply(
        s,
        dict(
            action="remove",
            conversation_id=gid,
            member_ids=["b"],
            operation_id="later-removal",
        ),
        actor_id="b",
        autonomous=True,
    )
    projected = projection(s)["conversations"][0]
    assert not projected["active"] and {p["id"] for p in projected["participants"]} == {
        "a",
        "b",
    }
    s = command(s, "read", conversation_id=gid)
    assert projection(s)["events"][0]["content"] == "Старое сообщение"
    with pytest.raises(ValueError):
        command(s, "send", conversation_id=gid, content="После выхода")


def test_existing_direct_conversation_does_not_bypass_contact_block():
    s = command(phone(), "send", contact_id="a-b", content="Привет")
    gid = next(iter(s["world_state"]["conversations"]))
    s = command(s, "edit_contact", contact_id="a-b", blocked=True)
    with pytest.raises(ValueError):
        command(s, "send", conversation_id=gid, content="Заблокирован")
    with pytest.raises(ValueError):
        command(s, "call", conversation_id=gid)


def test_extraction_call_audibility_cannot_create_physical_witness_knowledge():
    from backend.runtime_v3.resolver import StateResolver

    s = incoming(phone(), "call", "")
    eid = next(iter(s["world_state"]["remote_events"]))
    s = command(s, "answer", event_id=eid)
    c = s["world_state"]["camera"]
    narrative = "Борис говорит: пароль — кедр."
    raw = dict(
        final_scene=dict(
            location_id=c["location_id"],
            present_character_ids=c["present_character_ids"],
        ),
        events=[
            dict(
                id="speech",
                text=narrative,
                evidence=narrative,
                medium="conversation",
                interaction_channel="call",
                participants=["a", "b"],
                witnesses=["child"],
            )
        ],
    )
    denied = StateResolver(s["world_state"], narrative, "Слушаю.").resolve(raw)
    assert not denied.history["events"]
    raw["events"][0]["witnesses"] = []
    accepted = StateResolver(s["world_state"], narrative, "Слушаю.").resolve(raw)
    assert accepted.history["events"][0]["interaction_channel"] == "call"
    raw["events"][0]["interaction_channel"] = "physical"
    denied = StateResolver(s["world_state"], narrative, "Слушаю.").resolve(raw)
    assert not denied.history["events"]


def test_saturated_context_keeps_phone_bounded_without_unread_payload(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.remote_models import RemoteEvent
    from context_builder import estimate
    from test_narrative_test_world import NARRATIVE

    repo = Repository(tmp_path / "saturated-phone.sqlite")
    sid = load_fixture(repo, "newborn-triplets")["save"]
    snap = repo.get_snapshot(sid)
    s = snap["world_state"]
    actor = s["camera"]["controlled_actor_id"]
    sender = next(cid for cid in s["characters"] if cid != actor)
    s["meta"]["communication"] = CommunicationCapabilities(
        text_message=True, voice_call=True, presentation="phone"
    ).model_dump()
    for i in range(200):
        e = RemoteEvent(
            id=f"msg-{i}",
            ordinal=i,
            channel="TEXT_MESSAGE",
            sender_id=sender,
            recipient_ids=[actor],
            destination=actor,
            content="UNREAD_PRIVATE_PAYLOAD " * 80,
            world_time=s["meta"]["world_time"],
            updated_at=s["meta"]["world_time"],
            turn_id=s["meta"]["turn_id"],
            status="delivered",
            delivered_to=[actor],
            provenance="fixture",
            operation_id=f"fixture-{i}",
        )
        s["remote_events"][e.id] = e.model_dump()
    for extraction in (None, NARRATIVE):
        messages = build_context(
            snap, [], "Смотрю в окно.", "turn", 32768, 4096, extraction_text=extraction
        )
        assert estimate(messages) <= 32768 - 4096 - 256
        assert "UNREAD_PRIVATE_PAYLOAD" not in json.dumps(messages)
        current = json.loads(
            next(
                m["content"].split("\n", 1)[1]
                for m in messages
                if m["content"].startswith("Текущее состояние / GM-only\n")
            )
        )
        assert 1 <= len(current["communication"]["recent"]) <= 6
        assert (
            current["camera"]["present_character_ids"]
            == s["camera"]["present_character_ids"]
        )


def test_raw_history_cannot_leak_unread_message_payload_into_context():
    from backend.runtime_v3.context import build_context

    snap, batch = apply(
        phone(),
        dict(
            action="send",
            operation_id="secret-incoming",
            contact_id="b-a",
            content="SECRET_UNREAD_CONTENT",
        ),
        actor_id="b",
        autonomous=True,
    )
    messages = build_context(
        snap, [], "Смотрю в окно.", "turn", 32768, 4096, world_history=batch
    )
    assert "SECRET_UNREAD_CONTENT" not in json.dumps(messages)
    snap = command(
        snap, "read", event_id=next(iter(snap["world_state"]["remote_events"]))
    )
    messages = build_context(
        snap, [], "Смотрю в окно.", "turn", 32768, 4096, world_history=batch
    )
    assert "SECRET_UNREAD_CONTENT" in json.dumps(messages)


def test_device_choices_are_removed_before_continuity_projection():
    from backend.runtime_v3.resolver import StateResolver

    s = incoming(phone(), "call", "")
    c = s["world_state"]["camera"]
    result = StateResolver(
        s["world_state"], "В комнате тихо.", "Смотрю в окно."
    ).resolve(
        dict(
            final_scene=dict(
                location_id=c["location_id"],
                present_character_ids=c["present_character_ids"],
                elapsed_minutes=0,
            ),
            choices=[
                dict(action="Ответить", speech="", device_control="answer"),
                dict(action="Посмотреть в окно", speech=""),
            ],
        )
    )
    assert result.choices == [
        dict(action="Посмотреть в окно", speech="", interaction_channel="physical")
    ]
    assert next(iter(result.state["remote_events"].values()))["status"] == "ringing"


def test_rejected_remote_proposal_has_no_cue_payload_or_side_effect():
    from backend.runtime_v3.remote_initiative import stage
    from backend.runtime_v3.models import Motivation

    snap = phone()
    snap["world_state"]["characters"]["b"]["intentions"] = [
        Motivation(id="reason", text="Связаться").model_dump()
    ]

    def generate(*args, **kwargs):
        return iter(
            [
                json.dumps(
                    dict(
                        action=dict(
                            actor_id="b",
                            action="call",
                            contact_id="missing",
                            basis_ids=["reason"],
                        )
                    )
                )
            ]
        )

    staged = stage(snap, generate, "rejected-proposal")
    assert staged["world_state"] == snap["world_state"]
    assert staged["_remote_batch"]["state_changes"][0]["kind"] == "remote_rejected"
    assert not context_projection(staged["world_state"])["recent"]
    assert not projection(staged)["events"]


def test_remote_channel_is_setting_neutral_not_a_phone_presentation():
    from backend.runtime_v3.remote import validate_event_channel

    snap = phone()
    snap["world_state"]["meta"]["communication"]["presentation"] = "none"
    snap = incoming(snap, "call", "")
    eid = next(iter(snap["world_state"]["remote_events"]))
    snap = command(snap, "answer", event_id=eid)
    assert projection(snap) is None
    assert context_projection(snap["world_state"])["active_call"] == eid
    assert not validate_event_channel(
        snap["world_state"], dict(medium="observation", participants=["a", "b"])
    )


def test_lazy_identity_reply_reuses_original_direct_conversation():
    snap = command(phone(), "add_contact", label="Неизвестный", address="new-person")
    cid = list(snap["world_state"]["contacts"])[-1]
    snap = command(snap, "send", contact_id=cid, content="Привет")
    eid = next(iter(snap["world_state"]["remote_events"]))
    gid = next(iter(snap["world_state"]["conversations"]))
    snap, _ = accept(
        snap,
        dict(
            actor_id="endpoint",
            action="identify",
            event_id=eid,
            basis_ids=[eid],
            speaker_name="Иван",
        ),
        opportunities(snap["world_state"]),
        "identity-response",
    )
    actor = snap["world_state"]["contacts"][cid]["character_id"]
    contact = next(
        c["id"]
        for c in snap["world_state"]["contacts"].values()
        if c["owner_id"] == actor
    )
    snap, _ = apply(
        snap,
        dict(
            action="send",
            contact_id=contact,
            content="Привет!",
            operation_id="endpoint-reply",
        ),
        actor_id=actor,
        autonomous=True,
    )
    assert len(snap["world_state"]["conversations"]) == 1
    assert (
        list(snap["world_state"]["remote_events"].values())[-1]["conversation_id"]
        == gid
    )


def test_ui_world_history_does_not_bypass_phone_read_or_actor_scope():
    from backend.runtime_v3.selectors import ui_view

    snap, batch = apply(
        phone(),
        dict(
            action="send",
            operation_id="private-ui-message",
            contact_id="b-a",
            content="SECRET_PHONE_PAYLOAD",
        ),
        actor_id="b",
        autonomous=True,
    )
    assert "SECRET_PHONE_PAYLOAD" not in json.dumps(ui_view(snap, batch))
    eid = next(iter(snap["world_state"]["remote_events"]))
    snap, read = apply(
        snap, dict(action="read", operation_id="private-ui-read", event_id=eid)
    )
    for section, rows in read.items():
        batch.setdefault(section, []).extend(rows)
    assert "SECRET_PHONE_PAYLOAD" in json.dumps(ui_view(snap, batch))
    other, _ = transition(snap, "temporary", "child", "other-reader")
    assert "SECRET_PHONE_PAYLOAD" not in json.dumps(ui_view(other, batch))


@pytest.mark.parametrize("restricted", ["unavailable", "blocked"])
def test_endpoint_identity_does_not_bypass_known_actor_restrictions(restricted):
    snap = command(phone(), "add_contact", label="Другой контакт", address="address-b")
    cid = list(snap["world_state"]["contacts"])[-1]
    snap = command(snap, "call", contact_id=cid)
    eid = next(iter(snap["world_state"]["remote_events"]))
    if restricted == "unavailable":
        snap["world_state"]["characters"]["b"]["life_status"] = "dead"
    else:
        snap["world_state"]["contacts"]["b-a"]["blocked"] = True
    with pytest.raises(ValueError):
        accept(
            snap,
            dict(
                actor_id="endpoint",
                action="identify",
                event_id=eid,
                basis_ids=[eid],
                speaker_name="Борис",
                existing_character_id="b",
            ),
            opportunities(snap["world_state"]),
            "restricted-endpoint",
        )
    assert snap["world_state"]["remote_events"][eid]["status"] == "ringing"
    assert snap["world_state"]["contacts"][cid]["character_id"] is None


def test_shared_emergency_number_preserves_selected_service_in_call_log():
    snap = phone()
    snap["world_state"]["meta"]["communication"].update(
        region="fiction",
        emergency_numbers={
            "medical": "qa-shared",
            "police": "qa-shared",
            "fire": "qa-shared",
        },
    )
    snap = command(snap, "call", service="police")
    event = next(iter(snap["world_state"]["remote_events"].values()))
    assert event["destination"] == "qa-shared" and event["service"] == "police"
    assert projection(snap)["events"][0]["label"] == "Полиция"


def test_direct_reply_without_reverse_contact():
    s=phone();del s['world_state']['contacts']['b-a']
    s=command(s,'send',contact_id='a-b',content='Привет')
    event=list(s['world_state']['remote_events'].values())[-1]
    s,_=accept(s,dict(action='read',actor_id='b',event_id=event['id'],basis_ids=[event['id']]),opportunities(s['world_state']),'read-one-way')
    options=opportunities(s['world_state'])
    candidate=next(o for o in options if o['actor_id']=='b' and 'send' in o['actions'])
    assert {'conversation_id':event['conversation_id']} in candidate['paths']
    s,_=accept(s,dict(action='send',actor_id='b',conversation_id=event['conversation_id'],basis_ids=[event['id']],content='Привет в ответ'),options,'reply-one-way')
    reply=list(s['world_state']['remote_events'].values())[-1]
    assert reply['conversation_id']==event['conversation_id']
    assert 'a' in reply['delivered_to']
    assert 'b-a' not in s['world_state']['contacts']
