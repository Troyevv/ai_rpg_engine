"""#238: exact archived payloads and real jobs with deterministic provider replies.

Fixture before/initial/repair values are unchanged extracts of QA #239 archive
3979c8b...a277. Corrected replies below are test-authored Extraction, not Runtime
repairs or claims about live model reliability. No paid calls.
"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

from backend.repositories.preparation import Repository
from backend.runtime_v3.raw import extraction_schema
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_api import api
from test_narrative_test_world import ordinary_job, CONFIG
from test_event_presence import crisis
from test_player_action_targets import claim, payload, play, saved_events, MARINA

FIXTURES = Path(__file__).parent / 'fixtures' / 'issue238'


def archived(case):
    return json.loads((FIXTURES / f'{case}.json').read_text())


def corrected(data, case):
    raw = deepcopy(data['responses']['extraction_repair'])
    actions = {a['id']: a for a in raw['player_agency']['actions']}
    event = raw['events'][0]
    if case == 'campaign':
        event['player_action_id'] = next(iter(actions))
    event['player_evidence'] = actions[event['player_action_id']]['player_evidence']
    for action in actions.values():
        if action['id'] != event['player_action_id']:
            # Singular wire reference: one additional Event for the other act.
            raw['events'].append(dict(event, id='event-other-action',
                text=action['player_evidence'], player_action_id=action['id'],
                player_evidence=action['player_evidence']))
    return raw


def seed_archived(repo, case):
    """Exact archived state in a fresh fixture lineage, never a user save."""
    seed = load_fixture(repo)
    sid = seed['save']
    ordinary_job(repo, sid, 'start')
    data = archived(case)
    snapshot = repo.get_snapshot(sid)
    snapshot['world_state'] = deepcopy(data['before'])
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot), sid))
        db.execute('UPDATE turns SET sequence=? WHERE save_id=?', (data['before']['meta']['turn_id'], sid))
    return seed


@pytest.mark.parametrize('case', ['social', 'knowledge', 'campaign'])
@pytest.mark.parametrize('stage', ['extraction', 'extraction_repair'])
def test_exact_original_payloads_reject_with_field_diagnostics(case, stage):
    data = archived(case)
    before = deepcopy(data['before'])
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(before, data['narrative'], data['player_input'], require_player_agency=True).resolve(data['responses'][stage])
    diagnostics = exc.value.diagnostics('validation_failed')
    assert before == data['before']
    if case == 'campaign':
        assert {'missing_player_action_id', 'missing_player_evidence'} <= {d.get('reason') for d in diagnostics}
        assert any(d['code'] == 'event_minute_invalid' for d in diagnostics) == (stage == 'extraction')
    else:
        assert diagnostics[0]['reason'] == 'multiple_action_evidence'
        assert diagnostics[0]['path'] == 'events[0].player_evidence'
    assert all(d['entity'] == data['responses'][stage]['events'][0]['id'] for d in diagnostics if d['section']=='events')
    if case != 'campaign':
        # Keep the original payload index when another action's source failed.
        independent_index = 0 if case == 'social' else 1
        assert any(d['path']==f'player_agency.actions[{independent_index}].outcome' for d in diagnostics)


@pytest.mark.parametrize('case', ['social', 'knowledge', 'campaign'])
def test_exact_corrected_payloads_keep_narrative_and_action_identities(case):
    data = archived(case)
    raw = corrected(data, case)
    Draft202012Validator(extraction_schema()).validate(raw)
    result = StateResolver(data['before'], data['narrative'], data['player_input'], require_player_agency=True).resolve(raw)
    actions = {a['id']: a for a in raw['player_agency']['actions']}
    events = [e for e in result.history['events'] if e.get('player_action')]
    assert {e['player_action']['id'] for e in events} == actions.keys()
    assert all(e['player_evidence'] == actions[e['player_action']['id']]['player_evidence'] for e in events)
    assert result.state['meta']['world_time'] == data['before']['meta']['world_time'] + raw['final_scene']['elapsed_minutes']


@pytest.mark.parametrize('case', ['social', 'knowledge', 'campaign'])
@pytest.mark.parametrize('repair', ['valid', 'repeat', 'only_time', 'reauthor'])
def test_archived_state_through_context_jobs_history_sqlite(api, case, repair):
    client, app = api
    repo = app.state.repository
    data = archived(case)
    sid = seed_archived(repo, case)['save']
    before = repo.get_snapshot(sid)
    turns = repo.list_turns(sid)
    fixed = corrected(data, case)
    if repair == 'repeat':
        fixed = data['responses']['extraction']
    elif repair == 'only_time':
        fixed = data['responses']['extraction_repair']
    elif repair == 'reauthor':
        fixed['player_agency']['status'] = 'violated'
    job, calls = play((client, repo, sid), [data['responses']['extraction'], fixed], data['player_input'], data['narrative'], config=dict(CONFIG, context_length=40960), legacy=True)
    assert len(calls) == 3 and job['narrative'] == data['narrative'], job.get('error')
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    initial = [d for d in diagnostics if d['attempt'] == 0]
    feedback = calls[-1]['messages'][0]['content']
    for diagnostic in initial:
        assert diagnostic['path'] in feedback
    if case == 'campaign':
        assert {'events[0].minute', 'events[0].player_action_id', 'events[0].player_evidence'} <= {d['path'] for d in initial}
    fresh = Repository(repo.path)
    if repair == 'valid':
        assert job['status'] == 'saved', job.get('error')
        rows = saved_events(repo, sid)
        ids = [e['id'] for e in rows]
        assert len(ids) == len(set(ids))
        player_rows = [e for e in rows if e.get('player_action')]
        assert len(player_rows) == len(fixed['player_agency']['actions'])
        assert fresh.get_snapshot(sid)['world_state']['meta']['world_time'] == data['before']['meta']['world_time'] + 2
        # Old snapshot/history is immutable; reload doesn't duplicate acquisition.
        assert repo.get_snapshot(sid) == fresh.get_snapshot(sid)
    else:
        assert job['status'] == 'error'
        assert fresh.get_snapshot(sid) == before and fresh.list_turns(sid) == turns
        assert job['narrative_reauthor_required'] == (repair == 'reauthor')
        assert any(d['attempt'] == 1 and d['stage'] == 'validation_failed' for d in diagnostics)
        with patch('engine.chat_stream', side_effect=AssertionError('abandon calls LLM')):
            response = client.post(f'/api/saves/{sid}/jobs/{job["id"]}/abandon', json=dict(
                revision=fresh.get_save(sid)['revision'], attempt_epoch=job['attempt_epoch']))
        assert response.status_code == 200
        assert fresh.get_snapshot(sid) == before


@pytest.mark.parametrize('marker', [False, True])
@pytest.mark.parametrize('fault,field,reason', [
    ('wide', 'player_evidence', 'multiple_action_evidence'),
    ('other', 'player_evidence', 'other_action_evidence'),
    ('invented', 'player_evidence', 'action_evidence_mismatch'),
    ('unknown', 'player_action_id', 'unknown_player_action_id'),
    ('missing_id', 'player_action_id', 'missing_player_action_id'),
    ('missing_quote', 'player_evidence', 'missing_player_evidence'),
    ('actor', 'actor_id', 'wrong_actor'),
    ('targets', 'target_ids', 'target_ids_mismatch'),
])
def test_structural_diagnostics_are_precise_without_quote_or_secret_disclosure(marker, fault, field, reason):
    data = archived('social')
    raw = corrected(data, 'social')
    event = raw['events'][0]
    action = next(a for a in raw['player_agency']['actions'] if a['id'] == event['player_action_id'])
    other = next(a for a in raw['player_agency']['actions'] if a['id'] != event['player_action_id'])
    if not marker:
        event.pop('player_assertion')
    if fault == 'wide': event['player_evidence'] = data['player_input']
    elif fault == 'other': event['player_evidence'] = other['player_evidence']
    elif fault == 'invented': event['player_evidence'] = 'Я обещаю передать оригинал.'
    elif fault == 'unknown': event['player_action_id'] = 'nonexistent'
    elif fault == 'missing_id': event.pop('player_action_id')
    elif fault == 'missing_quote': event.pop('player_evidence')
    elif fault == 'actor': event['actor_id'] = 'qa_vera'
    elif fault == 'targets': event['target_ids'] = ['qa_asya']
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(data['before'], data['narrative'], data['player_input'], require_player_agency=True).resolve(raw)
    row = next(d for d in exc.value.diagnostics('validation_failed') if d.get('reason') == reason)
    assert row['path'] == f'events[0].{field}' and row['entity'] == event['id']
    assert action['player_evidence'] not in json.dumps(row, ensure_ascii=False)
    assert all(fact['text'] not in json.dumps(row, ensure_ascii=False) for fact in data['before']['facts'].values() if fact['visibility'] == 'secret')


@pytest.mark.parametrize('first', ['Согласен помочь Марине.', 'Отказываюсь помогать Марине.', 'Решу насчёт помощи Марине завтра.'])
def test_decision_and_new_question_remain_separate(crisis, first):
    _, repo, sid = crisis
    question = 'Спрашиваю Марину о фотографиях.'
    raw = payload(repo.get_snapshot(sid)['world_state'], [claim([MARINA], quote=first), claim([MARINA], quote=question, id='question')])
    job, calls = play(crisis, [raw], first + ' ' + question, 'Нина отвечает Марине, затем задаёт вопрос о фотографиях.')
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    assert [e['player_evidence'] for e in saved_events(repo, sid)[-2:]] == [first, question]


def test_two_completed_actions_cannot_share_one_singular_event_reference():
    data = archived('social')
    raw = corrected(data, 'social')
    raw['events'].pop()  # The broader Event text does not attest the other action.
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(data['before'], data['narrative'], data['player_input'], require_player_agency=True).resolve(raw)
    assert exc.value.code == 'player_action_completion_invalid'


def test_schema_requires_event_link_fields_and_preserves_npc_independence():
    schema = Draft202012Validator(extraction_schema())
    raw = corrected(archived('social'), 'social')
    for field in ('player_action_id', 'player_evidence', 'actor_id', 'target_ids'):
        bad = deepcopy(raw)
        bad['events'][0].pop(field)
        assert list(schema.iter_errors(bad)), field
    schema.validate(raw)


def test_manual_retry_reuses_all_latest_diagnostics_without_new_narrative(api):
    import engine
    client, app = api
    repo = app.state.repository
    data = archived('campaign')
    sid = seed_archived(repo, 'campaign')['save']
    job, calls = play((client, repo, sid), [data['responses']['extraction']] * 2,
        data['player_input'], data['narrative'], config=dict(CONFIG, context_length=40960), legacy=True)
    assert job['status'] == 'error' and len(calls) == 3
    repo = Repository(repo.path)
    original = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert len(original) == 6
    repo.retry_job(job['id'])
    calls = []
    def stream(**kw):
        calls.append(kw)
        assert kw.get('response_format'), 'retry must not reauthor Narrative'
        yield json.dumps(corrected(data, 'campaign'), ensure_ascii=False)
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, job['id'], engine.Worker(epoch=repo.get_job(job['id'])['attempt_epoch']))
    assert repo.get_job(job['id'])['status'] == 'saved', repo.get_job(job['id'])['error']
    assert len(calls) == 1
    prompt = calls[0]['messages'][0]['content']
    assert all(path in prompt for path in ('events[0].minute', 'events[0].player_action_id', 'events[0].player_evidence'))
    assert json.loads(repo.get_job(job['id'])['repair_diagnostics_json']) == original
