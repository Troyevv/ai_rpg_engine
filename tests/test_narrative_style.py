"""Prompt wiring checks, never an automated judge of literary quality (#111)."""
from copy import deepcopy
import json

import pytest

from backend.runtime_v3.context_contract import CONTROL_CONTRACT, NARRATIVE_STYLE_CONTRACT
from context_builder import build_context, estimate
from test_runtime_v3_storage import snapshot_fixture


def assert_style(messages, count=1):
    text = '\n'.join(m['content'] for m in messages)
    assert text.count('NARRATIVE STYLE CONTRACT:') == count
    assert text.count(NARRATIVE_STYLE_CONTRACT.strip()) == count
    if count:
        assert CONTROL_CONTRACT in text
        assert 'GM-only карточки и внутренние состояния не являются знанием POV.' in text
        assert 'Respect current canonical appearance.' in text
    return text


@pytest.mark.parametrize('kind', ['start', 'turn', 'background', 'pov'])
@pytest.mark.parametrize('custom', [False, True])
@pytest.mark.parametrize('genre', [None, 'slice_of_life', 'romance', 'drama', 'thriller'])
def test_single_style_with_overrides_genres_and_budget(kind, custom, genre):
    snapshot = snapshot_fixture()
    if genre:
        snapshot['world_state']['meta']['genre'] = dict(
            primary_genre=genre, secondary_genres=[], custom_genre='')
    before = deepcopy(snapshot)
    prompts = {name: {'content': 'CUSTOM: restrained dialogue in the game language.'}
               for name in ('game_system_prompt.md', 'background_prompt.md')} if custom else None
    messages = build_context(snapshot, [], 'Продолжить.', kind, 16000, 2000, prompts=prompts)
    text = assert_style(messages)
    assert ('CUSTOM:' in text) == custom
    assert text.count('Genre / soft creative guidance') == bool(genre)
    assert estimate(messages) <= 16000 - 2000 - 256
    assert snapshot == before
    extraction = build_context(snapshot, [], '', kind, 32768, 4096,
                               prompts=prompts, extraction_text='Тихая сцена.')
    assert_style(extraction, 0)


@pytest.mark.parametrize('text,mode', [
    ('Осматриваюсь.', 'INDEX'),
    ('Что случилось с Соней?', 'COMPACT_REFERENCED'),
    ('Перечитываю старое сообщение Сони.', 'ACTIVE_REFERENCED'),
    ('Пишу Соне: привет.', 'FULL_REMOTE'),
])
def test_style_preserves_visibility_and_individual_voice(text, mode):
    from test_context_builder_v2 import clean_world, section
    snapshot = clean_world()
    before = deepcopy(snapshot)
    messages = build_context(snapshot, [], text, 'turn', 128000, 4000)
    assert_style(messages)
    assert messages.selection['characters'][mode] >= 1
    assert 'VOICE_b' in str(messages)  # present NPC retains individual speech
    if mode in ('INDEX', 'COMPACT_REFERENCED', 'ACTIVE_REFERENCED'):
        assert 'APPEARANCE_c' not in str(messages)
    if mode in ('ACTIVE_REFERENCED', 'FULL_REMOTE'):
        assert 'VOICE_c' in str(messages)
    assert 'UNRELATED_SECRET_' not in str(messages)
    current = section(messages, 'Текущее состояние / GM-only')
    assert current['camera']['controlled_actor_id'] == before['world_state']['camera']['controlled_actor_id']
    assert snapshot == before


def test_missing_appearance_remains_missing_and_core_survives_soft_budget():
    snapshot = snapshot_fixture()
    before = deepcopy(snapshot)
    messages = build_context(snapshot, [], '', 'turn', 32768, 2000, target_context_budget=1)
    assert_style(messages)
    assert snapshot == before
    assert all(not c['fields'] for c in snapshot['character_cards'])


@pytest.mark.parametrize("custom", [False, True])
def test_start_turn_reload_regenerate_rollback_no_extra_calls(tmp_path, custom):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo = Repository(tmp_path / 'style.sqlite')
    sid = load_fixture(repo, 'base')['save']
    custom_text = 'Пиши сдержанно, без метафор. CUSTOM SAVED STYLE'
    if custom:
        head = repo.prompt_snapshot()['game_system_prompt.md']['id']
        repo.change_document('prompt', 'game_system_prompt.md', custom_text, head)
    for kind in ('start', 'turn'):
        ordinary_job(repo, sid, kind)  # asserts exactly narrative + extraction
        wire = assert_style(json.loads(repo.latest_job(sid)['context_json']))
        assert (custom_text in wire) == custom
    original = repo.get_snapshot(sid)
    original_context = repo.latest_job(sid)['context_json']
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == original
    if custom:
        assert repo.prompt_snapshot()['game_system_prompt.md']['content'] == custom_text
    ordinary_job(repo, sid, 'regenerate')
    assert repo.latest_job(sid)['context_json'] == original_context
    assert_style(json.loads(repo.latest_job(sid)['context_json']))
    repo.rollback_last(sid)
    ordinary_job(repo, sid)
    assert_style(json.loads(repo.latest_job(sid)['context_json']))


def test_legacy_regeneration_keeps_original_context(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    from unittest.mock import patch
    from backend.runtime_v3 import context
    repo = Repository(tmp_path / 'legacy-style.sqlite')
    sid = load_fixture(repo, 'base')['save']
    # Simulate a pre-policy recorded turn, without editing any stored snapshot.
    with patch.object(context, 'NARRATIVE_CONTRACT',
                      context.NARRATIVE_CONTRACT.replace(NARRATIVE_STYLE_CONTRACT, '')):
        ordinary_job(repo, sid, 'start')
    original_context = repo.latest_job(sid)['context_json']
    assert_style(json.loads(original_context), 0)
    ordinary_job(repo, sid, 'regenerate')
    assert repo.latest_job(sid)['context_json'] == original_context
    ordinary_job(repo, sid)
    assert_style(json.loads(repo.latest_job(sid)['context_json']))
