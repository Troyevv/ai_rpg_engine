"""Issue #64: structured endpoints, not prose heuristics, determine canonical truth."""
from copy import deepcopy
import json
import pytest
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from backend.services.world import CARD_FIELDS
from test_runtime_v3_domain import initial
from test_engine import db, CONFIG
from runtime_v3_fixture import execute

NARRATIVE = 'Илья и Соня сидят за столиком у окна в кофейне «Гвоздь».'

def world():
    state = initial()
    state['locations']['room']['name'] = 'Критический успех'
    return state

def raw(lid='nail', present=None):
    return dict(final_scene=dict(location_id=lid, present_character_ids=present or ['a', 'b'],
        situation=NARRATIVE, situation_evidence=NARRATIVE),
        locations=[dict(id='nail', name='Гвоздь', evidence=NARRATIVE)])

def test_new_location_and_situation_are_canonical_and_patch_replays():
    before = world()
    payload = raw()
    payload['character_changes'] = [dict(id='b', situation=NARRATIVE, evidence=NARRATIVE)]
    result = StateResolver(before, NARRATIVE, '').resolve(payload)
    assert result.state['camera']['location_id'] == 'nail'
    assert result.state['locations']['nail']['name'] == 'Гвоздь'
    for cid in ['a', 'b']:
        assert result.state['characters'][cid]['location_id'] == 'nail'
        assert result.state['characters'][cid]['situation'] == NARRATIVE
    assert result.patch.apply(before) == result.state
    assert before == world()

def test_return_to_existing_location_keeps_identity():
    first = StateResolver(world(), NARRATIVE, '').resolve(raw()).state
    back = dict(final_scene=dict(location_id='room', present_character_ids=['a', 'b']))
    second = StateResolver(first, 'Они вернулись в «Критический успех».', '').resolve(back).state
    assert second['camera']['location_id'] == 'room'
    assert second['locations'] == first['locations']
    again = raw()
    again['locations'] = []
    third = StateResolver(second, NARRATIVE, '').resolve(again).state
    assert third['camera']['location_id'] == 'nail'
    assert third['locations'] == first['locations']

def test_new_location_and_stale_scene_with_endpoint_claim_requires_repair():
    payload = raw('room')
    payload['movements'] = [dict(actor_id='a', to_location_id='nail', evidence=NARRATIVE)]
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(world(), NARRATIVE, '').resolve(payload)
    assert error.value.code == 'scene_movement_conflict'
    assert error.value.repairable

def test_mentions_and_unprovable_semantics_do_not_force_transition():
    text = 'Обсуждают кофейню «Гвоздь», оставаясь в магазине.'
    payload = raw('room')
    payload['locations'][0]['evidence'] = text
    result = StateResolver(world(), text, '').resolve(payload)
    assert result.state['camera']['location_id'] == 'room'
    assert result.state['characters']['a']['location_id'] == 'room'
    # A new location alone is not proof that the camera went there.
    assert StateResolver(world(), NARRATIVE, '').resolve(raw('room')).state['camera']['location_id'] == 'room'

def test_departure_and_arrival_update_presence_and_character_endpoints():
    text = 'Соня ушла в коридор. К Илье пришёл Юра и остался.'
    payload = dict(final_scene=dict(location_id='room', present_character_ids=['a', 'c']),
        movements=[dict(actor_id='b', to_location_id='hall', evidence=text)])
    state = world()
    state['characters']['c']['location_id'] = 'hall'
    result = StateResolver(state, text, '').resolve(payload).state
    assert result['camera']['present_character_ids'] == ['a', 'c']
    assert result['characters']['b']['location_id'] == 'hall'
    assert result['characters']['c']['location_id'] == 'room'

def test_ordered_route_uses_last_endpoint_and_does_not_duplicate_movement_history():
    payload = raw()
    payload['movements'] = [
        dict(actor_id='a', to_location_id='nail', order=2, evidence=NARRATIVE),
        dict(actor_id='a', to_location_id='hall', order=1, evidence=NARRATIVE)]
    result = StateResolver(world(), NARRATIVE, '').resolve(payload)
    assert len([m for m in result.history['movements'] if m['actor_id'] == 'a']) == 1

