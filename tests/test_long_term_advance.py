"""#43 canonical interval regressions; providers are deterministic fakes only."""

from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.long_term import plan, run, AdvanceRequest
from backend.runtime_v3.long_term_calendar import target_minute, annual_occurrences
from backend.runtime_v3.models import Character, ScheduledEvent, Thread
from test_reproduction import state, snap, conceive


def fixture():
    snapshot = snap(state())
    snapshot["world_state"]["camera"]["present_character_ids"] = ["a"]
    return snapshot


@pytest.mark.parametrize("years", [5, 15])
def test_long_advance_no_calls_or_invented_biography(years):
    before = fixture()
    original = deepcopy(before)
    after, batch, report = run(
        before, dict(amount=years, unit="years", max_llm_calls=0)
    )
    assert before == original
    assert report["llm_calls"] == 0
    assert after["world_state"]["meta"]["world_time"] == target_minute(
        before["world_state"], years, "years"
    )
    for key in (
        "knowledge",
        "roles",
        "residences",
        "relationships",
        "objective_relations",
    ):
        assert after["world_state"][key] == before["world_state"][key]
    assert (
        after["world_state"]["characters"]["a"]["personality"]
        == before["world_state"]["characters"]["a"]["personality"]
    )


def test_due_process_survives_zero_budget_without_invented_birth():
    before = snap(conceive().state)
    before["world_state"]["camera"].update(
        controlled_actor_id="c", present_character_ids=["c"]
    )
    after, batch, report = run(before, dict(amount=15, unit="years", max_llm_calls=0))
    p = next(iter(after["world_state"]["pregnancies"].values()))
    assert p["status"] == "due"
    assert all(
        child["id"] not in after["world_state"]["characters"] for child in p["children"]
    )
    assert any(c["kind"] == "process_due" for c in batch["state_changes"])
    assert report["unresolved"]


def test_commitment_interrupts_but_never_happens():
    before = fixture()
    s = before["world_state"]
    s["scheduled_events"]["meeting"] = ScheduledEvent(
        id="meeting",
        description="Встреча",
        character_ids=["a"],
        due_minute=50000,
        commitment=True,
    ).model_dump()
    after, _, report = run(before, dict(amount=5, unit="years", max_llm_calls=0))
    assert report["actual_target"] == 50000
    assert report["interruption"]["source_id"] == "meeting"
    assert after["world_state"]["scheduled_events"]["meeting"]["status"] == "pending"
    s["scheduled_events"]["meeting"]["status"] = "cancelled"
    assert plan(before, dict(amount=5, unit="years")).interruption is None
    s["scheduled_events"]["meeting"].update(status="pending", due_minute=100_000_000)
    assert plan(before, dict(amount=5, unit="years")).interruption is None


def test_dependencies_block_due_and_preserve_cancelled():
    before = fixture()
    s = before["world_state"]
    s["scheduled_events"]["cancelled"] = ScheduledEvent(
        id="cancelled", description="Отмена", status="cancelled"
    ).model_dump()
    s["scheduled_events"]["child"] = ScheduledEvent(
        id="child",
        description="Зависит",
        character_ids=["a"],
        due_minute=10,
        depends_on=["cancelled"],
    ).model_dump()
    assert plan(before, dict(amount=15, unit="years")).interruption is None


