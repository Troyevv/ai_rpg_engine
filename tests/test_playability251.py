"""Original Berezovsk replies, plus explicitly labelled human JSON controls.

Only provider IO is scripted. No Narrative rewrite or paid calls. Source hashes
and the limits of the extracted fixture are documented alongside it.
"""
from copy import deepcopy
import lzma
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import current_time, scheduled_window, normalize_temporal
from backend.runtime_v3.context import build_context
from backend.runtime_v3.models import TemporalValue
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.raw import prompt_schema
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_integrated_repair247 import execute, history

DATA = json.loads(lzma.decompress((Path(__file__).parent/'fixtures/issue251/berezovsk.json.xz').read_bytes()))
CONFIG = dict(model='test', context_length=131072, max_tokens=2400, update_tokens=8192)


def resolve(case, raw=None, *, state=None):
    data = DATA[case]
    state = state or data['snapshot']['world_state']
    return StateResolver(state, data['narrative'], data['player_input'],
        **resolver_options(state, data['player_input'], contract_version=4)).resolve(
            raw if raw is not None else data['responses'][-1]['payload'])


def payload(case, index=-1):
    return json.loads(DATA[case]['responses'][index]['payload'])


def seed(repo, case):
    """Import the recorded world and preceding turn, never generate a new world."""
    data = DATA[case]
    snapshot = deepcopy(data['snapshot'])
    snapshot['history_head'] = None  # Minimal fixture; full lineage replay uses SQLite copies.
    for key in list(snapshot):
        if key.startswith('_'):
            del snapshot[key]
    with repo.connect() as db:
        wid = db.execute('INSERT INTO worlds(name,name_key,version,source_md,digest) VALUES(?,?,?,?,?)',
            ('Berezovsk 251 '+case, 'berezovsk251-'+case, 1, '', 'recorded251-'+case)).lastrowid
        sid = db.execute('INSERT INTO saves(world_id,name,state_json) VALUES(?,?,?)',
            (wid, 'Recorded '+case, json.dumps(snapshot, ensure_ascii=False))).lastrowid
        row = data['previous_turn']
        keys = list(row)
        db.execute('INSERT INTO turns(save_id,'+','.join(keys)+') VALUES('+','.join('?' for _ in range(len(keys)+1))+')',
                   [sid, *row.values()])
    repo.init_runtime()  # Initialize the imported turn's existing variant metadata before measuring.
    return dict(world=wid, save=sid, action=data['player_input'])


def control(case):
    """A human correction of JSON only, separately identified from real responses."""
    raw = payload(case)
    if case == '001':
        action = raw['player_agency']['actions'][1]
        action['target_ids'] = list(action['narrative_target_ids'])
    elif case == '008':
        # Incidental strangers are not the player and need no invented NPC IDs.
        for action in raw['player_agency']['actions']:
            action['target_ids'] = list(action['narrative_target_ids'])
    elif case == '016':
        # Time normalization alone cannot supply the missing assent assertion.
        raw['scheduled_event_changes'][0]['player_assertion'] = 'explicit_choice'
    else:
        raise ValueError(case)
    return raw


@pytest.mark.parametrize('case', ['001', '006', '008'])
def test_original_target_conflicts_are_repairable_not_narrative_reauthor(case):
    raw = DATA[case]['responses'][-1]['payload']
    original = deepcopy(DATA[case])
    with pytest.raises(StructuralDeltaError) as exc:
        resolve(case, raw)
    assert exc.value.code == 'player_action_targets_inconsistent'
    assert exc.value.repairable
    assert all(r['action'] == 'extraction_repair' for r in exc.value.diagnostics('test'))
    assert DATA[case] == original