def test_promoted_npc_gets_same_location_and_card_identity():
    payload = raw(present=['a', 'b', 'barista'])
    payload['promotions'] = [dict(id='barista', name='Маша',
        fields={key: 'Описание' for key in CARD_FIELDS}, evidence=NARRATIVE)]
    result = StateResolver(world(), NARRATIVE, '').resolve(payload)
    assert result.cards[0]['id'] == 'barista'
    assert result.state['characters']['barista']['location_id'] == 'nail'

@pytest.mark.parametrize('section', ['locations', 'promotions'])
def test_missing_evidence_for_required_scene_entity_is_repairable(section):
    payload = raw(present=['a', 'barista']) if section == 'promotions' else raw()
    if section == 'promotions':
        payload['promotions'] = [dict(id='barista', name='Маша',
            fields={key: 'Описание' for key in CARD_FIELDS}, evidence='Нет в тексте')]
    else:
        payload['locations'][0]['evidence'] = 'Нет в тексте'
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(world(), NARRATIVE, '').resolve(payload)
    assert error.value.repairable

@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_real_engine_repairs_once_with_original_and_full_context(db, repair_succeeds):
    repo, _, sid = db
    before = repo.get_snapshot(sid)
    camera = before['world_state']['camera']
    bad = raw(camera['location_id'], camera['present_character_ids'])
    bad['movements'] = [dict(actor_id=camera['controlled_actor_id'],
        to_location_id='nail', evidence=NARRATIVE)]
    fixed = deepcopy(bad)
    fixed['final_scene']['location_id'] = 'nail'
    job = repo.begin_job(sid, '', 'start', CONFIG)
    calls = execute(repo, job, bad, NARRATIVE, repaired=fixed if repair_succeeds else bad)
    assert len(calls) == 3
    messages = calls[2]['messages']
    system = messages[0]['content']
    feedback = json.loads(system.split('Исправь структурную ошибку, верни полный JSON:\n', 1)[1])
    assert json.loads(feedback['original_extraction']) == bad
    assert feedback['previous_camera'] == camera
    assert feedback['known_locations'] == before['world_state']['locations']
    assert feedback['diagnostic']['repair_error_code'] == 'scene_movement_conflict'
    assert any(NARRATIVE in m['content'] for m in messages if m['content'].startswith('completed_narrative'))
    if repair_succeeds:
        assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
        state = repo.get_snapshot(sid)['world_state']
        assert state['camera']['location_id'] == 'nail'
        assert all(state['characters'][cid]['location_id'] == 'nail' for cid in camera['present_character_ids'])
    else:
        assert repo.get_job(job)['status'] == 'error'
        assert repo.get_snapshot(sid) == before
        assert not repo.list_turns(sid)

def test_valid_dynamic_location_saves_with_two_calls_and_rolls_back(db):
    repo, _, sid = db
    before = repo.get_snapshot(sid)
    camera = before['world_state']['camera']
    payload = raw(present=camera['present_character_ids'])
    job = repo.begin_job(sid, '', 'start', CONFIG)
    assert len(execute(repo, job, payload, NARRATIVE)) == 2
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    assert repo.get_snapshot(sid)['world_state']['locations']['nail']['name'] == 'Гвоздь'
    assert repo.turn_diagnostics(sid)[0]['repairs'] == []
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before

def test_scene_contract_overrides_saved_prompt_without_previous_narratives():
    from backend.runtime_v3.context_contract import EXTRACTION_CONTRACT
    from test_context_builder_v2 import clean_world, build, section
    snapshot = clean_world()
    snapshot['world_state']['locations']['nail'] = dict(id='nail', name='Гвоздь', description='')
    messages = build(snapshot, extraction_text=NARRATIVE,
        prompts={'state_update_prompt.md': {'content': 'Сохранённая инструкция'}})
    assert EXTRACTION_CONTRACT in messages[0]['content']
    assert messages[0]['content'].index('Сохранённая инструкция') < messages[0]['content'].index(EXTRACTION_CONTRACT)
    assert section(messages, 'Текущее состояние / GM-only')['locations']['nail']['name'] == 'Гвоздь'
    assert not any(m['role'] == 'assistant' for m in messages)
