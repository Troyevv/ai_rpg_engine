"""Extraction/11 controls use the ordinary persistence and planning paths."""
import json
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import commitment_view
from backend.runtime_v3.long_term import plan
from backend.runtime_v3.models import ScheduledEvent
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.time_skip import TimeSkipRequest, plan_skip
from backend.services.provider_attempt import identity
from test_published_narrative263 import CONFIG, game
from test_life_social import state, snapshot

pytestmark = pytest.mark.extraction_current


def apply(world, proposal, turn=1):
    return StateResolver(world, 'Закончилась встреча.', 'Идём вместе.', turn_id=turn,
                         **resolver_options(world, 'Идём вместе.', contract_version=11)).resolve(proposal)


def test_unresolved_appointment_is_context_across_all_clocks():
    world = state()
    world['meta']['world_time'] = 1080
    world['scheduled_events']['tea'] = ScheduledEvent(
        id='tea', description='Чай', character_ids=['a'], interrupts=False, due_minute=1080).model_dump()
    request = TimeSkipRequest(1080, 1860, source='sleep')
    assert plan_skip(world, request, version=11)['actual_target'] == 1860
    interval = plan(snapshot(world), dict(amount=2, unit='weeks'), version=11)
    assert interval.actual_target == interval.requested_target
    from backend.runtime_v3.long_term import run
    advanced, _, report = run(snapshot(world), dict(amount=2,unit='weeks'), config={'_extraction_contract':11})
    assert advanced['world_state']['meta']['world_time'] == interval.requested_target
    assert advanced['world_state']['scheduled_events']['tea'] == world['scheduled_events']['tea']
    assert report['llm_calls'] == 0
    after = apply(world, {'scene': {'end_time': {'day_offset': 1, 'time': '07:00'}}}).state
    assert after['meta']['world_time'] == 1860
    tea = after['scheduled_events']['tea']
    assert tea == world['scheduled_events']['tea']
    assert commitment_view(after, tea)['temporal_projection']['relevance'] == 'overdue'


def test_one_endpoint_across_publication_extraction_and_reload(game):
    repo, sid = game
    snap = repo.get_snapshot(sid)
    before = snap['world_state']
    start = (before['meta']['world_time'] // 1440 + 1) * 1440 + 553
    before['meta']['world_time'] = start
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    camera = before['camera']
    origin = camera['location_id']
    dest = next(loc for loc in before['locations'] if loc != origin)
    cast = camera['present_character_ids']
    prose = 'В семь вечера они дошли до сквера.'
    jid = repo.begin_job(sid, 'Идём вместе.', 'turn', CONFIG)

    def stream(**kw):
        stage = identity()['stage']
        if stage == 'remote_initiative':
            yield '{"action":null}'
        elif stage == 'world_simulation':
            yield 'На улице было тихо.'
        elif stage == 'world_simulation_delta':
            yield '{}'
        elif stage == 'narrative':
            yield json.dumps(dict(scene=prose, actions=[], ending=dict(elapsed_minutes=480)))
        elif stage == 'extraction':
            fresh = Repository(repo.path)
            turn = fresh.list_turns(sid)[-1]
            assert turn['assistant_text'] == prose
            assert json.loads(turn['changes_json'])['interpretation'] == 'pending'
            assert fresh.get_snapshot(sid)['world_state']['meta']['world_time'] == start
            yield json.dumps(dict(scene=dict(end_time=dict(day_offset=0,time='19:00'),
                                             ending=dict(location_id=origin,present_ids=cast)),
                                  scene_steps=[dict(kind='movement',actor_ids=cast,endpoint=dest)]))
        else:
            raise AssertionError(stage)

    with patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker(epoch=0, api_key='offline'))
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    after = Repository(repo.path).get_snapshot(sid)['world_state']
    assert after['meta']['world_time'] == start + 587
    assert after['camera']['location_id'] == dest
    assert all(after['characters'][cid]['location_id'] == dest for cid in cast)
    changes = json.loads(repo.list_turns(sid)[-1]['changes_json'])
    assert 'ending_disagrees_with_route' in {r['code'] for r in changes['interpretation_warnings']}


def test_observers_follow_replaced_and_concurrent_phases():
    from backend.runtime_v3.residence import visible_social_state
    world = state()

    def job(title, **extra):
        return dict(kind='employment', actor_id='b', title=title, perceived_by=['b'], **extra)
    world = apply(world, dict(role_changes=[job('Архивариус')])).state
    result = apply(world, dict(role_changes=[job('Хранитель', replaces='current')],
                               residence_changes=[dict(actor_ids=['a','b'], location_id='home',
                                                       perceived_by=['a','missing'])]), 2)
    assert 'invalid_phase_recipient' in {w['code'] for w in result.warnings}
    world = apply(result.state, dict(role_changes=[job('Лектор')]), 3).state
    known = visible_social_state(world, 'b')
    assert {(r['label'],r['status']) for r in known['roles']} == {
        ('Архивариус','closed'), ('Хранитель','active'), ('Лектор','active')}
    assert not known['residences']
    assert {r['actor_id'] for r in visible_social_state(world,'a')['residences']} == {'a','b'}
    assert visible_social_state(world,'c') == {'residences':[], 'roles':[]}


