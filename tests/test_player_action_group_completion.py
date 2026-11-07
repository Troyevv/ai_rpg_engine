"""One reviewed action can be witnessed by several independently valid Events."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.raw import extraction_schema
from test_api import api
from test_event_presence import crisis, history, NINA, VERA
from test_player_action_targets import claim, payload, play, saved_events, MARINA
from test_narrative_test_world import CONFIG, ordinary_job

ASYA = 'qa_asya'
QUOTE = 'По очереди спрашиваю Марину и Асю о Кирилле.'
TEXT = 'Нина спрашивает Марину, затем обращается с тем же вопросом к Асе.'


def group(state, *, marker=False, split=True, targets=None):
    targets = [MARINA, ASYA] if targets is None else targets
    raw = payload(state, [claim(targets, quote=QUOTE)], completed=marker)
    if split:
        template = raw['events'][0]
        raw['events'] = [dict(deepcopy(template), id=f'part-{i}', target_ids=[target],
                              participants=[NINA, target]) for i, target in enumerate(targets)]
    return raw


@pytest.mark.parametrize('marker', [False, True])
@pytest.mark.parametrize('split', [False, True])
def test_one_action_completed_by_one_or_several_events(crisis, marker, split):
    from jsonschema import Draft202012Validator
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = group(before['world_state'], marker=marker, split=split)
    Draft202012Validator(extraction_schema()).validate(raw)
    job, calls = play(crisis, [raw, raw], QUOTE, TEXT)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    events = saved_events(repo, sid)[-len(raw['events']):]
    assert [e['target_ids'] for e in events] == [e['target_ids'] for e in raw['events']]
    assert all(e['player_action']['narrative_target_ids'] == [MARINA, ASYA] for e in events)
    assert all(bool(e.get('player_interaction')) == marker for e in events)
    assert Repository(repo.path).get_snapshot(sid)['world_state']['knowledge'] == before['world_state']['knowledge']


def test_split_events_with_global_targets_cannot_claim_every_recipient(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = group(before['world_state'])
    for event in raw['events']:
        event['target_ids'] = [MARINA, ASYA]
    job, calls = play(crisis, [raw, raw], QUOTE, TEXT)
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('fault', ['missing', 'duplicate_target', 'bystander', 'substituted',
                                  'missing_link', 'wrong_actor', 'unavailable', 'hidden_unavailable'])
def test_only_valid_event_targets_cover_an_action_atomically(crisis, fault):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    turns = repo.list_turns(sid)
    variants = repo.variants(turns[-1]['node_id'])
    raw = group(before['world_state'])
    if fault == 'missing':
        raw['events'].pop()
    elif fault == 'duplicate_target':
        raw['events'][1].update(target_ids=[MARINA], participants=[NINA, MARINA])
    elif fault == 'bystander':
        raw['events'].pop()
        raw['events'][0]['participants'].append(ASYA)
    elif fault == 'substituted':
        raw['events'][1].update(target_ids=['qa_zoya'], participants=[NINA, 'qa_zoya'])
    elif fault == 'missing_link':
        raw['events'][1].pop('player_action_id')
    elif fault == 'wrong_actor':
        raw['events'][1]['actor_id'] = ASYA
    else:
        raw = group(before['world_state'], targets=[MARINA, VERA])
        if fault == 'hidden_unavailable':
            raw['events'][1]['participants'] = [NINA]
    raw['facts'] = [dict(id='group-news', text='Нина принесла документы.', visibility='secret')]
    raw['events'][0].update(fact_ids=['group-news'], witnesses=[NINA, MARINA])
    raw['knowledge_gained'] = [dict(actor_id=MARINA, fact_id='group-news', source_event_id='part-0')]
    job, calls = play(crisis, [raw, raw], QUOTE, TEXT)
    assert job['status'] == 'error' and len(calls) == 3
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(sid) == before and fresh.list_turns(sid) == turns
    assert fresh.variants(turns[-1]['node_id']) == variants
    assert history(fresh, before) == history(repo, before)
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    if fault in ('missing', 'duplicate_target', 'bystander'):
        assert diagnostics[-1]['code'] == 'player_action_completion_invalid'
        assert ASYA in diagnostics[-1]['source_ids']


@pytest.mark.parametrize('split', [False, True])
def test_partial_group_preserves_unreached_intended_target(crisis, split):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    actual = [MARINA, ASYA] if split else [MARINA]
    raw = group(before['world_state'], targets=actual, split=split)
    raw['player_agency']['actions'][0].update(outcome='partial', target_ids=[*actual, VERA])
    job, calls = play(crisis, [raw], QUOTE, 'Нина спрашивает Марину. Веры здесь нет.')
    assert job['status'] == 'saved' and len(calls) == 2
    events = saved_events(repo, sid)[-len(raw['events']):]
    assert set().union(*(set(e['target_ids']) for e in events)) == set(actual)
    assert all(e['player_action']['target_ids'] == [*actual, VERA] for e in events)
    assert all(e['player_action']['outcome'] == 'partial' for e in events)
    assert Repository(repo.path).get_snapshot(sid)['world_state']['knowledge'] == before['world_state']['knowledge']


@pytest.mark.parametrize('repair', [True, False])
def test_group_coverage_repair_preserves_narrative_and_original_lineage(crisis, repair):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    good = group(before['world_state'])
    bad = deepcopy(good)
    bad['events'].pop()
    job, calls = play(crisis, [bad, good if repair else bad], QUOTE, TEXT)
    assert len(calls) == 3 and job['narrative'] == TEXT
    assert ASYA in calls[-1]['messages'][0]['content']
    if not repair:
        assert job['status'] == 'error' and Repository(repo.path).get_snapshot(sid) == before
        return
    assert job['status'] == 'saved', job.get('error')
    accepted = Repository(repo.path).get_snapshot(sid)
    turn = repo.list_turns(sid)[-1]
    sibling, _ = play(crisis, [good], '', TEXT, 'regenerate')
    assert sibling['status'] == 'saved'
    assert repo.get_job(sibling['id'])['context_json'] == repo.get_job(job['id'])['context_json']
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid) == accepted
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('fault', [None, 'cross_coverage', 'wrong_quote', 'wrong_action'])
def test_group_and_independent_action_keep_separate_provenance(crisis, fault):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = group(before['world_state'], marker=True)
    second_quote = 'Прошу Асю принести фотографии.'
    second = payload(before['world_state'], [claim([ASYA], quote=second_quote, id='second')])
    raw['player_agency']['actions'] += second['player_agency']['actions']
    raw['events'] += second['events']
    if fault == 'cross_coverage':
        raw['events'].pop(1)
    elif fault == 'wrong_quote':
        raw['events'][1]['player_evidence'] = second_quote
    elif fault == 'wrong_action':
        raw['events'][1]['player_action_id'] = 'second'
    job, calls = play(crisis, [raw, raw], QUOTE + ' ' + second_quote, TEXT)
    if fault:
        assert job['status'] == 'error' and len(calls) == 3
        assert Repository(repo.path).get_snapshot(sid) == before
    else:
        assert job['status'] == 'saved' and len(calls) == 2
        assert [e['player_action']['id'] for e in saved_events(repo, sid)[-3:]] == ['input-1', 'input-1', 'second']
        assert [e['player_evidence'] for e in saved_events(repo, sid)[-3:]] == [QUOTE, QUOTE, second_quote]


@pytest.mark.parametrize('channel,valid', [('call', True), ('call', False), ('message', True), ('message', False)])
def test_group_uses_each_events_own_physical_or_remote_delivery(api, channel, valid):
    from devtools.narrative_test_world import load_fixture
    from test_phone122 import execute as answer_call
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone-office')['save']
    ordinary_job(repo, sid, 'start')
    quote = 'Спрашиваю Марину лично, а Веру по связи о Кирилле.'
    if channel == 'call':
        with patch('engine.launch'):
            response = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
                revision=repo.get_save(sid)['revision'], config=CONFIG,
                command=dict(action='call', contact_id='phone-qa_kirill-qa-vera', operation_id='group-call')))
        assert response.status_code == 200, response.text
        answer_call(repo, response.json()['job']['id'])
        if not valid:
            call, = repo.get_snapshot(sid)['world_state']['remote_events']
            response = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
                command=dict(action='end', event_id=call, operation_id='group-call-end')))
            assert response.status_code == 200, response.text
    else:
        response = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
            command=dict(action='send', character_id=VERA, content=quote, operation_id='group-send')))
        assert response.status_code == 200, response.text
    before = repo.get_snapshot(sid)
    state = before['world_state']
    actor = state['camera']['controlled_actor_id']
    raw = group(state, marker=True, targets=[MARINA, VERA])
    raw['player_agency']['actions'][0]['player_evidence'] = quote
    raw['movements'] = [dict(actor_id=MARINA, to_location_id=state['camera']['location_id'], order=1)]
    raw['final_scene']['present_character_ids'] = [actor, MARINA]
    for event in raw['events']:
        event.update(actor_id=actor, participants=[actor, *event['target_ids']], witnesses=[actor], player_evidence=quote, order=2)
    remote = raw['events'][1]
    if channel == 'call':
        remote['interaction_channel'] = 'call'
    else:
        remote.update(medium='message', author_id=actor)
        sent = next(e for e in state['remote_events'].values() if e['operation_id'] == 'group-send')
        assert sent['delivered_to'] == [VERA] and sent['read_by'] == []
        if valid:
            raw['remote_events'] = [dict(sender_id=actor, recipient_ids=[VERA], channel='TEXT_MESSAGE',
                existing_event_id=sent['id'], source_event_id=remote['id'])]
    job, calls = play((client, repo, sid), [raw, raw], quote, 'Марина вошла. Игрок задал ей вопрос лично, а Вере по связи.')
    assert job['status'] == ('saved' if valid else 'error'), job.get('error')
    assert len(calls) == (2 if valid else 3) + (channel == 'message')
    fresh = Repository(repo.path).get_snapshot(sid)
    if valid:
        assert [e['target_ids'] for e in saved_events(repo, sid)[-2:]] == [[MARINA], [VERA]]
        assert fresh['world_state']['knowledge'] == before['world_state']['knowledge']
    else:
        assert fresh == before


@pytest.mark.parametrize('substituted', [False, True])
def test_continuity_uses_own_event_targets_not_group_bystanders(crisis, substituted):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    quote = 'Согласен помочь Марине и Асе с документами.'
    raw = group(before['world_state'], marker=True)
    raw['player_agency']['actions'][0]['player_evidence'] = quote
    for event in raw['events']:
        event.update(player_evidence=quote, evidence='Нина соглашается помочь.', participants=[NINA, MARINA, ASYA])
    raw['facts'] = [dict(id='group-basis', text='Документы принесены.', visibility='public')]
    raw['events'][0]['fact_ids'] = ['group-basis']
    raw['knowledge_gained'] = [dict(actor_id=NINA, fact_id='group-basis', source_event_id='part-0')]
    raw['continuity_beats'] = [dict(source_event_id='part-0', actor_id=NINA, decision_actor_id=NINA,
        target_ids=[ASYA if substituted else MARINA], basis_ids=['group-basis'], kind='decision',
        status='resolved', evidence='Нина соглашается.', player_evidence=quote)]
    job, calls = play(crisis, [raw, raw], quote, 'Нина соглашается помочь Марине, затем Асе.')
    assert job['status'] == ('error' if substituted else 'saved'), job.get('error')
    if substituted:
        assert len(calls) == 3 and Repository(repo.path).get_snapshot(sid) == before
        assert 'continuity_external_decision' in repo.get_job(job['id'])['repair_diagnostics_json']
    else:
        assert len(calls) == 2
        events = saved_events(repo, sid)[-2:]
        beat, = events[0]['continuity']
        assert beat['target_ids'] == [MARINA] and beat['source_event_id'] == events[0]['id']
