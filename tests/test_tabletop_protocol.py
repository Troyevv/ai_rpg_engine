"""The DM may request mechanics only through typed intent and durable pending state."""

import json
from unittest.mock import Mock, patch
import pytest
from backend.tabletop.commands import Command, CheckCommand, LookCommand
from backend.tabletop.dm import DMAgent, DMContextBuilder
from backend.tabletop.models import GameState
from backend.tabletop.narration import contains_mechanical_instruction
from backend.tabletop.repository import TabletopRepository
from backend.tabletop.projection import public_state
from tabletop_fixture import state, definition
from test_tabletop import api, create, send, CONFIG, runtime


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "look", "target": "archivist"},
        {"type": "move", "hp": 99},
        {"type": "attack"},
        {"type": "check", "dc": 1},
        {"type": "check", "result": 20},
        {"type": "save", "skill": "athletics"},
        {"type": "rest", "item_id": "potion"},
        {"type": "use_item", "item_id": "potion", "quantity": 99},
        {"type": "look", "spell_slots": 999},
        {"type": "patch_state", "path": "hp"},
    ],
)
def test_commands_reject_unrelated_or_authoritative_fields(payload):
    with pytest.raises(ValueError):
        Command.model_validate(payload)


def test_constructor_returns_typed_commands():
    assert isinstance(Command(type="look"), LookCommand)
    assert isinstance(Command(type="check", reason="Тяжёлый шкаф"), CheckCommand)
    assert set(Command(type="look").model_dump()) == {"type", "actor_id"}


@pytest.mark.parametrize(
    "text",
    [
        "Брось d20 +4.",
        "Нужна проверка Athletics.",
        "Выполни спасбросок.",
        "Потеряй 5 HP.",
        "Получи предмет в инвентарь.",
        "Потрать spell slot.",
        "Брось initiative.",
        "Нанеси 4 урона.",
        "Добавь +4.",
        "Получи condition.",
        "DC 15.",
        "Нажми кнопку.",
        "Roll a d20.",
        "Make a saving throw.",
    ],
)
def test_narration_cannot_invent_mechanics(api, text):
    _, app = api
    repo = app.state.tabletop_repository
    dm = DMAgent(repo, CONFIG, "secret")
    s = state()
    before = s.model_dump_json()
    with patch.object(dm, "call", return_value=text) as call:
        result = dm.narrate("probe", s, [], "Осматриваюсь")
    assert result == "Результат действия сохранён в журнале."
    assert not contains_mechanical_instruction(result)
    assert s.model_dump_json() == before and not s.session_state.pending
    assert call.call_count == 1  # No second repair/adjudication call.
    assert repo.usage("probe")[0]["stage"] == "narration_guard"


def test_pending_roll_never_calls_result_narration(api):
    c, app = api
    g = create(c)
    calls = []

    def stream(**kw):
        calls.append(kw)
        if kw.get("response_format"):
            yield json.dumps(
                {
                    "type": "check",
                    "ability": "strength",
                    "skill": "athletics",
                    "difficulty": "MEDIUM",
                    "reason": "Поток мешает пройти",
                }
            )
        else:
            yield "Ты преодолеваешь течение и выходишь на берег."

    with patch("llm.chat_stream", side_effect=stream):
        g = send(
            c, g, text="Иду через затопленный тоннель", config=CONFIG, api_key="secret"
        ).json()
        p = g["state"]["pending"]
        assert p and p["reason"] == "Поток мешает пройти"
        assert len(calls) == 1 and g["history"][-1]["narrative"] == ""
        assert not g["state"]["mechanical_resolution_complete"]
        gid = g["id"]
        # Durable restart, no new interpretation for the roll.
        restored = TabletopRepository(app.state.repository.path).load(gid)[1]
        assert restored.session_state.pending.id == p["id"]
        result = send(c, g, "roll", pending_id=p["id"], config=CONFIG, api_key="secret")
    assert result.status_code == 200 and len(calls) == 2
    assert result.json()["state"]["mechanical_resolution_complete"]
    context = json.loads(calls[-1]["messages"][-1]["content"])["context"]
    assert context["mechanical_resolution_complete"] is True
    assert "NEVER_DISCLOSE" not in json.dumps(context)
    assert result.json()["history"][-1]["narrative"]