def test_relation_observer_sees_established_divorce_only():
    from backend.runtime_v3.kinship import visible_relations
    world = state()
    pair = dict(source_id='b', target_id='c')
    world = apply(world, dict(social_relation_changes=[dict(**pair, kind='spouse', perceived_by=['d'])])).state
    world = apply(world, {}, 2).state
    assert next(iter(world['objective_relations'].values()))['status'] == 'active'
    world = apply(world, dict(social_relation_changes=[dict(**pair, kind='divorce', perceived_by=['d'])]), 3).state
    marriage, = world['objective_relations'].values()
    assert marriage['status'] == 'closed'
    assert {row['fact_id'] for row in world['knowledge'].values() if row['actor_id']=='d'} == {
        marriage['fact_id'],marriage['closure_fact_id']}
    assert not visible_relations(world,'a')


def test_assembled_prompts_and_actor_owned_experience():
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.narrative_frame import AUTHOR_FORMAT, RECORDED_FORMAT
    from backend.services.structured_extraction import request_schema
    from test_narrative_choices import initial
    snap = initial()
    style = 'Короткие диалоги, мягкий юмор.'
    prompts = {'game_system_prompt.md': {'content': style}}
    for turn in range(1,4):
        snap['world_state'] = apply(snap['world_state'], dict(development_evidence=[
            dict(actor_id='b', meaning='Выслушал ученика.', theme='listen', perceived_by=['a'],
                 develops=dict(field='habits',text='Даёт собеседнику договорить.'))]), turn).state
    args = (snap, [], 'Молчу.', 'turn', 65536, 4096)
    narrative = build_context(*args, prompts=prompts)
    extraction = build_context(*args, prompts=prompts, extraction_text='Тимур выслушал ученика.')
    assert AUTHOR_FORMAT in narrative[0]['content'] and style in str(narrative)
    assert 'accepted Runtime involuntary consequences' not in str(narrative)
    assert 'need canonical Condition/Life State' not in str(narrative)
    assert 'End prose/choices' not in str(extraction)
    assert 'Даёт собеседнику договорить.' in str(narrative)
    evidence = next(m for m in narrative if m['content'].startswith('Наблюдавшийся опыт'))
    owners = json.loads(evidence['content'].split('\n',1)[1])
    assert list(owners) == ['b'] and len(owners['b']) == 3
    schema = request_schema(extraction)['properties']
    assert 'end_time' in schema['scene']['properties']
    assert 'closure_fact_id' not in schema['role_changes']['items']['properties']
    assert 'perceived_by' in schema['role_changes']['items']['properties']
    recorded = build_context(*args, extraction_contract=10, prompts=prompts)
    assert json.loads(recorded[-1]['content'].split('\n',1)[1])['response_format'].startswith(RECORDED_FORMAT)
    assert prompts['game_system_prompt.md']['content'] == style


def test_legacy_regeneration_keeps_version_and_original_context(game, monkeypatch):
    from test_published_narrative263 import play
    repo, sid = game
    with monkeypatch.context() as old:
        old.setattr('backend.runtime_v3.player_actions.EXTRACTION_VERSION', 10)
        first = play(repo, sid, 'Открыто окно.', '{}')
    turn = repo.list_turns(sid)[-1]
    jid = repo.begin_job(sid, '', 'regenerate', dict(CONFIG, target_turn_id=turn['id']))
    regen = repo.get_job(jid)
    assert json.loads(regen['config_json'])['_extraction_contract'] == 10
    assert regen['context_json'] == first['context_json']
    assert json.loads(regen['config_json'])['_prompts'] == json.loads(first['config_json'])['_prompts']


def test_malformed_inline_action_does_not_consume_following_actions():
    from backend.runtime_v3.narrative_frame import read, menu
    raw = '{"scene":"Листок лежит на столе.","actions":[{"text":"Прочитать"},{"text":},{"text":"Отойти"}]}'
    prose, frame = read(raw, complete=True)
    choices, warnings = menu(frame, state())
    assert prose == 'Листок лежит на столе.'
    assert [c['action'] for c in choices] == ['Прочитать','Отойти']
    assert warnings[0]['received'] == 3 and warnings[0]['available'] == 2


def test_free_text_target_is_a_hint_and_structured_skip_keeps_its_bound():
    from backend.runtime_v3.time_skip import interpreted_skip
    world = state()
    start = world['meta']['world_time']
    for source, expected in [('sleep',90), ('manual',60)]:
        request = TimeSkipRequest(start, start+60, source=source)
        planned = plan_skip(world, request, version=11)
        assert interpreted_skip(world, request, planned, 90)['elapsed_minutes'] == expected
        stopped = interpreted_skip(world, request, planned, 20)
        assert stopped['elapsed_minutes'] == 20 and stopped['interrupted']
        assert stopped['interruption_event_id'] is None


def test_shared_final_leg_adds_new_companion_without_moving_observer():
    world = state()
    for lid in ('station','park'):
        world['locations'][lid] = dict(world['locations']['home'], id=lid, name=lid)
    world['characters']['c']['location_id'] = 'station'
    result = apply(world, dict(scene=dict(observed_character_ids=['b']),scene_steps=[
        dict(kind='movement',actor_ids=['a'],endpoint='station'),
        dict(kind='movement',actor_ids=['a','c'],endpoint='park')]))
    assert result.state['camera']['present_character_ids'] == ['a','c']
    assert result.state['camera']['observed_character_ids'] == ['b']
    assert result.state['characters']['b']['location_id'] == 'home'
    assert len(result.history['movements']) == 3