@pytest.mark.parametrize('case', ['002r', '020r', '024r'])
def test_original_replies_keep_events_without_decorative_blockers(case):
    for record in DATA[case]['responses'][1 if case == '024r' else 0:]:
        raw = json.loads(record['payload'])
        result = resolve(case, raw)
        assert {e['local_id'] for e in result.history['events']} == {e['id'] for e in raw['events']}
        assert result.state['knowledge'] == DATA[case]['snapshot']['world_state']['knowledge']
        if case == '002r':
            assert all(not e.get('continuity') for e in result.history['events'])
            assert any(w['code'] == 'continuity_external_decision_ignored' for w in result.warnings)
        if case == '020r':
            arrival = next(e for e in result.history['events'] if e['local_id'] == 'event_alexey_arrives_cafe')
            assert not arrival.get('player_interaction') and arrival['target_ids'] == []
            assert arrival['participants'] == ['char_alexey']
        if case == '024r':
            assert result.state['characters']['char_alexey']['location_id'] == 'loc_home_galina'
            assert result.state['scheduled_events']['sched_tamara_talks_saturday']['character_ids'] == ['char_alexey', 'char_tamara']


@pytest.mark.parametrize('case', ['006', '009r', '016r'])
def test_original_real_conflicts_remain_atomic(case):
    data = deepcopy(DATA[case])
    for r in data['responses'][:1] if case == '006' else data['responses']:
        with pytest.raises(StructuralDeltaError) as exc:
            resolve(case, r['payload'])
        rows = exc.value.diagnostics('replay')
        if case == '006':
            assert exc.value.code == 'scene_movement_conflict'
        elif case == '009r':
            assert any(r['code'] == 'movement_source_invalid' and r.get('field') == 'to_location_id' for r in rows)
            assert not any(r['code'] == 'movement_agency' for r in rows)
        else:
            assert exc.value.code == 'controlled_actor_unsupported'
            assert exc.value.path['evidence_field'] == 'player_assertion'
    assert DATA[case] == data


@pytest.mark.parametrize('case', ['002', '020', '024'])
def test_original_jobs_commit_reload_rollback(tmp_path, case):
    repo = Repository(tmp_path/'game.sqlite'); sid = seed(repo, case)['save']
    before, hist = repo.get_snapshot(sid), history(repo, sid)
    # 024 original first response needs repair; the original saved repair suffices.
    replies = [json.loads(r['payload']) for r in DATA[case]['responses']]
    job, calls = execute(repo, sid, DATA[case], replies, legacy=False, config=CONFIG)
    assert job['status'] == 'saved', job['error']
    stages = [r['stage'] for r in repo.request_log(job_id=job['id'])]
    assert stages.count('narrative') == 1
    assert stages.count('extraction') == 1
    assert stages.count('extraction_repair') == (1 if case == '024' else 0)
    fresh = Repository(repo.path)
    assert fresh.list_turns(sid)[-1]['assistant_text'] == DATA[case]['narrative']
    assert fresh.get_snapshot(sid) == repo.get_snapshot(sid)
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid) == before and history(fresh, sid) == hist


