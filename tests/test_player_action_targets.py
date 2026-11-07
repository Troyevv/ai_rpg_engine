"""#232 Crisis/001 equivalent replay: scripted providers, real jobs/SQLite/history.

Original /workspace/work/live99-stage-c-retest-20261107 artifacts are unavailable.
The pre-change replay on 25c834b saved Marina as a completed Vera interaction (2
calls, +1 minute), including after reopening SQLite. No paid provider is used here.
"""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.raw import extraction_schema, prompt_schema
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_event_presence import crisis, history, ACTION, NINA, VERA
from test_api import api
from test_narrative_test_world import CONFIG

MARINA = 'qa_marina'
BAD_TEXT = 'Нина негромко окликает Марину: — Марина, доброе утро. Как Вера? И что с Кириллом — есть новости?'
ATTEMPT = 'Нина зовёт Веру. Ответа нет: Веры здесь нет. Марина поднимает голову.'
GOOD_TEXT = 'Нина спрашивает Марину о Кирилле и предлагает помощь.'
GOOD_INPUT = 'Спрашиваю Марину о Кирилле и предлагаю помощь.'


def claim(targets, *, quote=ACTION, actual=None, outcome='completed', id='input-1'):
    return dict(id=id, player_evidence=quote, target_ids=targets,
                narrative_target_ids=targets if actual is None else actual,
                outcome=outcome, meaning='preserved')


def payload(state, actions, *, completed=True):
    camera = state['camera']
    events = []
    for action in actions:
        targets = action['narrative_target_ids']
        participants = [NINA] + ([t for t in targets if t in state['characters'] and t != NINA]
                                 if action['outcome'] == 'completed' else [])
        event = dict(id='event-'+action['id'], text='Исход действия', medium='conversation',
                     participants=participants, witnesses=[NINA], actor_id=NINA,
                     target_ids=targets, player_action_id=action['id'])
        if completed:
            event.update(player_assertion='completed_interaction', player_evidence=action['player_evidence'])
        events.append(event)
    return dict(final_scene=dict(location_id=camera['location_id'],
                                present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
                player_agency=dict(status='preserved', actions=actions), events=events)


def play(crisis, responses, text=GOOD_INPUT, narrative=GOOD_TEXT, kind='turn'):
    client, repo, sid = crisis
    jid = repo.begin_job(sid, text, kind, CONFIG)
    responses = iter(responses)
    calls = []
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(next(responses), ensure_ascii=False) if kw.get('response_format') else narrative
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return client.get('/api/jobs/'+jid).json(), calls


def saved_events(repo, sid):
    fresh = Repository(repo.path)
    return history(fresh, fresh.get_snapshot(sid))['events']


def test_original_crisis001_quote_is_not_completion_proof(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim([MARINA])])
    raw.pop('player_agency')
    event = raw['events'][0]
    for key in ('actor_id', 'target_ids', 'player_action_id'):
        event.pop(key)
    event.update(id='event_nina_asks_marina_help', text=GOOD_TEXT)
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(before['world_state'], BAD_TEXT, ACTION).resolve(raw)
    assert exc.value.code == 'player_action_event_mismatch'
    job, calls = play(crisis, [raw, raw], ACTION, BAD_TEXT)
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before
    assert all(not e.get('player_interaction') for e in saved_events(repo, sid))


