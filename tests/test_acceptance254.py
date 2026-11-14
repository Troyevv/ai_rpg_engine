"""Original #252 v5 replies; authored controls are identified explicitly."""
import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError

ROOT = Path(__file__).parent / 'fixtures' / 'issue254'

def recorded(name, attempt=0):
    data = json.loads(gzip.decompress((ROOT / (name+'.json.gz')).read_bytes()))
    return data, json.loads(data['responses'][attempt]['response'])

def replay(data, payload):
    selection = data['selection']['5']
    return StateResolver(data['before'], data['narrative'], data['player_input'],
        **resolver_options(data['before'], data['player_input'], contract_version=5),
        chronology_events=data['world_history'].get('events', []),
        pacing_decision=selection.get('pacing'), initiative_decision=selection.get('initiative'),
        continuity_decision=selection.get('continuity')).resolve(payload)

def test_original_birth_optional_contact_does_not_cancel_child():
    data, payload = recorded('family_birth')
    # Original response has a SECOND, semantic source omission. Do not waive it.
    with pytest.raises(StructuralDeltaError) as exc:
        replay(data, payload)
    assert exc.value.code == 'birth_sex_observation_invalid'
    # Authored repair: unnamed examining clinician, original prose unchanged.
    payload['births'][0]['sex_observations'][0]['source_assertion'] = 'direct_observation'
    result = replay(data, payload)
    child = 'character_827f657aa87adc1fb374'
    assert child in result.state['characters']
    assert sum(child == c for c in result.state['characters']) == 1
    assert any(w['code'] == 'event_contact_annotation_ignored' for w in result.warnings)
    assert not result.history['relationship_changes']


@pytest.mark.parametrize('damage', ['sex', 'listener', 'child'])
def test_birth_substantial_invariants_remain_fatal(damage):
    data, payload = recorded('family_birth')
    observation = payload['births'][0]['sex_observations'][0]
    observation['source_assertion'] = 'direct_observation'
    if damage == 'sex': observation['narrative_sex'] = 'female'
    elif damage == 'listener': observation['perceived_by'].append('qa_timur')
    else: observation['child_id'] = 'invented-child'
    with pytest.raises(StructuralDeltaError): replay(data,payload)


def test_semantic_information_source_never_becomes_optional_contact():
    from test_policy252 import state, raw, info, resolve
    s=state();p=raw(s);event=info();event['target_ids']=['missing']
    p['information_events']=[event]
    with pytest.raises(StructuralDeltaError): resolve(s,p)
    assert not s['knowledge']


@pytest.mark.parametrize('damage', ['wrong_place', 'remote', 'ambiguous_route'])
def test_source_order_does_not_override_substantial_route_conflicts(damage):
    data,payload=recorded('arrival')
    if damage == 'wrong_place': payload['events'][1]['location_id']='loc_street_lenina'
    elif damage == 'remote': payload['events'][1]['interaction_channel']='call'
    else:
        move=deepcopy(payload['movements'][0]);move.update(to_location_id='loc_street_lenina',from_location_id='loc_home_viktor')
        payload['movements'].append(move)
    with pytest.raises(StructuralDeltaError): replay(data,payload)

def test_original_arrival_uses_source_event_order():
    data, payload = recorded('arrival')
    result = replay(data, payload)
    assert result.state['characters']['char_alexey']['location_id'] == 'loc_home_viktor'
    assert result.history['movements'][0]['order'] == 2
    assert payload['movements'][0]['order'] == 1

@pytest.mark.parametrize('name', ['knowledge', 'campaign', 'family', 'social'])
def test_original_successful_scenes_remain_accepted(name):
    data, payload = recorded(name)
    replay(data, payload)

@pytest.mark.parametrize('name', ['crisis', 'phone', 'phone_departure'])
def test_original_semantic_failures_are_not_silently_saved(name):
    data, payload = recorded(name)
    before = deepcopy(data['before'])
    with pytest.raises(StructuralDeltaError):
        replay(data, payload)
    assert data['before'] == before


@pytest.mark.parametrize('attempt,paths', [(0, ['events[0].advance_candidate_ids', 'information_events[0].advance_candidate_ids']),
                                        (1, ['information_events[0].advance_candidate_ids'])])
