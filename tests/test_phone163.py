"""PR #163 P0: deterministic provider, real API/jobs/SQLite and common Resolver."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
import engine
from backend.runtime_v3.remote_semantics import messages, resolve
from backend.runtime_v3.calendar import scheduled_window
from backend.repositories.preparation import Repository
from test_phone122 import setup, dispatch, execute, read, CONFIG
from test_communication_cycle import decision

GREETING = 'Привет. Ты занята сегодня?'
OFFER = 'Можем встретиться через час?'
OFFICE = 'Привет. Ещё в офисе, разгребаю бумаги.'
PLACE = 'Да, через час встретимся в кафе «Липа».'


def run(repo, jid, reply, transform=None):
    calls = []
    def provider(**kw):
        ms = kw['messages']; data = json.loads(ms[1]['content'])
        if not ms[0]['content'].startswith('Remote semantic extraction/'):
            calls.append('decision')
            value = json.loads(decision(ms))
            if value.get('action', {}).get('action') == 'send':
                value['action']['content'] = reply
        else:
            calls.append('semantic')
            value = dict(final_scene=data['final_scene'])
            rows = data['accepted_messages']
            offer = next((r for r in rows if r['content'] == OFFER), None)
            assent = next((r for r in rows if offer and r['ordinal'] > offer['ordinal'] and r['content'].startswith('Да,')), None)
            if assent:
                value['scheduled_event_changes'] = [dict(id='ilya-katya-meeting', description='Встреча через час',
                    assertion='agreed', character_ids=[offer['sender_id'], assent['sender_id']],
                    temporal={'minute_offset': 60}, location_id=None,
                    evidence=assent['content'], remote_source_ids=[offer['id'], assent['id']],
                    remote_time_source_id=offer['id'], player_assertion='explicit_choice',
                    player_source_id=offer['id'], player_evidence=offer['content'])]
                if assent['content'] == PLACE:
                    value['locations'] = [dict(id='cafe-lipa', name='Кафе «Липа»', aliases=['Липа'], evidence=PLACE)]
                    value['scheduled_event_changes'][0]['location_id'] = 'cafe-lipa'
            if transform: value = transform(value, data)
        yield json.dumps(value, ensure_ascii=False)
    with patch('engine.chat_stream', side_effect=provider):
        engine.run_job(repo.path, jid, engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return calls


def frame(repo, jid):
    return next(f for f in json.loads(repo.get_job(jid)['context_json']) if f['stage'] == 'remote_semantics')


@pytest.mark.parametrize('reply', [PLACE, 'Да, давай через час.', 'Пока не знаю, я ещё в офисе.'])
def test_ilya_katya_api_sqlite_location_and_nullable_meeting(tmp_path, reply):
    repo, client, sid = setup(tmp_path)
    first = dispatch(repo, client, sid, GREETING, 'greeting')
    run(repo, first, OFFICE); read(repo, client, sid)
    before = repo.get_snapshot(sid)
    jid = dispatch(repo, client, sid, OFFER, 'one-hour')
    assert run(repo, jid, reply) == ['decision', 'decision', 'semantic']
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    state = repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events']) == 4
    assert state['camera'] == before['world_state']['camera']
    assert state['meta']['world_time'] == before['world_state']['meta']['world_time'] + 1
    if not reply.startswith('Да,'):
        assert not state['scheduled_events']; return
    plan = state['scheduled_events']['ilya-katya-meeting']
    assert plan['location_id'] == ('cafe-lipa' if reply == PLACE else None)
    assert set(plan['character_ids']) == {'qa_kirill', 'qa_vera'}
    source = state['remote_events'][plan['remote_source_ids'][0]]
    assert scheduled_window(state, plan)['start_minute'] == source['world_time'] + 60
    if reply == PLACE:
        assert state['locations']['cafe-lipa']['name'] == 'Кафе «Липа»'
        # The accepted variant stores both, not separate persistence operations.
        turn = repo.list_turns(sid)[-1]
        with repo.connect() as db:
            saved = json.loads(db.execute('SELECT after_json FROM turns WHERE id=?', (turn['id'],)).fetchone()[0])['world_state']
        assert saved['locations']['cafe-lipa'] and saved['scheduled_events'][plan['id']]
    assert not repo.get_save(sid)['state']['world']['scheduled_events']  # unread assent
    read(repo, client, sid)
    assert plan['id'] in client.get(f'/api/saves/{sid}').json()['state']['world']['scheduled_events']
    assert Repository(repo.path).get_snapshot(sid) == repo.get_snapshot(sid)
    # Repeated operation is idempotent and cannot advance time or add messages.
    snapshot = repo.get_snapshot(sid)
    assert dispatch(repo, client, sid, OFFER, 'one-hour') == jid
    assert repo.get_snapshot(sid) == snapshot
    repo.rollback_last(sid)
    rolled = repo.get_snapshot(sid)['world_state']
    assert 'cafe-lipa' not in rolled['locations']
    assert not rolled['scheduled_events']


def test_location_context_existing_alias_repeat_and_private_projection(tmp_path):
    repo, client, sid = setup(tmp_path)
    jid = dispatch(repo, client, sid, OFFER)
    run(repo, jid, PLACE)
    snapshot = repo.get_snapshot(sid); state = snapshot['world_state']
    source = next(e['id'] for e in state['remote_events'].values() if e['content'] == OFFER)
    context = json.loads(messages(snapshot, source)[1]['content'])
    assert 'locations' in context['schema']['properties']
    assert all(set(row) == {'id','name','aliases','parent_id'} for row in context['known_locations'])
    assert not any('known_locations' in json.dumps(f['messages']) for f in json.loads(repo.get_job(jid)['context_json']) if f['stage'] == 'communication')
    raw = json.loads(frame(repo, jid)['response'])
    raw['locations'][0]['id'] = 'lipa-mentioned-again'
    raw['locations'][0]['name'] = 'Липа'
    raw['scheduled_event_changes'][0]['location_id'] = 'lipa-mentioned-again'
    diagnostics = []
    after, _ = resolve(snapshot, source, raw, diagnostics)
    assert after['world_state']['locations'] == state['locations']
    assert after['world_state']['scheduled_events'] == state['scheduled_events']
    assert any(w['code'] == 'location_identity_reused' for w in diagnostics)
    raw.pop('locations'); raw['scheduled_event_changes'][0]['location_id'] = 'cafe-lipa'
    assert resolve(snapshot, source, raw)[0]['world_state']['scheduled_events'] == state['scheduled_events']


def test_failed_repair_quarantines_unknown_place_preserves_valid_plan_and_recovers(tmp_path):
    repo, client, sid = setup(tmp_path)
    jid = dispatch(repo, client, sid, OFFER)
    before = repo.get_snapshot(sid)
    def unknown(raw, data):
        invalid = deepcopy(raw['scheduled_event_changes'][0]); invalid.update(id='bad-place-plan',location_id='unknown')
        raw['scheduled_event_changes'].extend([invalid, dict(invalid, id='second-bad-plan')])
        return raw
    assert run(repo, jid, PLACE, unknown) == ['decision','decision','semantic','semantic']
    job = repo.get_job(jid); assert job['status'] == 'saved', job['error']
    state = repo.get_snapshot(sid)['world_state']
    assert list(state['scheduled_events']) == ['ilya-katya-meeting']
    assert 'unknown' not in state['locations'] and 'cafe-lipa' in state['locations']
    assert len(state['remote_events']) == 2
    assert state['meta']['world_time'] == before['world_state']['meta']['world_time'] + 1
    journal = frame(repo, jid)
    assert journal['deferred'] and journal['repair_response'] and journal['repair_validation_errors']
    warnings = json.loads(job['warnings_json'])
    deferred = [w for w in warnings if w.get('action') == 'defer_record']
    assert [w['index'] for w in deferred] == [1, 2]
    assert all(w.get('remote_source_ids') for w in deferred)
    # Existing regeneration/variant path recovers consequences from the same
    # command boundary; no new transport or recovery state is introduced.
    regen = repo.begin_job(sid, '', 'regenerate', CONFIG)
    run(repo, regen, PLACE)
    assert repo.get_job(regen)['status'] == 'saved'
    recovered = repo.get_snapshot(sid)['world_state']
    assert len(recovered['remote_events']) == 2 and len(recovered['scheduled_events']) == 1
    assert recovered['meta']['world_time'] == state['meta']['world_time']


def test_rejected_plan_does_not_partially_create_its_new_location(tmp_path):
    repo, client, sid = setup(tmp_path); jid = dispatch(repo, client, sid, OFFER)
    def invalid(raw, data):
        raw['scheduled_event_changes'][0].pop('player_assertion'); return raw
    run(repo, jid, PLACE, invalid)
    assert repo.get_job(jid)['status'] == 'saved'
    state = repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events']) == 2
    assert not state['scheduled_events'] and 'cafe-lipa' not in state['locations']


def test_canonical_location_conflict_stays_atomic_and_retry_does_not_duplicate(tmp_path):
    repo, client, sid = setup(tmp_path); jid = dispatch(repo, client, sid, OFFER)
    before = repo.get_snapshot(sid)
    existing = next(iter(before['world_state']['locations']))
    def conflict(raw, data):
        raw['locations'][0].update(id=existing, name='Conflicting canonical identity'); return raw
    run(repo, jid, PLACE, conflict)
    assert repo.get_job(jid)['status'] == 'error'
    assert repo.get_snapshot(sid) == before
    with patch('engine.launch'):
        assert client.post(f'/api/jobs/{jid}/retry', json={'config': CONFIG}).status_code == 200
    assert run(repo, jid, PLACE) == ['semantic']
    assert repo.get_job(jid)['status'] == 'saved'
    state = repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events']) == 2 and len(state['scheduled_events']) == 1
    assert state['meta']['world_time'] == before['world_state']['meta']['world_time'] + 1


@pytest.mark.parametrize('repair_kind', ['invalid_json_shape', 'omission', 'provider_failure'])
def test_unusable_repair_preserves_original_valid_records(tmp_path, repair_kind):
    repo, client, sid = setup(tmp_path); jid = dispatch(repo, client, sid, OFFER)
    def invalid(raw, data):
        if 'repair' in data:
            if repair_kind == 'provider_failure': raise RuntimeError('Controlled repair transport failure')
            return 'not an extraction object' if repair_kind == 'invalid_json_shape' else dict(final_scene=data['final_scene'])
        bad = deepcopy(raw['scheduled_event_changes'][0]); bad.update(id='bad', location_id='unknown')
        raw['scheduled_event_changes'].append(bad)
        return raw
    run(repo, jid, PLACE, invalid)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    state = repo.get_snapshot(sid)['world_state']
    assert list(state['scheduled_events']) == ['ilya-katya-meeting']
    assert 'cafe-lipa' in state['locations'] and len(state['remote_events']) == 2
    assert frame(repo, jid)['repair_validation_errors']


def test_standalone_new_place_does_not_require_commitment(tmp_path):
    repo, client, sid = setup(tmp_path); jid = dispatch(repo, client, sid, GREETING)
    reply = 'Я в новом кафе «Липа», сегодня встречаться не могу.'
    def place(raw, data):
        raw['locations'] = [dict(id='cafe-lipa', name='Кафе «Липа»', evidence=reply)]
        return raw
    run(repo, jid, reply, place)
    assert repo.get_job(jid)['status'] == 'saved'
    state = repo.get_snapshot(sid)['world_state']
    assert 'cafe-lipa' in state['locations'] and not state['scheduled_events']
    # Learning a place exists does not physically move either participant.
    assert state['characters']['qa_vera']['location_id'] != 'cafe-lipa'


def test_rejected_update_never_deletes_already_confirmed_plan(tmp_path):
    repo, client, sid = setup(tmp_path); jid = dispatch(repo, client, sid, OFFER)
    run(repo, jid, PLACE); read(repo, client, sid)
    original = deepcopy(repo.get_snapshot(sid)['world_state']['scheduled_events'])
    jid = dispatch(repo, client, sid, 'Спасибо.', 'follow-up')
    def invalid(raw, data):
        raw['scheduled_event_changes'][0].update(assertion='rescheduled', location_id='unknown')
        return raw
    run(repo, jid, 'До встречи.', invalid)
    assert repo.get_job(jid)['status'] == 'saved'
    state = repo.get_snapshot(sid)['world_state']
    assert state['scheduled_events'] == original and len(state['remote_events']) == 4