@pytest.mark.parametrize('formal_event', [False, True])
def test_narrative_substitution_cannot_be_laundered_through_repair(crisis, formal_event):
    client, repo, sid = crisis
    before = repo.get_snapshot(sid)
    turns = repo.list_turns(sid)
    variants = repo.variants(turns[-1]['node_id'])
    raw = payload(before['world_state'], [claim([VERA], actual=[MARINA])])
    if formal_event:
        # A formally input-aligned Event does not fix the already written story.
        raw['events'][0].update(target_ids=[VERA], participants=[NINA, VERA])
    good = payload(before['world_state'], [claim([VERA], outcome='attempted')], completed=False)
    job, calls = play(crisis, [raw, good], ACTION, BAD_TEXT)
    assert job['status'] == 'error' and len(calls) == 2  # no futile extraction repair
    assert job['retry_allowed'] is False and job['narrative'] == BAD_TEXT
    fresh = Repository(repo.path)
    assert fresh.get_snapshot(sid) == before and fresh.list_turns(sid) == turns
    assert fresh.variants(turns[-1]['node_id']) == variants
    with patch('engine.chat_stream', side_effect=AssertionError('No paid retry')), patch('engine.launch') as launch:
        response = client.post('/api/jobs/'+job['id']+'/retry', json=dict(config=CONFIG))
        assert response.status_code == 409 and not launch.called
        response = client.post(f'/api/saves/{sid}/jobs/{job["id"]}/abandon', json=dict(
            revision=fresh.get_save(sid)['revision'], attempt_epoch=job['attempt_epoch']))
        assert response.status_code == 200 and response.json()['status'] == 'abandoned'
    assert fresh.get_snapshot(sid) == before
    assert fresh.get_job(job['id'])['user_text'] == ACTION
    recovered, calls = play(crisis, [good], ACTION, ATTEMPT)
    assert recovered['status'] == 'saved' and len(calls) == 2
    assert not saved_events(repo, sid)[-1].get('player_interaction')


@pytest.mark.parametrize('outcome', ['attempted', 'partial', 'deferred', 'not_performed'])
def test_uncompleted_actions_keep_targets_without_teleportation(crisis, outcome):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    actual = [] if outcome in ('deferred', 'not_performed') else [VERA]
    raw = payload(before['world_state'], [claim([VERA], actual=actual, outcome=outcome)], completed=False)
    job, calls = play(crisis, [raw], ACTION, ATTEMPT)
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    fresh = Repository(repo.path).get_snapshot(sid)
    event = saved_events(repo, sid)[-1]
    assert event['player_action']['target_ids'] == [VERA]
    assert event['player_action']['outcome'] == outcome and not event.get('player_interaction')
    assert fresh['world_state']['characters'][VERA] == before['world_state']['characters'][VERA]
    assert fresh['world_state']['knowledge'] == before['world_state']['knowledge']
    assert fresh['world_state']['remote_events'] == before['world_state']['remote_events']


@pytest.mark.parametrize('outcome', ['attempted', 'partial', 'deferred'])
def test_uncompleted_actions_cannot_claim_completion(crisis, outcome):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim([MARINA], quote=GOOD_INPUT, outcome=outcome)])
    job, calls = play(crisis, [raw, raw])
    assert job['status'] == 'error' and len(calls) == 3
    assert Repository(repo.path).get_snapshot(sid) == before
    diagnostics = json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])
    assert [d['code'] for d in diagnostics] == ['player_action_completion_invalid'] * 2


@pytest.mark.parametrize('corrected', [False, True])
def test_correct_narrative_wrong_extraction_bounded_repair(crisis, corrected):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    good = payload(before['world_state'], [claim([MARINA], quote=GOOD_INPUT)])
    bad = deepcopy(good)
    bad['events'][0].update(target_ids=['qa_zoya'], participants=[NINA, 'qa_zoya'])
    job, calls = play(crisis, [bad, good if corrected else bad])
    assert len(calls) == 3
    assert 'events[0].player_action_id' in calls[-1]['messages'][0]['content']
    assert job['status'] == ('saved' if corrected else 'error')
    if corrected:
        event = saved_events(repo, sid)[-1]
        assert event['player_interaction'] and event['target_ids'] == [MARINA]
        assert job['narrative'] == GOOD_TEXT and event['player_evidence'] == GOOD_INPUT
    else:
        assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('text,targets', [
    (GOOD_INPUT, [MARINA]),
    ('Мариш, расскажи, как Кирилл.', [MARINA]),
    ('Спрашиваю её о Кирилле.', [MARINA]),
    ('Марина и Ася, вы знаете, как Кирилл?', [MARINA, 'qa_asya']),
    ('Я сажусь за стол.', []),
])
def test_present_alias_pronoun_group_and_untargeted_actions(crisis, text, targets):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim(targets, quote=text)])
    raw['events'][0]['medium'] = 'conversation' if targets else 'action'
    job, calls = play(crisis, [raw], text, 'Нина выполняет выбранное действие.')
    assert job['status'] == 'saved', job.get('error')
    assert len(calls) == 2
    event = saved_events(repo, sid)[-1]
    assert event['player_interaction'] and event['target_ids'] == targets
    assert text in json.dumps(calls[1]['messages'], ensure_ascii=False)
    assert 'PLAYER ACTION AGENCY' in calls[0]['messages'][0]['content']
    assert 'PLAYER ACTION REVIEW' in calls[1]['messages'][0]['content']


