"""#109: real engine/Resolver/SQLite lifecycle, with controlled provider output."""

from copy import deepcopy
import json
from unittest.mock import patch

import engine
import pytest
from backend.repositories.preparation import Repository
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.repository import read_history
from devtools.narrative_test_world import ACTOR_ID, load_fixture
from runtime_v3_fixture import execute
from test_narrative_test_world import CONFIG, ordinary_job


def connected(tmp_path):
    repo = Repository(tmp_path / "call.sqlite")
    sid = load_fixture(repo, "phone")["save"]
    ordinary_job(repo, sid, "start")
    ordinary_job(repo, sid)
    # Establish actual physical separation through the ordinary Resolver, rather
    # than editing persisted WorldState or treating the call as co-location.
    state = repo.get_snapshot(sid)["world_state"]
    camera = state["camera"]
    away = next(lid for lid in state["locations"] if lid != camera["location_id"])
    text = "Вера ушла в другое место."
    jid = repo.begin_job(sid, text, "turn", CONFIG)
    execute(
        repo,
        jid,
        dict(
            final_scene=dict(
                location_id=camera["location_id"],
                present_character_ids=[
                    cid for cid in camera["present_character_ids"] if cid != "qa_vera"
                ],
                elapsed_minutes=0,
            ),
            movements=[dict(actor_id="qa_vera", to_location_id=away, evidence=text)],
        ),
        text,
    )
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]

    def remote(action, **kw):
        return repo.remote_action(
            sid,
            repo.get_save(sid)["revision"],
            dict(action=action, operation_id="audit-call-" + action, **kw),
        )

    contact = next(
        c["id"]
        for c in repo.get_snapshot(sid)["world_state"]["contacts"].values()
        if c["owner_id"] == ACTOR_ID and c["character_id"] == "qa_vera"
    )
    remote("call", contact_id=contact)
    eid = next(iter(repo.get_snapshot(sid)["world_state"]["remote_events"]))
    repo.transition_protagonist(
        sid,
        repo.get_save(sid)["revision"],
        "audit-control-vera",
        "temporary",
        "qa_vera",
    )
    remote("answer", event_id=eid)
    repo.transition_protagonist(
        sid,
        repo.get_save(sid)["revision"],
        "audit-control-kirill",
        "temporary",
        ACTOR_ID,
    )
    remote("focus", focus="call")
    return repo, sid, eid


def job(
    repo,
    sid,
    actor=ACTOR_ID,
    effect="conscious",
    kind="turn",
    change=True,
    reject=False,
):
    text = ("Кирилл" if actor == ACTOR_ID else "Вера") + (
        " умер." if effect == "dead" else " потерял сознание."
    )
    camera = repo.get_snapshot(sid)["world_state"]["camera"]
    payload = dict(
        final_scene=dict(
            location_id=camera["location_id"],
            present_character_ids=camera["present_character_ids"],
            elapsed_minutes=0,
        ),
        choices=[],
    )
    evidence = dict(
        assertion="established",
        evidence=text,
        player_assertion="explicit_choice",
        player_evidence=text,
    )
    if change:
        if effect == "dead":
            payload["life_changes"] = [dict(id=actor, life_status="dead", **evidence)]
        else:
            payload["condition_changes"] = [
                dict(
                    id="audit-unconscious",
                    actor_id=actor,
                    description="Невозможно продолжить разговор",
                    effects={effect: False},
                    **evidence
                )
            ]
    if reject:
        payload["final_scene"]["present_character_ids"] = [
            *camera["present_character_ids"],
            "qa_vera",
        ]
    jid = repo.begin_job(sid, text if kind == "turn" else "", kind, CONFIG)
    calls = execute(repo, jid, payload, text if change else "В комнате тихо.")
    assert repo.get_job(jid)["status"] == (
        "error" if reject else "saved"
    ), repo.get_job(jid)["error"]
    if not reject:
        assert len(calls) == 2
    return repo.get_snapshot(sid)


