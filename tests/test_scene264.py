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