@pytest.mark.parametrize('case', ['008', '016'])
def test_same_narrative_retry_after_original_error(tmp_path, case):
    repo = Repository(tmp_path/'retry.sqlite'); sid = seed(repo, case)['save']
    before, hist, turns = repo.get_snapshot(sid), history(repo, sid), repo.list_turns(sid)
    bad = payload(case)
    job, calls = execute(repo, sid, DATA[case], [bad, bad], legacy=False, config=CONFIG)
    if case == '016':
        # Real storage.list_turns -> engine -> provider boundary. list_turns used
        # to discard both timestamps, which a builder-only test cannot detect.
        current = next(json.loads(m['content'].split('\n', 1)[1]) for m in calls[0]['messages']
            if m['content'].startswith('Текущее состояние / GM-only\n'))
        assert current['last_time_advance']['start']['date'] == '2026-04-11'
        assert current['current_time']['date'] == '2026-04-16'
        assert current['past_situations']['observed_no_later_than']['date'] == '2026-04-11'
        assert not current['camera'].get('situation')
        assert all('temporal_before' not in row for row in repo.list_turns(sid))
    assert job['status'] == 'error'
    assert repo.public_job(job)['retry_allowed'] and not repo.public_job(job)['narrative_reauthor_required']
    assert repo.get_snapshot(sid) == before and history(repo, sid) == hist and repo.list_turns(sid) == turns
    retry, calls = execute(repo, sid, DATA[case], [control(case)], retry=job['id'], legacy=False, config=CONFIG)
    assert retry['status'] == 'saved', retry['error']
    assert calls[0]['response_format']
    stages = [r['stage'] for r in repo.request_log(job_id=job['id'])]
    assert stages.count('narrative') == 1  # Retry never reauthors; optional background is independent.
    assert stages.count('extraction') == 2 and stages.count('extraction_repair') == 1
    assert retry['narrative'] == DATA[case]['narrative']
    assert repo.list_turns(sid)[-1]['assistant_text'] == DATA[case]['narrative']
    if case == '016':
        state = repo.get_snapshot(sid)['world_state']
        old = before['world_state']['scheduled_events']['sched_alexey_photo_galina_library']
        new = state['scheduled_events'][old['id']]
        assert new['character_ids'] == old['character_ids']
        assert new['time_reference_minute'] == old['time_reference_minute']
        assert current_time(state, scheduled_window(state, new)['start_minute'])['date'] == '2026-04-16'
        assert current_time(state, scheduled_window(state, new)['start_minute'])['time'] == '10:00'
        context = repo.get_job(job['id'])['context_json']
        regenerated, _ = execute(repo, sid, DATA[case], [control(case)], kind='regenerate', legacy=False, config=CONFIG)
        assert regenerated['status'] == 'saved', regenerated['error']
        assert regenerated['context_json'] == context


def test_original_001_target_repair_exposes_separate_unanchored_plan(tmp_path):
    repo = Repository(tmp_path/'001.sqlite'); sid = seed(repo,'001')['save']
    before = repo.get_snapshot(sid)
    job, _ = execute(repo,sid,DATA['001'],[payload('001')]*2,legacy=False,config=CONFIG)
    assert job['status'] == 'error' and repo.public_job(job)['retry_allowed']
    job, _ = execute(repo,sid,DATA['001'],[control('001')]*2,retry=job['id'],legacy=False,config=CONFIG)
    assert job['status'] == 'error' and repo.public_job(job)['retry_allowed']
    assert 'commitment_invalid' in {r['code'] for r in json.loads(job['repair_diagnostics_json'])}
    assert repo.get_snapshot(sid) == before
    assert job['narrative'] == DATA['001']['narrative']


def independent_movement():
    raw = payload('024'); movement = raw['movements'][0]
    aid = raw['events'][-1]['player_action_id']
    raw['events'] = raw['events'][:-1]
    movement.pop('source_event_id'); movement.pop('evidence'); movement.pop('actor_evidence')
    movement['player_action_id'] = aid
    return raw


@pytest.mark.parametrize('proof', ['action', 'quote', 'npc'])
def test_movement_has_one_canonical_record_without_duplicate_event(proof):
    raw = independent_movement()
    if proof == 'quote':
        raw['movements'][0].pop('player_action_id')
        raw['movements'][0].update(player_assertion='explicit_choice', player_evidence='Прощаюсь и возвращаюсь домой.')
    if proof == 'npc':
        # Independent NPC movement need not create PlayerAction/contact/Knowledge.
        raw = {'final_scene': dict(location_id='loc_cafe', present_character_ids=['char_alexey','char_tamara'], elapsed_minutes=1),
               'movements': [dict(actor_id='char_viktor', from_location_id='loc_home_viktor',
                    to_location_id='loc_library', assertion='completed_arrival')]}
    result = resolve('024', raw)
    assert len(result.history['movements']) == 1
    assert all(e['local_id'] != 'event_alexey_walks_home' for e in result.history['events'])
    assert result.state['knowledge'] == DATA['024']['snapshot']['world_state']['knowledge']


