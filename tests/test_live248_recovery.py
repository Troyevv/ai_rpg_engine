"""Exact Live #248 replies. Explicitly labelled controls are not model QA.

Shared #245 before states are reused, with exact subsequent state updates and a
hash of every reconstructed checkpoint. Bulk SQLite/streams stay in the archive.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from backend.repositories.preparation import Repository
from backend.runtime_v3.raw import repair_feedback
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_integrated_repair247 import ROOT, archived, execute, history, seed


def live(case):
    data = json.loads((ROOT / 'live248.json').read_text())['cases'][case]
    before = archived(case)['before']
    for section, updates in data['before_updates'].items():
        before[section].update(updates)
    assert hashlib.sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == data['before_sha256']
    return dict(data, before=before)


def control(data):
    """Human-reviewed corrections; never Runtime synthesis or live receipts."""
    raw = deepcopy(data['responses'][-1]['payload'])
    case = data['case']
    if case == 'crisis':
        raw['player_agency']['status'] = 'violated'
    elif case == 'phone':
        raw['player_agency']['actions'][0]['target_ids'] = ['qa_timur']
    elif case == 'family':
        # The prose's clinician has no established canonical Character identity.
        raw['births'][0]['sex_observations'][0]['source_actor_id'] = None
    else:
        action = raw['player_agency']['actions'][0]
        raw['events'].append(dict(id='player_address', text=action['player_evidence'],
            actor_id='qa_kirill', target_ids=['qa_vera'], participants=['qa_kirill','qa_vera'],
            witnesses=['qa_kirill','qa_vera', 'qa_timur' if case=='knowledge' else 'qa_asya'],
            player_action_id=action['id'], player_evidence=action['player_evidence'],
            medium='conversation', location_id=data['before']['camera']['location_id'],
            evidence=action['player_evidence']))
    return raw


def resolve(data, raw):
    return StateResolver(data['before'], data['narrative'], data['player_input'], require_player_agency=True).resolve(raw)


@pytest.mark.parametrize('index', [0,1])
def test_exact_crisis_cannot_use_final_scene_as_arrival(index):
    data=live('crisis');before=deepcopy(data['before'])
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data,data['responses'][index]['payload'])
    codes=[d['code'] for d in error.value.diagnostics('test')]
    assert 'scene_arrival_unproven' in codes
    if index==0:
        assert codes.count('knowledge_fact_link_missing')==2
    assert data['before']==before


def test_exact_phone_reference_mismatch_is_repairable_not_narrative_violation():
    data=live('phone')
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data,data['responses'][0]['payload'])
    assert error.value.code=='player_action_targets_inconsistent'
    assert error.value.repairable
    assert error.value.diagnostic('test')['action']=='extraction_repair'
    result=resolve(data,control(data))
    assert result.state['characters']['qa_timur']['location_id'] is None
    assert 'qa_timur' not in result.state['camera']['present_character_ids']
    assert not result.history['movements']
    changed=control(data);changed['player_agency']['actions'][0]['meaning']='changed'
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data,changed)
    assert error.value.code=='narrative_agency_conflict' and not error.value.repairable


@pytest.mark.parametrize('case', ['knowledge','social'])
@pytest.mark.parametrize('index', [0,1])
def test_actual_missing_address_feedback_preserves_npc_response(case,index):
    data=live(case);raw=data['responses'][index]['payload']
    with pytest.raises(StructuralDeltaError) as error:
        resolve(data,raw)
    rows=error.value.diagnostics('test')
    missing=next(r for r in rows if r.get('reason')=='missing_player_action_event')
    assert raw['player_agency']['actions'][0]['id'] in missing['source_ids']
    assert 'отдельный Event' in missing['repair_reason'] and 'actor_id=qa_kirill' in missing['repair_reason']
    feedback=json.loads(repair_feedback(rows,raw,data['before']))
    assert feedback['original_extraction']==raw
    assert 'Never relabel the NPC response' in feedback['contract']
    if case=='knowledge' and index==0:
        assert sum(r['code']=='knowledge_fact_link_missing' for r in rows)==4
    result=resolve(data,control(data))
    original={e['id'] for e in raw['events']}
    assert original <= {e['local_id'] for e in result.history['events']}
    if case=='knowledge':assert len(result.history['knowledge_acquisitions'])==4


def test_actual_family_unknown_clinician_identity_preserves_birth_and_listeners():
    data=live('family');raw=control(data)
    result=resolve(data,raw)
    child=raw['births'][0]['sex_observations'][0]['child_id']
    assert result.state['characters'][child]['biological_sex']=='male'
    assert result.state['pregnancies'][raw['births'][0]['pregnancy_id']]['status']=='born'
    gains=result.history['knowledge_acquisitions']
    assert len(gains)==10 and {g['actor_id'] for g in gains}=={'qa_kirill','qa_vera'}
    assert set(result.state['characters'])-set(data['before']['characters'])=={child}
    for field,value in [('source_actor_id','qa_timur'),('source_assertion','prior_knowledge'),('perceived_by',['qa_timur'])]:
        bad=deepcopy(raw);bad['births'][0]['sex_observations'][0][field]=value
        with pytest.raises(StructuralDeltaError):resolve(data,bad)


@pytest.mark.parametrize('case', ['crisis','knowledge','social','phone','family'])
def test_live248_jobs_sqlite_repair_reload_siblings_and_rollback(tmp_path,case):
    data=live(case);repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before,hist,turns=repo.get_snapshot(sid),history(repo,sid),repo.list_turns(sid)
    good=control(data);bad=data['responses'][0]['payload']
    # Family's original wrong speaker is semantically false but structurally valid.
    # No prose parser can reject it; test the corrected representable source here.
    replies=[good] if case=='family' else [bad,good]
    job,calls=execute(repo,sid,data,replies)
    assert len(calls)==1+len(replies),job['error']
    assert sum(not c.get('response_format') for c in calls)==1
    assert all(json.dumps(data['narrative'],ensure_ascii=False) in '\n'.join(m['content'] for m in c['messages']) for c in calls[1:])
    fresh=Repository(repo.path)
    if case=='crisis':
        assert job['status']=='error' and repo.public_job(job)['narrative_reauthor_required']
        assert fresh.get_snapshot(sid)==before and history(fresh,sid)==hist and fresh.list_turns(sid)==turns
        repo.abandon_job(sid,job['id'],repo.get_save(sid)['revision'],job['attempt_epoch'])
        assert repo.get_snapshot(sid)==before
        return
    assert job['status']=='saved',job['error']
    saved=fresh.get_snapshot(sid)
    gains=history(fresh,sid)['knowledge_acquisitions'][len(hist['knowledge_acquisitions']):]
    if case=='knowledge':assert len(gains)==4
    if case=='phone':assert saved['world_state']['characters']['qa_timur']['location_id'] is None
    if case=='family':assert len(gains)==10
    turn=repo.list_turns(sid)[-1]
    sibling,_=execute(repo,sid,data,[good],kind='regenerate')
    assert sibling['status']=='saved',sibling['error']
    assert len(repo.variants(turn['node_id']))==2
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid)==saved
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid)==before and history(repo,sid)==hist


def test_saved_default_is_not_duplicated_on_retry_but_custom_prompt_survives(tmp_path,monkeypatch):
    import backend.runtime_v3.context as context
    from test_context_builder_v2 import clean_world
    old='Legacy bundled extraction default, with superseded arrival rules.'
    custom='CUSTOM USER EXTRACTION INSTRUCTION'
    prompts=tmp_path/'prompts';prompts.mkdir()
    (prompts/'state_update_prompt.md').write_text('Current bundled extraction default.')
    (prompts/'default_updates.json').write_text(json.dumps({'state_update_prompt.md':[hashlib.sha256(old.encode()).hexdigest()]}))
    monkeypatch.setattr(context,'PROMPTS',prompts)
    snap=clean_world()
    for text,included in [(old,False),(custom,True)]:
        settings={'state_update_prompt.md':{'id':1,'content':text}}
        messages=context.build_context(snap,[],'Смотрю.','turn',49152,4096,
            extraction_text='Тишина.',prompts=settings)
        assert (text in '\n'.join(m['content'] for m in messages))==included
        assert settings['state_update_prompt.md']['content']==text


@pytest.mark.parametrize('bypass', ['unmarked_movement','character_location'])
def test_actual_crisis_cannot_bypass_arrival_via_alternate_fields(bypass):
    data=live('crisis');raw=deepcopy(data['responses'][-1]['payload'])
    if bypass=='unmarked_movement':
        raw['movements']=[dict(actor_id='qa_vera',to_location_id=raw['final_scene']['location_id'])]
    else:
        raw['character_changes'].append(dict(id='qa_vera',location_id=raw['final_scene']['location_id']))
    with pytest.raises(StructuralDeltaError) as error:resolve(data,raw)
    assert error.value.repairable
    assert error.value.code in ('movement_source_invalid','scene_arrival_unproven')


@pytest.mark.parametrize('explicit', [False, True])
def test_startup_does_not_erase_established_npc_location(explicit):
    data=live('crisis');raw=deepcopy(data['responses'][-1]['payload'])
    # A missing first camera is not permission to relocate an already placed NPC.
    data['before']['meta']['turn_id']=0
    actor=data['before']['camera']['controlled_actor_id']
    data['before']['camera'].update(location_id=None,present_character_ids=[actor],observed_character_ids=[])
    data['before']['characters'][actor]['location_id']=None
    if explicit:
        raw['movements']=[dict(actor_id='qa_vera',to_location_id=raw['final_scene']['location_id'])]
    with pytest.raises(StructuralDeltaError) as error:resolve(data,raw)
    assert error.value.code in ('movement_source_invalid','scene_arrival_unproven')