def test_original_lta_feedback_addresses_every_source(attempt, paths):
    from backend.runtime_v3.raw import RawTurnResult, compile_semantic, repair_feedback
    from backend.runtime_v3.long_term import validate_event_causes
    data = json.loads(gzip.decompress((ROOT / 'lta.json.gz').read_bytes()))
    original = data['responses'][attempt]
    raw = compile_semantic(RawTurnResult.parse(original), data['before'], data['narrative'], 1)
    with pytest.raises(StructuralDeltaError) as exc:
        validate_event_causes(raw, ['advance_62b4bd97a0ff73d86fdb'])
    diagnostics = exc.value.diagnostics('repair')
    assert [d['path'] for d in diagnostics] == paths
    feedback = json.loads(repair_feedback(diagnostics, original, data['before']))
    assert all(d['allowed_candidate_ids'] == ['advance_62b4bd97a0ff73d86fdb'] for d in feedback['diagnostics'])
    assert feedback['original_extraction'] == json.loads(original)


@pytest.mark.parametrize('links', [[], ['unselected'], ['one', 'two']])
def test_lta_never_guesses_or_collapses_causes(links):
    from backend.runtime_v3.raw import RawTurnResult, compile_semantic
    from backend.runtime_v3.long_term import validate_event_causes
    from test_policy252 import state, raw, info
    s = state(); p = raw(s); item = info(); item['advance_candidate_ids'] = links
    p['information_events'] = [item]
    compiled = compile_semantic(RawTurnResult.parse(p), s, 'Контроль', 1)
    assert compiled.records['events'][0].get('advance_candidate_ids', []) == links
    if links == ['one', 'two']:
        validate_event_causes(compiled, ['one', 'two'])
    else:
        with pytest.raises(StructuralDeltaError): validate_event_causes(compiled, ['one', 'two'])


@pytest.mark.parametrize('assertion', ['narrator', 'belief', 'lie', 'quotation'])
def test_current_calendar_contrast(assertion):
    from test_calendar_v2 import state
    from test_policy252 import raw, resolve
    s = state('2026-04-19', 1080, 6)
    p = raw(s); p['chronology_claims'] = [dict(kind='current_calendar', weekday='saturday',
        assertion=assertion, evidence='Субботний вечер.')]
    if assertion == 'narrator':
        with pytest.raises(StructuralDeltaError) as exc: resolve(s, p)
        assert not exc.value.repairable
        assert exc.value.path['chronology']['actual_weekday'] == 'sunday'
    else: resolve(s, p)


def test_calendar_unknown_date_custom_week_and_scene_reference():
    from test_calendar_v2 import state
    from test_policy252 import raw, resolve
    s = state(None, 0, 0); p = raw(s)
    p['chronology_claims'] = [dict(kind='current_calendar', date='2040-01-01', assertion='narrator', evidence='Сегодня.')]
    resolve(s, p)  # No canonical absolute date to contradict.
    s = state('0042-01-19', 0, 0, dict(system='custom',month_lengths=[20,25],weekday_names=['A','B','C']))
    p = raw(s); p['chronology_claims'] = [dict(kind='current_calendar', weekday='A', assertion='narrator', evidence='День A.')]
    resolve(s, p)
    s = state('2026-04-19', 1430, 6); p = raw(s); p['final_scene']['elapsed_minutes'] = 20
    p['chronology_claims'] = [dict(kind='current_calendar',weekday='monday',reference_minute=1445,assertion='narrator',evidence='Понедельник.')]
    resolve(s, p)
    p['chronology_claims'][0]['reference_minute'] = 1451
    with pytest.raises(StructuralDeltaError) as exc: resolve(s, p)
    assert exc.value.code == 'chronology_reference_invalid'


def test_phone_independent_endpoint_and_action_errors_share_feedback():
    data, payload = recorded('phone')
    with pytest.raises(StructuralDeltaError) as exc: replay(data, payload)
    codes = {d['code'] for d in exc.value.diagnostics('repair')}
    assert 'movement_endpoint_invalid' in codes
    assert len(codes) > 1


def calendar_payload(repo, sid, *, corrected=False):
    from backend.runtime_v3.calendar import current_time, weekday_options
    from test_policy252 import raw
    state = repo.get_snapshot(sid)['world_state']
    now = current_time(state)
    days = weekday_options(state)
    actual = days[now['weekday']]['id']
    wrong = days[(now['weekday'] + 1) % len(days)]['id']
    p = raw(state)
    p['chronology_claims'] = [dict(kind='current_calendar', weekday=actual if corrected else wrong,
        reference_minute=now['world_time'], assertion='narrator',
        evidence='Верный день.' if corrected else 'Неверный день.')]
    return p


def seed_calendar(repo):
    from test_policy252 import seed_chronology
    selected = seed_chronology(repo)
    selected['narrative'] = 'В комнате тихо. Неверный день. За окном дождь.'
    return selected


