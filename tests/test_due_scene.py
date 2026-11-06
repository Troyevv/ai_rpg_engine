"""Offline Stage C Family replay through the recorded prompts and the real job transaction."""
import json
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.models import Knowledge
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.selectors import ui_view
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG as BASE_CONFIG, NARRATIVE
from test_reproduction import conceive, snap
from test_temporal_guard import run as ordinary

HELP = 'Я остаюсь рядом с Верой и держу её за руку, пока она рожает. Жду указаний врача.'
OBSERVE = 'Я наблюдаю и не вмешиваюсь.'
SIGNS = 'Пальцы Веры сжимаются вокруг протянутой руки. Ещё одна потуга.'
DELIVERY = 'Вера родила. Слышен первый крик.'
AWAY = 'В комнате тихо. За окном шелестят ветки.'
REQUEST = dict(amount=2, unit='weeks', max_llm_calls=4)
CONFIG = dict(BASE_CONFIG, context_length=65536)


def block(messages, name):
    return json.loads(next(m['content'].split('\n', 1)[1] for m in messages
                           if m['content'].startswith(name + '\n')))


def provider(**kwargs):
    """Respond to the supplied scene direction. Extraction sees only its own wire request."""
    messages = kwargs['messages']
    state = block(messages, 'Текущее состояние / GM-only')
    camera = state['camera']
    action = block(messages, 'Текущий ввод')['player_input']
    if not kwargs.get('response_format'):
        if action.startswith('Фоновая симуляция:') and 'потуги' in action:
            yield DELIVERY
            return
        scene = block(messages, 'Director / GM-only').get('immediate_scene')
        if scene and 'qa_vera' in scene['observable_actor_ids']:
            yield SIGNS if action == HELP else DELIVERY
        else:
            yield AWAY if scene else NARRATIVE
        return
    narrative = block(messages, 'completed_narrative')
    births = state.get('pregnancies', [])
    # An unrelated 1-minute map scene reproduces the original failed delta.
    minutes = int(narrative == NARRATIVE and block(messages, 'Текущий ввод')['kind'] != 'background')
    raw = dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'], elapsed_minutes=minutes))
    if narrative in (SIGNS, DELIVERY):
        mother = next(p for p in births if p['gestational_actor_id'] in camera['present_character_ids'])
        witnesses = camera['present_character_ids']
        raw['events'] = [dict(id='observed', text=narrative, evidence=narrative, medium='observation',
            participants=[mother['gestational_actor_id']], witnesses=witnesses)]
        if narrative == DELIVERY:
            raw['births'] = [dict(pregnancy_id=mother['id'], source_event_id='observed',
                assertion='birth_completed', location_id=camera['location_id'], evidence=narrative)]
    yield json.dumps(raw, ensure_ascii=False)


def job(repo, sid, kind, action='', **config):
    jid = repo.begin_job(sid, action, kind, dict(CONFIG, **config))
    with patch('engine.chat_stream', side_effect=provider), patch('engine.find_loaded_model', return_value={'config': {}}):
        engine.run_job(repo.path, jid, engine.Worker())
    result = repo.get_job(jid)
    assert result['status'] == 'saved', result['error']
    return repo.get_snapshot(sid), list(reversed(repo.request_log(job_id=jid)))


