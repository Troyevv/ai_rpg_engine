"""QA-01: real jobs and persistence with controlled provider responses."""
from copy import deepcopy
import pytest
from backend.repositories.preparation import Repository
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG
import json
from unittest.mock import patch
import engine


def run(repo, sid, minutes, *, kind='turn', compression='missing', text='Рассматриваю карту.', config=None, extra=None, player_input='Рассматриваю карту.',retry=None):
    s = repo.get_snapshot(sid)['world_state']
    raw = dict(final_scene=dict(location_id=s['camera']['location_id'],
        present_character_ids=s['camera']['present_character_ids'], elapsed_minutes=minutes))
    if compression != 'missing':
        raw['final_scene']['compression'] = compression
    raw.update(extra or {})
    if retry: repo.retry_job(retry,config or CONFIG)
    job = retry or repo.begin_job(sid, '' if kind == 'start' else player_input, kind, config or CONFIG)
    calls = []
    def stream(**kw):
        calls.append(kw)
        background = any('Фоновая симуляция:' in m['content'] for m in kw['messages'])
        if kw.get('response_format'):
            result = dict(final_scene=dict(location_id=None, present_character_ids=[], elapsed_minutes=0)) if background else raw
            yield json.dumps(result, ensure_ascii=False)
        else:
            yield 'Тихо.' if background else text
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, job, engine.Worker())
    return repo.get_job(job), calls


