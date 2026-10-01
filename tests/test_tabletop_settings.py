import json
from unittest.mock import patch
import pytest
from backend.tabletop.settings import DMSettings
from backend.tabletop.dm import DMAgent
from backend.tabletop.models import Command, GameState
from backend.tabletop.projection import public_state, public_history
from tabletop_fixture import state
from test_tabletop import api, create, runtime, CONFIG


@pytest.mark.parametrize("mode", ["hidden", "after", "always"])
def test_dc_projection_and_outcome_do_not_change_rules(mode):
    r = runtime(14)
    s = state()
    s.dm_settings.difficulty = mode
    s, _ = r.execute(s, Command(type="check", ability="strength", skill="athletics"))
    p = s.session_state.pending
    assert ("dc" in public_state(s)["pending"]) == (mode == "always")
    after, events = r.resolve_roll(s, p.id)
    roll = next(e for e in events if "roll" in e)
    assert roll["success"] == (roll["roll"]["total"] >= p.dc)
    history = public_history([{"events": events}], s.dm_settings)
    assert ("dc" in history[0]["events"][0]) == (mode != "hidden")
    assert (
        GameState.model_validate_json(after.model_dump_json()).dm_settings.difficulty
        == mode
    )


def test_settings_are_atomic_idempotent_and_survive_replay(api):
    c, app = api
    g = create(c)
    url = f"/api/tabletop/games/{g['id']}"
    settings = DMSettings(style="dark", difficulty="after", hints=False).model_dump()
    body = dict(revision=g["revision"], request_id="settings-once", settings=settings)
    result = c.post(url + "/settings", json=body)
    assert result.status_code == 200
    saved = result.json()
    assert saved["state"]["dm_settings"] == settings
    assert saved["state"]["characters"] == g["state"]["characters"]
    assert c.post(url + "/settings", json=body).json()["revision"] == saved["revision"]
    assert c.get(url).json()["state"]["dm_settings"] == settings
    assert (
        c.get(url + f"/replay/{saved['revision']}").json()["state"]["dm_settings"]
        == settings
    )
    body["request_id"] = "settings-stale"
    assert c.post(url + "/settings", json=body).status_code == 409
    body["revision"] = saved["revision"]
    body["settings"]["hp"] = 999
    assert c.post(url + "/settings", json=body).status_code == 422


def test_preferences_reach_both_prompts_without_state_mutation(api):
    _, app = api
    g = create(api[0])
    s = state()
    s.dm_settings = DMSettings(style="dark", length="short", strictness="strict")
    dm = DMAgent(app.state.tabletop_repository, CONFIG, "secret")
    before = s.model_dump_json()
    with patch.object(dm, "call", return_value='{"type":"look"}') as call:
        dm.interpret(g["id"], s, "Осматриваюсь")
        assert '"style":"dark"' in call.call_args.args[2][0]["content"]
    with patch.object(dm, "call", return_value="Туман окутывает площадь.") as call:
        dm.narrate(g["id"], s, [])
        assert '"length":"short"' in call.call_args.args[2][0]["content"]
    assert s.model_dump_json() == before
