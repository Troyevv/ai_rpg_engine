"""#209: the pregnancy process, its calendar reminder and the committed clock."""
from copy import deepcopy
import json

import pytest
import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import age_on, current_time, profile_of
from backend.runtime_v3.continuity import compression_limit
from backend.runtime_v3.context import build_context
from backend.runtime_v3.long_term import run, plan
from backend.runtime_v3.models import ScheduledEvent
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.time_skip import plan_skip, TimeSkipRequest
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG
from pregnancy_boundary_fixture import REACTION, DELIVERY, delivery_claim
from test_reproduction import conceive, snap
from test_temporal_guard import run as ordinary

REQUEST = dict(amount=2, unit='weeks', max_llm_calls=0)


@pytest.mark.parametrize(('actor', 'present'), [
    ('a', True), ('b', False), ('b', True), ('c', False), ('c', True),
], ids=['mother', 'father-alone', 'father-with-mother', 'observer-alone', 'observer-with-mother'])
@pytest.mark.parametrize('offset', [60, 0, -60], ids=['future', 'due', 'overdue'])
def test_boundary_matrix(actor, present, offset):
    state = conceive().state
    p = next(iter(state['pregnancies'].values()))
    now = p['due_minute'] - offset
    state['meta']['world_time'] = now
    state['camera'].update(controlled_actor_id=actor,
                           present_character_ids=sorted({actor} | ({'a'} if present else set())))
    before = deepcopy(state)
    snapshot = snap(state)
    after, history, report = run(snapshot, REQUEST)
    candidate = next(c for c in plan(snapshot, REQUEST).candidates if c.kind == 'birth')
    parent = actor in ('a', 'b')
    target = max(now, p['due_minute']) if parent else now + 14*1440
    assert state == before
    assert report['actual_target'] == after['world_state']['meta']['world_time'] == target
    assert report['interruption'] == (dict(kind='pregnancy_due', minute=target, source_id=p['id']) if parent else None)
    assert candidate.requires_player == parent
    assert dict(id=candidate.id, reason='player_decision' if parent else 'budget') in report['unresolved']
    assert history['state_changes'][-1]['report'] == report
    assert after['world_state']['pregnancies'][p['id']]['status'] == 'due'
    assert after['world_state']['characters'].keys() == state['characters'].keys()
    assert after['world_state']['knowledge'] == state['knowledge']
    assert not history['events']
    assert plan_skip(state, TimeSkipRequest(now, now+120))['actual_target'] == (target if parent else now+120)
    actors = set(state['camera']['present_character_ids']) | {actor}
    assert compression_limit(state, actors, 120)['max_minutes'] == (max(0,offset) if parent or present else 120)


@pytest.mark.parametrize('calendar_status', ['missing', 'resolved', 'pending'])
def test_legacy_reminder_cannot_hide_or_discharge_a_process(calendar_status):
    state = conceive().state
    p = next(iter(state['pregnancies'].values()))
    state['meta']['world_time'] = p['due_minute']
    # Gestational participant need not be an established legal/social parent.
    p['parent_ids'] = ['b']
    if calendar_status == 'missing':
        del state['scheduled_events'][p['id']]
    else:
        state['scheduled_events'][p['id']].update(status=calendar_status, due_minute=p['due_minute']+1440)
    projection = plan(snap(state), REQUEST)
    assert projection.actual_target == p['due_minute']
    assert next(c.actor_ids for c in projection.candidates if c.kind=='birth') == ('a', 'b')
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(state, 'Тихо.', '').resolve(dict(player_agency=dict(status='preserved', actions=[]), final_scene=dict(location_id='home',
            present_character_ids=['a','b'], elapsed_minutes=1)))
    assert exc.value.code == 'ordinary_temporal_boundary'


def test_earliest_cause_wins_and_future_decisions_do_not_enter_history():
    state = conceive().state
    p = next(iter(state['pregnancies'].values()))
    state['camera']['controlled_actor_id'] = 'b'
    state['scheduled_events']['meeting'] = ScheduledEvent(id='meeting', description='Встреча',
        character_ids=['b'], due_minute=p['due_minute']-10).model_dump()
    after, hist, report = run(snap(state), REQUEST)
    assert report['interruption']['source_id'] == 'meeting'
    assert hist['state_changes'][-1]['minute'] == p['due_minute']-10
    assert after['world_state']['pregnancies'][p['id']]['status'] == 'active'
    assert all(c['kind'] != 'birth' for c in report['decisions'])