@pytest.mark.parametrize('compression', ['missing', None, {}, 'routine', {'kind': 'work', 'evidence': 'Прошла неделя спокойной работы.'}])
def test_ordinary_turn_cannot_cross_due_commitment(tmp_path, compression):
    repo = Repository(tmp_path/'guard.sqlite')
    sid = load_fixture(repo, 'commitments')['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    before = repo.get_snapshot(sid)
    assert before['world_state']['meta']['world_time'] == 5563
    turns = deepcopy(repo.list_turns(sid))
    job, calls = run(repo, sid, 10080, compression=compression, text='Прошла неделя спокойной работы.')
    assert job['status'] == 'error', job
    assert len(calls) == 2  # Reject prose and delta together; no extraction-only repair.
    assert repo.get_snapshot(sid) == before
    assert repo.list_turns(sid) == turns
    assert Repository(repo.path).get_snapshot(sid) == before


def test_rejected_regenerate_and_successful_variants_rollback_branch(tmp_path):
    repo = Repository(tmp_path/'variants.sqlite')
    sid = load_fixture(repo, 'commitments')['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    started = repo.get_snapshot(sid)
    assert run(repo, sid, 2)[0]['status'] == 'saved'
    accepted = repo.get_snapshot(sid)
    turn = repo.list_turns(sid)[-1]
    assert run(repo, sid, 10080, kind='regenerate')[0]['status'] == 'error'
    assert repo.get_snapshot(sid) == accepted
    assert repo.list_turns(sid)[-1] == turn
    repo = Repository(repo.path)
    assert run(repo, sid, 3, kind='regenerate')[0]['status'] == 'saved'
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time'] == 5566
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == accepted
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == started
    assert run(repo, sid, 4)[0]['status'] == 'saved'
    assert Repository(repo.path).get_snapshot(sid)['world_state']['meta']['world_time'] == 5567


@pytest.mark.parametrize('compression', ['missing', None, {}, {'kind': 'work', 'evidence': 'Тихо.'}])
@pytest.mark.parametrize('minutes', [1, 120])
def test_unresolved_response_metadata_does_not_gate_elapsed_time(compression, minutes):
    from test_narrative_continuity import setup, payload
    from backend.runtime_v3.resolver import StateResolver
    from backend.services.world_delta_errors import StructuralDeltaError
    s = setup()['world_state']; before = deepcopy(s)
    raw = payload(s, 'Тихо.'); raw['final_scene']['elapsed_minutes'] = minutes
    if compression != 'missing': raw['final_scene']['compression'] = compression
    result=StateResolver(s, 'Тихо.', 'Смотрю.', continuity_decision={'pending_response_ids': ['question']}).resolve(raw)
    assert result.state['meta']['world_time']==before['meta']['world_time']+minutes
    assert result.history['turns'][0]['continuity']['answered_response_ids']==[]
    assert s==before


@pytest.mark.parametrize('offset,minutes,allowed', [(5,5,True), (5,6,False), (0,1,False), (0,31,False), (-5,31,False)])
def test_exact_due_boundary_and_short_due_scene(offset, minutes, allowed):
    from test_narrative_continuity import setup, payload
    from backend.runtime_v3.models import ScheduledEvent
    from backend.runtime_v3.resolver import StateResolver
    from backend.services.world_delta_errors import StructuralDeltaError
    s = setup()['world_state']; s['meta']['world_time'] = 1000
    s['scheduled_events']['due'] = ScheduledEvent(id='due', description='Встреча', character_ids=['a'], due_minute=1000+offset).model_dump()
    raw = payload(s); raw['final_scene']['elapsed_minutes'] = minutes
    if allowed:
        assert StateResolver(s, 'Разговор завершён.', '').resolve(raw).state['meta']['world_time'] == 1000+minutes
    else:
        with pytest.raises(StructuralDeltaError): StateResolver(s, 'Разговор завершён.', '').resolve(raw)


@pytest.mark.parametrize('status,outcome,ready', [('pending','',False), ('pending','blocked',False), ('cancelled','cancelled',False), ('resolved','missed',False), ('resolved','fulfilled',True)])
def test_shared_readiness_for_skip_compression_and_lta(status, outcome, ready):
    from test_narrative_continuity import setup
    from backend.runtime_v3.models import ScheduledEvent
    from backend.runtime_v3.commitments import commitment_ready
    from backend.runtime_v3.continuity import compression_limit
    from backend.runtime_v3.time_skip import plan_skip, TimeSkipRequest
    from backend.runtime_v3.long_term import plan
    snap = setup(); s = snap['world_state']; s['meta']['world_time'] = 1000
    s['scheduled_events']['parent'] = ScheduledEvent(id='parent', description='Поездка', character_ids=['b'], status=status, outcome=outcome).model_dump()
    s['scheduled_events']['child'] = ScheduledEvent(id='child', description='Возвращение', character_ids=['a'], due_minute=1005, depends_on=['parent']).model_dump()
    before = deepcopy(s)
    assert commitment_ready(s, s['scheduled_events']['child']) == ready
    assert compression_limit(s, {'a'})['max_minutes'] == (5 if ready else 30)
    assert plan_skip(s, TimeSkipRequest(1000, 1100))['actual_target'] == (1005 if ready else 1100)
    report = plan(snap, {'amount': 2, 'unit': 'weeks', 'reason': 'Жду.'})
    assert bool(report.interruption) == ready
    assert s == before


def test_runtime_owned_skip_reaches_boundary_and_regenerates(tmp_path):
    repo = Repository(tmp_path/'skip.sqlite')
    sid = load_fixture(repo, 'commitments')['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    before = repo.get_snapshot(sid)
    config = dict(CONFIG, time_skip=dict(duration=2880))
    job, _ = run(repo, sid, 10080, config=config, compression=None)
    assert job['status'] == 'saved', job['error']
    after = repo.get_snapshot(sid)
    assert after['world_state']['meta']['world_time'] == 6840
    assert after['world_state']['scheduled_events']['qa_friday_trip']['status'] == 'pending'
    assert Repository(repo.path).get_snapshot(sid) == after
    job, _ = run(repo, sid, 10080, kind='regenerate')
    assert job['status'] == 'saved', job['error']
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time'] == 6840
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before


def test_real_response_remains_unanswered_without_blocking_history(tmp_path):
    from devtools.narrative_test_world import ACTOR_ID
    from backend.runtime_v3.repository import read_history
    from test_narrative_continuity import permit
    repo = Repository(tmp_path/'responses.sqlite')
    sid = load_fixture(repo, 'continuity')['save']
    text = 'Соня спрашивает о работе.'
    extra = dict(events=[dict(id='question', text=text, evidence=text,
        participants=[ACTOR_ID, 'qa_vera'], witnesses=[ACTOR_ID, 'qa_vera'], medium='conversation')],
        scene_actions=[dict(actor_id='qa_vera', target_ids=[ACTOR_ID], source_event_id='question',
            phase='continue', modality='speech', interruptible=True, response='open', evidence=text)])
    job, _ = run(repo, sid, 0, kind='start', text=text, extra=extra)
    assert job['status'] == 'saved', job['error']
    before = repo.get_snapshot(sid)
    with repo.connect() as db: history, _ = read_history(db, before['history_head'])
    assert len(permit(before, history)['pending_response_ids']) == 1
    turns = repo.list_turns(sid)
    job, calls = run(repo, sid, 120)
    assert job['status'] == 'saved'
    ordinary=[c for c in calls if not any('Фоновая симуляция:' in m['content'] for m in c['messages'])]
    assert len(ordinary)==2
    after=Repository(repo.path).get_snapshot(sid)
    assert after['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+120
    assert len(repo.list_turns(sid))==len(turns)+1
    with repo.connect() as db: history, _ = read_history(db, after['history_head'])
    assert len(permit(after, history)['pending_response_ids'])==1


def test_extraction_cannot_claim_runtime_time_ownership(tmp_path):
    repo = Repository(tmp_path/'ownership.sqlite')
    sid = load_fixture(repo, 'commitments')['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    before = repo.get_snapshot(sid)
    job, _ = run(repo, sid, 10080, extra=dict(runtime_time_skip=True, mode='background',
        time_skip={'elapsed_minutes': 10080}))
    assert job['status'] == 'error' and repo.get_snapshot(sid) == before


def test_due_commitment_requires_accepted_outcome_not_just_extraction_claim():
    from test_narrative_continuity import setup, payload
    from backend.runtime_v3.models import ScheduledEvent
    from backend.runtime_v3.resolver import StateResolver
    from backend.services.world_delta_errors import StructuralDeltaError
    s = setup()['world_state']; s['meta']['world_time'] = 1000
    s['scheduled_events']['due'] = ScheduledEvent(id='due', description='Встреча',
        character_ids=['a', 'b'], due_minute=1000, commitment=True).model_dump()
    raw = payload(s, 'Встреча завершилась.', scheduled_event_changes=[dict(
        id='due', assertion='occurred', source_event_id='event', evidence='Нет такого свидетельства.')])
    before = deepcopy(s)
    result=StateResolver(s, 'Встреча завершилась.', '').resolve(raw)
    assert result.state['scheduled_events']['due']['status']=='resolved'
    assert s == before
    raw['scheduled_event_changes'][0]['evidence'] = 'Встреча завершилась.'
    result = StateResolver(s, 'Встреча завершилась.', '').resolve(raw)
    assert result.state['meta']['world_time'] == 1001
    assert result.state['scheduled_events']['due']['status'] == 'resolved'
    # A future boundary cannot be crossed by attaching a same-turn outcome.
    s['scheduled_events']['due']['due_minute'] = 1005
    raw['final_scene']['elapsed_minutes'] = 6
    with pytest.raises(StructuralDeltaError):
        StateResolver(s, 'Встреча завершилась.', '').resolve(raw)


def test_linked_accepted_response_unlocks_only_its_own_boundary():
    from test_narrative_continuity import setup
    from test_npc_initiative import payload, permit
    from backend.runtime_v3.resolver import StateResolver
    from backend.services.world_delta_errors import StructuralDeltaError
    snap = setup(); player = 'Нет.'
    raw = payload(snap, response='player_supplied', player_evidence=player, response_event_id='first')
    raw['final_scene']['elapsed_minutes'] = 1
    args = dict(initiative_decision=permit(snap), continuity_decision={'pending_response_ids': ['first']})
    result = StateResolver(snap['world_state'], raw['events'][0]['text'], player, **args).resolve(raw)
    assert result.history['turns'][0]['continuity']['answered_response_ids'] == ['first']
    args['continuity_decision']['pending_response_ids'].append('second')
    result=StateResolver(snap['world_state'], raw['events'][0]['text'], player, **args).resolve(raw)
    assert result.history['turns'][0]['continuity']['answered_response_ids']==['first']
