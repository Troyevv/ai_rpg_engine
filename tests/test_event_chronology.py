"""Campaign/014 equivalent replay and the canonical Event write boundary (#220)."""
from copy import deepcopy
import json

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import current_time
from backend.runtime_v3.models import Calendar
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from runtime_v3_fixture import execute
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG
from test_runtime_v3_domain import initial

START = 2105840
LINE = 'Тимур отвечает: «Позвоню Олегу завтра в десять».'
LOCAL_ID = 'event_13_timur_call_plan'


def conversation(camera, elapsed=2):
    ids = camera['present_character_ids']
    return dict(
        final_scene=dict(location_id=camera['location_id'], present_character_ids=ids, elapsed_minutes=elapsed),
        events=[dict(id=LOCAL_ID, text=LINE, evidence=LINE, participants=ids, witnesses=ids,
                     medium='conversation', minute=2, order=1, fact_ids=['plan'])],
        facts=[dict(id='plan', text=LINE)],
        knowledge_gained=[dict(actor_id=ids[0], fact_id='plan', source_event_id=LOCAL_ID, evidence=LINE)],
    )


def scene(clock=START):
    state = initial()
    state['meta'].update(world_time=clock, turn_id=13, calendar=Calendar(
        start_date='2026-10-05', start_minute=0, start_weekday=0).model_dump())
    return state


@pytest.mark.parametrize('minute,elapsed', [(2, 2), (START+3, 2), (START-1, 0), (START+1, 0),
                                            (-1, 2), (True, 2), (None, 2), ('2', 2)])
def test_campaign_event_invalid(minute, elapsed):
    before = scene()
    raw = conversation(before['camera'], elapsed)
    raw['events'][0]['minute'] = minute
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(before, LINE, '').resolve(raw)
    diag = error.value.diagnostic('validation')
    assert (diag['code'], diag['path'], diag['source_ids']) == ('event_minute_invalid', 'events[0].minute', [LOCAL_ID])
    assert error.value.repairable and f'[{START}, {START+elapsed}]' in diag['repair_reason']


def test_unknown_time_and_report_about_the_past_at_a_zero_minute_scene():
    before = scene()
    raw = conversation(before['camera'], elapsed=0)
    report = 'Тимур вспоминает, как в детстве потерял ключ.'
    event = raw['events'][0]
    event.update(text=report, evidence=report, medium='testimony')
    raw['facts'][0]['text'] = report
    raw['knowledge_gained'][0]['evidence'] = report
    for precise in (False, True):
        if precise:
            event['minute'] = START
        else:
            del event['minute']
        result = StateResolver(before, report, '').resolve(raw)
        saved, = result.history['events']
        assert saved['recorded_minute'] == START and saved['source_sequence'] == 13
        assert ('minute' in saved) == precise and ('calendar_date' in saved) == precise
        if precise:
            assert saved['minute'] == START and saved['calendar_date'] == current_time(before)['date']
        assert result.history['knowledge_acquisitions'][0]['source_event_id'] == saved['id']


def test_multiple_events_across_midnight_keep_calendar_order_and_sources():
    before = scene(1439)
    raw = conversation(before['camera'])
    raw['events'][0]['minute'] = 1439
    raw['events'] += [dict(raw['events'][0], id='reply', minute=1441, order=2),
                      dict(raw['events'][0], id='nod', minute=1441, order=3)]
    result = StateResolver(before, LINE, '').resolve(raw)
    assert [(e['minute'], e['calendar_date'], e['order']) for e in result.history['events']] == [
        (1439, '2026-10-05', 1), (1441, '2026-10-06', 2), (1441, '2026-10-06', 3)]
    turn, = result.history['turns']
    assert all((e['recorded_minute'], e['source_sequence'], e['source_record_id']) ==
               (1441, turn['sequence'], turn['id']) for e in result.history['events'])


@pytest.mark.parametrize('corrected', [True, False])
def test_bounded_repair_and_history_lineage(tmp_path, corrected):
    repo = Repository(tmp_path / 'campaign.sqlite')
    sid = load_fixture(repo)['save']
    before = repo.get_snapshot(sid)
    state = before['world_state']
    start = state['meta']['world_time']
    raw = conversation(state['camera'])
    raw['scheduled_event_changes'] = [dict(
        id='call_oleg', description=LINE, character_ids=['qa_timur', 'qa_oleg'], assertion='agreed',
        decision_actor_id='qa_timur', source_event_id=LOCAL_ID, temporal=dict(day_offset=1, time='10:00'),
        evidence=LINE)]
    raw['events'][0]['minute'] = start+3
    revised = deepcopy(raw)
    if corrected:
        revised['events'][0]['minute'] = start+2

    with repo.connect() as conn:
        original_nodes = conn.execute('SELECT id, payload_json FROM world_history_v3 ORDER BY id').fetchall()
    jid = repo.begin_job(sid, '', 'start', CONFIG)
    calls = execute(repo, jid, raw, LINE, repaired=revised)
    assert [bool(c.get('response_format')) for c in calls] == [False, True, True]
    job = repo.get_job(jid)
    diagnostics = json.loads(job['repair_diagnostics_json'])
    assert [d['code'] for d in diagnostics] == ['event_minute_invalid'] * (1 if corrected else 2)
    repo = Repository(repo.path)
    if not corrected:
        assert job['status'] == 'error'
        assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == []
        with repo.connect() as conn:
            assert conn.execute('SELECT id, payload_json FROM world_history_v3 ORDER BY id').fetchall() == original_nodes
        return

    assert job['status'] == 'saved', job['error']
    saved = repo.get_snapshot(sid)
    with repo.connect() as conn:
        history, _ = read_history(conn, saved['history_head'])
    event, = [e for e in history['events'] if e.get('local_id') == LOCAL_ID]
    old_letter, = [e for e in history['events'] if e['id'] == 'qa_read_letter']
    assert old_letter['minute'] == 480 and not old_letter['player_observed']
    assert 'qa_kirill:qa_private_letter' not in saved['world_state']['knowledge']
    assert saved['world_state']['scheduled_events']['call_oleg']['temporal']['time'] == '10:00'
    assert event['minute'] == event['recorded_minute'] == start+2
    assert event['calendar_date'] == current_time(state, start+2)['date']
    assert history['knowledge_acquisitions'][-1]['source_event_id'] == event['id']
    turn, = repo.list_turns(sid)
    assert event['source_sequence'] == turn['sequence']
    jid = repo.begin_job(sid, '', 'regenerate', CONFIG)
    revised['events'][0]['minute'] = start
    execute(repo, jid, revised, LINE)
    assert repo.get_job(jid)['status'] == 'saved'
    with repo.connect() as conn:
        replay, _ = read_history(conn, repo.get_snapshot(sid)['history_head'])
        assert [e['minute'] for e in replay['events'] if e.get('local_id') == LOCAL_ID] == [start]
        assert read_history(conn, saved['history_head'])[0] == history
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == saved
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