def test_background_group_cannot_deliver_a_player_required_birth():
    state = conceive().state
    state['camera']['controlled_actor_id'] = 'b'
    process = next(iter(state['pregnancies'].values()))
    state['scheduled_events']['visit'] = ScheduledEvent(id='visit', description='Визит',
        character_ids=['a'], due_minute=process['due_minute']).model_dump()
    snapshot = snap(state)
    request = dict(REQUEST, max_llm_calls=2)
    visit = next(c for c in plan(snapshot, request).candidates if c.source_id == 'visit')
    text = 'Роды завершились.'
    raw = dict(player_agency=dict(status='preserved', actions=[]), final_scene=dict(location_id='home', present_character_ids=['a'], elapsed_minutes=0),
        events=[dict(id='visit', text=text, evidence=text, participants=['a'], witnesses=['a'],
                     advance_candidate_ids=[visit.id])],
        births=[dict(pregnancy_id=process['id'], source_event_id='visit',
                     assertion='birth_completed', location_id='home', evidence=text)])
    def generate(stage, *args, **kwargs):
        yield json.dumps(raw) if stage == 'long_term_extraction' else text
    after, history, report = run(snapshot, request, generate=generate)
    assert report['llm_calls'] == 2 and not report['accepted']
    assert report['diagnostics'][0]['message'] == 'Рождение не входит в причины выбранной фоновой группы.'
    assert not history['events']
    assert after['world_state']['pregnancies'][process['id']]['status'] == 'due'
    assert after['world_state']['knowledge'] == state['knowledge']
    assert after['world_state']['characters'] == state['characters']


def test_pregnancy_job_continuation_lineage_and_knowledge(tmp_path):
    repo = Repository(tmp_path/'family.sqlite')
    sid = load_fixture(repo, 'pregnancy')['save']
    def advance(kind='long_term'):
        job = repo.begin_job(sid, '', kind, dict(CONFIG, long_term_advance=REQUEST))
        engine.run_job(repo.path, job, engine.Worker())
        assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
        return repo.get_snapshot(sid)
    def history(snapshot):
        with repo.connect() as db:
            return read_history(db,snapshot['history_head'])[0]

    before = repo.get_snapshot(sid)
    p = next(iter(before['world_state']['pregnancies'].values()))
    child = p['children'][0]['id']
    stopped = advance()
    state = stopped['world_state']
    assert state['meta']['world_time'] == p['due_minute']
    assert state['scheduled_events'][p['id']]['status'] == 'pending'
    assert state['knowledge'] == before['world_state']['knowledge']
    assert child not in state['characters']
    assert advance('regenerate')['world_state'] == state
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    advance()
    reaction = 'Я остаюсь рядом с Верой.'
    # The player may respond without resolving the process or advancing time.
    assert ordinary(repo,sid,0,player_input=reaction,text='Вера кивает.')[0]['status']=='saved'
    pending = repo.get_snapshot(sid)
    assert pending['world_state']['meta']['world_time'] == p['due_minute']
    assert pending['world_state']['pregnancies'][p['id']]['status'] == 'due'
    director = next(m['content'] for m in build_context(pending,[],reaction,'turn',65536,2000)
                    if m['content'].startswith('Director / GM-only'))
    assert p['id'] not in director

    extra = delivery_claim(p, state['camera'])
    def deliver(kind):
        job,_ = ordinary(repo,sid,1,player_input=REACTION,text=DELIVERY,extra=extra,kind=kind,
                         config=dict(CONFIG, context_length=65536))
        assert job['status']=='saved',job['error']
        return repo.get_snapshot(sid)
    born = deliver('turn')
    world = born['world_state']
    assert world['pregnancies'][p['id']]['birth_minute'] == p['due_minute']
    assert world['scheduled_events'][p['id']]['status'] == 'resolved'
    assert world['characters'][child]['birth_date'] == current_time(state)['date']
    assert world['characters']['qa_kirill'] == state['characters']['qa_kirill']
    assert not world['naming_decisions']
    assert not any(k['actor_id']=='qa_oleg' and k['fact_id']==p['fact_id'] for k in world['knowledge'].values())
    assert sum(r.get('kind')=='birth' for r in history(born)['state_changes']) == 1
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == born
    assert deliver('regenerate')['world_state'] == world
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == pending
    born = deliver('turn')
    after = advance()
    world = after['world_state']
    assert after['last_long_term_advance']['interruption'] is None
    assert world['meta']['world_time'] == p['due_minute']+1+14*1440
    assert world['characters'][child]['birth_provenance'] == born['world_state']['characters'][child]['birth_provenance']
    assert age_on(world['characters'][child]['birth_date'],current_time(world)['date'],profile_of(world)) == 0
    assert sum(r.get('kind')=='birth' for r in history(after)['state_changes']) == 1
