"""Lossless, actor-owned context deduplication under real model pressure."""
from copy import deepcopy
import json

from backend.runtime_v3.context import compact_choice_context


def expand(current, value):
    if isinstance(value, dict):
        if set(value) == {'state_ref'}:
            node = current
            for part in value['state_ref'].split('/')[1:]:
                key = part.replace('~1', '/').replace('~0', '~')
                node = node[int(key)] if isinstance(node, list) else node[key]
            return deepcopy(node)
        return {key: expand(current, child) for key, child in value.items()}
    if isinstance(value, list):
        return [expand(current, child) for child in value]
    return value


def test_choice_references_are_lossless_and_do_not_expand_subjective_knowledge():
    known = {'fact_id':'known', 'text':'Подтверждённые сведения. ' * 20}
    private = {'fact_id':'secret', 'text':'Неизвестные игроку сведения.'}
    current = {'knowledge':[known, private], 'a/b~c':{'situation':'Тихая сцена. ' * 30}}
    choice = {'knowledge':[known], 'scene':current['a/b~c'], 'unknown':[], 'enabled':True}
    before = deepcopy((current, choice))
    compacted = compact_choice_context(current, choice)
    assert 'state_ref' in json.dumps(compacted)
    assert '~1' in json.dumps(compacted) and '~0' in json.dumps(compacted)
    assert expand(current, compacted) == choice
    assert private not in expand(current, compacted)['knowledge']
    assert (current, choice) == before
    assert len(json.dumps(compacted)) < len(json.dumps(choice))


def test_saturated_world_repeated_reload_preserves_choice_and_scene_context(tmp_path, monkeypatch):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job, NARRATIVE
    from backend.runtime_v3 import context
    from backend.runtime_v3.repository import read_history
    repo = Repository(tmp_path/'saturated.sqlite')
    sid = load_fixture(repo, 'newborn-triplets')['save']
    comparisons = []
    wire_contexts = []
    build = context.build_context
    def capture(*args, **kwargs):
        messages = build(*args, **kwargs)
        wire_contexts.append(messages)
        return messages
    monkeypatch.setattr(context, 'build_context', capture)
    original = context.compact_choice_context
    def checked(current, choice):
        before = deepcopy((current, choice))
        result = original(current, choice)
        assert expand(current, result) == choice
        assert (current, choice) == before
        comparisons.append((current, result))
        return result
    monkeypatch.setattr(context, 'compact_choice_context', checked)
    # Exercise the failing second turn and the entire six-turn retention window.
    for _ in range(6):
        ordinary_job(repo, sid)
        saved = repo.get_snapshot(sid)
        repo = Repository(repo.path)
        assert repo.get_snapshot(sid) == saved
        with repo.connect() as db:
            history, _ = read_history(db, saved['history_head'])
        turn = history['turns'][-1]
        # Narrative is stored verbatim; no recent text was cut to fit Extraction.
        assert turn['narrative'] == NARRATIVE
    assert comparisons  # Only hard pressure triggers deduplication.
    for current, compacted in comparisons:
        assert len(current['pregnancies'][0]['children']) == 3
        assert current['camera']['present_character_ids']
        assert current['reproductive_knowledge']

    from context_builder import estimate
    extraction = [messages for messages in wire_contexts
                  if any(m['content'].startswith('completed_narrative\n') for m in messages)]
    assert len(extraction) == 6
    assert 'state_ref' in next(m['content'] for m in extraction[1]
                               if m['content'].startswith('Choice context'))
    for messages in extraction:
        def content(title):
            return json.loads(next(m['content'].split('\n', 1)[1] for m in messages
                                   if m['content'].startswith(title+'\n')))
        assert content('completed_narrative') == NARRATIVE
        assert estimate(messages) <= 32768 - 4096 - 256
        current = content('Текущее состояние / GM-only')
        choice = expand(current, content('Choice context / controlled actor'))
        assert choice['scene']['present_actor_ids'] == sorted(current['camera']['present_character_ids'])
        assert len(choice['reproduction']['pregnancies'][0]['known_children']) == 3
