"""#237 equivalent Crisis replay: real Context/jobs/SQLite, scripted provider only.

The original #239 raw-response archive was not published when this replay was
written. The fixture reproduces its scene, actor, absent target and repair shape.
"""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_api import api
from test_event_presence import crisis, history, ACTION, NINA, VERA
from test_player_action_targets import claim, payload, play, saved_events, ATTEMPT
from test_player_action_targets import MARINA, GOOD_INPUT, GOOD_TEXT


def absent(state, *, marker=False, outcome='completed'):
    raw = payload(state, [claim([VERA], outcome=outcome)], completed=marker)
    raw['events'][0].update(participants=[NINA], witnesses=[NINA, 'qa_marina', 'qa_asya', 'qa_zoya'])
    return raw


@pytest.mark.parametrize('marker', [False, True])
def test_crisis_repair_removing_participant_cannot_keep_completed_outcome(crisis, marker):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    repaired = absent(before['world_state'], marker=marker)
    initial = deepcopy(repaired)
    initial['events'][0]['participants'].append(VERA)
    job, calls = play(crisis, [initial, repaired], ACTION, ATTEMPT)
    fresh = Repository(repo.path)
    assert len(calls) == 3
    # Also expose the actual persisted provenance in a pre-fix replay failure.
    persisted = [e.get('player_action') for e in saved_events(repo, sid) if e.get('player_action')]
    assert job['status'] == 'error', (job['status'], persisted)
    assert fresh.get_snapshot(sid) == before
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [d['code'] for d in diagnostics] == ['event_presence_invalid', 'player_action_completion_invalid']


def test_resolver_rejects_unmarked_completed_absent_target(crisis):
    _, repo, sid = crisis
    state = repo.get_snapshot(sid)['world_state']
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, ATTEMPT, ACTION, require_player_agency=True).resolve(absent(state))
    assert error.value.code == 'player_action_completion_invalid'


@pytest.mark.parametrize('outcome', ['attempted', 'deferred', 'not_performed'])
def test_absent_noncompleted_outcomes_are_not_delivery(crisis, outcome):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    job, calls = play(crisis, [absent(before['world_state'], outcome=outcome)], ACTION, ATTEMPT)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    row = saved_events(repo, sid)[-1]
    assert row['player_action']['outcome'] == outcome and row['target_ids'] == [VERA]
    assert not row.get('player_interaction')
    state = Repository(repo.path).get_snapshot(sid)['world_state']
    assert state['knowledge'] == before['world_state']['knowledge']
    assert state['characters'][VERA] == before['world_state']['characters'][VERA]


@pytest.mark.parametrize('recovery', ['attempt', 'repeated', 'reauthor', 'deleted'])
def test_completion_repair_and_abandon_are_bounded_and_atomic(crisis, recovery):
    client, repo, sid = crisis
    before = repo.get_snapshot(sid)
    turns = repo.list_turns(sid)
    variants = repo.variants(turns[-1]['node_id'])
    bad = absent(before['world_state'])
    fixed = deepcopy(bad)
    narrative = ATTEMPT
    if recovery == 'attempt':
        fixed['player_agency']['actions'][0]['outcome'] = 'attempted'
    elif recovery == 'reauthor':
        narrative = 'Нина спрашивает Веру. Вера отвечает ей, стоя рядом в библиотеке.'
        fixed['player_agency']['status'] = 'violated'
    elif recovery == 'deleted':
        fixed['events'] = []
    job, calls = play(crisis, [bad, fixed], ACTION, narrative)
    assert len(calls) == 3 and job['narrative'] == narrative
    assert 'input-1' in calls[-1]['messages'][0]['content']
    assert 'outcome=completed' in calls[-1]['messages'][0]['content']
    fresh = Repository(repo.path)
    if recovery == 'attempt':
        assert job['status'] == 'saved', job.get('error')
        assert saved_events(repo, sid)[-1]['player_action']['outcome'] == 'attempted'
    else:
        assert job['status'] == 'error'
        assert job['narrative_reauthor_required'] == (recovery == 'reauthor')
        assert fresh.get_snapshot(sid) == before and fresh.list_turns(sid) == turns
        assert fresh.variants(turns[-1]['node_id']) == variants
        with patch('engine.chat_stream', side_effect=AssertionError('abandon must not call LLM')):
            response = client.post(f'/api/saves/{sid}/jobs/{job["id"]}/abandon', json=dict(
                revision=fresh.get_save(sid)['revision'], attempt_epoch=job['attempt_epoch']))
        assert response.status_code == 200
        assert fresh.get_snapshot(sid) == before