def history(repo, snapshot):
    with repo.connect() as db:
        return read_history(db, snapshot["history_head"])[0]


def lta(repo, sid):
    config = dict(
        CONFIG, long_term_advance=dict(amount=1, unit="months", max_llm_calls=0)
    )
    jid = repo.begin_job(sid, "", "long_term", config)
    with patch(
        "engine.chat_stream", side_effect=AssertionError("No LLM for zero budget")
    ):
        engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]
    return repo.get_snapshot(sid)


def test_incapacitated_actor_is_not_trapped_in_call(tmp_path):
    repo, sid, eid = connected(tmp_path)
    before = repo.get_snapshot(sid)
    after = job(repo, sid)
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == after
    state = after["world_state"]
    assert all(
        not capabilities(state, ACTOR_ID)[k]
        for k in ("can_act", "can_speak", "can_perceive")
    )
    assert state["remote_events"][eid]["status"] == "ended"
    assert state["meta"]["current_protagonist_id"] == ACTOR_ID
    assert state["camera"] == before["world_state"]["camera"]
    assert state["meta"]["interaction_focus"] == "physical"
    advanced = lta(repo, sid)
    assert advanced["last_long_term_advance"]["interruption"] is None
    assert advanced["world_state"]["meta"]["world_time"] > state["meta"]["world_time"]
    assert not capabilities(advanced["world_state"], ACTOR_ID)["can_act"]


@pytest.mark.parametrize(
    "actor,effect",
    [
        ("qa_vera", "conscious"),
        (ACTOR_ID, "dead"),
        ("qa_vera", "dead"),
        (ACTOR_ID, "can_act"),
        ("qa_vera", "can_speak"),
        ("qa_vera", "can_perceive"),
    ],
)
def test_either_participant_capability_transition_is_atomic_and_historical(
    tmp_path, actor, effect
):
    repo, sid, eid = connected(tmp_path)
    before = repo.get_snapshot(sid)
    after = job(repo, sid, actor, effect)
    s = after["world_state"]
    event = s["remote_events"][eid]
    assert event["status"] == "ended"
    assert event["provenance"] == "system:participant_incapacitated"
    for key in (
        "id",
        "sender_id",
        "recipient_ids",
        "world_time",
        "operation_id",
        "turn_id",
    ):
        assert event[key] == before["world_state"]["remote_events"][eid][key]
    changes = [r for r in history(repo, after)["state_changes"] if r.get("termination")]
    assert len(changes) == 1
    assert changes[0]["before"] == before["world_state"]["remote_events"][eid]
    assert changes[0]["after"] == event
    assert changes[0]["termination"]["actors"][actor]["unavailable"]
    assert s["meta"]["current_protagonist_id"] == ACTOR_ID
    assert s["meta"]["protagonist_required"] == (actor == ACTOR_ID and effect == "dead")
    assert s["meta"]["interaction_focus"] == "physical"
    assert not s["camera"]["remote_interactions"]
    assert s["knowledge"] == before["world_state"]["knowledge"]
    assert Repository(repo.path).get_snapshot(sid) == after
    assert not repo.get_save(sid)["history_warnings"]
    if actor == ACTOR_ID and effect == "dead":
        with pytest.raises(ValueError, match="Главный герой умер"):
            lta(repo, sid)
    else:
        advanced = lta(repo, sid)
        assert advanced["last_long_term_advance"]["interruption"] is None
        assert (
            len(
                [
                    r
                    for r in history(repo, advanced)["state_changes"]
                    if r.get("termination")
                ]
            )
            == 1
        )
        repo.rollback_last(sid)
        assert repo.get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    ordinary_job(repo, sid)
    assert (
        repo.get_snapshot(sid)["world_state"]["remote_events"][eid]["status"]
        == "answered"
    )