@pytest.mark.parametrize("cap", [0, 1, 2, 3, 4, 8])
def test_hard_cap_100_npcs_and_deterministic_transitions(cap):
    before = fixture()
    s = before["world_state"]
    for n in range(120):
        cid = f"npc-{n:03}"
        s["characters"][cid] = Character(
            id=cid,
            life_status="alive",
            birth_date="2025-01-01",
            developmental_stage="infant",
        ).model_dump()
        before["character_cards"].append(dict(id=cid, name=cid, fields={}))
        s["threads"][cid] = Thread(
            id=cid, description="Нерешённая задача", character_ids=[cid], relevance=0.8
        ).model_dump()
    calls = []

    def generate(stage, *args, **kwargs):
        calls.append(stage)
        # Bad result cannot consume a repair budget or become a canonical outcome.
        return iter([""])

    after, batch, report = run(
        before, dict(amount=15, unit="years", max_llm_calls=cap), generate=generate
    )
    assert report["llm_calls"] == len(calls) <= cap
    assert (
        after["world_state"]["characters"]["npc-119"]["developmental_stage"]
        == "adolescent"
    )
    assert all(
        t["status"] == "active" for t in after["world_state"]["threads"].values()
    )
    assert not report["accepted"]
    assert all(
        after["world_state"]["characters"][f"npc-{n:03}"]["personality"] is None
        for n in range(120)
    )


@given(st.permutations(["a", "b", "c"]))
def test_candidate_order_does_not_depend_on_mapping_order(order):
    a = fixture()
    b = deepcopy(a)
    b["world_state"]["characters"] = {
        cid: b["world_state"]["characters"][cid] for cid in order
    }
    assert (
        plan(a, dict(amount=15, unit="years")).candidates
        == plan(b, dict(amount=15, unit="years")).candidates
    )


def test_dormant_reactivation_keeps_identity_and_state():
    before = fixture()
    original = deepcopy(before)
    assert plan(before, dict(amount=5, unit="years")).relevance["c"] == "dormant"
    before["world_state"]["threads"]["contact"] = Thread(
        id="contact", description="Контакт", character_ids=["c"]
    ).model_dump()
    assert plan(before, dict(amount=5, unit="years")).relevance["c"] == "background"
    assert (
        before["world_state"]["characters"]["c"]
        == original["world_state"]["characters"]["c"]
    )


def test_calendar_coalesces_15_birthdays_without_scenes():
    before = fixture()
    s = before["world_state"]
    rows = annual_occurrences(s, 0, target_minute(s, 15, "years"), {"a"})
    assert len(rows) == 1 and rows[0]["count"] == 15
    after, batch, _ = run(before, dict(amount=15, unit="years", max_llm_calls=0))
    assert not batch["events"]


def test_month_end_and_time_skip_boundary():
    s = state()
    s["meta"]["calendar"]["start_date"] = "2028-01-31"
    assert target_minute(s, 1, "months") == 29 * 1440
    with pytest.raises(ValueError):
        target_minute(s, 1, "weeks")
    with pytest.raises(ValueError):
        AdvanceRequest(amount=True, unit="years")


def test_accepted_role_and_secret_residence_use_resolver_without_broadcast():
    before = fixture()
    s = before["world_state"]
    s["threads"]["education"] = Thread(
        id="education", description="Учёба", character_ids=["c"], relevance=1
    ).model_dump()
    text = "Персонаж c начал учиться и тайно переехал."
    raw = dict(
        final_scene=dict(
            location_id="home", present_character_ids=["c"], elapsed_minutes=0
        ),
        events=[
            dict(
                id="accepted",
                text=text,
                evidence=text,
                participants=["c"],
                witnesses=["c"],
                medium="observation",
            )
        ],
        role_changes=[
            dict(
                id="study",
                actor_id="c",
                kind="education",
                title="Курс",
                assertion="established",
                evidence=text,
            )
        ],
        residence_changes=[
            dict(
                id="secret-home",
                actor_id="c",
                location_id="home",
                assertion="established",
                evidence=text,
            )
        ],
    )
    raw["events"][0]["advance_candidate_ids"] = [
        next(
            c.id
            for c in plan(before, dict(amount=5, unit="years")).candidates
            if c.source_id == "education"
        )
    ]

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=5, unit="years", max_llm_calls=2), generate=generate
    )
    assert report["accepted"], report["diagnostics"]
    assert after["world_state"]["roles"]["study"]["status"] == "active"
    assert after["world_state"]["residences"]["secret-home"]["status"] == "active"
    assert after["world_state"]["knowledge"] == before["world_state"]["knowledge"]
    assert batch["events"][0]["advance_source_ids"] == ["education"]