@pytest.mark.parametrize('damage', ['origin', 'endpoint', 'unknown_action', 'unauthorized', 'quote', 'future', 'order', 'foreign_source'])
def test_movement_minimal_invariants_reject_real_contradictions(damage):
    raw = independent_movement(); m = raw['movements'][0]
    if damage == 'origin': m['from_location_id'] = 'loc_library'
    elif damage == 'endpoint': m['to_location_id'] = 'loc_home_viktor'
    elif damage == 'unknown_action': m['player_action_id'] = 'missing'
    elif damage == 'unauthorized': m.pop('player_action_id')
    elif damage == 'quote': m['player_evidence'] = 'Соглашаюсь переехать.'
    elif damage == 'future': m['assertion'] = 'future_intent'
    elif damage == 'order':
        raw['movements'].append(dict(m, to_location_id='loc_library', from_location_id='loc_home_galina'))
    elif damage == 'foreign_source': m['source_event_id'] = 'event_alexey_agrees_saturday'
    with pytest.raises(StructuralDeltaError): resolve('024', raw)


def test_supplied_arrival_order_need_not_duplicate_movement_but_cannot_precede_it():
    raw = payload('024')
    raw['events'][-1]['order'] = 4
    assert resolve('024', raw).state['characters']['char_alexey']['location_id'] == 'loc_home_galina'
    raw['events'][-1]['order'] = 2
    with pytest.raises(StructuralDeltaError): resolve('024', raw)


def test_new_place_and_departure_without_event_preserve_distinct_semantics():
    raw = independent_movement(); m = raw['movements'][0]
    raw['locations'] = [dict(id='new_court', name='Новый двор', description='Двор у дома.')]
    raw['final_scene'].update(location_id='new_court', present_character_ids=['char_alexey'])
    m['to_location_id'] = 'new_court'
    result = resolve('024', raw)
    assert result.state['characters']['char_alexey']['location_id'] == 'new_court'
    raw = {'final_scene': dict(location_id='loc_cafe', present_character_ids=['char_alexey'], elapsed_minutes=1),
           'movements': [dict(actor_id='char_tamara', from_location_id='loc_cafe', to_location_id=None, assertion='departure')]}
    assert resolve('024', raw).state['characters']['char_tamara']['location_id'] is None
    raw.pop('movements')
    assert resolve('024', raw).state['characters']['char_tamara']['location_id'] == 'loc_cafe'


def test_invalid_optional_beat_cannot_authorize_domain_consequence():
    raw = payload('002')
    raw['scheduled_event_changes'] = [dict(id='coerced', assertion='agreed', description='Обещание',
        character_ids=['char_alexey','char_galina'], temporal={'day_offset':1},
        source_event_id=raw['events'][0]['id'])]
    with pytest.raises(StructuralDeltaError) as exc: resolve('002', raw)
    assert exc.value.code == 'controlled_actor_unsupported'


@pytest.mark.parametrize('case,day,date', [('005','wednesday','2026-04-15'),('025r','saturday','2026-04-18')])
def test_original_numeric_weekdays_preserved_new_semantic_ids_correct(case, day, date):
    raw = payload(case); original = resolve(case, raw)
    change = raw['scheduled_event_changes'][0]
    legacy = change['temporal']['weekday']
    assert original.state['scheduled_events'][change['id']]['temporal']['weekday'] == legacy
    change['temporal']['weekday'] = day  # labelled corrected Extraction, never historical migration
    result = resolve(case, raw); event = result.state['scheduled_events'][change['id']]
    assert current_time(result.state, scheduled_window(result.state,event)['start_minute'])['date'] == date