@pytest.mark.parametrize('npc_text', ['Марина сама предлагает помочь.', 'Марина отвечает на вопрос, обращённый к Вере.'])
def test_independent_npc_response_is_not_a_player_action(crisis, npc_text):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim([VERA], outcome='attempted')], completed=False)
    raw['events'].append(dict(id='npc-response', text=npc_text, medium='conversation',
                              actor_id=MARINA, target_ids=[NINA], participants=[MARINA, NINA], witnesses=[NINA]))
    job, calls = play(crisis, [raw], ACTION, ATTEMPT+' '+npc_text)
    assert job['status'] == 'saved' and len(calls) == 2
    events = saved_events(repo, sid)[-2:]
    assert not any(e.get('player_interaction') for e in events)
    assert events[1]['text'] == npc_text and 'player_action' not in events[1]


def test_multiple_input_actions_remain_separate(crisis):
    _, repo, sid = crisis
    first, second = 'Спрашиваю Марину о Кирилле.', 'Предлагаю Зое помощь.'
    state = repo.get_snapshot(sid)['world_state']
    raw = payload(state, [claim([MARINA], quote=first), claim(['qa_zoya'], quote=second, id='input-2')])
    job, _ = play(crisis, [raw], first+' '+second)
    assert job['status'] == 'saved', job.get('error')
    events = saved_events(repo, sid)[-2:]
    assert [e['target_ids'] for e in events] == [[MARINA], ['qa_zoya']]
    assert [e['player_evidence'] for e in events] == [first, second]


@pytest.mark.parametrize('review', [None, {}, {'status':'uncertain','actions':[]}, {'status':'violated','actions':[]}])
def test_missing_or_unsafe_review_cannot_hide_prose_by_omitting_events(crisis, review):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [])
    raw['player_agency'] = review
    job, calls = play(crisis, [raw, raw], ACTION, BAD_TEXT)
    assert job['status'] == 'error'
    assert len(calls) == (2 if review and review.get('status') in ('violated', 'uncertain') else 3)
    assert Repository(repo.path).get_snapshot(sid) == before


def test_reload_regenerate_siblings_rollback_branching(crisis):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    raw = payload(before['world_state'], [claim([MARINA], quote=GOOD_INPUT)])
    first, _ = play(crisis, [raw])
    assert first['status'] == 'saved'
    saved = repo.get_snapshot(sid)
    accepted = history(repo, saved)
    turn = repo.list_turns(sid)[-1]
    failed = deepcopy(raw)
    failed['player_agency']['actions'][0]['narrative_target_ids'] = ['qa_zoya']
    job, _ = play(crisis, [failed], '', 'Нина обращается к Зое.', 'regenerate')
    assert job['status'] == 'error' and repo.get_snapshot(sid) == saved
    repo.abandon_job(sid, job['id'], repo.get_save(sid)['revision'], job['attempt_epoch'])
    sibling, calls = play(crisis, [raw], '', 'Нина вновь спрашивает Марину о Кирилле.', 'regenerate')
    assert sibling['status'] == 'saved'
    assert repo.get_job(sibling['id'])['context_json'] == repo.get_job(first['id'])['context_json']
    assert repo.get_job(sibling['id'])['user_text'] == GOOD_INPUT
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid) == saved
    assert history(repo, saved) == accepted
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    branch, _ = play(crisis, [raw])
    assert branch['status'] == 'saved'
    assert history(repo, saved) == accepted
    assert saved_events(repo, sid)[-1]['player_interaction']


