"""Original smoke outputs + explicitly authored repair controls, no live claims."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.runtime_v3.scene_repair import SceneCandidate
from backend.runtime_v3.scene_steps import compile_scene
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError
from test_scene_steps255 import fixture

pytestmark = pytest.mark.extraction_v6
SOURCE = Path(__file__).parent / 'fixtures/issue255/provider-smoke.json'


def original():
    return json.loads(SOURCE.read_text())


def prepare(data):
    candidate = SceneCandidate(data['before'], data['narrative'], data['player_input'], data['turn_id'])
    with pytest.raises(StructuralDeltaError) as error:
        candidate.parse(data['extraction'])
    rows = error.value.diagnostics('extraction_repair')
    assert error.value.repairable
    assert {(d['code'], d['path']) for d in rows} == {
        ('movement_endpoint_invalid', 'scene_steps[3]'),
        ('movement_agency', 'scene_steps[5]'),
        ('camera_invalid', 'scene.observer_location_id'),
    }
    feedback = json.loads(candidate.feedback(rows, data['extraction']))
    assert feedback['diagnostics'] == rows
    assert 'scene' in feedback['scope']['sections']
    assert {'step_39_04', 'step_39_06'} <= set(feedback['scope']['step_ids'])
    assert 'observer_location_id=null' in feedback['contract']
    return candidate, feedback


def authored_patch(data, feedback):
    # NOT a provider response: both semantic corrections and explicit authority
    # are authored solely to verify the existing one-repair production path.
    reply = json.loads(data['repair'])
    departure, arrival = deepcopy(reply['replacements'][3]), deepcopy(reply['replacements'][5])
    arrival['input_source'] = dict(quote='иду домой к маме на Лесную.', meaning='preserved')
    return dict(candidate_hash=feedback['candidate_hash'], replacements=[departure, arrival],
        sections={'scene': {'observer_location_id': None}},
        reason='Authored regression control: repair departure, clear observer override, link chosen arrival.')


def test_original_response_collects_errors_without_changing_candidate_or_before():
    data = original(); before = deepcopy(data)
    candidate, _ = prepare(data)
    assert data == before
    assert candidate.base == json.loads(data['extraction'])
    assert candidate.raw is None


def test_original_real_repair_remains_rejected_not_laundered():
    data = original(); candidate, feedback = prepare(data)
    reply = json.loads(data['repair'])
    # Only rebind to this test's before/namespace; semantic content is unchanged.
    reply['candidate_hash'] = feedback['candidate_hash']
    with pytest.raises(StructuralDeltaError) as error:
        candidate.parse(reply)
    assert {d['code'] for d in error.value.diagnostics('validation_failed')} == {'camera_invalid', 'movement_agency'}


def test_one_authored_patch_preserves_original_outcomes_and_reaches_home():
    data = original(); before = deepcopy(data['before'])
    candidate, feedback = prepare(data)
    raw = candidate.parse(authored_patch(data, feedback))
    expected = json.loads(data['extraction'])
    expected['scene']['observer_location_id'] = None
    expected['scene_steps'][3]['endpoint'] = None
    expected['scene_steps'][5]['input_source'] = dict(quote='иду домой к маме на Лесную.', meaning='preserved')
    assert raw.semantic_candidate == expected
    resolved = StateResolver(before, data['narrative'], data['player_input'], turn_id=data['turn_id'],
        **resolver_options(before, data['player_input'], contract_version=6)).resolve(raw)
    assert resolved.state['camera']['location_id'] == 'loc_home_galina'
    assert resolved.state['camera']['controlled_actor_id'] == 'char_alexey'
    assert resolved.state['camera']['mode'] == 'actor'
    assert resolved.state['camera']['present_character_ids'] == ['char_alexey']
    assert resolved.state['characters']['char_alexey']['location_id'] == 'loc_home_galina'
    for cid in ('char_viktor', 'char_tamara', 'char_galina'):
        assert resolved.state['characters'][cid]['location_id'] == before['characters'][cid]['location_id']
    assert len(resolved.history['movements']) == 2
    assert len(resolved.history['events']) == 5
    assert resolved.state['knowledge'] == before['knowledge']
    assert data['before'] == before


@pytest.mark.parametrize('leave', ['route', 'camera', 'agency'])
def test_incomplete_patch_still_fails(leave):
    data = original(); candidate, feedback = prepare(data); patch = authored_patch(data, feedback)
    if leave == 'route': patch['replacements'] = patch['replacements'][1:]
    if leave == 'camera': patch['sections'] = {}
    if leave == 'agency': patch['replacements'] = patch['replacements'][:1]
    with pytest.raises(StructuralDeltaError): candidate.parse(patch)


def test_schema_damage_does_not_hide_independent_valid_node_checks():
    state, p = fixture(); before = deepcopy(state)
    p['scene']['elapsed_minutes'] = 'bad'
    p['scene']['observer_location_id'] = 'park'
    p['scene_steps'][0]['kind'] = 'bad'
    p['scene_steps'][1]['assertion'] = 'departure'
    with pytest.raises(StructuralDeltaError) as error:
        compile_scene(p, state, 'Original prose', 1)
    codes = [d['code'] for d in error.value.diagnostics('repair')]
    assert codes.count('scene_schema_invalid') == 2
    assert 'movement_endpoint_invalid' in codes and 'camera_invalid' in codes
    assert 'scene_actor_unknown' not in codes  # Never infer from the malformed node.
    assert state == before


def test_multiple_independent_errors_in_one_step_and_scene_are_reported():
    state, p = fixture()
    p['scene_steps'][1].update(actor_id='missing', assertion='departure', timing='uncertain')
    p['scene_steps'][2]['outcome'] = 'not_performed'
    p['scene'].update(observer_location_id='park', visible_character_ids=[])
    with pytest.raises(StructuralDeltaError) as error: compile_scene(p, state, 'Prose', 1)
    assert {d['code'] for d in error.value.diagnostics('repair')} == {
        'scene_actor_unknown', 'player_action_source_invalid', 'movement_endpoint_invalid',
        'scene_order_ambiguous', 'scene_step_invalid', 'camera_invalid', 'camera_actor_missing'}


def test_camera_error_does_not_expand_repair_to_independent_npc_outcome():
    state, p = fixture()
    walk = deepcopy(p['scene_steps'][1]); p['scene_steps'] = [dict(walk, assertion='departure')]
    independent = dict(id='independent', kind='interaction', actor_id='b', target_ids=[],
        outcome='completed', text='NPC занимается своим делом.')
    p['scene_steps'].append(independent); p['scene']['observer_location_id'] = 'park'
    candidate = SceneCandidate(state, 'Prose', 'иду в парк', 1)
    with pytest.raises(StructuralDeltaError) as error: candidate.parse(p)
    feedback = json.loads(candidate.feedback(error.value.diagnostics('repair'), p))
    assert feedback['scope']['step_ids'] == ['walk']
    patch = dict(candidate_hash=feedback['candidate_hash'], replacements=[walk],
        sections={'scene': {'observer_location_id': None}}, reason='Authored repair control')
    repaired = candidate.parse(patch)
    assert repaired.semantic_candidate['scene_steps'][1] == independent
    patch['replacements'].append(dict(independent, text='Подменённый исход'))
    with pytest.raises(StructuralDeltaError) as error: candidate.parse(patch)
    assert error.value.code == 'scene_repair_scope'
