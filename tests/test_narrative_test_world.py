"""Selected integration coverage for the developer fixture, not a unit-test base."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
import pytest

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.models import assert_world_state_v3_invariants, identity
from backend.services import draft_world
from devtools.narrative_test_world import (
    ACTOR_ID, CHECKPOINTS, HOME, PEOPLE, PRESENT, START_MINUTE,
    build_fixture, load_fixture,
)

CONFIG = dict(model='test', context_length=32768, max_tokens=2000, update_tokens=4096)
NARRATIVE = 'Тимур показывает снимки карты. Вера рассматривает фотографии.'
ROOT = Path(__file__).resolve().parents[1]


def ordinary_job(repo, sid, kind='turn'):
    before = repo.get_snapshot(sid)
    camera = before['world_state']['camera']
    raw = dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
        choices=[dict(action=f'Рассмотреть деталь {i}', speech='') for i in range(6)])
    def stream(**kwargs):
        yield json.dumps(raw, ensure_ascii=False) if kwargs.get('response_format') else NARRATIVE
    text = 'Рассмотреть фотографии.' if kind == 'turn' else ''
    jid = repo.begin_job(sid, text, kind, CONFIG)
    with patch('engine.find_loaded_model', return_value={'config': {'context_length': 32768}}), \
         patch('engine.chat_stream', side_effect=stream) as calls:
        engine.run_job(repo.path, jid, engine.Worker())
    job = repo.get_job(jid)
    assert job['status'] == 'saved', job['error']
    assert calls.call_count == 2  # ordinary narrative + extraction, no repair or extra LLM
    after = repo.get_snapshot(sid)
    assert_world_state_v3_invariants(after['world_state'])
    assert after['world_state']['camera']['controlled_actor_id'] == ACTOR_ID
    assert ACTOR_ID + ':qa_private_letter' not in after['world_state']['knowledge']
    assert after['world_state']['characters'][ACTOR_ID]['goals'] == []
    return after


def test_base_uses_supported_initial_state_and_canonical_migration():
    base = build_fixture()
    assert base == build_fixture()
    assert draft_world.validate(base) == {'errors': [], 'warnings': []}
    migrated = migrate_v2(base)
    assert migrated.report == []
    state = assert_world_state_v3_invariants(migrated.snapshot['world_state'])
    assert set(state['characters']) == {row[0] for row in PEOPLE}
    assert len(state['characters']) == 12 and len(state['locations']) == 6
    assert state['camera']['present_character_ids'] == list(PRESENT)
    assert state['camera']['location_id'] == identity('location', HOME.casefold())
    assert state['meta']['world_time'] == START_MINUTE
    assert state['meta']['calendar']['start_date'] is None
    assert state['relationships'][ACTOR_ID + ':qa_vera']['dimensions']['trust'] == 70
    assert state['relationships']['qa_vera:' + ACTOR_ID]['dimensions']['trust'] == 60
    assert state['knowledge']['qa_oleg:qa_private_letter']['status'] == 'known'
    assert ACTOR_ID + ':qa_private_letter' not in state['knowledge']
    assert len(state['knowledge']) == 4
    assert state['characters']['qa_oleg']['goals'][0]['status'] == 'active'
    assert state['scheduled_events'] == {}
    assert 'qa_private_letter' not in draft_world.player_view(base)['world']['facts']


def test_checkpoint_reuses_base_validation_and_does_not_mutate_it(tmp_path, monkeypatch):
    base = build_fixture()
    def invalid(state):
        state['world']['knowledge']['bad'] = dict(actor_id='missing', fact_id='qa_private_letter', status='known')
        return state
    monkeypatch.setitem(CHECKPOINTS, 'invalid-test', invalid)
    repo = Repository(tmp_path / 'qa.sqlite3')
    with pytest.raises(ValueError, match='QA fixture'):
        load_fixture(repo, 'invalid-test')
    with pytest.raises(ValueError, match='checkpoint'):
        load_fixture(repo, 'not-registered')
    assert repo.list_workspaces() == [] and repo.list_worlds() == []
    assert build_fixture() == base


def test_load_reset_preserves_normal_save_draft_and_previous_qa_game(tmp_path):
    from test_worlds import summary
    repo = Repository(tmp_path / 'qa.sqlite3')
    wid = repo.save_world('Обычный мир', summary())
    normal_sid = repo.create_save(wid, 'Обычное прохождение')
    normal_workspace = repo.create_workspace('Обычный черновик')
    normal_before = repo.get_snapshot(normal_sid)
    first = load_fixture(repo)
    initial = repo.get_snapshot(first['save'])
    advanced = ordinary_job(repo, first['save'], 'start')
    old_turns = repo.list_turns(first['save'])
    second = load_fixture(repo)
    assert second['save'] != first['save'] and second['workspace'] != first['workspace']
    assert repo.get_snapshot(second['save']) == initial
    assert repo.list_turns(second['save']) == []
    assert repo.get_snapshot(first['save']) == advanced
    assert repo.list_turns(first['save']) == old_turns
    assert repo.get_snapshot(normal_sid) == normal_before
    assert repo.workspace(normal_workspace['id']) == normal_workspace
    assert repo.draft(second['workspace'], author=True)['state'] == build_fixture()


def test_start_turn_persist_reload_next_turn_and_variant_rollback(tmp_path):
    repo = Repository(tmp_path / 'qa.sqlite3')
    loaded = load_fixture(repo)
    sid = loaded['save']
    opening = ordinary_job(repo, sid, 'start')
    first = ordinary_job(repo, sid)
    assert first['world_state']['meta']['world_time'] == START_MINUTE + 2
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == first
    assert repo.get_save(sid)['history_warnings'] == []
    second = ordinary_job(repo, sid)
    last = repo.list_turns(sid)[-1]
    ordinary_job(repo, sid, 'regenerate')
    repo.select_variant(sid, last['id'], last['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == second
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == first
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == opening
    ordinary_job(Repository(repo.path), sid)


def test_cli_is_opt_in_and_returns_normal_api_readable_save(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    path = tmp_path / 'cli.sqlite3'
    command = [sys.executable, str(ROOT / 'scripts/narrative_test_world.py'), '--db', str(path)]
    env = {k: v for k, v in os.environ.items() if k != 'RPG_DEV_TOOLS'}
    blocked = subprocess.run(command, env=env, capture_output=True, text=True)
    assert blocked.returncode != 0 and not path.exists()
    invalid = subprocess.run(command + ['--checkpoint', 'unknown'],
        env=dict(env, RPG_DEV_TOOLS='1'), capture_output=True, text=True)
    assert invalid.returncode != 0 and not path.exists()
    loaded = subprocess.run(command, env=dict(env, RPG_DEV_TOOLS='1'), capture_output=True, text=True)
    assert loaded.returncode == 0, loaded.stderr
    result = json.loads(loaded.stdout)
    with TestClient(create_app(path)) as client:
        save = client.get(f"/api/saves/{result['save']}")
        assert save.status_code == 200
        assert save.json()['state']['scene_meta']['present_ids'] == list(PRESENT)
        assert client.get(f"/api/workspaces/{result['workspace']}/draft?author=true").json()['validation']['errors'] == []
        assert client.post('/api/dev/narrative-test-world/reset').status_code in (404, 405)


@settings(max_examples=12, deadline=None, derandomize=True)
@given(st.lists(st.sampled_from(['turn', 'reset', 'reload']), min_size=1, max_size=6))
def test_reset_reload_sequences_preserve_canonical_state_and_older_saves(operations):
    # Each generated example gets an independent database (no function-scoped
    # fixture state leaking between Hypothesis examples).
    with TemporaryDirectory() as directory:
        repo = Repository(Path(directory) / 'property.sqlite3')
        sid = load_fixture(repo)['save']
        initial = deepcopy(repo.get_snapshot(sid)['world_state'])
        preserved = {}
        for operation in operations:
            if operation == 'reset':
                preserved[sid] = repo.get_snapshot(sid)
                sid = load_fixture(repo)['save']
                assert repo.get_snapshot(sid)['world_state'] == initial
                assert not repo.list_turns(sid)
            elif operation == 'reload':
                before = repo.get_snapshot(sid)
                repo = Repository(repo.path)
                assert repo.get_snapshot(sid) == before
            else:
                ordinary_job(repo, sid, 'turn' if repo.list_turns(sid) else 'start')
            for old_sid, snapshot in preserved.items():
                assert repo.get_snapshot(old_sid) == snapshot