def test_regenerate_variants_and_rollback_restore_both_sides(tmp_path):
    repo, sid, eid = connected(tmp_path)
    before = repo.get_snapshot(sid)
    after = job(repo, sid)
    original = repo.list_turns(sid)[-1]
    repeated = job(repo, sid, kind="regenerate")
    assert repeated["world_state"] == after["world_state"]
    assert (
        len(
            [
                r
                for r in history(repo, repeated)["state_changes"]
                if r.get("termination")
            ]
        )
        == 1
    )
    alternate = job(repo, sid, kind="regenerate", change=False)
    assert alternate["world_state"]["remote_events"][eid]["status"] == "answered"
    assert alternate["world_state"]["meta"]["interaction_focus"] == "call"
    assert not alternate["world_state"]["conditions"]
    assert not [
        r for r in history(repo, alternate)["state_changes"] if r.get("termination")
    ]
    repo.select_variant(
        sid,
        original["id"],
        original["active_variant_id"],
        repo.get_save(sid)["revision"],
    )
    assert repo.get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    ordinary_job(repo, sid)


def test_rejected_job_cannot_publish_partial_life_or_remote_state(tmp_path):
    repo, sid, _ = connected(tmp_path)
    before = repo.get_snapshot(sid)
    original_history = history(repo, before)
    # Resolver's real false-colocation guard runs after Life + remote reconciliation.
    job(repo, sid, reject=True)
    assert Repository(repo.path).get_snapshot(sid) == before
    assert history(repo, before) == original_history


def test_healthy_call_blocks_lta_and_reconciliation_is_idempotent(tmp_path):
    from backend.runtime_v3.models import WorldHistoryV3
    from backend.runtime_v3.remote import advance

    repo, sid, eid = connected(tmp_path)
    before = repo.get_snapshot(sid)
    advanced = lta(repo, sid)
    assert advanced["last_long_term_advance"]["interruption"]["kind"] == "remote_call"
    assert (
        advanced["world_state"]["meta"]["world_time"]
        == before["world_state"]["meta"]["world_time"]
    )
    assert (
        advanced["world_state"]["remote_events"][eid]
        == before["world_state"]["remote_events"][eid]
    )
    assert advanced["world_state"]["meta"]["interaction_focus"] == "call"
    repo.rollback_last(sid)
    after = job(repo, sid)
    state = deepcopy(after["world_state"])
    batch = WorldHistoryV3()
    advance(state, batch)
    advance(state, batch)
    assert state == after["world_state"]
    assert not batch.events and not batch.state_changes


def test_legacy_incapacitated_call_reconciles_at_lta_commit_not_reload(tmp_path):
    from backend.runtime_v3.long_term import plan

    repo, sid, eid = connected(tmp_path)
    # Simulate a pre-fix persisted job with the original lifecycle implementation.
    with patch("backend.runtime_v3.remote.reconcile_calls"):
        legacy = job(repo, sid)
    assert legacy["world_state"]["remote_events"][eid]["status"] == "answered"
    assert Repository(repo.path).get_snapshot(sid) == legacy
    original_history = history(repo, legacy)
    preview = plan(legacy, dict(amount=1, unit="months", max_llm_calls=0))
    assert preview.interruption is None
    assert Repository(repo.path).get_snapshot(sid) == legacy
    after = lta(repo, sid)
    assert after["world_state"]["remote_events"][eid]["status"] == "ended"
    assert (
        after["world_state"]["remote_events"][eid]["updated_at"]
        == legacy["world_state"]["meta"]["world_time"]
    )
    assert after["last_long_term_advance"]["interruption"] is None
    assert history(repo, legacy) == original_history
    assert Repository(repo.path).get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == legacy
    second = lta(repo, sid)
    assert second["world_state"] == after["world_state"]