def test_custom_weekdays_unknown_date_and_input_schema():
    state = deepcopy(DATA['016']['snapshot']['world_state'])
    state['meta']['calendar'].update(start_date=None, start_weekday=0,
        profile=dict(system='custom', id='fiction', month_lengths=[31]*12, weekday_names=['Sun','Moon','Star']))
    assert normalize_temporal(state, {'weekday':'Star'}) == {'weekday':2}
    assert normalize_temporal(state, {'weekday':2}) == {'weekday':2}
    with pytest.raises(ValueError): normalize_temporal(state, {'weekday':'wednesday'})
    raw = control('016'); old = state['scheduled_events']['sched_alexey_photo_galina_library']
    old['temporal']['weekday'] = 2
    old_due = scheduled_window(state, old)['start_minute']
    state['meta']['world_time'] = old_due
    result = resolve('016', raw, state=state)
    new_due = scheduled_window(result.state,result.state['scheduled_events'][old['id']])['start_minute']
    assert new_due//1440 == old_due//1440
    schema = prompt_schema(consequence_first=True, explicit_departures=True)
    validator = Draft202012Validator({'$defs':schema.get('$defs',{}), 'properties':{'scheduled_event_changes':schema['properties']['scheduled_event_changes']}})
    for temporal in ({'weekday':'wednesday'}, {'weekday':'Star','time':'18:00'}, {'time':'10:00'}):
        validator.validate({'scheduled_event_changes':[dict(id='meeting', assertion='rescheduled', temporal=temporal)]})
    # Persisted canonical models stay numeric and reject unanchored values.
    with pytest.raises(ValueError): TemporalValue.model_validate({'time':'10:00'})


@pytest.mark.parametrize('case', ['016','017'])
def test_actual_context_dates_old_scenes_and_projects_stale_situations(case):
    d = deepcopy(DATA[case]); before = deepcopy(d)
    original = d['original_messages'][0]
    assert any('2026-04-16' in m['content'] for m in original)
    assert not any(m['content'].startswith('Прошлая сцена / canonical time') for m in original)
    messages = build_context(d['snapshot'],d['views'],d['player_input'],'turn',131072,8192)
    current = next(json.loads(m['content'].split('\n',1)[1]) for m in messages if m['content'].startswith('Текущее состояние / GM-only\n'))
    assert current['current_time']['date'] == '2026-04-16'
    assert current['last_time_advance']['start']['date'] == '2026-04-11'
    assert current['last_time_advance']['end']['date'] == '2026-04-16'
    assert current['past_situations']['observed_no_later_than']['date'] == '2026-04-11'
    assert not current['camera'].get('situation')
    assert not current['characters']['char_alexey'].get('situation')
    wrappers = [m for m in messages if m['content'].startswith('Прошлая сцена / canonical time')]
    assert len(wrappers) == 6 and any('2026-04-11' in m['content'] for m in wrappers)
    # Assistant prose is byte-for-byte the stored scene (POV projection unchanged).
    for m in messages:
        if m['role'] == 'assistant': assert m['content'] in [v['assistant_text'] for v in d['views']]
    assert d == before


def test_sqlite_failure_does_not_apply_valid_movement(tmp_path):
    repo = Repository(tmp_path/'failure.sqlite'); sid = seed(repo,'024')['save']
    before, hist = repo.get_snapshot(sid), history(repo,sid)
    with patch('backend.runtime_v3.repository.append_history', side_effect=sqlite3.OperationalError('injected failure')):
        job, _ = execute(repo,sid,DATA['024'],[payload('024')],legacy=False,config=CONFIG)
    assert job['status'] == 'error'
    assert Repository(repo.path).get_snapshot(sid) == before and history(repo,sid) == hist


@pytest.mark.parametrize('now_delta', [0, 1440, 8*1440, 366*1440])
@pytest.mark.parametrize('temporal', [{'weekday':3,'day_period':'morning'}, {'day_offset':5}, {'minute_offset':7600}])
def test_time_refinement_never_reanchors_to_a_later_week(now_delta, temporal):
    from backend.runtime_v3.calendar import refine_scheduled_time
    state = deepcopy(DATA['016']['snapshot']['world_state'])
    old = deepcopy(state['scheduled_events']['sched_alexey_photo_galina_library'])
    old.update(temporal=temporal, end_temporal=None)
    due = scheduled_window(state, old)['start_minute']
    state['meta']['world_time'] += now_delta
    original = deepcopy(old)
    refined = refine_scheduled_time(state,old,{'time':'23:59'})
    new = dict(old,temporal=refined)
    assert scheduled_window(state,new)['start_minute'] == due//1440*1440+1439
    assert old == original and new['time_reference_minute'] == original['time_reference_minute']