def test_minimal_promotion_is_bounded_grounded_and_deduplicated():
    from backend.runtime_v3.raw import RawTurnResult
    from backend.runtime_v3.long_term_promotions import prepare

    before = fixture()
    raw = RawTurnResult.parse(
        dict(
            final_scene={},
            promotions=[dict(id="new", name="Новый", fields={}, evidence="встреча")],
            events=[dict(id="e", participants=["c", "new"], evidence="встреча")],
            social_relation_changes=[dict(id="friend", source_id="c", target_id="new")],
        )
    )
    ids = prepare(raw, before, ["cause"])
    assert len(ids) == 1 and raw.records["promotions"][0]["fields"] == {}
    duplicate = RawTurnResult.parse(
        dict(
            final_scene={},
            promotions=[dict(id="c", name="c", fields={})],
            events=[dict(id="e", participants=["c"])],
        )
    )
    assert not prepare(duplicate, before, ["cause"])
    assert duplicate.records["events"][0]["participants"] == ["c"]
    incidental = RawTurnResult.parse(
        dict(final_scene={}, promotions=[dict(id="new", name="Официант", fields={})])
    )
    with pytest.raises(ValueError):
        prepare(incidental, before, ["cause"])


def test_real_jobs_reload_regenerate_rollback_branch_and_ordinary_turn(tmp_path):
    import engine
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute

    repo = Repository(tmp_path / "long-term.sqlite")
    sid = load_fixture(repo, "long-term")["save"]
    before = repo.get_snapshot(sid)
    assert len(before["world_state"]["characters"]) > 120
    config = dict(
        CONFIG, long_term_advance=dict(amount=15, unit="years", max_llm_calls=0)
    )
    jid = repo.begin_job(sid, "", "long_term", config)
    engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]
    after = repo.get_snapshot(sid)
    assert (
        after["world_state"]["meta"]["world_time"]
        > before["world_state"]["meta"]["world_time"]
    )
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == after
    regen = repo.begin_job(sid, "", "regenerate", CONFIG)
    engine.run_job(repo.path, regen, engine.Worker())
    assert repo.get_job(regen)["status"] == "saved", repo.get_job(regen)["error"]
    assert repo.get_snapshot(sid)["world_state"] == after["world_state"]
    repo.rollback_last(sid, repo.get_save(sid)["revision"])
    assert repo.get_snapshot(sid)["world_state"] == before["world_state"]
    camera = before["world_state"]["camera"]
    jid = repo.begin_job(sid, "Осматриваюсь.", "turn", CONFIG)
    execute(
        repo,
        jid,
        dict(
            final_scene=dict(
                location_id=camera["location_id"],
                present_character_ids=camera["present_character_ids"],
                elapsed_minutes=1,
            )
        ),
        "Тихий день.",
    )
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]