def choice_command():
    return Command(
        type="request_choice",
        prompt="Как действуешь?",
        options=[
            {"id": "watch", "label": "Осмотреться", "command": {"type": "look"}},
            {
                "id": "check",
                "label": "Проверить путь",
                "command": {
                    "type": "check",
                    "ability": "strength",
                    "skill": "athletics",
                },
            },
        ],
    )


def test_choice_owner_snapshot_projection_and_resolution(api):
    c, app = api
    g = create(c)
    g = send(c, g, command=choice_command().model_dump()).json()
    choice = g["state"]["choice"]
    assert choice and not g["state"]["mechanical_resolution_complete"]
    assert "command" not in choice["options"][0]
    assert not g["history"][-1]["narrative"]
    repo = TabletopRepository(app.state.repository.path)
    saved = repo.load(g["id"])[1]
    assert saved.session_state.choice.id == choice["id"]
    with pytest.raises(ValueError):
        runtime().execute(
            saved,
            Command(type="resolve_choice", pending_id=choice["id"], option_id="watch"),
            player_id="other",
        )
    assert send(c, g, command={"type": "look"}).status_code == 409
    invalid = send(
        c,
        g,
        command={
            "type": "resolve_choice",
            "pending_id": choice["id"],
            "option_id": "missing",
        },
    )
    assert invalid.status_code == 409 and repo.load(g["id"])[1] == saved
    resolved = send(
        c,
        g,
        command={
            "type": "resolve_choice",
            "pending_id": choice["id"],
            "option_id": "check",
        },
    )
    assert resolved.status_code == 200, resolved.text
    after = resolved.json()
    assert after["state"]["choice"] is None and after["state"]["pending"]
    duplicate = send(
        c,
        g,
        command={
            "type": "resolve_choice",
            "pending_id": choice["id"],
            "option_id": "check",
        },
    )
    assert duplicate.json() == after
    assert repo.load(g["id"])[0] == after["revision"]
    replay = c.get(f"/api/tabletop/games/{g['id']}/replay/{g['revision']}").json()
    assert replay["state"]["choice"] == choice
    rolled_back = send(c, after, "rollback").json()
    assert rolled_back["state"]["choice"] == choice


def test_pending_reaction_suppresses_narration(api):
    _, app = api
    s = state()
    s.session_state.reaction = {
        "actor": "traveler",
        "mover": "sentinel",
        "weapon": "sword",
        "distance": 10,
    }
    dm = DMAgent(app.state.tabletop_repository, CONFIG)
    with patch.object(dm, "call") as call:
        assert dm.narrate("probe", s, []) == ""
    call.assert_not_called()


def test_ai_dm_required_in_normal_mode(api):
    c, app = api
    g = create(c)
    app.state.tabletop_debug = False
    assert send(c, g, command={"type": "look"}).status_code == 409
    assert c.get(f"/api/tabletop/games/{g['id']}").json()["revision"] == g["revision"]
    d = c.post(
        "/api/tabletop/drafts", json={"definition": definition().model_dump()}
    ).json()
    rejected = c.post(
        "/api/tabletop/games",
        json={"draft_id": d["id"], "draft_revision": 0, "character": {}},
    )
    assert rejected.status_code == 409
    # Client cannot enable debug for a production installation.
    assert send(c, g, command={"type": "look"}, debug=True).status_code == 422


def test_roleplay_context_without_arbitrary_bonuses():
    s = state()
    a = s.actor("traveler")
    a.biography = "Бывший страж"
    a.ideals = "Защищать слабых"
    a.bonds = "Сестра"
    a.flaws = "Упрямство"
    before = a.model_dump_json()
    context = DMContextBuilder.build(s)
    for field in ("biography", "ideals", "bonds", "flaws"):
        assert context["characters"]["traveler"][field] == getattr(a, field)
    assert a.model_dump_json() == before