@pytest.mark.parametrize('damage', ['new','unresolved','bad_day','bad_clock'])
def test_ambiguous_time_refinement_is_repairable_without_losing_plan(damage):
    raw = control('016'); change = raw['scheduled_event_changes'][0]
    state = deepcopy(DATA['016']['snapshot']['world_state'])
    if damage == 'new': change.update(id='new_meeting',assertion='agreed')
    elif damage == 'unresolved': state['scheduled_events'][change['id']].update(temporal=None,due_minute=None,time_semantics='explicit')
    elif damage == 'bad_day': change['temporal'] = {'weekday':'not_a_day','time':'10:00'}
    else: change['temporal'] = {'time':'25:00'}
    before = deepcopy(state)
    with pytest.raises(StructuralDeltaError) as exc: resolve('016',raw,state=state)
    assert exc.value.repairable and state == before
    if damage in ('new','unresolved','bad_day'):
        assert exc.value.code == 'commitment_temporal_invalid'
        assert exc.value.path['current_time']['date'] == '2026-04-16'
        assert 'previous_anchor' in exc.value.path


@pytest.mark.parametrize('start_date,minutes,expected', [('2026-12-31',2,'2027-01-01'),('2024-02-28',1442,'2024-03-01'),(None,10080,None)])
def test_jump_projection_calendar_bounds_unknown_time_and_refresh(start_date,minutes,expected):
    from backend.runtime_v3.context import project_temporal_context, scene_time
    state = deepcopy(DATA['016']['snapshot']['world_state'])
    state['meta']['world_time']=1439
    state['meta']['calendar'].update(start_date=start_date,start_minute=0)
    end=deepcopy(state);end['meta']['world_time']+=minutes
    view=dict(kind='turn',changes_json=json.dumps({'time_skip':{'duration':minutes}}),
              before_json=json.dumps({'world_state':state}),after_json=json.dumps({'world_state':end}))
    current=deepcopy(end)
    project_temporal_context({'world_state':end},[view],current)
    assert current['last_time_advance']['end']['date']==expected
    assert current['last_time_advance']['elapsed_minutes']==minutes
    assert not current['camera'].get('situation')
    assert scene_time(state,view)['end']['date']==expected
    assert scene_time(state,{'assistant_text':'Недатированный старый текст'})=={'time':'unknown'}
    # No future jump can enter a rolled-back branch's current situation.
    current=deepcopy(state)
    project_temporal_context({'world_state':state},[view],current)
    assert 'last_time_advance' not in current and current['camera']==state['camera']
    # A real later situation update remains current; old source state is immutable.
    later=deepcopy(end);later['meta']['world_time']+=1;later['camera']['situation']='Новая сцена'
    next_view=dict(kind='turn',before_json=json.dumps({'world_state':end}),after_json=json.dumps({'world_state':later}))
    current=deepcopy(later)
    project_temporal_context({'world_state':later},[view,next_view],current)
    assert current['camera']['situation']=='Новая сцена'
    assert end['camera']['situation']==state['camera']['situation']


@pytest.mark.parametrize('section,source_key', [('scheduled_event_changes','source_event_id'),('knowledge_gained','source_event_id'),('relationship_changes','source_event_ids')])
def test_arrival_contact_marker_is_not_dropped_for_substantial_consumer(section,source_key):
    raw=payload('020')
    source='event_alexey_arrives_cafe'
    raw[section]=[{source_key:[source] if source_key.endswith('ids') else source}]
    with pytest.raises(StructuralDeltaError) as exc: resolve('020',raw)
    assert any(d['code']=='player_action_completion_invalid' for d in exc.value.diagnostics('test'))


@pytest.mark.parametrize('key',['source_event_id','player_action_id'])
@pytest.mark.parametrize('reference',[{},[],17])
def test_malformed_movement_reference_reaches_repair(key,reference):
    raw=independent_movement();raw['movements'][0][key]=reference
    with pytest.raises(StructuralDeltaError) as exc: resolve('024',raw)
    assert exc.value.repairable
    assert exc.value.code in ('movement_source_invalid','movement_agency')
