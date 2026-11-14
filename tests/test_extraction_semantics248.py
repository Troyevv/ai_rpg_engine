"""Exact final Live #248 regressions; scripted controls never measure model accuracy."""
from copy import deepcopy
import gzip
import hashlib
import json

import pytest

from backend.repositories.documents import is_builtin_prompt
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_integrated_repair247 import ROOT, seed, execute, history
from test_live248_recovery import live


def final_live(case):
    data = json.loads((ROOT / 'live248_final.json').read_text())[case]
    before = live(case)['before']
    for section, updates in data['before_updates'].items():
        before[section].update(updates)
    assert hashlib.sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == data['before_sha256']
    return dict(data, before=before)


def resolve(data, raw):
    return StateResolver(data['before'], data['narrative'], data['player_input'], require_player_agency=True).resolve(raw)


@pytest.mark.parametrize('index', [0, 1])
def test_final_crisis_original_and_witness_stripping_repair_are_rejected(index):
    data = final_live('crisis'); before = deepcopy(data['before'])
    raw = json.loads(data['responses'][index]['response_text'])
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data, raw)
    assert error.value.code == 'event_presence_invalid'
    assert error.value.path['field'] == 'participants[1]'
    assert data['before'] == before


def test_visibility_still_supports_observation_without_contact_or_knowledge():
    data = final_live('crisis'); raw = json.loads(data['responses'][-1]['response_text'])
    raw.pop('player_agency'); raw['events'][0].update(medium='observation')
    for field in ('actor_id', 'target_ids', 'player_action_id', 'player_evidence'):
        raw['events'][0].pop(field, None)
    result = StateResolver(data['before'], 'Нина видит Веру.', '').resolve(raw)
    assert result.state['characters']['qa_vera']['location_id'] == data['before']['characters']['qa_vera']['location_id']
    assert not result.history['movements'] and not result.history['knowledge_acquisitions']


def test_typed_completed_contact_cannot_be_relabelled_as_observation():
    data = final_live('crisis'); raw = json.loads(data['responses'][-1]['response_text'])
    raw['events'][0]['medium'] = 'observation'
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data, raw)
    assert error.value.code == 'event_presence_invalid'


@pytest.mark.parametrize('observed', [False, True])
def test_doorway_conversation_uses_shared_place_not_camera_membership(observed):
    # Explicit positive control: both at the same canonical house; B stays outside
    # camera membership. No new threshold node, route, or contact flag is needed.
    data = final_live('crisis'); raw = json.loads(data['responses'][-1]['response_text'])
    lid = data['before']['camera']['location_id']
    data['before']['characters']['qa_vera']['location_id'] = lid
    raw['final_scene']['observed_character_ids'] = ['qa_vera'] if observed else []
    raw['events'][0]['witnesses'] = ['qa_nina', 'qa_vera']
    result = resolve(data, raw)
    assert result.history['events'][0]['participants'] == ['qa_nina', 'qa_vera']
    assert 'qa_vera' not in result.state['camera']['present_character_ids']
    assert not result.history['movements']


@pytest.mark.parametrize('case', ['crisis', 'phone'])
def test_original_prose_violation_control_refuses_atomically_and_abandons(tmp_path, case):
    data = final_live(case); repo = Repository(tmp_path/'game.sqlite'); sid = seed(repo, data)['save']
    before, hist, turns = repo.get_snapshot(sid), history(repo, sid), repo.list_turns(sid)
    original = json.loads(data['responses'][-1]['response_text'])
    violated = deepcopy(original); violated['player_agency']['status'] = 'violated'
    replies = [json.loads(data['responses'][0]['response_text']), violated] if case == 'crisis' else [violated]
    job, calls = execute(repo, sid, data, replies)
    assert len(calls) == 1 + len(replies)
    assert job['status'] == 'error' and repo.public_job(job)['narrative_reauthor_required']
    assert not repo.public_job(job)['retry_allowed']
    assert job['narrative'] == data['narrative']
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(sid) == before and history(fresh, sid) == hist
    assert fresh.list_turns(sid) == turns
    repo.abandon_job(sid, job['id'], repo.get_save(sid)['revision'], job['attempt_epoch'])
    assert repo.get_snapshot(sid) == before


def test_phone_original_is_still_a_semantic_gate_not_a_python_prose_classifier():
    data = final_live('phone'); raw = json.loads(data['responses'][0]['response_text'])
    # Characterization: consistent JSON cannot reveal an unreported decision in prose.
    result = resolve(data, raw)
    assert result.state['characters']['qa_timur']['location_id'] is None
    assert not result.history['movements']


