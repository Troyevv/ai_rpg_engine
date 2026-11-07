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
        schema = content('JSON Schema')
        assert 'player_agency' in schema['required']
        assert {'events', 'final_scene', 'knowledge_gained'} <= schema['properties'].keys()
        assert 'PLAYER ACTION REVIEW:' in messages[0]['content']
        from backend.runtime_v3.context_contract import SCENE_ACTION_EXTRACTION_CONTRACT, CONTINUITY_EXTRACTION_CONTRACT
        if 'scene_actions' not in schema['properties']:
            assert SCENE_ACTION_EXTRACTION_CONTRACT not in messages[0]['content']
        if not {'scene_transitions', 'continuity_beats'} & schema['properties'].keys():
            assert CONTINUITY_EXTRACTION_CONTRACT not in messages[0]['content']
        assert estimate(messages) <= 32768 - 4096 - 256
        current = content('Текущее состояние / GM-only')
        choice = expand(current, content('Choice context / controlled actor'))
        assert choice['scene']['present_actor_ids'] == sorted(current['camera']['present_character_ids'])
        assert len(choice['reproduction']['pregnancies'][0]['known_children']) == 3


def test_visual_portrait_metadata_never_enters_narrative_or_extraction():
    from test_runtime_v3_storage import snapshot_fixture
    from backend.runtime_v3.context import build_context
    from backend.services.draft_portraits import default_descriptor
    snapshot = snapshot_fixture()
    baseline = deepcopy(snapshot)
    for cid, actor in snapshot['world_state']['characters'].items():
        actor['procedural_portrait'] = default_descriptor(cid, 'adult')
        actor['portrait_mode'] = 'procedural'
    before = deepcopy(snapshot)
    for extraction_text in (None, 'Продолжение истории.'):
        def messages(value):
            return build_context(value, [], 'Продолжить', 'turn', 32768, 2000,
                                 extraction_text=extraction_text)
        assert messages(snapshot) == messages(baseline)
        wire = json.dumps(messages(snapshot))
        assert 'procedural_portrait' not in wire and 'portrait_mode' not in wire
    assert snapshot == before


def test_compact_schema_preserves_secret_role_validation():
    from jsonschema import Draft202012Validator
    from backend.runtime_v3.raw import extraction_schema, prompt_schema
    full, compact = extraction_schema(), prompt_schema()
    a = Draft202012Validator({'$defs': compact['$defs'], 'properties': {'facts': compact['properties']['facts']}})
    b = Draft202012Validator({'properties': {'facts': full['properties']['facts']}})
    for field in ('secret_keeper_ids', 'secret_biography_ids', 'secret_subject_ids'):
        for value, valid in [([], True), (['a', 'b'], True), ('a', False), ([1], False), (None, False)]:
            payload = {'facts': [{'id': 'f', 'text': 'Скрытая история.', 'evidence': 'Источник.', field: value}]}
            assert a.is_valid(payload) == b.is_valid(payload) == valid