@pytest.mark.parametrize('movement', ['present', 'arrive', 'leave', 'cross', 'ordered_meeting'])
def test_unmarked_completion_uses_existing_presence_timeline(crisis, movement):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    s = before['world_state']
    library, home = s['camera']['location_id'], s['characters'][VERA]['location_id']
    target = MARINA if movement in ('present', 'leave') else VERA
    quote = 'Я иду к Вере и спрашиваю о Кирилле.' if movement in ('cross', 'ordered_meeting') else ACTION if target == VERA else GOOD_INPUT
    raw = payload(s, [claim([target], quote=quote)], completed=False)
    if movement == 'arrive':
        raw['movements'] = [dict(actor_id=VERA, to_location_id=library, order=1)]
        raw['final_scene']['present_character_ids'] = [*s['camera']['present_character_ids'], VERA]
        raw['events'][0]['order'] = 2
    elif movement == 'leave':
        raw['movements'] = [dict(actor_id=MARINA, to_location_id=home, order=2)]
        raw['final_scene']['present_character_ids'] = [c for c in s['camera']['present_character_ids'] if c != MARINA]
        raw['events'][0]['order'] = 1
    elif movement in ('cross', 'ordered_meeting'):
        raw['final_scene'].update(location_id=home, present_character_ids=[NINA])
        raw['movements'] = [dict(actor_id=NINA, from_location_id=library, to_location_id=home,
                                 player_assertion='explicit_choice', player_evidence=quote),
                            dict(actor_id=VERA, from_location_id=home, to_location_id=library)]
        if movement == 'ordered_meeting':
            raw['movements'][0]['order'], raw['events'][0]['order'], raw['movements'][1]['order'] = 1, 2, 3
    job, calls = play(crisis, [raw, raw], quote, 'Нина задаёт вопрос. Ответа пока нет.')
    if movement == 'cross':
        assert job['status'] == 'error' and len(calls) == 3
        assert Repository(repo.path).get_snapshot(sid) == before
    else:
        assert job['status'] == 'saved', job.get('error')
        assert len(calls) == 2
        assert saved_events(repo, sid)[-1]['player_action']['outcome'] == 'completed'


@pytest.mark.parametrize('target_type', ['place', 'organization', 'object', 'none', 'reference'])
def test_completion_does_not_turn_every_target_into_a_participant(crisis, target_type):
    _, repo, sid = crisis
    if target_type in ('organization', 'object'):
        from devtools.narrative_test_world import load_fixture
        checkpoint = 'residence-roles' if target_type == 'organization' else 'possessions'
        sid = load_fixture(repo, checkpoint)['save']
        from test_narrative_test_world import ordinary_job
        ordinary_job(repo, sid, 'start')
        repo.transition_protagonist(sid, repo.get_save(sid)['revision'], 'completion237', 'permanent', NINA)
        crisis = (crisis[0], repo, sid)
    s = repo.get_snapshot(sid)['world_state']
    targets = {'place': [s['camera']['location_id']], 'organization': list(s['organizations'])[:1],
               'object': list(s['possessions'])[:1], 'none': [], 'reference': [VERA]}[target_type]
    assert target_type == 'none' or targets
    quote = 'Рассматриваю запись и обдумываю её.'
    action = claim(targets, quote=quote)
    if target_type == 'reference':
        action['target_mode'] = 'reference'
    raw = payload(s, [action], completed=False)
    raw['events'][0].update(medium='action', participants=[NINA])
    job, calls = play(crisis, [raw], quote, 'Нина рассматривает запись и обдумывает её.')
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    assert saved_events(repo, sid)[-1]['target_ids'] == targets


def test_reference_classification_cannot_describe_a_delivered_question(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = absent(before['world_state'])
    raw['player_agency']['actions'][0]['target_mode'] = 'reference'
    job, calls = play(crisis, [raw, raw], ACTION, ATTEMPT)
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before


def test_directed_physical_action_cannot_complete_without_contact(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    quote = 'Подаю Вере чашку.'
    raw = absent(before['world_state'])
    raw['player_agency']['actions'][0]['player_evidence'] = quote
    raw['events'][0]['medium'] = 'action'
    job, calls = play(crisis, [raw, raw], quote, 'Нина протягивает чашку, но Веры рядом нет.')
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('repair', [True, False])
def test_completion_preserves_per_action_evidence_contract_238(crisis, repair):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    first, second = 'Спрашиваю Марину о Кирилле.', 'Прошу Зою показать фотографии.'
    raw = payload(before['world_state'], [claim([MARINA], quote=first),
        claim(['qa_zoya'], quote=second, id='input-2')])
    bad = deepcopy(raw)
    bad['events'][1]['player_evidence'] = first + ' ' + second
    job, calls = play(crisis, [bad, raw if repair else bad], first + ' ' + second, GOOD_TEXT)
    assert len(calls) == 3
    assert job['status'] == ('saved' if repair else 'error'), job.get('error')
    if repair:
        events = saved_events(repo, sid)[-2:]
        assert [e['player_evidence'] for e in events] == [first, second]
        assert [e['target_ids'] for e in events] == [[MARINA], ['qa_zoya']]
    else:
        assert Repository(repo.path).get_snapshot(sid) == before


def test_unmarked_completion_reload_regeneration_siblings_and_rollback(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim([MARINA], quote=GOOD_INPUT)], completed=False)
    job, calls = play(crisis, [raw])
    assert job['status'] == 'saved' and len(calls) == 2
    accepted = Repository(repo.path).get_snapshot(sid)
    accepted_history = history(repo, accepted)
    turn = repo.list_turns(sid)[-1]
    bad = deepcopy(raw)
    bad['events'][0]['participants'] = [NINA]
    failed, calls = play(crisis, [bad, bad], '', GOOD_TEXT, 'regenerate')
    assert failed['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == accepted
    repo.abandon_job(sid, failed['id'], repo.get_save(sid)['revision'], failed['attempt_epoch'])
    sibling, calls = play(crisis, [raw], '', GOOD_TEXT, 'regenerate')
    assert sibling['status'] == 'saved' and len(calls) == 2
    assert repo.get_job(sibling['id'])['context_json'] == repo.get_job(job['id'])['context_json']
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid) == accepted
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid) == before
    branch, _ = play(crisis, [raw])
    assert branch['status'] == 'saved'
    assert history(repo, accepted) == accepted_history