@pytest.mark.parametrize('remote', [False, True], ids=['at-bedside', 'elsewhere'])
def test_stage_c_from_lta_to_next_turn(tmp_path, remote):
    repo = Repository(tmp_path/'game.sqlite')
    sid = load_fixture(repo, 'pregnancy')['save']
    start = repo.get_snapshot(sid)['world_state']
    p, = start['pregnancies'].values()
    child, = p['children']
    if remote:
        cam = start['camera']
        target = next(lid for lid in start['locations'] if lid != cam['location_id'])
        move = dict(actor_id='qa_vera', to_location_id=target, evidence='Вера вышла.')
        result, _ = ordinary(repo,sid,0,text=move['evidence'],extra=dict(movements=[move],
            final_scene=dict(location_id=cam['location_id'], elapsed_minutes=0,
                             present_character_ids=[c for c in cam['present_character_ids'] if c!='qa_vera'])))
        assert result['status'] == 'saved', result['error']
    stopped, _ = job(repo,sid,'long_term',long_term_advance=REQUEST)
    state = stopped['world_state']
    report = stopped['last_long_term_advance']
    assert report['actual_target'] == state['meta']['world_time'] == p['due_minute'] == 1980
    assert report['requested_target'] == 20700 and report['max_llm_calls'] == 4
    assert state['pregnancies'][p['id']]['status'] == 'due' and child['id'] not in state['characters']
    assert state['knowledge'] == start['knowledge']
    view = ui_view(stopped)['last_long_term_advance']
    assert 'pregnancy_due' not in str(view) and p['id'] not in str(view)

    if not remote:
        observed, calls = job(repo,sid,'turn',HELP)
        assert [c['stage'] for c in calls] == ['narrative', 'extraction']
        assert calls[0]['response_text'] == SIGNS
        assert p['id'] not in str(calls[0]['messages'])
        assert 'At the due birth boundary' in str(calls[1]['messages'])
        assert observed['world_state']['knowledge'] == state['knowledge']
        assert observed['world_state']['pregnancies'][p['id']]['status'] == 'due'
        assert observed['world_state']['meta']['world_time'] == 1980
    born, calls = job(repo,sid,'turn',OBSERVE)
    assert calls[0]['response_text'] == (AWAY if remote else DELIVERY)
    if remote:
        assert [c['stage'] for c in calls] == ['narrative','extraction','world_simulation','world_simulation_delta']
        assert not block(calls[0]['messages'], 'Director / GM-only')['immediate_scene']['observable_actor_ids']
    world = born['world_state']
    assert world['pregnancies'][p['id']]['birth_minute'] == world['meta']['world_time'] == 1980
    assert world['scheduled_events'][p['id']]['status'] == 'resolved'
    assert world['characters'][child['id']]['developmental_stage'] == 'infant'
    assert {r['source_id'] for r in world['objective_relations'].values()
            if r['kind'] == 'parent' and r['target_id'] == child['id']} == set(p['parent_ids'])
    assert ('qa_kirill:'+p['fact_id'] in world['knowledge']) == (not remote)
    assert 'qa_vera:'+p['fact_id'] in world['knowledge']
    assert all(k['fact_id'] not in p['sex_fact_ids'].values() for k in world['knowledge'].values())
    with repo.connect() as db:
        history, _ = read_history(db, born['history_head'])
    births = [row for row in history['state_changes'] if row.get('kind') == 'birth']
    assert len(births) == 1
    assert sum(e['text'] == DELIVERY for e in history['events']) == 1
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == born
    first = repo.list_turns(sid)[-1]
    sibling, _ = job(repo, sid, 'regenerate')
    assert sibling['world_state'] == world
    repo.select_variant(sid, first['id'], first['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == born
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == (stopped if remote else observed)
    branch, _ = job(repo, sid, 'turn', OBSERVE)
    assert branch['world_state'] == world
    following, calls = job(repo,sid,'turn','Осматриваюсь.')
    assert following['world_state']['meta']['world_time'] == 1981
    if remote:
        assert DELIVERY not in str(calls[0]['messages'])
        assert child['id'] not in str(calls[0]['messages'])
    later, _ = job(repo,sid,'long_term',long_term_advance=REQUEST)
    assert later['last_long_term_advance']['interruption'] is None
    assert later['world_state']['meta']['world_time'] == 1981+14*1440


def test_failed_stage_c_delta_and_retry_leave_checkpoint_intact(tmp_path):
    repo = Repository(tmp_path/'retry.sqlite')
    sid = load_fixture(repo, 'pregnancy')['save']
    stopped, _ = job(repo, sid, 'long_term', long_term_advance=REQUEST)
    turns = repo.list_turns(sid)
    retry = None
    for _ in range(2):
        failed, _ = ordinary(repo, sid, 1, text=NARRATIVE, player_input=HELP, config=CONFIG, retry=retry)
        assert failed['status'] == 'error'
        assert json.loads(failed['repair_diagnostics_json'])[-1]['code'] == 'ordinary_temporal_boundary'
        assert repo.get_snapshot(sid) == stopped
        assert repo.list_turns(sid) == turns
        retry = failed['id']


def test_witness_can_learn_about_pregnancy_before_birth(tmp_path):
    repo = Repository(tmp_path/'discovery.sqlite')
    sid = load_fixture(repo, 'pregnancy')['save']
    stopped, _ = job(repo, sid, 'long_term', long_term_advance=REQUEST)
    p, = stopped['world_state']['pregnancies'].values()
    exam = 'При осмотре беременность подтвердилась. Кирилл слышал заключение.'
    event = dict(id='exam', text=exam, participants=['qa_vera'], witnesses=['qa_vera', 'qa_kirill'],
                 medium='discovery', fact_ids=[p['fact_id']], evidence=exam)
    result, _ = ordinary(repo, sid, 0, text=exam, player_input=OBSERVE, config=CONFIG,
        extra=dict(events=[event], knowledge_gained=[dict(actor_id=actor, fact_id=p['fact_id'],
            source_event_id='exam', evidence=exam) for actor in event['witnesses']]))
    assert result['status'] == 'saved', result['error']
    after = repo.get_snapshot(sid)
    assert after['world_state']['pregnancies'][p['id']]['status'] == 'due'
    messages = build_context(after, [], OBSERVE, 'turn', 65536, 2000)
    projection, = block(messages, 'Текущее состояние / GM-only')['pregnancies']
    assert projection == dict(id=p['id'], gestational_actor_id='qa_vera', due=True)
    with repo.connect() as db:
        history, _ = read_history(db, after['history_head'])
    source = next(e for e in history['events'] if e['text'] == exam)
    assert {k['actor_id'] for k in history['knowledge_acquisitions']
            if k['source_event_id'] == source['id']} == set(event['witnesses'])


@pytest.mark.parametrize(('actor','pov','present','perceives','known','subjects'), [
    ('a','a',['a'],True,False,['a']), ('a','a',['a'],True,True,['a']),
    ('b','b',['a','b'],True,False,['a']), ('b','b',['b'],True,True,[]),
    ('b','c',['a','b'],True,False,[]), ('c','c',['a','c'],False,False,[]),
    ('c','c',['a','c'],True,False,['a']),
])
def test_observation_uses_pov_presence_capability_and_separate_facts(actor,pov,present,perceives,known,subjects):
    state = conceive().state
    p, = state['pregnancies'].values()
    state['meta']['world_time'] = p['due_minute']
    state['camera'].update(controlled_actor_id=actor,pov_actor_id=pov,present_character_ids=present)
    state['characters'][pov]['capabilities']['can_perceive'] = perceives
    if known:
        state['knowledge'][pov+':'+p['fact_id']] = Knowledge(actor_id=pov,fact_id=p['fact_id']).model_dump()
    messages = build_context(snap(state), [], OBSERVE, 'turn', 65536, 2000)
    assert block(messages, 'Director / GM-only')['immediate_scene']['observable_actor_ids'] == subjects
    projected = block(messages, 'Текущее состояние / GM-only').get('pregnancies', [])
    assert bool(projected) == known
    assert all(ch['id'] not in str(messages) for ch in p['children'])
    assert 'pregnancy_due' not in str(messages)
    if not known:
        assert p['id'] not in str(messages)