def test_accepted_birth_then_child_ages_without_adult_personality():
    before = snap(conceive().state)
    s = before["world_state"]
    s["camera"].update(controlled_actor_id="c", present_character_ids=["c"])
    p = next(iter(s["pregnancies"].values()))
    candidate = next(
        c
        for c in plan(before, dict(amount=15, unit="years")).candidates
        if c.kind == "birth"
    )
    text = "Роды завершились."
    raw = dict(
        final_scene=dict(location_id="home", present_character_ids=["a"]),
        events=[
            dict(
                id="birth",
                text=text,
                evidence=text,
                participants=["a"],
                witnesses=["a"],
                medium="observation",
                advance_candidate_ids=[candidate.id],
            )
        ],
        births=[
            dict(
                pregnancy_id=p["id"],
                source_event_id="birth",
                assertion="birth_completed",
                location_id="home",
                evidence=text,
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=15, unit="years", max_llm_calls=2), generate=generate
    )
    assert report["accepted"], report["diagnostics"]
    process = after["world_state"]["pregnancies"][p["id"]]
    assert process["status"] == "born" and process["birth_minute"] == p["due_minute"]
    child = after["world_state"]["characters"][p["children"][0]["id"]]
    assert child["developmental_stage"] == "adolescent"
    assert set(child["personality"]["items"]) == {"early_temperament"}
    assert not any(
        k["actor_id"] == "c" for k in after["world_state"]["knowledge"].values()
    )


def test_incapacitated_controlled_actor_has_no_invented_actions():
    before = fixture()
    before["world_state"]["characters"]["a"]["capabilities"]["conscious"] = False
    after, batch, report = run(before, dict(amount=5, unit="years", max_llm_calls=0))
    assert after["world_state"]["characters"]["a"]["capabilities"]["conscious"] is False
    assert not batch["events"]
    assert after["world_state"]["camera"]["controlled_actor_id"] == "a"


def test_existing_protagonist_death_interrupts_without_time_or_actions():
    before = fixture()
    s = before["world_state"]
    s["meta"]["current_protagonist_id"] = "a"
    s["characters"]["a"]["life_status"] = "dead"
    s["camera"]["present_character_ids"] = []
    from backend.runtime_v3.protagonist import reconcile

    reconcile(s)
    after, batch, report = run(before, dict(amount=15, unit="years", max_llm_calls=0))
    assert report["interruption"]["kind"] == "protagonist_required"
    assert after["world_state"]["meta"]["world_time"] == s["meta"]["world_time"]
    assert after["world_state"]["camera"]["controlled_actor_id"] is None
    assert not batch["events"]


def test_npc_experience_changes_personality_and_preserves_role_chronology():
    from backend.runtime_v3.models import NarrativeRole

    before = fixture()
    s = before["world_state"]
    s["roles"]["course"] = NarrativeRole(
        id="course", actor_id="c", kind="education", title="Курс", since=0
    ).model_dump()
    s["threads"]["education"] = Thread(
        id="education", description="Завершение учёбы", character_ids=["c"], relevance=1
    ).model_dump()
    text = "Персонаж c завершил курс; этот опыт стал для него поворотным."
    candidate = next(
        c
        for c in plan(before, dict(amount=5, unit="years")).candidates
        if c.source_id == "education"
    )
    raw = dict(
        final_scene=dict(location_id="home", present_character_ids=["c"]),
        events=[
            dict(
                id="graduate",
                text=text,
                evidence=text,
                participants=["c"],
                witnesses=["c"],
                medium="observation",
                advance_candidate_ids=[candidate.id],
            )
        ],
        role_changes=[
            dict(
                id="course",
                status="closed",
                outcome="graduated",
                assertion="established",
                evidence=text,
            )
        ],
        development_evidence=[
            dict(
                id="experience",
                actor_id="c",
                source_event_id="graduate",
                meaning="Осмысленный опыт",
                kind="turning_point",
                assertion="completed",
                evidence=text,
            )
        ],
        personality_deltas=[
            dict(
                actor_id="c",
                evidence_ids=["experience"],
                rationale="Опыт выпускника",
                developmental_fit="established_capability",
                evidence=text,
                operations=[
                    dict(
                        item_id="care",
                        field="habits",
                        operation="establish",
                        text="Проверяет результаты своей работы",
                        expected_text=None,
                        expected_revision=0,
                    )
                ],
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=5, unit="years", max_llm_calls=2), generate=generate
    )
    assert report["accepted"], report["diagnostics"]
    course = after["world_state"]["roles"]["course"]
    assert (
        course["since"] == 0
        and course["status"] == "closed"
        and course["outcome"] == "graduated"
    )
    assert after["world_state"]["characters"]["c"]["personality"]["items"]["care"][
        "source_ids"
    ]
    assert any(row.get("kind") == "personality_delta" for row in batch["state_changes"])


def test_learned_work_facet_does_not_reveal_secret_residence():
    from backend.runtime_v3.models import Fact, Knowledge

    before = fixture()
    s = before["world_state"]
    s["threads"]["letter"] = Thread(
        id="letter",
        description="Сообщение о работе",
        character_ids=["b", "c"],
        relevance=1,
    ).model_dump()
    s["facts"]["job"] = Fact(
        id="job", text="Персонаж b уволился", character_ids=["b"], visibility="secret"
    ).model_dump()
    s["facts"]["city"] = Fact(
        id="city",
        text="Персонаж b живёт в Казани",
        character_ids=["b"],
        visibility="secret",
    ).model_dump()
    s["facts"]["belief"] = Fact(
        id="belief",
        text="Персонаж b предположительно живёт в Туле",
        character_ids=["b"],
        visibility="secret",
    ).model_dump()
    s["knowledge"]["c:belief"] = Knowledge(
        actor_id="c", fact_id="belief", status="suspected"
    ).model_dump()
    candidate = next(
        c
        for c in plan(before, dict(amount=5, unit="years")).candidates
        if c.source_id == "letter"
    )
    text = "Персонаж b сообщил персонажу c об увольнении."
    raw = dict(
        final_scene=dict(location_id="home", present_character_ids=["b"]),
        events=[
            dict(
                id="message",
                text=text,
                evidence=text,
                participants=["b", "c"],
                witnesses=["c"],
                fact_ids=["job"],
                medium="message",
                author_id="b",
                advance_candidate_ids=[candidate.id],
            )
        ],
        knowledge_gained=[
            dict(
                actor_id="c",
                fact_id="job",
                status="known",
                source_event_id="message",
                evidence=text,
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=5, unit="years", max_llm_calls=2), generate=generate
    )
    assert report["accepted"], report["diagnostics"]
    knowledge = after["world_state"]["knowledge"]
    assert knowledge["c:job"]["status"] == "known"
    assert "c:city" not in knowledge and "a:job" not in knowledge
    assert knowledge["c:belief"]["status"] == "suspected"
    assert after["world_state"]["facts"]["city"] == s["facts"]["city"]
    assert batch["knowledge_acquisitions"][0]["source_event_id"]
    assert json.loads(json.dumps(after))["world_state"]["knowledge"] == knowledge


def test_regenerate_keeps_group_context_when_prior_call_count_changes(tmp_path):
    import engine
    from unittest.mock import patch
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG

    repo = Repository(tmp_path / "replay.sqlite")
    sid = load_fixture(repo, "long-term")["save"]
    config = dict(
        CONFIG, long_term_advance=dict(amount=15, unit="years", max_llm_calls=4)
    )
    recorded = []

    def first(**kw):
        if kw.get("response_format"):
            yield json.dumps(dict(final_scene={}))
        else:
            recorded.append(deepcopy(kw["messages"]))
            yield "" if len(recorded) == 1 else "Исход пока неизвестен."

    jid = repo.begin_job(sid, "", "long_term", config)
    with patch("engine.chat_stream", side_effect=first):
        engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)["status"] == "saved", repo.get_job(jid)["error"]
    assert len(recorded) == 2
    replayed = []

    def again(**kw):
        if kw.get("response_format"):
            yield json.dumps(dict(final_scene={}))
        else:
            replayed.append(deepcopy(kw["messages"]))
            yield "Исход пока неизвестен."

    regen = repo.begin_job(sid, "", "regenerate", CONFIG)
    with patch("engine.chat_stream", side_effect=again):
        engine.run_job(repo.path, regen, engine.Worker())
    assert repo.get_job(regen)["status"] == "saved", repo.get_job(regen)["error"]
    assert replayed == recorded
    assert repo.get_snapshot(sid)["last_long_term_advance"]["llm_calls"] == 4


def test_new_character_only_committed_with_accepted_relationship():
    before = fixture()
    before["world_state"]["threads"]["contact"] = Thread(
        id="contact", description="Знакомство по работе", character_ids=["c"]
    ).model_dump()
    cause = next(
        c
        for c in plan(before, dict(amount=5, unit="years")).candidates
        if c.source_id == "contact"
    )
    text = "c и Новый стали друзьями."
    raw = dict(
        final_scene=dict(location_id="home", present_character_ids=["c"]),
        promotions=[dict(id="new", name="Новый", fields={}, evidence=text)],
        events=[
            dict(
                id="meeting",
                text=text,
                evidence=text,
                participants=["c", "new"],
                witnesses=["c"],
                medium="observation",
                advance_candidate_ids=[cause.id],
            )
        ],
        social_relation_changes=[
            dict(
                id="friendship",
                source_id="c",
                target_id="new",
                kind="friend",
                assertion="established",
                evidence=text,
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=5, unit="years", max_llm_calls=2), generate=generate
    )
    assert report["accepted"], report["diagnostics"]
    new = set(after["world_state"]["characters"]) - set(
        before["world_state"]["characters"]
    )
    assert len(new) == 1
    assert after["world_state"]["objective_relations"]["friendship"]["target_id"] in new
    assert next(c for c in after["character_cards"] if c["id"] in new)["fields"] == {}
    assert after["world_state"]["knowledge"] == before["world_state"]["knowledge"]


@pytest.mark.parametrize("allow_death", [True, False])
def test_accepted_protagonist_death_interrupts_at_cause_boundary(allow_death):
    from backend.runtime_v3.models import Condition
    from backend.runtime_v3.protagonist import initialize

    before = fixture()
    before["campaign"]["protagonist_id"] = "a"
    before = initialize(before)
    s = before["world_state"]
    s["camera"].update(controlled_actor_id="c", present_character_ids=["c"])
    s["meta"]["narrative_risk"].update(preset="custom", protagonist_death=allow_death)
    s["conditions"]["illness"] = Condition(
        id="illness", actor_id="a", description="Установленная болезнь"
    ).model_dump()
    s["scheduled_events"]["crisis"] = ScheduledEvent(
        id="crisis", description="Кризис болезни", character_ids=["a"], due_minute=100
    ).model_dump()
    cause = next(
        c
        for c in plan(before, dict(amount=15, unit="years")).candidates
        if c.source_id == "crisis"
    )
    text = "Персонаж погиб от установленной болезни."
    raw = dict(
        final_scene=dict(location_id="home", present_character_ids=[]),
        events=[
            dict(
                id="death",
                text=text,
                evidence=text,
                participants=["a"],
                advance_candidate_ids=[cause.id],
            )
        ],
        life_changes=[
            dict(
                id="a",
                life_status="dead",
                assertion="established",
                source_event_id="death",
                evidence=text,
            )
        ],
        consequences=[
            dict(
                kind="protagonist_death",
                actor_id="a",
                source_event_id="death",
                basis_ids=["illness"],
                evidence=text,
            )
        ],
    )

    def generate(stage, *args, **kwargs):
        return iter([json.dumps(raw) if "extraction" in stage else text])

    after, batch, report = run(
        before, dict(amount=15, unit="years", max_llm_calls=2), generate=generate
    )
    if not allow_death:
        assert not report["accepted"]
        assert after["world_state"]["characters"]["a"]["life_status"] == "alive"
        assert any(d["code"] == "risk_death_denied" for d in report["diagnostics"])
        return
    assert report["accepted"], report["diagnostics"]
    assert report["actual_target"] == 100
    assert report["interruption"]["kind"] == "protagonist_required"
    assert after["world_state"]["meta"]["protagonist_required"]
    assert after["world_state"]["camera"]["controlled_actor_id"] is None
    assert (
        after["world_state"]["characters"]["c"]
        == before["world_state"]["characters"]["c"]
    )


def test_controlled_role_opportunity_is_bounded_and_not_silently_accepted():
    from backend.runtime_v3.models import NarrativeRole

    before = fixture()
    before["world_state"]["roles"]["study"] = NarrativeRole(
        id="study", actor_id="a", kind="education", title="Университет"
    ).model_dump()
    request = dict(amount=5, unit="years", max_llm_calls=0)
    p = plan(before, request)
    opportunities = [c for c in p.candidates if c.kind == "opportunity"]
    assert 0 < len(opportunities) <= p.policy["budget"]["candidates"]
    assert any("employment" in c.domains and c.requires_player for c in opportunities)
    after, batch, report = run(before, request)
    assert after["world_state"]["roles"] == before["world_state"]["roles"]
    assert any("employment" in c["domains"] for c in report["decisions"])
    assert not batch["events"]
    # Receipts follow the branch history, not a global opportunity store.
    history = dict(
        state_changes=[
            dict(
                kind="long_term_advance",
                report=dict(
                    accepted=[dict(candidate_ids=[c.id for c in opportunities])]
                ),
            )
        ]
    )
    assert not any(
        c.kind == "opportunity" for c in plan(before, request, history).candidates
    )
    assert any(c.kind == "opportunity" for c in plan(before, request, {}).candidates)


def test_significant_message_candidate_requires_proven_read_and_is_not_broadcast():
    from backend.runtime_v3.models import Fact
    from backend.runtime_v3.remote_models import RemoteEvent

    before = fixture()
    s = before["world_state"]
    s["threads"]["work"] = Thread(
        id="work", description="Работа", character_ids=["c"]
    ).model_dump()
    s["facts"]["notice"] = Fact(
        id="notice", text="Предложение", character_ids=["a", "c"]
    ).model_dump()
    message = RemoteEvent(
        id="message",
        channel="TEXT_MESSAGE",
        sender_id="a",
        recipient_ids=["c"],
        destination="c",
        world_time=0,
        updated_at=0,
        turn_id=0,
        status="delivered",
        delivered_to=["c"],
        fact_ids=["notice"],
        provenance="accepted message",
        operation_id="message-op",
    ).model_dump()
    s["remote_events"]["message"] = message
    request = dict(amount=5, unit="years", max_llm_calls=0)
    assert not any(c.kind == "communication" for c in plan(before, request).candidates)
    message["read_by"] = ["c"]
    assert any(
        c.kind == "communication" and c.actor_ids == ("c",)
        for c in plan(before, request).candidates
    )
    after, batch, report = run(before, request)
    assert after["world_state"]["knowledge"] == before["world_state"]["knowledge"]
    assert not batch["events"]


def test_extraction_cannot_override_interval_clock_or_consume_repair_calls():
    before = fixture()
    before["world_state"]["threads"]["cause"] = Thread(
        id="cause", description="Ожидание", character_ids=["c"]
    ).model_dump()
    calls = []

    def generate(stage, *args, **kwargs):
        calls.append(stage)
        return iter(
            [
                json.dumps(dict(final_scene=dict(elapsed_minutes=99999999)))
                if "extraction" in stage
                else "Исход не определён."
            ]
        )

    after, batch, report = run(
        before, dict(amount=5, unit="years", max_llm_calls=2), generate=generate
    )
    assert len(calls) == report["llm_calls"] == 2
    assert not report["accepted"]
    assert after["world_state"]["meta"]["world_time"] == target_minute(
        before["world_state"], 5, "years"
    )
    assert after["world_state"]["threads"]["cause"]["status"] == "active"


def test_identical_event_local_ids_in_distinct_groups_do_not_collide():
    before = fixture()
    for cid in ("b", "c"):
        before["world_state"]["threads"][cid] = Thread(
            id=cid, description="Завершение курса", character_ids=[cid], relevance=1
        ).model_dump()
    request = dict(amount=5, unit="years", max_llm_calls=4)
    causes = {
        c.actor_ids[0]: c.id
        for c in plan(before, request).candidates
        if c.kind == "thread"
    }
    calls = []

    def generate(stage, messages, *args, **kwargs):
        if "extraction" not in stage:
            calls.append(kwargs["context_key"])
            return iter(["Курс завершён."])
        cid = next(cid for cid, cause in causes.items() if cause in calls[-1])
        raw = dict(
            final_scene=dict(location_id="home", present_character_ids=[cid]),
            events=[
                dict(
                    id="event",
                    text="Курс завершён.",
                    evidence="Курс завершён.",
                    participants=[cid],
                    witnesses=[cid],
                    medium="observation",
                    advance_candidate_ids=[causes[cid]],
                )
            ],
        )
        return iter([json.dumps(raw)])

    after, batch, report = run(before, request, generate=generate)
    assert len(report["accepted"]) == 2, report["diagnostics"]
    assert len(batch["events"]) == 2
    assert len({e["id"] for e in batch["events"]}) == 2
    again, rebatch, _ = run(before, request, generate=generate)
    assert [e["id"] for e in rebatch["events"]] == [e["id"] for e in batch["events"]]


def test_canonical_milestone_experience_is_bounded_and_not_time_generated():
    from backend.runtime_v3.models import identity

    before = fixture()
    before["world_state"]["threads"]["recovery"] = Thread(
        id="recovery", description="После важного опыта", character_ids=["c"]
    ).model_dump()
    rows = [
        dict(
            id=f"experience-{n}",
            category="occupation",
            actor_ids=["c"],
            minute=0,
            summary="Завершено обучение",
            fact_id=None,
        )
        for n in range(16)
    ]
    queries = []

    def read(**kw):
        queries.append(kw)
        return rows[: kw["limit"]]

    request = dict(amount=15, unit="years", max_llm_calls=0)
    p = plan(before, request, {"_milestone_query": read})
    experiences = [c for c in p.candidates if c.kind == "personality"]
    assert len(experiences) == 16
    assert len(queries) <= 2 and all(
        q["limit"] <= 24 and len(q["actor_ids"]) <= 16 for q in queries
    )
    assert not any(c.kind == "personality" for c in plan(before, request).candidates)
    assert [c.id for c in experiences] == [
        c.id
        for c in plan(
            before,
            request,
            {"_milestone_query": lambda **kw: list(reversed(rows))[: kw["limit"]]},
        ).candidates
        if c.kind == "personality"
    ]
    # Already registered source experiences do not create duplicate acquisition.
    before["world_state"]["characters"]["c"]["personality"]["seen_sources"] = [
        identity("development", "c", r["id"]) for r in rows
    ]
    assert not any(
        c.kind == "personality"
        for c in plan(before, request, {"_milestone_query": read}).candidates
    )


def test_promotion_preserves_existing_id_and_canonical_renamed_identity():
    from backend.runtime_v3.raw import RawTurnResult
    from backend.runtime_v3.long_term_promotions import prepare

    before = fixture()

    def proposal(cid, name):
        return RawTurnResult.parse(
            dict(
                final_scene={},
                promotions=[dict(id=cid, name=name, fields={}, evidence="встреча")],
                events=[dict(id="e", participants=["b", cid], evidence="встреча")],
                social_relation_changes=[
                    dict(id="friend", source_id="b", target_id=cid)
                ],
            )
        )

    with pytest.raises(ValueError, match="canonical ID"):
        prepare(proposal("c", "Другое имя"), before, ["cause"])
    before["world_state"]["characters"]["c"]["display_name"] = "Новое имя"
    with pytest.raises(ValueError, match="дубликат"):
        prepare(proposal("new", "Новое имя"), before, ["cause"])
    existing = proposal("c", "Новое имя")
    assert not prepare(existing, before, ["cause"])
    assert existing.records["promotions"] == []
    assert existing.records["events"][0]["participants"] == ["b", "c"]