def test_calendar_recovery_new_extraction_commit_reload_and_rollback(tmp_path):
    from unittest.mock import patch
    import engine
    from backend.repositories.preparation import Repository
    from test_integrated_repair247 import execute, history
    from test_policy252 import CONFIG
    repo = Repository(tmp_path/'calendar.sqlite')
    selected = seed_calendar(repo); sid = selected['save']
    before = repo.get_snapshot(sid); old_history = history(repo, sid)
    failed, _ = execute(repo, sid, dict(player_input=selected['action'], narrative=selected['narrative']),
        [calendar_payload(repo, sid)], config=CONFIG, legacy=False)
    assert failed['status'] == 'error'
    assert repo.public_job(failed)['chronology_correction_available']
    assert repo.get_snapshot(sid) == before
    jid = repo.correct_chronology_job(failed['id'], failed['revision'], failed['attempt_epoch'])
    stages = []
    def stream(**kw):
        if 'Исправь только хронологические' in str(kw['messages']):
            stages.append('correction')
            yield json.dumps(dict(edits=[dict(original='Неверный день.', replacement='Верный день.')]))
        else:
            stages.append('new-extraction')
            assert 'Верный день.' in str(kw['messages'])
            yield json.dumps(calendar_payload(repo, sid, corrected=True))
    with patch('engine.find_loaded_model', return_value={'config':{}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker())
    accepted = Repository(repo.path).get_job(jid)
    assert accepted['status'] == 'saved', accepted['error']
    assert stages == ['correction', 'new-extraction']
    assert accepted['narrative'] == selected['narrative'].replace('Неверный', 'Верный')
    assert repo.get_job(failed['id'])['narrative'] == selected['narrative']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state'] == before['world_state']
    assert history(repo, sid) == old_history


@pytest.mark.parametrize('damage', ['missing', 'belief', 'other_minute', 'other_field'])
def test_calendar_correction_requires_same_objective_ground(damage):
    from backend.runtime_v3.raw import RawTurnResult
    from backend.runtime_v3.continuity import require_chronology_recheck
    p = dict(final_scene={}, chronology_claims=[dict(kind='current_calendar', weekday='sunday',
        reference_minute=1080, assertion='narrator', evidence='Воскресенье.')])
    grounds = [dict(kind='current_calendar', current_minute=1080, claimed_weekday='saturday')]
    require_chronology_recheck(RawTurnResult.parse(p), grounds)
    if damage == 'missing': p['chronology_claims'] = []
    elif damage == 'belief': p['chronology_claims'][0]['assertion'] = 'belief'
    elif damage == 'other_minute': p['chronology_claims'][0]['reference_minute'] = 1081
    else:
        p['chronology_claims'][0].pop('weekday')
        p['chronology_claims'][0]['date'] = '2026-04-19'
    with pytest.raises(StructuralDeltaError): require_chronology_recheck(RawTurnResult.parse(p), grounds)


@pytest.mark.parametrize('scope', ['partial', 'full', 'rumor', 'hypothetical'])
def test_authored_information_scope_controls_do_not_expand_secret(scope):
    from backend.runtime_v3.models import Fact, Knowledge
    from test_policy252 import state, raw, resolve
    from test_reproduction import snap
    from test_milestones import db
    from backend.runtime_v3.repository import committed_snapshot, read_history
    s = state()
    s['facts']['letter'] = Fact(id='letter',text='Бывшая ученица пишет Виктору о напряжении в семье.',
        visibility='secret',story_secret=True,secret_keeper_ids=['b']).model_dump()
    s['knowledge']['b:letter'] = Knowledge(actor_id='b', fact_id='letter', status='known').model_dump()
    p = raw(s)
    if scope != 'hypothetical':
        claim = dict(assertion='rumor' if scope == 'rumor' else 'testimony',
                     perceived_by=['a'],status='suspected' if scope == 'rumor' else 'known')
        if scope in ('full', 'rumor'): claim['fact_id'] = 'letter'
        else: claim['fact'] = dict(text='Виктор получил письмо с просьбой о совете.')
        p['information_events'] = [dict(id='talk',text='Рассказ о письме.',source_actor_id='b',medium='conversation',claims=[claim])]
    result = resolve(s,p)
    con = db(); saved = committed_snapshot(con, snap(s), result)
    knowledge = saved['world_state']['knowledge']
    assert ('a:letter' in knowledge) == (scope in ('full','rumor'))
    assert 'c:letter' not in knowledge  # Mention/nearby character is not a perceiver.
    if scope == 'rumor': assert knowledge['a:letter']['status'] == 'suspected'
    if scope == 'partial': assert len(result.history['knowledge_acquisitions']) == 1
    if scope == 'hypothetical': assert not result.history['knowledge_acquisitions']
    assert saved['world_state']['facts']['letter'] == s['facts']['letter']