def test_schema_has_resolvable_typed_review():
    from jsonschema import Draft202012Validator
    action = claim([MARINA], quote=GOOD_INPUT)
    data = dict(final_scene=dict(location_id=None, present_character_ids=[]),
                player_agency=dict(status='preserved', actions=[action]))
    for schema in (extraction_schema(), prompt_schema(player_agency_required=True)):
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(data)


@pytest.mark.parametrize('channel', ['active', 'closed', 'unavailable'])
def test_targeted_call_uses_only_existing_channel(api, channel):
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    from test_phone122 import execute as answer_call
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone-office')['save']
    ordinary_job(repo, sid, 'start')
    if channel != 'unavailable':
        with patch('engine.launch'):
            response = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
                revision=repo.get_save(sid)['revision'], config=CONFIG,
                command=dict(action='call', contact_id='phone-qa_kirill-qa-vera', operation_id='232-call')))
        assert response.status_code == 200, response.text
        answer_call(repo, response.json()['job']['id'])
        if channel == 'closed':
            call, = repo.get_snapshot(sid)['world_state']['remote_events']
            response = client.post(f'/api/saves/{sid}/phone', json=dict(
                revision=repo.get_save(sid)['revision'], command=dict(action='end', event_id=call, operation_id='232-end-call-operation')))
            assert response.status_code == 200, response.text
    before = repo.get_snapshot(sid)
    state = before['world_state']
    actor = state['camera']['controlled_actor_id']
    text = 'Вера, ты меня слышишь?'
    raw = payload(state, [claim([VERA], quote=text)])
    raw['events'][0].update(actor_id=actor, participants=[actor, VERA], witnesses=[actor], interaction_channel='call')
    job, calls = play((client, repo, sid), [raw, raw], text, 'Кирилл спрашивает Веру по телефону. Вера отвечает.')
    assert len(calls) == (2 if channel == 'active' else 3), job.get('error')
    if channel == 'active':
        assert job['status'] == 'saved', job.get('error')
        event = saved_events(repo, sid)[-1]
        assert event['player_interaction'] and event['target_ids'] == [VERA]
        assert event['interaction_channel'] == 'call'
    else:
        assert job['status'] == 'error'
        assert Repository(repo.path).get_snapshot(sid) == before
    assert repo.get_snapshot(sid)['world_state']['characters'][VERA]['location_id'] == state['characters'][VERA]['location_id']


@pytest.mark.parametrize('mutate,code', [
    (lambda raw: (raw['player_agency']['actions'][0].update(target_ids=['missing'], narrative_target_ids=['missing']),
                  raw['events'][0].update(target_ids=['missing'])), 'player_action_target_invalid'),
    (lambda raw: raw['player_agency']['actions'][0].update(player_evidence='Чужой ввод'), 'player_action_source_invalid'),
    (lambda raw: raw['events'][0].pop('player_action_id'), 'player_action_event_mismatch'),
    (lambda raw: raw['events'][0].update(actor_id=MARINA), 'player_action_event_mismatch'),
    (lambda raw: raw['events'][0].update(player_evidence=123), 'player_action_completion_invalid'),
])
def test_invalid_provenance_is_repairable_not_silently_dropped(crisis, mutate, code):
    _, repo, sid = crisis
    state = repo.get_snapshot(sid)['world_state']
    raw = payload(state, [claim([MARINA], quote=GOOD_INPUT)])
    mutate(raw)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, GOOD_TEXT, GOOD_INPUT).resolve(raw)
    assert error.value.code == code and error.value.repairable


def test_player_actor_cannot_omit_both_reference_and_completion_marker(crisis):
    _, repo, sid = crisis
    state = repo.get_snapshot(sid)['world_state']
    raw = payload(state, [claim([MARINA], quote=GOOD_INPUT)], completed=False)
    raw['events'][0].pop('player_action_id')
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, GOOD_TEXT, GOOD_INPUT).resolve(raw)
    assert error.value.code == 'player_action_event_mismatch'