def test_mixed_events_cannot_partially_commit_or_grant_knowledge(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    quote = GOOD_INPUT + ' ' + ACTION
    raw = payload(before['world_state'], [claim([MARINA], quote=GOOD_INPUT, id='good'),
                                            claim([VERA], id='bad')], completed=False)
    raw['events'][1]['participants'] = [NINA]
    raw['facts'] = [dict(id='news237', text='Нина принесла документы.', visibility='secret')]
    raw['events'][0]['fact_ids'] = ['news237']
    raw['events'][0]['witnesses'].append(MARINA)
    raw['knowledge_gained'] = [dict(actor_id=MARINA, fact_id='news237', source_event_id='event-good')]
    job, calls = play(crisis, [raw, raw], quote, ATTEMPT)
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before
    assert history(repo, before) == history(Repository(repo.path), before)


@pytest.mark.parametrize('linked', [True, False])
def test_message_requires_accepted_delivery_but_not_a_reply(api, linked):
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone-office')['save']
    ordinary_job(repo, sid, 'start')
    quote = 'Вера, как Кирилл?'
    response = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='send', character_id=VERA, content=quote, operation_id='send-237')))
    assert response.status_code == 200, response.text
    before = repo.get_snapshot(sid)
    s = before['world_state']
    actor = s['camera']['controlled_actor_id']
    sent = next(e for e in s['remote_events'].values() if e['sender_id'] == actor and e['content'] == quote)
    assert sent['delivered_to'] == [VERA] and sent['read_by'] == []
    raw = payload(s, [claim([VERA], quote=quote)], completed=False)
    raw['events'][0].update(medium='message', author_id=actor, actor_id=actor,
                            participants=[actor, VERA], witnesses=[actor])
    if linked:
        raw['remote_events'] = [dict(sender_id=actor, recipient_ids=[VERA], channel='TEXT_MESSAGE',
                                     existing_event_id=sent['id'], source_event_id='event-input-1')]
    job, calls = play((client, repo, sid), [raw, raw], quote, 'Сообщение доставлено Вере. Ответа нет.')
    assert job['status'] == ('saved' if linked else 'error'), job.get('error')
    # Existing autonomous Remote selection also runs after a pending player send.
    assert calls[0]['messages'][0]['content'].startswith('Select at most ONE')
    assert len(calls) == (3 if linked else 4)
    fresh = Repository(repo.path).get_snapshot(sid)
    assert fresh['world_state']['knowledge'] == before['world_state']['knowledge']
    if not linked:
        assert fresh == before
    else:
        assert saved_events(repo, sid)[-1]['player_action']['outcome'] == 'completed'
        assert fresh['world_state']['remote_events'][sent['id']]['read_by'] == []


def test_canonical_send_in_transit_is_not_completed_delivery(api):
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone-office')['save']
    # Seed the world's historical communication capability before its first job.
    with repo.connect() as db:
        snapshot = repo.get_snapshot(sid)
        snapshot['world_state']['meta']['communication'].update(letter=True, delivery_minutes={'letter': 30})
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot), sid))
    ordinary_job(repo, sid, 'start')
    quote = 'Письмом спрашиваю Веру о Кирилле.'
    response = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='send', channel='LETTER', character_id=VERA, content=quote, operation_id='post-237-delivery')))
    assert response.status_code == 200, response.text
    before = repo.get_snapshot(sid)
    s = before['world_state']
    actor = s['camera']['controlled_actor_id']
    sent = next(e for e in s['remote_events'].values() if e['operation_id'] == 'post-237-delivery')
    assert sent['status'] == 'in_transit' and sent['delivered_to'] == []
    raw = payload(s, [claim([VERA], quote=quote)], completed=False)
    raw['events'][0].update(medium='message', actor_id=actor, author_id=actor,
                            participants=[actor, VERA], witnesses=[actor])
    raw['remote_events'] = [dict(sender_id=actor, recipient_ids=[VERA], channel='LETTER',
                                 existing_event_id=sent['id'], source_event_id='event-input-1')]
    job, calls = play((client, repo, sid), [raw, raw], quote, 'Письмо ещё в пути.')
    assert job['status'] == 'error' and len(calls) == 3, job.get('error')
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [d['code'] for d in diagnostics] == ['player_action_completion_invalid'] * 2
    assert Repository(repo.path).get_snapshot(sid) == before
