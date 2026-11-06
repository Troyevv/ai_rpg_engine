"""Synthetic provider responses through the real API, jobs, Runtime and SQLite."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from storage import Storage
from test_api import api, wait_job
from test_runtime_handoff import REMOTE, arrival, imported, source, submit

NPC = 'viktoria_solovyova'
TEXT = 'Виктория молча пододвинула записку к Илье.'


def payload():
    raw = arrival(); raw['movements'] = []
    raw['events'] = [dict(id='note', text=TEXT, participants=['ilya', NPC],
                         witnesses=['ilya'], medium='observation')]
    return raw


def run(client, sid, responses, narrative=TEXT, kind='start', text=''):
    calls = []; responses = iter(responses)
    def provider(**kw):
        calls.append(kw)
        yield json.dumps(next(responses), ensure_ascii=False) if kw.get('response_format') else narrative
    with patch('engine.chat_stream', side_effect=provider):
        job = wait_job(client, submit(client, sid, kind, text))
    return job, calls


def history(repo, sid):
    from backend.runtime_v3.repository import read_history
    with repo.connect() as db:
        result, warnings = read_history(db, repo.get_snapshot(sid)['history_head'])
    assert all(w['code'] == 'history_provenance_incomplete' for w in warnings)  # Legacy E5 import.
    return result


@pytest.mark.parametrize('fault,code', [
    ('knowledge', 'initiative_knowledge_invalid'),
    ('player', 'initiative_player_evidence_required'),
    ('capabilities', 'initiative_capability_invalid'),
    ('adult', 'initiative_adult_context_required'),
])
def test_optional_annotation_cannot_veto_independent_event(api, fault, code):
    client, app = api; world = source()
    if fault == 'capabilities': world['world']['characters'][NPC]['capabilities']['can_speak'] = False
    if fault == 'adult':
        world['world']['characters'][NPC].update(birth_date='2015-01-01', developmental_stage='child')
    sid = imported(client, world); repo = app.state.repository; before = repo.get_snapshot(sid)
    claim = dict(actor_id=NPC, target_ids=['ilya'], source_event_id='note', phase='start',
                 modality='speech', response='open')
    if fault == 'knowledge': claim['knowledge_ids'] = ['missing-knowledge']
    if fault == 'player': claim.update(response='player_supplied', player_evidence='Да, обещаю прийти.')
    if fault == 'adult': claim['adult'] = True
    raw = payload(); raw['scene_actions'] = [claim]
    job, calls = run(client, sid, [raw])
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2  # No repair for an optional annotation.
    warnings = json.loads(repo.get_job(job['id'])['warnings_json'])
    assert any(w['code'] == code and w['section'] == 'scene_actions' and w['action'] == 'drop_record' for w in warnings)
    event = next(e for e in history(repo, sid)['events'] if e.get('local_id') == 'note')
    assert event['text'] == TEXT and 'scene_action' not in event
    after = Storage(repo.path).get_snapshot(sid)['world_state']
    assert after['knowledge'] == before['world_state']['knowledge']
    for field in ('goals', 'intentions', 'obligations', 'emotion'):
        assert after['characters']['ilya'][field] == before['world_state']['characters']['ilya'][field]
    assert after['characters'][NPC]['capabilities'] == before['world_state']['characters'][NPC]['capabilities']
    assert after['scheduled_events'] == before['world_state']['scheduled_events']


@pytest.mark.parametrize('fault', ['agency', 'knowledge', 'capability_grant'])
def test_domain_invariants_are_not_delegated_to_annotations(api, fault):
    client, app = api; sid = imported(client); repo = app.state.repository; before = repo.get_snapshot(sid)
    raw = payload(); raw['scene_actions'] = []
    if fault == 'agency':
        raw['final_scene']['location_id'] = 'salon_lak'
        raw['movements'] = [dict(actor_id='ilya', to_location_id='salon_lak')]
    elif fault == 'knowledge':
        raw['facts'] = [dict(id='secret', text='Закрытая информация.', visibility='secret', character_ids=[NPC])]
        raw['knowledge_gained'] = [dict(actor_id=NPC, fact_id='secret', source_event_id='note')]
    else:
        raw['condition_changes'] = [dict(id='grant', actor_id=NPC, description='Нельзя выдать способность условием.', effects={'can_speak':True})]
    job, calls = run(client, sid, [raw, raw])
    if fault == 'knowledge':
        assert job['status'] == 'saved', job.get('error')
        assert len(calls) == 2
        assert repo.get_snapshot(sid)['world_state']['knowledge'] == before['world_state']['knowledge']
        assert any(w['code'] == 'knowledge_path_invalid' for w in json.loads(repo.get_job(job['id'])['warnings_json']))
    else:
        assert job['status'] == 'error' and len(calls) == 3
        assert repo.get_snapshot(sid) == before and not repo.list_turns(sid)
        codes = {r['repair_error_code'] for r in json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])}
        assert ('movement_agency' if fault == 'agency' else 'life_transition_invalid') in codes


@pytest.mark.parametrize('initial_death,final_death', [(True,False), (False,True), (True,True)])
def test_bounded_repair_can_correct_provisional_semantics(api, initial_death, final_death):
    client, app = api; sid = imported(client); repo = app.state.repository
    before = repo.get_snapshot(sid)
    def interpretation(dead):
        raw = payload()
        raw['life_changes'] = [dict(id=NPC, life_status='dead')] if dead else []
        raw['events'] = [dict(id='outcome', text='Её дыхание оборвалось.' if dead else 'Она жива.', participants=[NPC])]
        return raw
    bad = interpretation(initial_death); bad['final_scene']['location_id'] = 'missing-room'
    good = interpretation(final_death)
    narrative = 'Её дыхание оборвалось.' if final_death else 'Она жива; сообщение о смерти оказалось ошибкой.'
    job, calls = run(client, sid, [bad, good], narrative)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 3 and sum(not c.get('response_format') for c in calls) == 1
    after = Storage(repo.path).get_snapshot(sid)
    assert after['world_state']['characters'][NPC]['life_status'] == ('dead' if final_death else 'alive')
    assert len(repo.list_turns(sid)) == 1
    saved = repo.get_job(job['id']); assert json.loads(saved['before_json']) == before
    for call in calls[1:]: assert narrative in '\n'.join(m['content'] for m in call['messages'])
    requests = {r['stage']:r for r in repo.request_log(job_id=job['id'])}
    assert json.loads(requests['extraction']['response_text']) == bad
    assert json.loads(requests['extraction_repair']['response_text']) == good
    if initial_death != final_death:
        assert any(w['code'] == 'extraction_revised' and w['section'] == 'life_changes' for w in json.loads(saved['warnings_json']))
    assert 'предварительный' in json.dumps(calls[-1]['messages'], ensure_ascii=False)


def test_retry_reinterprets_failed_claims_and_keeps_same_lineage(api):
    client, app = api; sid = imported(client); repo = app.state.repository; before = repo.get_snapshot(sid)
    bad = payload(); bad['final_scene']['location_id'] = 'missing-room'
    bad['life_changes'] = [dict(id=NPC, life_status='dead')]
    job, _ = run(client, sid, [bad, bad], 'Виктория жива; её смерть была только слухом.')
    assert job['status'] == 'error' and repo.get_snapshot(sid) == before
    reopened = Storage(repo.path); original = reopened.get_job(job['id']); logs = reopened.request_log(job_id=job['id'])
    calls = []
    def provider(**kw):
        calls.append(kw); assert kw.get('response_format')
        yield json.dumps(payload())
    with patch('engine.chat_stream', side_effect=provider):
        r = client.post(f"/api/jobs/{job['id']}/retry", json=dict(config=REMOTE, api_key='test-secret'))
        assert r.status_code == 200, r.text
        assert wait_job(client, job['id'])['status'] == 'saved'
    assert len(calls) == 1
    final = reopened.get_job(job['id'])
    for field in ('narrative','before_json','memory_before_json','context_json'): assert final[field] == original[field]
    current_logs = {r['id']:r for r in reopened.request_log(job_id=job['id'])}
    assert all(current_logs[r['id']] == r for r in logs)
    assert reopened.get_snapshot(sid)['world_state']['characters'][NPC]['life_status'] == 'alive'
    assert len(reopened.list_turns(sid)) == 1
    assert client.post(f"/api/jobs/{job['id']}/retry", json=dict(config=REMOTE, api_key='test-secret')).status_code == 409


def test_committed_death_survives_repair_reload_regenerate_and_rollback(api):
    client, app = api; sid = imported(client); repo = app.state.repository
    death = payload(); death['life_changes'] = [dict(id=NPC, life_status='dead')]
    death['events'] = [dict(id='death', text='Её дыхание оборвалось.', participants=[NPC])]
    first, _ = run(client, sid, [death], 'Её дыхание оборвалось.')
    assert first['status'] == 'saved'
    canonical = Storage(repo.path).get_snapshot(sid); accepted = history(repo, sid)
    good = payload(); good['events'] = []
    good['final_scene']['present_character_ids'] = ['ilya']
    bad = deepcopy(good); bad['final_scene']['location_id'] = 'missing-room'
    second, calls = run(client, sid, [bad,good], 'Илья ждёт.', 'turn', 'Жду.')
    assert second['status'] == 'saved' and len(calls) == 3
    turn = repo.list_turns(sid)[-1]; after = repo.get_snapshot(sid)
    regenerated, _ = run(client, sid, [good], 'Илья молча ждёт.', 'regenerate')
    assert regenerated['status'] == 'saved'
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == after
    repo.rollback_last(sid)
    assert Storage(repo.path).get_snapshot(sid) == canonical
    assert history(repo, sid) == accepted
    assert len(repo.list_turns(sid)) == 1
    # A contradictory explicit patch cannot resurrect committed canon either.
    resurrect = deepcopy(good); resurrect['life_changes'] = [dict(id=NPC, life_status='alive')]
    failed, _ = run(client, sid, [resurrect,resurrect], 'Илья ждёт.', 'turn', 'Жду.')
    assert failed['status'] == 'error'
    assert repo.get_snapshot(sid) == canonical and history(repo, sid) == accepted