@pytest.mark.parametrize("actor,expected", [("a", "ended"), ("b", "ringing")])
def test_ringing_uses_caller_capacity_without_inventing_recipient_refusal(
    actor, expected
):
    from test_remote_communication import phone, command
    from backend.runtime_v3.models import WorldHistoryV3
    from backend.runtime_v3.remote import advance

    snapshot = command(phone(), "call", contact_id="a-b")
    state = snapshot["world_state"]
    state["characters"][actor]["capabilities"]["can_speak"] = False
    before = deepcopy(state)
    batch = WorldHistoryV3()
    advance(state, batch)
    event = next(iter(state["remote_events"].values()))
    assert event["status"] == expected
    assert state["camera"] == before["camera"]
    assert state["meta"]["interaction_focus"] == "physical"
    if actor == "b":
        assert not batch.events
        state["meta"]["world_time"] += state["meta"]["communication"][
            "ring_timeout_minutes"
        ]
        advance(state, batch)
        assert event["status"] == "missed"
        assert "termination" not in batch.events[0]


def test_voluntary_end_remains_distinct_and_movement_loss_does_not_end_call():
    from test_remote_communication import phone, incoming, command
    from backend.runtime_v3.models import WorldHistoryV3
    from backend.runtime_v3.remote import advance, apply

    snapshot = incoming(phone(), "call", "")
    eid = next(iter(snapshot["world_state"]["remote_events"]))
    snapshot = command(snapshot, "answer", event_id=eid)
    snapshot["world_state"]["characters"]["b"]["capabilities"]["can_move"] = False
    batch = WorldHistoryV3()
    advance(snapshot["world_state"], batch)
    assert not batch.events
    assert snapshot["world_state"]["remote_events"][eid]["status"] == "answered"
    after, history_batch = apply(
        snapshot, dict(action="end", event_id=eid, operation_id="voluntary-hangup")
    )
    assert after["world_state"]["remote_events"][eid]["status"] == "ended"
    assert (
        after["world_state"]["remote_events"][eid]["provenance"]
        != "system:participant_incapacitated"
    )
    assert "termination" not in history_batch["events"][0]


def test_lta_group_keeps_system_call_transition_separate_from_extracted_events():
    from test_remote_communication import phone, incoming, command
    from backend.runtime_v3.long_term import plan, run
    from backend.runtime_v3.models import Thread

    snapshot = incoming(phone(), "call", "")
    eid = next(iter(snapshot["world_state"]["remote_events"]))
    snapshot = command(snapshot, "answer", event_id=eid)
    state = snapshot["world_state"]
    state["camera"].update(mode="observer", controlled_actor_id=None)
    state["camera"]["remote_interactions"] = [dict(actor_id="b", channel="phone", last_active_turn=0)]
    state["meta"]["interaction_focus"] = "physical"
    state["threads"]["health"] = Thread(
        id="health", description="Состояние Бориса", character_ids=["b"]
    ).model_dump()
    request = dict(amount=2, unit="weeks", max_llm_calls=2)
    candidate = next(
        c for c in plan(snapshot, request).candidates if c.source_id == "health"
    )
    text = "Борис потерял сознание."
    raw = dict(
        final_scene=dict(
            location_id="away", present_character_ids=["b"], elapsed_minutes=0
        ),
        events=[
            dict(
                id="collapse",
                text=text,
                evidence=text,
                participants=["b"],
                witnesses=[],
                medium="observation",
                advance_candidate_ids=[candidate.id],
            )
        ],
        consequences=[
            dict(kind="injury", actor_id="b", source_event_id="collapse",
                 basis_ids=["health"], evidence=text)
        ],
        condition_changes=[
            dict(
                id="collapse",
                actor_id="b",
                description="Без сознания",
                effects={"conscious": False},
                source_event_id="collapse",
                assertion="established",
                evidence=text,
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(snapshot, request, generate=generate)
    assert report["accepted"], report["diagnostics"]
    assert after["world_state"]["remote_events"][eid]["status"] == "ended"
    assert len([e for e in batch["events"] if e.get("termination")]) == 1
    assert not after["world_state"]["camera"]["remote_interactions"]