def test_target_can_be_newly_promoted_character(crisis):
    from test_npc_review import promoted
    _, repo, sid = crisis
    raw = promoted(repo.get_snapshot(sid))
    raw.pop('relationship_changes')
    quote = 'Спрашиваю Ладу о мастерской.'
    action = claim(['new_npc'], quote=quote)
    raw['player_agency'] = dict(status='preserved', actions=[action])
    raw['events'][0].update(actor_id=NINA, target_ids=['new_npc'], player_action_id=action['id'],
                            player_assertion='completed_interaction', player_evidence=quote)
    job, calls = play(crisis, [raw], quote, 'Лада пришла. Нина спрашивает её о мастерской. Лада рассказала о мастерской.')
    assert job['status'] == 'saved', job.get('error')
    event, = [e for e in saved_events(repo, sid) if e.get('local_id') == 'meeting']
    assert event['player_interaction'] and event['target_ids'] == ['new_npc']
    assert len(calls) == 2


@pytest.mark.parametrize('substituted', [False, True])
def test_partial_group_action_can_reach_subset_but_never_replacement(crisis, substituted):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    quote = 'Спрашиваю Марину и Веру о Кирилле.'
    actual = ['qa_asya'] if substituted else [MARINA]
    raw = payload(before['world_state'], [claim([MARINA, VERA], quote=quote, actual=actual, outcome='partial')], completed=False)
    raw['events'][0]['participants'] = [NINA, *actual]
    text = 'Нина спрашивает Асю.' if substituted else 'Нина обращается к Марине и Вере. Марина слушает; Веры здесь нет.'
    job, calls = play(crisis, [raw], quote, text)
    assert len(calls) == 2
    if substituted:
        assert job['status'] == 'error' and not job['retry_allowed']
        assert Repository(repo.path).get_snapshot(sid) == before
    else:
        assert job['status'] == 'saved', job.get('error')
        event, = [e for e in saved_events(repo, sid) if e.get('local_id') == 'event-input-1']
        assert event['player_action']['outcome'] == 'partial'
        assert not event.get('player_interaction') and event['target_ids'] == [MARINA]
        assert Repository(repo.path).get_snapshot(sid)['world_state']['characters'][VERA] == before['world_state']['characters'][VERA]


@pytest.mark.parametrize('accepted', [True, False])
def test_new_object_target_requires_accepted_canonical_creation(crisis, accepted):
    _, repo, sid = crisis
    before = repo.get_snapshot(sid)
    state = before['world_state']
    quote = 'Рассматриваю старый атлас на столе.'
    text = 'Нина рассматривает старый атлас. На столе лежит старый атлас с картами.'
    raw = payload(state, [claim(['atlas232'], quote=quote)])
    raw['facts'] = [dict(id='atlas-fact', text='На столе лежит старый атлас с картами.',
                         character_ids=[NINA], evidence=text)]
    raw['events'][0].update(fact_ids=['atlas-fact'], text=text, medium='observation')
    raw['possession_deltas'] = [dict(item_id='atlas232', operation='introduce', expected_revision=0,
        updates=dict(owner_id=None, holder_id=None, location_id=state['camera']['location_id'], status='available'),
        assertion='completed_outcome', significance='continuity_required' if accepted else 'incidental',
        transition='established', source_event_id=raw['events'][0]['id'], fact_id='atlas-fact',
        name='Старый атлас', kind='book', evidence=text)]
    job, calls = play(crisis, [raw, raw], quote, text)
    if accepted:
        assert job['status'] == 'saved', job.get('error')
        assert len(calls) == 2
        assert 'atlas232' in Repository(repo.path).get_snapshot(sid)['world_state']['possessions']
        event, = [e for e in saved_events(repo, sid) if e.get('local_id') == 'event-input-1']
        assert event['player_interaction'] and event['target_ids'] == ['atlas232']
    else:
        assert job['status'] == 'error' and len(calls) == 3
        assert Repository(repo.path).get_snapshot(sid) == before
        assert 'player_action_target_invalid' in repo.get_job(job['id'])['repair_diagnostics_json']