DEFAULTS = json.loads(gzip.decompress((ROOT/'historical_defaults.json.gz').read_bytes()))


@pytest.mark.parametrize('record', DEFAULTS, ids=[r['commit'][:8] for r in DEFAULTS])
def test_all_historical_bundled_defaults_share_existing_registry(record):
    from test_context_builder_v2 import clean_world
    text = record['content']
    assert hashlib.sha256(text.encode()).hexdigest() == record['sha256']
    assert is_builtin_prompt('state_update_prompt.md', text)
    settings = {'state_update_prompt.md': {'id': 2, 'content': text}}
    saved = deepcopy(settings)
    messages = build_context(clean_world(), [], 'Смотрю.', 'turn', 49152, 4096,
                             extraction_text='Тишина.', prompts=settings)
    assert text not in messages[0]['content'] and settings == saved
    assert not is_builtin_prompt('state_update_prompt.md', text + '\nUSER: keep my instructions.')


@pytest.mark.parametrize('custom', [False, True])
def test_recorded_prompt_retry_regeneration_and_sibling_preserve_sources(tmp_path, custom):
    from test_live248_recovery import control
    data = live('knowledge'); repo = Repository(tmp_path/'game.sqlite'); sid = seed(repo, data)['save']
    old = next(r['content'] for r in DEFAULTS if r['sha256'].startswith('3578e11b'))
    text = old + ('\nUSER OVERRIDE: concise choices.' if custom else '')
    head = repo.document_history('prompt', 'state_update_prompt.md')['active_id']
    repo.change_document('prompt', 'state_update_prompt.md', text, head)
    before, hist = repo.get_snapshot(sid), history(repo, sid)
    bad = data['responses'][0]['payload']; good = control(data)
    failed, initial_calls = execute(repo, sid, data, [bad, bad])
    assert failed['status'] == 'error'
    recorded = failed['context_json']
    # Changing today's active prompt must not replace a recorded custom override.
    head = repo.document_history('prompt', 'state_update_prompt.md')['active_id']
    repo.change_document('prompt', 'state_update_prompt.md', 'NEW ACTIVE PROMPT', head)
    saved, retry_calls = execute(repo, sid, data, [good], retry=failed['id'])
    assert saved['status'] == 'saved' and len(retry_calls) == 1, saved['error']
    assert saved['narrative'] == data['narrative']
    assert saved['context_json'] == recorded
    after = repo.get_snapshot(sid); turn = repo.list_turns(sid)[-1]
    sibling, regen_calls = execute(repo, sid, data, [good], kind='regenerate')
    assert sibling['status'] == 'saved', sibling['error']
    assert len(repo.variants(turn['node_id'])) == 2
    for call in initial_calls[1:] + retry_calls + regen_calls[1:]:
        system = call['messages'][0]['content']
        assert (text in system) == custom
        assert 'NEW ACTIVE PROMPT' not in system
        assert system.count('CURRENT RUNTIME narrative-authority-v1') == 1
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before and history(repo, sid) == hist


def test_confirmed_background_arrival_new_place_preserves_player_knowledge(tmp_path):
    data = final_live('phone'); repo = Repository(tmp_path/'background.sqlite'); sid = seed(repo,data)['save']
    before, hist = repo.get_snapshot(sid), history(repo,sid)
    data['narrative'] = 'Тимур добрался до фотолаборатории «Свет», вошёл и оставил конверт у стойки.'
    raw = dict(final_scene=dict(location_id='lab_svet',present_character_ids=['qa_timur'],elapsed_minutes=0),
               locations=[dict(id='lab_svet',name='Фотолаборатория Свет',evidence=data['narrative'])],
               movements=[dict(actor_id='qa_timur',from_location_id=None,to_location_id='lab_svet',
                               assertion='completed_arrival',source_event_id='arrival',order=1)],
               events=[dict(id='arrival',text=data['narrative'],evidence=data['narrative'],
                            participants=['qa_timur'],witnesses=['qa_timur'],medium='action',location_id='lab_svet',order=1)])
    from test_integrated_repair247 import CONFIG
    job,calls = execute(repo,sid,data,[raw],kind='background',config=dict(CONFIG,camera_actor_id='qa_timur'))
    assert job['status']=='saved', job['error']
    assert len(calls)==2
    after=Repository(repo.path).get_snapshot(sid)
    assert after['world_state']['characters']['qa_timur']['location_id']=='lab_svet'
    assert after['world_state']['characters']['qa_kirill']==before['world_state']['characters']['qa_kirill']
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    assert after['world_state']['camera']['controlled_actor_id'] is None
    assert len(history(repo,sid)['movements'])==len(hist['movements'])+1
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before and history(repo,sid)==hist
